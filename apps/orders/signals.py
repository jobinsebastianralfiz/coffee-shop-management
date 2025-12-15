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
        broadcast_new_order(instance)
        return

    # Status changed
    if previous_status and previous_status != instance.status:
        # Order just confirmed (status changed to confirmed)
        if instance.status == Order.Status.CONFIRMED:
            broadcast_new_order(instance)
        # Other status changes
        elif instance.status in [
            Order.Status.PREPARING,
            Order.Status.READY,
            Order.Status.SERVED,
            Order.Status.COMPLETED,
            Order.Status.CANCELLED,
        ]:
            broadcast_order_status_changed(
                instance,
                previous_status,
                instance.status,
                user=None  # User context not available in signal
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
