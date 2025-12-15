"""
Waiter PWA views for mobile ordering and table management.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.core.models import BusinessSettings
from apps.menu.models import Category, MenuItem
from apps.orders.models import KitchenOrderTicket, Order, OrderItem
from apps.tables.models import Floor, Table


def waiter_required(view_func):
    """Decorator to check if user is a waiter or admin."""
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect("dashboard:login")
        if not (request.user.is_superuser or request.user.role in ["admin", "waiter"]):
            messages.error(request, "Access denied. Waiter access required.")
            return redirect("dashboard:home")
        return view_func(request, *args, **kwargs)
    return wrapper


@waiter_required
def waiter_home(request):
    """
    Waiter dashboard - quick stats and active tables.
    """
    today = timezone.now().date()

    # Get stats
    active_orders = Order.objects.filter(
        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING]
    ).count()

    today_orders = Order.objects.filter(
        created_at__date=today
    ).count()

    occupied_tables = Table.objects.filter(
        status=Table.Status.OCCUPIED,
        is_active=True
    ).count()

    # Get tables with active orders
    tables_with_orders = Table.objects.filter(
        status=Table.Status.OCCUPIED,
        is_active=True
    ).select_related("floor").order_by("floor__display_order", "number")[:6]

    # Recent orders
    recent_orders = Order.objects.filter(
        created_at__date=today
    ).select_related("table").order_by("-created_at")[:5]

    context = {
        "active_orders": active_orders,
        "today_orders": today_orders,
        "occupied_tables": occupied_tables,
        "tables_with_orders": tables_with_orders,
        "recent_orders": recent_orders,
        "business": BusinessSettings.load(),
    }
    return render(request, "waiter/home.html", context)


@waiter_required
def waiter_tables(request):
    """
    Floor map view showing all tables.
    """
    floors = Floor.objects.filter(is_active=True).prefetch_related(
        "tables"
    ).order_by("display_order")

    context = {
        "floors": floors,
        "business": BusinessSettings.load(),
    }
    return render(request, "waiter/tables.html", context)


@waiter_required
def waiter_table_detail(request, pk):
    """
    Table detail showing seats and their orders.
    """
    table = get_object_or_404(Table, pk=pk, is_active=True)

    # Get all active orders for this table
    active_orders = Order.objects.filter(
        table=table,
        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY]
    ).order_by("party_name")

    # Build seat status map
    seat_info = []
    for seat_num in range(1, table.capacity + 1):
        seat_order = None
        for order in active_orders:
            if order.party_name == f"Seat {seat_num}":
                seat_order = order
                break
        seat_info.append({
            "number": seat_num,
            "order": seat_order,
        })

    context = {
        "table": table,
        "seat_info": seat_info,
        "active_orders": active_orders,
        "business": BusinessSettings.load(),
    }
    return render(request, "waiter/table_detail.html", context)


@waiter_required
def waiter_take_order(request, pk, seat):
    """
    Take order for a specific seat at a table.
    """
    table = get_object_or_404(Table, pk=pk, is_active=True)

    if seat < 1 or seat > table.capacity:
        messages.error(request, "Invalid seat number.")
        return redirect("waiter:table_detail", pk=pk)

    # Get or find existing order for this seat
    existing_order = Order.objects.filter(
        table=table,
        party_name=f"Seat {seat}",
        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED]
    ).first()

    # Get menu categories and items
    categories = Category.objects.filter(is_active=True).prefetch_related(
        "items"
    ).order_by("display_order")

    context = {
        "table": table,
        "seat": seat,
        "current_order": existing_order,
        "categories": categories,
        "business": BusinessSettings.load(),
    }
    return render(request, "waiter/take_order.html", context)


@waiter_required
def waiter_add_item(request, pk, seat):
    """
    Add item to an order for a specific seat.
    """
    if request.method != "POST":
        return redirect("waiter:take_order", pk=pk, seat=seat)

    table = get_object_or_404(Table, pk=pk, is_active=True)

    if seat < 1 or seat > table.capacity:
        messages.error(request, "Invalid seat number.")
        return redirect("waiter:table_detail", pk=pk)

    # Get existing order for this seat or create new one
    order = Order.objects.filter(
        table=table,
        party_name=f"Seat {seat}",
        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED]
    ).first()

    created = False
    if not order:
        order = Order.objects.create(
            table=table,
            party_name=f"Seat {seat}",
            order_type=Order.OrderType.DINE_IN,
            order_source=Order.OrderSource.WAITER,
            status=Order.Status.PENDING,
            created_by=request.user,
        )
        created = True

    if created:
        # Create kitchen ticket
        KitchenOrderTicket.objects.create(order=order)
        # Update table status
        table.status = Table.Status.OCCUPIED
        table.save(update_fields=["status", "updated_at"])

    # Add item
    menu_item_id = request.POST.get("menu_item")
    quantity = int(request.POST.get("quantity", 1))
    special_instructions = request.POST.get("special_instructions", "")

    try:
        menu_item = MenuItem.objects.get(pk=menu_item_id, is_available=True)

        # Check if item already exists
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
                seat_number=seat,
            )

        # Recalculate totals
        order.calculate_totals()
        order.save()

        messages.success(request, f"Added {quantity}x {menu_item.name}")
    except MenuItem.DoesNotExist:
        messages.error(request, "Item not available.")

    return redirect("waiter:take_order", pk=pk, seat=seat)


@waiter_required
def waiter_submit_order(request, pk, seat):
    """
    Submit order for kitchen preparation.
    """
    if request.method != "POST":
        return redirect("waiter:take_order", pk=pk, seat=seat)

    table = get_object_or_404(Table, pk=pk, is_active=True)

    try:
        order = Order.objects.get(
            table=table,
            party_name=f"Seat {seat}",
            status=Order.Status.PENDING
        )

        if not order.items.exists():
            messages.error(request, "No items in order.")
            return redirect("waiter:take_order", pk=pk, seat=seat)

        order.update_status(Order.Status.CONFIRMED)
        messages.success(request, f"Order for Seat {seat} sent to kitchen!")

    except Order.DoesNotExist:
        messages.error(request, "Order not found.")

    return redirect("waiter:table_detail", pk=pk)


@waiter_required
def waiter_orders(request):
    """
    List all orders with filters.
    """
    status_filter = request.GET.get("status", "active")

    if status_filter == "active":
        orders = Order.objects.filter(
            status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY]
        )
    elif status_filter == "completed":
        orders = Order.objects.filter(status=Order.Status.COMPLETED)
    else:
        orders = Order.objects.all()

    orders = orders.select_related("table").order_by("-created_at")[:50]

    context = {
        "orders": orders,
        "status_filter": status_filter,
        "business": BusinessSettings.load(),
    }
    return render(request, "waiter/orders.html", context)


@waiter_required
def waiter_order_detail(request, pk):
    """
    View order details.
    """
    order = get_object_or_404(
        Order.objects.select_related("table").prefetch_related("items"),
        pk=pk
    )

    context = {
        "order": order,
        "business": BusinessSettings.load(),
    }
    return render(request, "waiter/order_detail.html", context)


@waiter_required
def waiter_update_order_status(request, pk):
    """
    Update order status.
    """
    if request.method != "POST":
        return redirect("waiter:order_detail", pk=pk)

    order = get_object_or_404(Order, pk=pk)
    new_status = request.POST.get("status")

    valid_statuses = [s[0] for s in Order.Status.choices]
    if new_status in valid_statuses:
        order.update_status(new_status)
        messages.success(request, f"Order status updated to {order.get_status_display()}")
    else:
        messages.error(request, "Invalid status.")

    return redirect("waiter:order_detail", pk=pk)


def offline_page(request):
    """
    Offline fallback page for PWA.
    """
    return render(request, "waiter/offline.html", {
        "business": BusinessSettings.load(),
    })
