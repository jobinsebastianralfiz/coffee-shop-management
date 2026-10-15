"""
Signal handlers for the orders app.
"""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.orders.models import Order, KitchenOrderTicket


# Store previous status to detect changes
_order_previous_status = {}


@receiver(pre_save, sender=Order)
def store_previous_order_status(sender, instance, **kwargs):
    """
    Store the previous order status before save to detect status changes.
    """
    if instance.pk:
        try:
            previous = Order.objects.get(pk=instance.pk)
            _order_previous_status[instance.pk] = previous.status
        except Order.DoesNotExist:
            _order_previous_status[instance.pk] = None
    else:
        _order_previous_status[instance.pk] = None


@receiver(post_save, sender=Order)
def handle_order_status_change(sender, instance, created, **kwargs):
    """
    Handle order status changes and broadcast to kitchen.
    """
    from apps.kitchen.services import (
        broadcast_new_order,
        broadcast_order_status_changed,
    )

    previous_status = _order_previous_status.get(instance.pk)

    # Clean up stored status
    if instance.pk in _order_previous_status:
        del _order_previous_status[instance.pk]

    # New order confirmed - broadcast to kitchen
    if created and instance.status == Order.Status.CONFIRMED:
        queue_station_tickets(instance)
        broadcast_new_order(instance)
        return

    # Status changed
    if previous_status and previous_status != instance.status:
        # Order just confirmed (status changed to confirmed)
        if instance.status == Order.Status.CONFIRMED:
            queue_station_tickets(instance)
            broadcast_new_order(instance)
        # Order completed - award points to employee
        elif instance.status == Order.Status.COMPLETED:
            award_points_for_order(instance)
            broadcast_order_status_changed(
                instance,
                previous_status,
                instance.status,
                user=None
            )
        # Other status changes
        elif instance.status in [
            Order.Status.PREPARING,
            Order.Status.READY,
            Order.Status.SERVED,
            Order.Status.CANCELLED,
        ]:
            broadcast_order_status_changed(
                instance,
                previous_status,
                instance.status,
                user=None  # User context not available in signal
            )


def queue_station_tickets(order):
    """
    Queue per-station kitchen tickets once the surrounding transaction commits
    (so items saved in the same request are included). Printing problems are
    logged and never block the order.
    """
    from django.db import transaction

    def _dispatch():
        import logging

        from apps.kitchen.routing import dispatch_kitchen_tickets

        try:
            dispatch_kitchen_tickets(order)
        except Exception:
            logging.getLogger(__name__).exception("Could not queue kitchen tickets for order %s", order.pk)

        # Items now carry their station: refresh station-filtered kitchen displays
        try:
            from apps.kitchen.services import broadcast_order_updated

            broadcast_order_updated(Order.objects.select_related("table", "kitchen_ticket").get(pk=order.pk))
        except Exception:
            logging.getLogger(__name__).exception("Could not broadcast station update for order %s", order.pk)

    transaction.on_commit(_dispatch)


def award_points_for_order(order):
    """
    Award points to the employee who handled the order.
    Points go to served_by (waiter) if set, otherwise to created_by.
    """
    from apps.accounts.models import EmployeePoints, User
    from datetime import date

    # Determine which employee gets the points
    employee = order.served_by or order.created_by

    if not employee:
        return

    # Only award points to staff roles (not super_admin)
    staff_roles = [
        User.Role.WAITER,
        User.Role.STAFF_CASHIER,
        User.Role.STAFF_KITCHEN,
        User.Role.OUTLET_MANAGER,
    ]
    if employee.role not in staff_roles:
        return

    # Get points value from outlet settings
    outlet = order.outlet
    if not outlet:
        # Try to get outlet from table
        if order.table and order.table.floor:
            outlet = order.table.floor.outlet

    points_value = outlet.points_per_order if outlet else 10

    # Check if points already awarded for this order
    if EmployeePoints.objects.filter(order=order, reason=EmployeePoints.Reason.ORDER_COMPLETED).exists():
        return

    # Get current month
    today = date.today()
    month = today.replace(day=1)

    # Create points record
    EmployeePoints.objects.create(
        employee=employee,
        order=order,
        points=points_value,
        reason=EmployeePoints.Reason.ORDER_COMPLETED,
        description=f"Order #{order.order_number} completed",
        month=month,
        created_by=None,  # System awarded
    )


@receiver(post_save, sender=KitchenOrderTicket)
def handle_kitchen_ticket_created(sender, instance, created, **kwargs):
    """
    Handle new kitchen ticket creation.
    """
    from apps.kitchen.services import broadcast_new_order

    if created:
        # Broadcast new order when KOT is created
        broadcast_new_order(instance.order)
