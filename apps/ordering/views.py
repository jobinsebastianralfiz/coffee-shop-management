"""
Customer-facing ordering views for QR code self-ordering.
"""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import BusinessSettings, OrderSettings
from apps.menu.models import Category, MenuItem
from apps.orders.models import KitchenOrderTicket, Order, OrderItem
from apps.tables.models import Table


def select_seat(request, table_uuid):
    """
    Seat selection page - customer chooses their seat number.
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)
    order_settings = OrderSettings.load()

    # Check if QR ordering is enabled
    if not order_settings.allow_qr_ordering:
        return render(request, "ordering/disabled.html", {
            "message": "QR ordering is currently disabled.",
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
    active_orders = Order.objects.filter(
        table=table,
        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING]
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

    # Check if QR ordering is enabled
    if not order_settings.allow_qr_ordering:
        return render(request, "ordering/disabled.html", {
            "message": "QR ordering is currently disabled.",
        })

    # Check if seat is selected
    seat_key = f"table_{table.uuid}_seat"
    current_seat = request.session.get(seat_key)

    if not current_seat:
        # Redirect to seat selection
        return redirect("ordering:select_seat", table_uuid=table_uuid)

    # Get active categories and items
    categories = Category.objects.filter(is_active=True).prefetch_related(
        "items"
    ).order_by("display_order")

    # Get or create session for this table and seat
    session_key = f"table_{table.uuid}_seat_{current_seat}_order"
    current_order_id = request.session.get(session_key)
    current_order = None

    if current_order_id:
        try:
            current_order = Order.objects.get(
                pk=current_order_id,
                table=table,
                party_name=f"Seat {current_seat}",
                status__in=[Order.Status.PENDING, Order.Status.CONFIRMED]
            )
        except Order.DoesNotExist:
            # Clear invalid session
            del request.session[session_key]

    context = {
        "table": table,
        "categories": categories,
        "current_order": current_order,
        "current_seat": current_seat,
        "require_customer_info": order_settings.require_customer_info_qr,
        "business": BusinessSettings.load(),
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

    if not order_settings.allow_qr_ordering:
        messages.error(request, "QR ordering is currently disabled.")
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

    # Create the order with seat-specific party_name
    order = Order.objects.create(
        table=table,
        order_type=Order.OrderType.DINE_IN,
        order_source=Order.OrderSource.QR_CODE,
        customer_name=customer_name,
        customer_phone=customer_phone,
        party_name=f"Seat {current_seat}",
        status=Order.Status.PENDING if not order_settings.auto_accept_orders else Order.Status.CONFIRMED,
    )

    # Create kitchen ticket
    KitchenOrderTicket.objects.create(order=order)

    # Update table status
    table.status = Table.Status.OCCUPIED
    table.save(update_fields=["status", "updated_at"])

    # Store order in session (seat-specific key)
    session_key = f"table_{table.uuid}_seat_{current_seat}_order"
    request.session[session_key] = order.pk

    messages.success(request, f"Order #{order.order_number} created for Seat {current_seat}!")
    return redirect("ordering:order_detail", table_uuid=table_uuid, order_uuid=order.uuid)


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
            status__in=[Order.Status.PENDING, Order.Status.CONFIRMED]
        )
    except Order.DoesNotExist:
        messages.error(request, "Order not found or already completed.")
        del request.session[session_key]
        return redirect("ordering:menu", table_uuid=table_uuid)

    menu_item_id = request.POST.get("menu_item")
    quantity = int(request.POST.get("quantity", 1))
    special_instructions = request.POST.get("special_instructions", "")

    try:
        menu_item = MenuItem.objects.get(pk=menu_item_id, is_available=True)

        # Check if item already exists in order
        existing_item = order.items.filter(menu_item=menu_item).first()
        if existing_item:
            existing_item.quantity += quantity
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

    context = {
        "table": table,
        "order": order,
        "business": BusinessSettings.load(),
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
            status=Order.Status.PENDING
        )
    except Order.DoesNotExist:
        return redirect("ordering:menu", table_uuid=table_uuid)

    item_id = request.POST.get("item_id")
    action = request.POST.get("action")

    try:
        item = order.items.get(pk=item_id)

        if action == "increase":
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
            status=Order.Status.PENDING
        )

        if not order.items.exists():
            messages.error(request, "Please add items to your order first.")
            return redirect("ordering:menu", table_uuid=table_uuid)

        # Update status based on settings
        if order_settings.auto_accept_orders:
            order.update_status(Order.Status.PREPARING)
        else:
            order.update_status(Order.Status.CONFIRMED)

        messages.success(request, f"Your order (Seat {current_seat}) has been submitted! We'll start preparing it shortly.")

        # Clear order session so customer can add more orders
        del request.session[session_key]

        return redirect("ordering:order_detail", table_uuid=table_uuid, order_uuid=order.uuid)

    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect("ordering:menu", table_uuid=table_uuid)


def call_waiter(request, table_uuid):
    """
    Request assistance from a waiter.
    """
    table = get_object_or_404(Table, uuid=table_uuid, is_active=True)

    # In a real implementation, this would trigger a notification
    # For now, just show a success message
    messages.success(request, "A waiter has been notified and will assist you shortly.")

    return redirect("ordering:menu", table_uuid=table_uuid)


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
