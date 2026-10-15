"""
Customer-facing ordering views for QR code self-ordering.

By default everyone at a table orders onto one table bill. Guests sharing a
table with others can choose "Separate bill" and pick a seat; each seat is
then its own bill.
"""

from django.contrib import messages
from django.db.models import Q
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

TABLE_BILL = "table"
TABLE_PARTY = "Table"


def _qr_disabled(table):
    outlet = guard.outlet_of(table)
    return not OrderSettings.load().allow_qr_ordering or (outlet is not None and not outlet.allow_qr_ordering)


# --- Which bill this phone orders on ----------------------------------------

def _party_key(table):
    return f"table_{table.uuid}_party"


def _order_key(table):
    return f"table_{table.uuid}_order"


def _party(request, table):
    """'table' (one bill for the table), a seat number, or None (just browsing)."""
    return request.session.get(_party_key(table))


def _set_party(request, table, party):
    if request.session.get(_party_key(table)) != party:
        request.session[_party_key(table)] = party
        request.session.pop(_order_key(table), None)


def party_label(party):
    if party == TABLE_BILL:
        return "Table bill"
    return f"Seat {party}" if party else ""


def _open_bills(table):
    """Open bills on this table, including a bill for tables merged with it."""
    return Order.objects.filter(Q(table=table) | Q(combined_tables=table), status__in=OPEN_STATUSES).distinct()


def _find_bill(table, party):
    """The existing bill this party should add to, if any."""
    bills = _open_bills(table).order_by("-created_at")
    if party == TABLE_BILL:
        shared = [o for o in bills if not (o.party_name or "").startswith("Seat ")]
        if len(shared) == 1:
            return shared[0]  # the table's bill, even if staff opened it
        return next((o for o in shared if o.party_name == TABLE_PARTY), None)
    return bills.filter(party_name=f"Seat {party}").first()


def _session_order(request, table):
    """This phone's open bill at the table (joins the existing one when there is one)."""
    party = _party(request, table)
    if not party:
        return None
    order_id = request.session.get(_order_key(table))
    order = _open_bills(table).filter(pk=order_id).first() if order_id else None
    if order is None:
        order = _find_bill(table, party)
        if order is not None:
            request.session[_order_key(table)] = order.pk
        else:
            request.session.pop(_order_key(table), None)
    return order


def landing(request, table_uuid):
    """What a guest sees after scanning the table QR: menu, order, call waiter, pay."""
    table = get_object_or_404(Table.objects.select_related("floor__outlet"), uuid=table_uuid, is_active=True)
    party = _party(request, table)
    return render(request, "ordering/landing.html", {
        "table": table,
        "outlet": guard.outlet_of(table),
        "business": BusinessSettings.load(),
        "ordering_enabled": not _qr_disabled(table),
        "current_order": _session_order(request, table),
        "current_party": party,
        "party_label": party_label(party),
    })


def order_here(request, table_uuid):
    """'Order now': order on the table's shared bill (unless this phone chose a seat)."""
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    if _qr_disabled(table):
        return redirect("ordering:select_seat", table_uuid=table_uuid)  # shows the "paused" page
    if not _party(request, table):
        _set_party(request, table, TABLE_BILL)
    return redirect("ordering:menu", table_uuid=table_uuid)


def select_seat(request, table_uuid):
    """
    Bill choice: one bill for the whole table (default), or a separate bill per
    seat for guests sharing a table.
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)

    # Check if QR ordering is enabled
    if _qr_disabled(table):
        return render(request, "ordering/disabled.html", {
            "message": "QR ordering is currently disabled.",
            "table": table,
        })

    if request.method == "POST":
        if request.POST.get("bill") == TABLE_BILL:
            _set_party(request, table, TABLE_BILL)
            return redirect("ordering:menu", table_uuid=table_uuid)
        seat_number = request.POST.get("seat_number")
        if seat_number:
            try:
                seat_number = int(seat_number)
                if 1 <= seat_number <= table.capacity:
                    _set_party(request, table, seat_number)
                    return redirect("ordering:menu", table_uuid=table_uuid)
            except (ValueError, TypeError):
                pass
        messages.error(request, "Please select a valid seat.")

    # A seat stays taken until its bill is paid or cancelled
    occupied_seats = []
    for order in _open_bills(table):
        if order.party_name and order.party_name.startswith("Seat "):
            try:
                occupied_seats.append(int(order.party_name.split(" ")[1]))
            except (ValueError, IndexError):
                pass

    context = {
        "table": table,
        "seat_range": range(1, table.capacity + 1),
        "occupied_seats": occupied_seats,
        "current_party": _party(request, table),
        "business": BusinessSettings.load(),
    }
    return render(request, "ordering/select_seat.html", context)


def table_menu(request, table_uuid):
    """
    Display menu for a specific table (QR code landing page).
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    order_settings = OrderSettings.load()

    # Without a bill choice (or with ordering off) the menu is browse-only
    ordering_enabled = not _qr_disabled(table)
    party = _party(request, table) if ordering_enabled else None

    # Get active categories and items
    categories = Category.objects.filter(is_active=True).prefetch_related(
        "items"
    ).order_by("display_order")

    current_order = _session_order(request, table) if party else None

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
        "current_party": party,
        "party_label": party_label(party),
        "is_table_bill": party == TABLE_BILL,
        "require_customer_info": order_settings.require_customer_info_qr,
        "business": BusinessSettings.load(),
        "browse_only": not party,
        "ordering_enabled": ordering_enabled,
        "guest_waiting": guard.is_waiting(guard.guest(request, table, create=False)),
        "location_enabled": guard.location_enabled(table),
    }
    return render(request, "ordering/menu.html", context)


def create_order(request, table_uuid):
    """
    Start this phone's bill: join the table's (or seat's) open bill, or open a new one.
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

    party = _party(request, table)
    if not party:
        _set_party(request, table, TABLE_BILL)
        party = TABLE_BILL

    # A table (or seat) keeps one open bill: later rounds add to it until it is paid
    order = _session_order(request, table)
    if order is not None:
        return redirect("ordering:menu", table_uuid=table_uuid)

    # Get customer info if required (only when opening a new bill)
    customer_name = request.POST.get("customer_name", "").strip()[:100]
    customer_phone = request.POST.get("customer_phone", "").strip()[:20]

    if order_settings.require_customer_info_qr:
        if not customer_name or not customer_phone:
            messages.error(request, "Please provide your name and phone number.")
            return redirect("ordering:menu", table_uuid=table_uuid)

    _open_bill(request, table, party, customer_name, customer_phone)
    messages.success(request, "Order started. Tap a dish to add it.")
    return redirect("ordering:menu", table_uuid=table_uuid)


def _open_bill(request, table, party, customer_name="", customer_phone=""):
    """Open a new bill for the table (or seat). It stays pending until the guest submits it."""
    order = Order.objects.create(
        table=table,
        order_type=Order.OrderType.DINE_IN,
        order_source=Order.OrderSource.QR_CODE,
        customer_name=customer_name,
        customer_phone=customer_phone,
        party_name=TABLE_PARTY if party == TABLE_BILL else f"Seat {party}",
        status=Order.Status.PENDING,
    )
    KitchenOrderTicket.objects.create(order=order)
    # The table is marked occupied when the first round is sent (after the
    # guest is confirmed to be at the table), so a stray scan can't block it
    request.session[_order_key(table)] = order.pk
    return order


def _require_order(request, table, open_if_missing=False):
    """This phone's bill, or a redirect telling the guest what to do."""
    if not _party(request, table):
        return None, redirect("ordering:order_here", table_uuid=table.uuid)
    order = _session_order(request, table)
    if order is None and open_if_missing and not _qr_disabled(table) and not OrderSettings.load().require_customer_info_qr:
        # No details to ask for: the first dish opens the bill
        if guard.throttle(f"create:{request.session.session_key or guard._client_ip(request)}", 6, 600):
            messages.error(request, "Too many tries. Please wait a few minutes or ask a staff member.")
            return None, redirect("ordering:menu", table_uuid=table.uuid)
        order = _open_bill(request, table, _party(request, table))
    if order is None:
        messages.error(request, "Please start an order first.")
        return None, redirect("ordering:menu", table_uuid=table.uuid)
    return order, None


def add_item(request, table_uuid):
    """
    Add item to the current order.
    """
    if request.method != "POST":
        return redirect("ordering:menu", table_uuid=table_uuid)

    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    order, stop = _require_order(request, table, open_if_missing=True)
    if stop:
        return stop

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
        Order.objects.prefetch_related("items").filter(Q(table=table) | Q(combined_tables=table)).distinct(),
        uuid=order_uuid,
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
    order, stop = _require_order(request, table)
    if stop:
        return stop

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
    order, stop = _require_order(request, table)
    if stop:
        return stop

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

    messages.success(request, "Your order has been sent to the kitchen! We'll start preparing it shortly.")

    # The session keeps pointing at this bill so the guest can order more later
    return redirect("ordering:order_detail", table_uuid=table_uuid, order_uuid=order.uuid)


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

    # Back to the bill choice (the table bill or a seat); the choice itself
    # only changes when the guest picks something there
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
        if order is not None and _open_bills(table).filter(pk=order.pk).exists():
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
        if order is not None and _open_bills(table).filter(pk=order.pk).exists():
            send_round(order)
        g.requested_at = None
        g.save(update_fields=["requested_at"])
        return JsonResponse({"ok": True})
    return JsonResponse({
        "ok": False,
        "error": "You seem to be away from the restaurant. A staff member will confirm your order at the table.",
        "distance_m": g.distance_m,
    })
