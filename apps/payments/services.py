"""
Online bill payment (Razorpay), shared by the guest pay-at-table page, the
Razorpay webhook and the status check. A Razorpay payment is recorded exactly
once, however many of those paths report it.
"""

import hashlib
import hmac
import logging
from decimal import Decimal

from django.db import transaction
from django.db.models import Q

logger = logging.getLogger(__name__)

OPEN_STATUSES = ("pending", "confirmed", "preparing", "ready", "served")

# Razorpay payment.method -> our Payment.Method
METHOD_MAP = {"upi": "upi", "card": "card", "wallet": "wallet", "emi": "card", "paylater": "wallet"}


def public_url(request, path):
    """Absolute URL for guests: PUBLIC_BASE_URL if set, else the current host."""
    from django.conf import settings

    base = (getattr(settings, "PUBLIC_BASE_URL", "") or "").rstrip("/")
    return f"{base}{path}" if base else request.build_absolute_uri(path)


def retail_due(order):
    """Unpaid shop items linked to the order (packed sweets etc. bought on the same bill)."""
    try:
        sales = order.retail_sales.all()
    except AttributeError:
        return Decimal("0")
    return sum(
        (s.total_amount - s.paid_amount for s in sales if s.payment_status not in ("paid", "cancelled", "refunded")),
        Decimal("0"),
    )


def amount_due(order):
    """What the guest owes right now: cafe balance plus unpaid shop items."""
    return order.balance_due + retail_due(order)


def tip_recipient(order):
    """Waiter credited with a tip: whoever served the table, else whoever took the order."""
    return order.served_by or order.created_by


def verify_checkout_signature(secret, razorpay_order_id, razorpay_payment_id, signature):
    expected = hmac.new(secret.encode(), f"{razorpay_order_id}|{razorpay_payment_id}".encode(), hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


def verify_webhook_signature(secret, body, signature):
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return bool(signature) and hmac.compare_digest(expected, signature)


def finalize_if_paid(order):
    """Close a fully paid order and free its tables (unless another party is still on them)."""
    from apps.orders.models import Order
    from apps.tables.models import Table

    order.refresh_from_db()
    if amount_due(order) > 0:
        return False
    if order.status in (Order.Status.SERVED, Order.Status.READY):
        order.update_status(Order.Status.COMPLETED)
    if order.order_type == Order.OrderType.DINE_IN:
        for tbl in order.all_tables:
            busy = Order.objects.filter(
                Q(table=tbl) | Q(combined_tables=tbl), status__in=OPEN_STATUSES
            ).exclude(pk=order.pk).exists()
            if not busy and tbl.status != Table.Status.VACANT:
                tbl.status = Table.Status.VACANT
                tbl.save(update_fields=["status", "updated_at"])
    return True


def record_razorpay_payment(rzp_order, payment_id, method="upi", signature="", processed_by=None):
    """
    Record a captured Razorpay payment against its order. Idempotent: returns
    (payment, created). The bill part settles the cafe balance and then any
    unpaid shop items; the tip is stored separately and credited to the waiter.
    """
    from apps.orders.models import Payment
    from apps.payments.models import RazorpayOrder

    if rzp_order.retail_sale_id:
        return record_retail_payment(rzp_order, payment_id, method=method, signature=signature)

    with transaction.atomic():
        rzp = RazorpayOrder.objects.select_for_update(of=("self",)).select_related("order").get(pk=rzp_order.pk)
        if rzp.status == RazorpayOrder.Status.PAID:
            existing = Payment.objects.filter(order=rzp.order, reference_number=rzp.razorpay_order_id).first()
            return existing, False

        order = rzp.order
        total = Decimal(rzp.amount) / 100
        tip = Decimal(rzp.tip_amount) / 100
        bill_part = Decimal(rzp.bill_amount) / 100 if rzp.bill_amount else total - tip

        # Bill part goes to the cafe balance first, the rest to shop items
        cafe_part = min(bill_part, order.balance_due)
        shop_part = bill_part - cafe_part

        payment = Payment.objects.create(
            order=order,
            amount=cafe_part,  # shop items are settled on their own sales below
            method=METHOD_MAP.get((method or "").lower(), Payment.Method.UPI),
            status=Payment.Status.COMPLETED,
            transaction_id=payment_id,
            reference_number=rzp.razorpay_order_id,
            processed_by=processed_by,
            tip_amount=tip,
            tip_for=tip_recipient(order) if tip > 0 else None,
            notes=("Paid online by guest" if rzp.paid_by_guest else "Paid online")
            + (f" (incl. shop items {shop_part})" if shop_part > 0 else ""),
        )

        if shop_part > 0:
            remaining = shop_part
            for sale in order.retail_sales.exclude(payment_status__in=["paid", "cancelled", "refunded"]):
                owed = sale.total_amount - sale.paid_amount
                pay = min(owed, remaining)
                if pay <= 0:
                    break
                sale.paid_amount += pay
                sale.payment_status = "paid" if sale.paid_amount >= sale.total_amount else "partial"
                sale.payment_method = METHOD_MAP.get((method or "").lower(), "upi")
                sale.save(update_fields=["paid_amount", "payment_status", "payment_method", "updated_at"])
                remaining -= pay

        rzp.razorpay_payment_id = payment_id
        if signature:
            rzp.razorpay_signature = signature
        rzp.status = RazorpayOrder.Status.PAID
        rzp.save(update_fields=["razorpay_payment_id", "razorpay_signature", "status", "updated_at"])

    finalize_if_paid(order)
    return payment, True


def record_retail_payment(rzp_order, payment_id, method="upi", signature=""):
    """
    Settle a Retail POS sale paid by scanning the counter QR. Idempotent:
    returns (sale, created).
    """
    from apps.payments.models import RazorpayOrder
    from apps.retail.models import RetailSale

    with transaction.atomic():
        rzp = RazorpayOrder.objects.select_for_update().get(pk=rzp_order.pk)
        sale = RetailSale.objects.select_for_update().get(pk=rzp.retail_sale_id)
        if rzp.status == RazorpayOrder.Status.PAID:
            return sale, False
        paid = Decimal(rzp.amount) / 100
        sale.paid_amount = min(sale.total_amount, sale.paid_amount + paid)
        sale.payment_status = RetailSale.PaymentStatus.PAID if sale.paid_amount >= sale.total_amount else RetailSale.PaymentStatus.PARTIAL
        sale.payment_method = "card" if (method or "").lower() in ("card", "emi") else "upi"
        note = f"Paid by QR (Razorpay {payment_id})"
        sale.internal_notes = f"{sale.internal_notes}\n{note}".strip()
        sale.save(update_fields=["paid_amount", "payment_status", "payment_method", "internal_notes", "updated_at"])

        rzp.razorpay_payment_id = payment_id
        if signature:
            rzp.razorpay_signature = signature
        rzp.status = RazorpayOrder.Status.PAID
        rzp.save(update_fields=["razorpay_payment_id", "razorpay_signature", "status", "updated_at"])
    return sale, True


def sync_from_gateway(rzp_order, client):
    """Ask Razorpay whether a checkout was paid (used when the browser callback was missed)."""
    from apps.payments.models import RazorpayOrder

    if rzp_order.status == RazorpayOrder.Status.PAID:
        return True
    try:
        payments = client.order.payments(rzp_order.razorpay_order_id)
    except Exception:
        logger.exception("Razorpay status check failed for %s", rzp_order.razorpay_order_id)
        return False
    for p in payments.get("items", []):
        if p.get("status") == "captured":
            record_razorpay_payment(rzp_order, p["id"], p.get("method", "upi"))
            return True
    return False
