"""
Signals for finance app - integrate with payments.
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.orders.models import Payment


@receiver(post_save, sender=Payment)
def record_cash_payment_transaction(sender, instance, created, **kwargs):
    """
    When a cash payment is completed, create a cash drawer transaction.
    """
    from apps.finance.models import CashDrawer, CashDrawerTransaction, CashierShift

    # Only process completed cash payments
    if not created:
        return

    if instance.method != Payment.Method.CASH:
        return

    if instance.status != Payment.Status.COMPLETED:
        return

    today = timezone.now().date()

    # Get or create today's cash drawer
    cash_drawer, _ = CashDrawer.objects.get_or_create(
        date=today,
        defaults={
            "opening_balance": 0,
            "opened_at": timezone.now(),
        },
    )

    # Find active shift for this cashier
    cashier_shift = None
    if instance.order and instance.order.served_by:
        cashier_shift = CashierShift.objects.filter(
            cashier=instance.order.served_by,
            cash_drawer=cash_drawer,
            is_closed=False,
        ).first()

    # Create cash drawer transaction
    CashDrawerTransaction.objects.create(
        cash_drawer=cash_drawer,
        cashier_shift=cashier_shift,
        transaction_type=CashDrawerTransaction.TransactionType.SALE,
        amount=instance.amount,
        payment=instance,
        description=f"Cash payment for Order #{instance.order.order_number}" if instance.order else "Cash payment",
        reference=instance.transaction_id or "",
        created_by=instance.order.served_by if instance.order else None,
    )
