"""
Customer-facing ordering views for QR code self-ordering.
"""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.core.models import BusinessSettings, OrderSettings
from apps.menu.models import Category, MenuItem
from apps.orders.models import KitchenOrderTicket, Order, OrderItem
from apps.tables.models import Table

from apps.kitchen.routing import OPEN_STATUSES, send_order_to_kitchen
from apps.ordering import guard


def _qr_disabled(table):
    outlet = guard.outlet_of(table)
    return not OrderSettings.load().allow_qr_ordering or (outlet is not None and not outlet.allow_qr_ordering)


def _seat_order(request, table):
    """This phone's open bill at the table, if it has one."""
    seat = request.session.get(f"table_{table.uuid}_seat")
    order_id = request.session.get(f"table_{table.uuid}_seat_{seat}_order") if seat else None
    if not order_id:
        return None
    return Order.objects.filter(pk=order_id, table=table, status__in=OPEN_STATUSES).first()


def landing(request, table_uuid):
    """What a guest sees after scanning the table QR: menu, order, call waiter, pay."""
    table = get_object_or_404(Table.objects.select_related("floor__outlet"), uuid=table_uuid, is_active=True)
    order = _seat_order(request, table)
    return render(request, "ordering/landing.html", {
        "table": table,
        "outlet": guard.outlet_of(table),
        "business": BusinessSettings.load(),
        "ordering_enabled": not _qr_disabled(table),
        "current_order": order,
        "current_seat": request.session.get(f"table_{table.uuid}_seat"),
    })


def select_seat(request, table_uuid):
    """
    Seat selection page - customer chooses their seat number.
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)

    # Check if QR ordering is enabled
    if _qr_disabled(table):
        return render(request, "ordering/disabled.html", {
            "message": "QR ordering is currently disabled.",
            "table": table,
        })

    if request.method == "POST":
        seat_number = request.POST.get("seat_number")
        if seat_number:
            try:
                seat_number = int(seat_number)
                if 1 <= seat_number <= table.capacity:
                    # Store seat in session
                    request.session[f"table_{table.uuid}_seat"] = seat_number
                    return redirect("ordering:menu", table_uuid=table_uuid)
            except (ValueError, TypeError):
                pass
        messages.error(request, "Please select a valid seat.")

    # Get existing orders for this table to show which seats have orders
    # A seat stays taken until its order is paid or cancelled
    active_orders = Order.objects.filter(
        table=table,
        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
    )

    # Extract seat numbers from party_name (format: "Seat X")
    occupied_seats = []
    for order in active_orders:
        if order.party_name and order.party_name.startswith("Seat "):
            try:
                seat_num = int(order.party_name.split(" ")[1])
                occupied_seats.append(seat_num)
            except (ValueError, IndexError):
                pass

    context = {
        "table": table,
        "seat_range": range(1, table.capacity + 1),
        "occupied_seats": occupied_seats,
        "business": BusinessSettings.load(),
    }
    return render(request, "ordering/select_seat.html", context)


def table_menu(request, table_uuid):
    """
    Display menu for a specific table (QR code landing page).
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    order_settings = OrderSettings.load()

    # Without a seat (or with ordering off) the menu is browse-only
    seat_key = f"table_{table.uuid}_seat"
    current_seat = request.session.get(seat_key)
    ordering_enabled = not _qr_disabled(table)
    if not ordering_enabled:
        current_seat = None

    # Get active categories and items
    categories = Category.objects.filter(is_active=True).prefetch_related(
        "items"
    ).order_by("display_order")

    # Get or create session for this table and seat
    session_key = f"table_{table.uuid}_seat_{current_seat}_order"
    current_order_id = request.session.get(session_key) if current_seat else None
    current_order = None

    if current_order_id:
        try:
            current_order = Order.objects.get(
                pk=current_order_id,
                table=table,
                party_name=f"Seat {current_seat}",
                status__in=OPEN_STATUSES
            )
        except Order.DoesNotExist:
            # Clear invalid session
            del request.session[session_key]

    # Split the bill into this round's new items and what was already ordered
    new_items, ordered_items = [], []
    if current_order is not None:
        for item in current_order.items.exclude(status="cancelled"):
            (new_items if item.kot_sent_at is None else ordered_items).append(item)

    context = {
        "table": table,
        "categories": categories,
        "current_order": current_order,
        "new_items": new_items,
        "ordered_items": ordered_items,
        "new_items_total": sum((i.total_price for i in new_items), 0),
        "current_seat": current_seat,
        "require_customer_info": order_settings.require_customer_info_qr,
        "business": BusinessSettings.load(),
        "browse_only": not current_seat,
        "ordering_enabled": ordering_enabled,
        "guest_waiting": guard.is_waiting(guard.guest(request, table, create=False)),
        "location_enabled": guard.location_enabled(table),
    }
    return render(request, "ordering/menu.html", context)


def create_order(request, table_uuid):
    """
    Create a new order for a table via QR code.
    Each seat gets its own separate order for split billing.
    """
    if request.method != "POST":
        return redirect("ordering:menu", table_uuid=table_uuid)

    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    order_settings = OrderSettings.load()

    if _qr_disabled(table):
        messages.error(request, "QR ordering is currently disabled.")
        return redirect("ordering:menu", table_uuid=table_uuid)

    if guard.throttle(f"create:{request.session.session_key or guard._client_ip(request)}", 6, 600):
        messages.error(request, "Too many tries. Please wait a few minutes or ask a staff member.")
        return redirect("ordering:menu", table_uuid=table_uuid)

    # Get current seat
    seat_key = f"table_{table.uuid}_seat"
    current_seat = request.session.get(seat_key)

    if not current_seat:
        return redirect("ordering:select_seat", table_uuid=table_uuid)

    # Get customer info if required
    customer_name = request.POST.get("customer_name", "").strip()
    customer_phone = request.POST.get("customer_phone", "").strip()

    if order_settings.require_customer_info_qr:
        if not customer_name or not customer_phone:
            messages.error(request, "Please provide your name and phone number.")
            return redirect("ordering:menu", table_uuid=table_uuid)

    session_key = f"table_{table.uuid}_seat_{current_seat}_order"

    # A seat keeps one open bill: later rounds add to it until it is paid
    order = Order.objects.filter(
        table=table, party_name=f"Seat {current_seat}", status__in=OPEN_STATUSES
    ).order_by("-created_at").first()
    if order is not None:
        request.session[session_key] = order.pk
        return redirect("ordering:menu", table_uuid=table_uuid)

    # Create the order with seat-specific party_name. It stays pending until the
    # guest submits it (auto-accept applies at submit).
    order = Order.objects.create(
        table=table,
        order_type=Order.OrderType.DINE_IN,
        order_source=Order.OrderSource.QR_CODE,
        customer_name=customer_name,
        customer_phone=customer_phone,
        party_name=f"Seat {current_seat}",
        status=Order.Status.PENDING,
    )

    # Create kitchen ticket
    KitchenOrderTicket.objects.create(order=order)

    # The table is marked occupied when the first round is sent (after the
    # guest is confirmed to be at the table), so a stray scan can't block it

    # Store order in session (seat-specific key)
    request.session[session_key] = order.pk

    messages.success(request, f"Order started for Seat {current_seat}. Tap a dish to add it.")
    return redirect("ordering:menu", table_uuid=table_uuid)


def add_item(request, table_uuid):
    """
    Add item to the current order.
    """
    if request.method != "POST":
        return redirect("ordering:menu", table_uuid=table_uuid)

    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)

    # Get current seat
    seat_key = f"table_{table.uuid}_seat"
    current_seat = request.session.get(seat_key)

    if not current_seat:
        return redirect("ordering:select_seat", table_uuid=table_uuid)

    # Get current order from session (seat-specific)
    session_key = f"table_{table.uuid}_seat_{current_seat}_order"
    order_id = request.session.get(session_key)

    if not order_id:
        messages.error(request, "Please start an order first.")
        return redirect("ordering:menu", table_uuid=table_uuid)

    try:
        order = Order.objects.get(
            pk=order_id,
            table=table,
            party_name=f"Seat {current_seat}",
            status__in=OPEN_STATUSES
        )
    except Order.DoesNotExist:
        messages.error(request, "Order not found or already completed.")
        del request.session[session_key]
        return redirect("ordering:menu", table_uuid=table_uuid)

    menu_item_id = request.POST.get("menu_item")
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(1, min(quantity, guard.MAX_QTY_PER_LINE))
    special_instructions = request.POST.get("special_instructions", "")[:200]

    if guard.throttle(f"add:{request.session.session_key}", 40, 600):
        messages.error(request, "Too many items added too quickly. Please wait a moment.")
        return redirect("ordering:menu", table_uuid=table_uuid)
    unsent = sum(i.quantity for i in order.items.filter(kot_sent_at__isnull=True).exclude(status="cancelled"))
    if unsent + quantity > guard.MAX_ITEMS_PER_ROUND:
        messages.error(request, f"That's a big order! Please place up to {guard.MAX_ITEMS_PER_ROUND} items at a time, or ask a staff member.")
        return redirect("ordering:menu", table_uuid=table_uuid)

    try:
        menu_item = MenuItem.objects.get(pk=menu_item_id, is_available=True)

        # Check if item already exists in order
        # Only merge into a line that has not gone to the kitchen yet
        existing_item = order.items.filter(menu_item=menu_item, kot_sent_at__isnull=True).exclude(status="cancelled").first()
        if existing_item:
            existing_item.quantity = min(existing_item.quantity + quantity, guard.MAX_QTY_PER_LINE)
            existing_item.total_price = existing_item.unit_price * existing_item.quantity
            existing_item.save()
        else:
            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                item_name=menu_item.name,
                unit_price=menu_item.base_price,
                quantity=quantity,
                total_price=menu_item.base_price * quantity,
                special_instructions=special_instructions,
            )

        # Recalculate totals
        order.calculate_totals()
        order.save()

        messages.success(request, f"Added {quantity}x {menu_item.name} to your order.")
    except MenuItem.DoesNotExist:
        messages.error(request, "Item not available.")

    return redirect("ordering:menu", table_uuid=table_uuid)


def order_detail(request, table_uuid, order_uuid):
    """
    View order details and status.
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        uuid=order_uuid,
        table=table
    )

    g = guard.guest(request, table, create=False)
    waiting = guard.is_waiting(g) and g.pending_order_id == order.pk
    context = {
        "table": table,
        "order": order,
        "business": BusinessSettings.load(),
        "guest_waiting": waiting,
        "guest_rejected": bool(g and g.rejected_at and g.pending_order_id == order.pk and not guard.is_confirmed(g, table)),
        "location_enabled": guard.location_enabled(table),
        "code_enabled": guard.code_enabled(table),
        "held_items": order.items.filter(kot_sent_at__isnull=True).exclude(status="cancelled") if waiting else [],
    }
    return render(request, "ordering/order_detail.html", context)


def update_item_quantity(request, table_uuid):
    """
    Update item quantity in the current order.
    """
    if request.method != "POST":
        return redirect("ordering:menu", table_uuid=table_uuid)

    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)

    # Get current seat
    seat_key = f"table_{table.uuid}_seat"
    current_seat = request.session.get(seat_key)

    if not current_seat:
        return redirect("ordering:select_seat", table_uuid=table_uuid)

    session_key = f"table_{table.uuid}_seat_{current_seat}_order"
    order_id = request.session.get(session_key)

    if not order_id:
        return redirect("ordering:menu", table_uuid=table_uuid)

    try:
        order = Order.objects.get(
            pk=order_id,
            table=table,
            party_name=f"Seat {current_seat}",
            status__in=OPEN_STATUSES
        )
    except Order.DoesNotExist:
        return redirect("ordering:menu", table_uuid=table_uuid)

    item_id = request.POST.get("item_id")
    action = request.POST.get("action")

    try:
        # Guests can only change what hasn't gone to the kitchen yet
        item = order.items.get(pk=item_id, kot_sent_at__isnull=True)

        if action == "increase" and item.quantity < guard.MAX_QTY_PER_LINE:
            item.quantity += 1
            item.total_price = item.unit_price * item.quantity
            item.save()
        elif action == "decrease":
            if item.quantity > 1:
                item.quantity -= 1
                item.total_price = item.unit_price * item.quantity
                item.save()
            else:
                item.delete()
        elif action == "remove":
            item.delete()

        # Recalculate totals
        order.calculate_totals()
        order.save()

    except OrderItem.DoesNotExist:
        pass

    return redirect("ordering:menu", table_uuid=table_uuid)


def submit_order(request, table_uuid):
    """
    Submit the order for preparation.
    """
    if request.method != "POST":
        return redirect("ordering:menu", table_uuid=table_uuid)

    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    order_settings = OrderSettings.load()

    # Get current seat
    seat_key = f"table_{table.uuid}_seat"
    current_seat = request.session.get(seat_key)

    if not current_seat:
        return redirect("ordering:select_seat", table_uuid=table_uuid)

    session_key = f"table_{table.uuid}_seat_{current_seat}_order"
    order_id = request.session.get(session_key)

    if not order_id:
        messages.error(request, "No order found.")
        return redirect("ordering:menu", table_uuid=table_uuid)

    try:
        order = Order.objects.get(
            pk=order_id,
            table=table,
            party_name=f"Seat {current_seat}",
            status__in=OPEN_STATUSES
        )

        if not order.items.filter(kot_sent_at__isnull=True).exclude(status="cancelled").exists():
            messages.error(request, "Please add items to your order first.")
            return redirect("ordering:menu", table_uuid=table_uuid)

        if _qr_disabled(table):
            messages.error(request, "QR ordering is currently disabled. Please ask a staff member.")
            return redirect("ordering:menu", table_uuid=table_uuid)

        # Is this phone really at the table? (not a photo of the QR used elsewhere)
        g = guard.guest(request, table)
        if not guard.is_confirmed(g, table):
            lat, lng = request.POST.get("lat"), request.POST.get("lng")
            if not (lat and lng and guard.check_location(g, table, lat, lng, request.POST.get("accuracy"))):
                if not guard.is_waiting(g) and guard.waiting_count(table, exclude=g) >= guard.MAX_WAITING_PER_TABLE:
                    messages.error(request, "Please ask a staff member to take your order.")
                    return redirect("ordering:menu", table_uuid=table_uuid)
                guard.request_staff(g, order)
                return redirect("ordering:order_detail", table_uuid=table_uuid, order_uuid=order.uuid)

        send_round(order, order_settings)

        messages.success(request, f"Your order (Seat {current_seat}) has been submitted! We'll start preparing it shortly.")

        # The session keeps pointing at this bill so the guest can order more later

        return redirect("ordering:order_detail", table_uuid=table_uuid, order_uuid=order.uuid)

    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect("ordering:menu", table_uuid=table_uuid)


def call_waiter(request, table_uuid):
    """
    Request assistance from a waiter.
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    back = request.GET.get("next") == "home" and "ordering:landing" or "ordering:menu"

    if guard.throttle(f"call:{request.session.session_key or guard._client_ip(request)}", 1, 90):
        messages.success(request, "We've already called a waiter. They'll be with you shortly.")
        return redirect(back, table_uuid=table_uuid)

    g = guard.guest(request, table)
    g.called_at = timezone.now()
    g.save(update_fields=["called_at"])
    messages.success(request, "A waiter has been notified and will assist you shortly.")

    return redirect(back, table_uuid=table_uuid)


def change_seat(request, table_uuid):
    """
    Allow customer to change their seat selection.
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)

    # Clear current seat selection
    seat_key = f"table_{table.uuid}_seat"
    if seat_key in request.session:
        del request.session[seat_key]

    return redirect("ordering:select_seat", table_uuid=table_uuid)


def send_round(order, order_settings=None, user=None):
    """Send the guest's new items to the kitchen and mark the table occupied."""
    order_settings = order_settings or OrderSettings.load()
    send_order_to_kitchen(order, user=user)
    if order_settings.auto_accept_orders and order.status == Order.Status.CONFIRMED:
        order.update_status(Order.Status.PREPARING)
    table = order.table
    if table is not None and table.status in (Table.Status.VACANT, Table.Status.RESERVED, Table.Status.CLEANING):
        table.status = Table.Status.OCCUPIED
        table.save(update_fields=["status", "updated_at"])


def guest_status(request, table_uuid):
    """Polled by the waiting screen: has a staff member confirmed this phone?"""
    table = get_object_or_404(Table.objects.select_related("floor__outlet"), uuid=table_uuid, is_active=True)
    g = guard.guest(request, table, create=False)
    if guard.is_confirmed(g, table):
        state = "confirmed"
    elif g and g.rejected_at:
        state = "rejected"
    elif guard.is_waiting(g):
        state = "waiting"
    else:
        state = "none"
    return JsonResponse({"state": state})


@require_POST
def guest_code(request, table_uuid):
    """Confirm a waiting phone with the table code and send its held round."""
    table = get_object_or_404(Table.objects.select_related("floor__outlet"), uuid=table_uuid, is_active=True)
    g = guard.guest(request, table, create=False)
    if g is None:
        return JsonResponse({"ok": False, "error": "Please scan the table QR again."}, status=400)
    # 10,000 codes: a few tries per phone and per table stops guessing
    if guard.throttle(f"code:{g.pk}", 5, 600) or guard.throttle(f"code-table:{table.pk}", 20, 600):
        return JsonResponse({"ok": False, "error": "Too many wrong codes. A staff member will confirm your order."}, status=429)
    if guard.is_confirmed(g, table) or guard.check_code(g, table, request.POST.get("code")):
        order = g.pending_order
        if order is not None and order.status in OPEN_STATUSES and order.table_id == table.pk:
            send_round(order)
        g.requested_at = None
        g.save(update_fields=["requested_at"])
        return JsonResponse({"ok": True})
    return JsonResponse({"ok": False, "error": "That code isn't right. Please check with a staff member."})


@require_POST
def guest_locate(request, table_uuid):
    """Confirm a waiting phone by location and send its held round."""
    table = get_object_or_404(Table.objects.select_related("floor__outlet"), uuid=table_uuid, is_active=True)
    g = guard.guest(request, table, create=False)
    if g is None:
        return JsonResponse({"ok": False, "error": "Please scan the table QR again."}, status=400)
    if guard.throttle(f"locate:{g.pk}", 8, 600):
        return JsonResponse({"ok": False, "error": "Too many tries. A staff member will confirm your order."}, status=429)
    if guard.is_confirmed(g, table) or guard.check_location(
        g, table, request.POST.get("lat"), request.POST.get("lng"), request.POST.get("accuracy")
    ):
        order = g.pending_order
        if order is not None and order.status in OPEN_STATUSES and order.table_id == table.pk:
            send_round(order)
        g.requested_at = None
        g.save(update_fields=["requested_at"])
        return JsonResponse({"ok": True})
    return JsonResponse({
        "ok": False,
        "error": "You seem to be away from the restaurant. A staff member will confirm your order at the table.",
        "distance_m": g.distance_m,
    })
