"""
Kitchen Display System services for real-time order management.
"""

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone


def get_order_data(order):
    """
    Serialize order data for WebSocket transmission.
    """
    items = []
    for item in order.items.all():
        items.append({
            "id": item.id,
            "name": item.item_name,
            "variant": item.variant_name,
            "quantity": item.quantity,
            "special_instructions": item.special_instructions,
            "status": item.status,
            "addons": item.addons,
        })

    # Get time elapsed since order creation
    elapsed_seconds = (timezone.now() - order.created_at).total_seconds()
    elapsed_minutes = int(elapsed_seconds // 60)

    # Get kitchen ticket info
    ticket_data = None
    if hasattr(order, "kitchen_ticket"):
        ticket = order.kitchen_ticket
        ticket_data = {
            "ticket_number": ticket.ticket_number,
            "priority": ticket.priority,
            "started_at": ticket.started_at.isoformat() if ticket.started_at else None,
            "assigned_to": ticket.assigned_to.get_full_name() if ticket.assigned_to else None,
        }

    return {
        "id": order.id,
        "order_number": order.order_number,
        "status": order.status,
        "order_type": order.order_type,
        "table_number": order.table.number if order.table else None,
        "table_name": order.table.name if order.table else "Takeaway",
        "customer_name": order.customer_name,
        "items": items,
        "item_count": order.item_count,
        "kitchen_notes": order.kitchen_notes,
        "created_at": order.created_at.isoformat(),
        "elapsed_minutes": elapsed_minutes,
        "estimated_prep_time": order.estimated_prep_time,
        "ticket": ticket_data,
    }


def broadcast_to_kitchen(event_type, order, extra_data=None):
    """
    Broadcast an event to the kitchen display WebSocket group.
    """
    channel_layer = get_channel_layer()
    if not channel_layer:
        return

    data = {
        "type": event_type,
        "order": get_order_data(order),
        "timestamp": timezone.now().isoformat(),
    }

    if extra_data:
        data.update(extra_data)

    async_to_sync(channel_layer.group_send)(
        "cafe_kitchen",
        {
            "type": "send_event",
            "data": data,
        }
    )


def broadcast_new_order(order):
    """
    Broadcast a new order to the kitchen display.
    Called when an order is confirmed.
    """
    broadcast_to_kitchen("new_order", order)


def broadcast_order_updated(order):
    """
    Broadcast order update to the kitchen display.
    Called when order items or details change.
    """
    broadcast_to_kitchen("order_updated", order)


def broadcast_order_status_changed(order, old_status, new_status, user=None):
    """
    Broadcast order status change to the kitchen display.
    """
    extra_data = {
        "old_status": old_status,
        "new_status": new_status,
        "changed_by": user.get_full_name() if user else None,
    }
    broadcast_to_kitchen("order_status_changed", order, extra_data)


def broadcast_order_bumped(order, user=None):
    """
    Broadcast that an order has been bumped (marked as ready).
    """
    extra_data = {
        "bumped_by": user.get_full_name() if user else None,
    }
    broadcast_to_kitchen("order_bumped", order, extra_data)


def broadcast_priority_changed(order, old_priority, new_priority, user=None):
    """
    Broadcast priority change for an order.
    """
    extra_data = {
        "old_priority": old_priority,
        "new_priority": new_priority,
        "changed_by": user.get_full_name() if user else None,
    }
    broadcast_to_kitchen("priority_changed", order, extra_data)


def get_kitchen_orders():
    """
    Get all active orders for kitchen display, organized by status.
    """
    from apps.orders.models import Order

    today = timezone.now().date()
    base_queryset = Order.objects.filter(
        created_at__date=today
    ).select_related(
        "table", "created_by", "kitchen_ticket", "kitchen_ticket__assigned_to"
    ).prefetch_related("items__menu_item")

    return {
        "pending": base_queryset.filter(status=Order.Status.CONFIRMED).order_by("created_at"),
        "preparing": base_queryset.filter(status=Order.Status.PREPARING).order_by("created_at"),
        "ready": base_queryset.filter(status=Order.Status.READY).order_by("-prepared_at"),
    }


def bump_order(order, user=None):
    """
    Bump an order from preparing to ready status.
    """
    from apps.orders.models import Order

    if order.status != Order.Status.PREPARING:
        return False, "Order is not in preparing status"

    old_status = order.status
    order.update_status(Order.Status.READY, user=user)

    # Update kitchen ticket
    if hasattr(order, "kitchen_ticket"):
        ticket = order.kitchen_ticket
        ticket.completed_at = timezone.now()
        ticket.save(update_fields=["completed_at"])

    # Broadcast the bump
    broadcast_order_bumped(order, user)

    return True, "Order bumped to ready"


def recall_order(order, user=None):
    """
    Recall an order from ready back to preparing status.
    """
    from apps.orders.models import Order

    if order.status != Order.Status.READY:
        return False, "Order is not in ready status"

    old_status = order.status
    order.status = Order.Status.PREPARING
    order.prepared_at = None
    order.save(update_fields=["status", "prepared_at", "updated_at"])

    # Update kitchen ticket
    if hasattr(order, "kitchen_ticket"):
        ticket = order.kitchen_ticket
        ticket.completed_at = None
        ticket.save(update_fields=["completed_at"])

    broadcast_order_status_changed(order, old_status, Order.Status.PREPARING, user)

    return True, "Order recalled to preparing"


def start_preparing(order, user=None):
    """
    Move order from confirmed to preparing status.
    """
    from apps.orders.models import Order

    if order.status != Order.Status.CONFIRMED:
        return False, "Order is not in confirmed status"

    old_status = order.status
    order.update_status(Order.Status.PREPARING, user=user)

    # Update kitchen ticket
    if hasattr(order, "kitchen_ticket"):
        ticket = order.kitchen_ticket
        if not ticket.started_at:
            ticket.started_at = timezone.now()
            ticket.assigned_to = user
            ticket.save(update_fields=["started_at", "assigned_to"])

    broadcast_order_status_changed(order, old_status, Order.Status.PREPARING, user)

    return True, "Order moved to preparing"


def set_order_priority(order, priority, user=None):
    """
    Set the priority of an order's kitchen ticket.
    """
    from apps.orders.models import KitchenOrderTicket

    if not hasattr(order, "kitchen_ticket"):
        return False, "Order has no kitchen ticket"

    ticket = order.kitchen_ticket
    old_priority = ticket.priority

    if priority not in [choice[0] for choice in KitchenOrderTicket.Priority.choices]:
        return False, "Invalid priority value"

    ticket.priority = priority
    ticket.save(update_fields=["priority"])

    broadcast_priority_changed(order, old_priority, priority, user)

    return True, f"Priority changed to {priority}"
