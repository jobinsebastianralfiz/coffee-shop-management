"""
Pay at table: the guest scans the QR on the printed bill (or opens the shared
link), checks the bill, optionally adds a tip and pays with Razorpay (UPI, card
or wallet). The link is the order's random UUID, so it cannot be guessed.
"""

import io
import json
import logging
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.core.models import BusinessSettings
from apps.orders.models import Order
from apps.payments import services
from apps.payments.models import PaymentSettings, RazorpayOrder

logger = logging.getLogger(__name__)

TIP_PERCENTS = (5, 10, 15)


def _order(order_uuid):
    return get_object_or_404(Order.objects.select_related("table", "outlet"), uuid=order_uuid)


def _bill_lines(order):
    lines = [i for i in order.items.all() if i.status != "cancelled"]
    shop = []
    try:
        for sale in order.retail_sales.exclude(payment_status="cancelled"):
            shop.extend(sale.items.all())
    except AttributeError:
        pass
    return lines, shop


@require_GET
def pay_page(request, order_uuid):
    order = _order(order_uuid)
    settings_obj = PaymentSettings.load()
    due = services.amount_due(order)
    lines, shop_lines = _bill_lines(order)
    payments = list(order.payments.filter(status="completed").order_by("created_at"))
    is_settled = due <= 0 and bool(payments)
    tips = sum((p.tip_amount for p in payments), Decimal("0"))
    return render(request, "ordering/pay.html", {
        "is_settled": is_settled,
        "receipt": {
            "bill": sum((p.amount for p in payments), Decimal("0")),
            "tip": tips,
            "total": sum((p.amount + p.tip_amount for p in payments), Decimal("0")),
            "last": payments[-1] if payments else None,
        },
        "order": order,
        "business": BusinessSettings.load(),
        "lines": lines,
        "shop_lines": shop_lines,
        "amount_due": due,
        "is_open": order.status in services.OPEN_STATUSES,
        "online_enabled": settings_obj.get_razorpay_client() is not None,
        "tip_options": [(p, (due * p / 100).quantize(Decimal("1"))) for p in TIP_PERCENTS] if due > 0 else [],
        "paid_payments": order.payments.filter(status="completed").order_by("-created_at"),
    })


@require_GET
def pay_receipt(request, order_uuid):
    """Printable receipt for the guest once the bill is fully paid."""
    order = _order(order_uuid)
    if services.amount_due(order) > 0:
        return HttpResponse("This bill isn't fully paid yet.", status=404)
    linked = list(order.retail_sales.all()) if hasattr(order, "retail_sales") else []
    return render(request, "dashboard/orders/print.html", {
        "order": order,
        "business": BusinessSettings.load(),
        "linked_retail_sales": linked,
        "retail_total": sum((s.total_amount for s in linked), Decimal("0")),
        "combined_total": order.total_amount + sum((s.total_amount for s in linked), Decimal("0")),
        "amount_to_pay": Decimal("0"),
        "online_pay": False,
    })


@require_GET
def pay_qr(request, order_uuid):
    """PNG QR code of the pay link, printed on the bill."""
    import qrcode

    order = _order(order_uuid)
    url = services.public_url(request, f"/pay/{order.uuid}/")
    img = qrcode.make(url, box_size=6, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    resp = HttpResponse(buf.getvalue(), content_type="image/png")
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


def _parse_tip(raw, due):
    try:
        tip = Decimal(str(raw or "0")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None
    if tip < 0 or tip > max(due, Decimal("0")):
        return None  # tips are capped at the bill amount to catch typos
    return tip


@require_POST
def pay_start(request, order_uuid):
    """Create a Razorpay checkout for the current balance plus the chosen tip."""
    order = _order(order_uuid)
    if order.status not in services.OPEN_STATUSES:
        return JsonResponse({"error": "This bill is already closed."}, status=400)

    due = services.amount_due(order)
    if due <= 0:
        return JsonResponse({"error": "Nothing left to pay on this bill."}, status=400)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        body = {}
    tip = _parse_tip(body.get("tip"), due)
    if tip is None:
        return JsonResponse({"error": "Please enter a valid tip."}, status=400)

    settings_obj = PaymentSettings.load()
    client = settings_obj.get_razorpay_client()
    if client is None:
        return JsonResponse({"error": "Online payment isn't available. Please pay at the counter."}, status=400)

    bill_paise = int((due * 100).quantize(Decimal("1")))
    tip_paise = int((tip * 100).quantize(Decimal("1")))
    try:
        rzp = client.order.create({
            "amount": bill_paise + tip_paise,
            "currency": "INR",
            "receipt": f"bill_{order.order_number}"[:40],
            "notes": {"order_id": str(order.pk), "order_number": order.order_number, "tip": str(tip), "source": "pay_at_table"},
        })
    except Exception:
        logger.exception("Razorpay order create failed for %s", order.order_number)
        return JsonResponse({"error": "Couldn't start the payment. Please try again or pay at the counter."}, status=502)

    RazorpayOrder.objects.create(
        order=order,
        razorpay_order_id=rzp["id"],
        amount=bill_paise + tip_paise,
        bill_amount=bill_paise,
        tip_amount=tip_paise,
        paid_by_guest=True,
    )
    business = BusinessSettings.load()
    return JsonResponse({
        "key": settings_obj.razorpay_key_id,
        "razorpay_order_id": rzp["id"],
        "amount": bill_paise + tip_paise,
        "currency": "INR",
        "name": getattr(business, "business_name", "") or "Bill",
        "description": f"Bill #{order.order_number}" + (f" + tip {tip}" if tip else ""),
        "prefill": {"name": order.customer_name, "contact": order.customer_phone},
    })


@require_POST
def pay_verify(request, order_uuid):
    """Browser callback after Razorpay checkout succeeds (signature-checked)."""
    order = _order(order_uuid)
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request"}, status=400)

    rzp_order_id = data.get("razorpay_order_id", "")
    payment_id = data.get("razorpay_payment_id", "")
    signature = data.get("razorpay_signature", "")
    rzp = RazorpayOrder.objects.filter(order=order, razorpay_order_id=rzp_order_id).first()
    if rzp is None:
        return JsonResponse({"error": "Payment not found"}, status=404)

    settings_obj = PaymentSettings.load()
    if not services.verify_checkout_signature(settings_obj.razorpay_key_secret, rzp_order_id, payment_id, signature):
        return JsonResponse({"error": "We couldn't verify this payment. If money was taken, show this screen at the counter."}, status=400)

    method = "upi"
    client = settings_obj.get_razorpay_client()
    if client is not None:
        try:
            method = client.payment.fetch(payment_id).get("method", "upi")
        except Exception:
            pass  # method is cosmetic; the payment itself is verified by signature
    services.record_razorpay_payment(rzp, payment_id, method=method, signature=signature)
    order.refresh_from_db()
    return JsonResponse({"ok": True, "paid": services.amount_due(order) <= 0, "amount_due": str(services.amount_due(order))})


@require_GET
def pay_status(request, order_uuid):
    """Polled by the pay page: settle any checkout the gateway says was captured."""
    order = _order(order_uuid)
    client = PaymentSettings.load().get_razorpay_client()
    if client is not None:
        for rzp in order.razorpay_orders.filter(status=RazorpayOrder.Status.CREATED, paid_by_guest=True)[:3]:
            services.sync_from_gateway(rzp, client)
    order.refresh_from_db()
    due = services.amount_due(order)
    return JsonResponse({"paid": due <= 0, "amount_due": str(due), "status": order.status})


@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Razorpay -> server notification (payment.captured / order.paid). This is what
    makes online payments reliable even if the guest closes the page early.
    Configure it in the Razorpay dashboard with the webhook secret from Settings.
    """
    settings_obj = PaymentSettings.load()
    secret = settings_obj.razorpay_webhook_secret
    if not secret:
        return JsonResponse({"error": "Webhook secret not configured"}, status=400)
    if not services.verify_webhook_signature(secret, request.body, request.META.get("HTTP_X_RAZORPAY_SIGNATURE", "")):
        return JsonResponse({"error": "Invalid signature"}, status=400)

    try:
        event = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if event.get("event") in ("payment.captured", "order.paid"):
        payment = (event.get("payload", {}).get("payment") or {}).get("entity") or {}
        rzp_order_id = payment.get("order_id")
        if rzp_order_id and payment.get("status") == "captured":
            rzp = RazorpayOrder.objects.filter(razorpay_order_id=rzp_order_id).first()
            if rzp is not None:
                services.record_razorpay_payment(rzp, payment.get("id", ""), method=payment.get("method", "upi"))
    return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Retail POS: the customer scans the QR shown at the counter and pays the sale
# ---------------------------------------------------------------------------

def _sale(sale_uuid):
    from apps.retail.models import RetailSale

    return get_object_or_404(RetailSale.objects.select_related("outlet"), uuid=sale_uuid)


def sale_due(sale):
    if sale.payment_status in ("paid", "cancelled", "refunded"):
        return Decimal("0")
    return max(sale.total_amount - sale.paid_amount, Decimal("0"))


@require_GET
def pay_sale_page(request, sale_uuid):
    sale = _sale(sale_uuid)
    due = sale_due(sale)
    return render(request, "ordering/pay_sale.html", {
        "sale": sale,
        "lines": list(sale.items.all()),
        "business": BusinessSettings.load(),
        "amount_due": due,
        "is_settled": sale.payment_status == "paid",
        "is_cancelled": sale.payment_status in ("cancelled", "refunded"),
        "online_enabled": PaymentSettings.load().get_razorpay_client() is not None,
        "last_payment": sale.razorpay_orders.filter(status=RazorpayOrder.Status.PAID).order_by("-updated_at").first(),
    })


@require_GET
def pay_sale_qr(request, sale_uuid):
    """QR of the sale's pay link, shown on the POS and the customer display."""
    from apps.tables.qr_svg import qr_svg

    sale = _sale(sale_uuid)
    url = services.public_url(request, f"/pay/s/{sale.uuid}/")
    resp = HttpResponse(qr_svg(url, logo_hole=False), content_type="image/svg+xml")
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


@require_POST
def pay_sale_start(request, sale_uuid):
    sale = _sale(sale_uuid)
    due = sale_due(sale)
    if due <= 0:
        return JsonResponse({"error": "Nothing left to pay on this bill."}, status=400)
    settings_obj = PaymentSettings.load()
    client = settings_obj.get_razorpay_client()
    if client is None:
        return JsonResponse({"error": "Online payment isn't available. Please pay at the counter."}, status=400)
    paise = int((due * 100).quantize(Decimal("1")))
    try:
        rzp = client.order.create({
            "amount": paise,
            "currency": "INR",
            "receipt": f"sale_{sale.sale_number}"[:40],
            "notes": {"retail_sale_id": str(sale.pk), "sale_number": sale.sale_number, "source": "retail_pos_qr"},
        })
    except Exception:
        logger.exception("Razorpay order create failed for sale %s", sale.sale_number)
        return JsonResponse({"error": "Couldn't start the payment. Please try again or pay at the counter."}, status=502)
    RazorpayOrder.objects.create(
        retail_sale=sale, razorpay_order_id=rzp["id"], amount=paise, bill_amount=paise, paid_by_guest=True,
    )
    business = BusinessSettings.load()
    return JsonResponse({
        "key": settings_obj.razorpay_key_id,
        "razorpay_order_id": rzp["id"],
        "amount": paise,
        "currency": "INR",
        "name": getattr(business, "business_name", "") or "Bill",
        "description": f"Bill #{sale.sale_number}",
        "prefill": {"name": sale.customer_name, "contact": sale.customer_phone},
    })


@require_POST
def pay_sale_verify(request, sale_uuid):
    sale = _sale(sale_uuid)
    try:
        data = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid request"}, status=400)
    rzp_order_id = data.get("razorpay_order_id", "")
    payment_id = data.get("razorpay_payment_id", "")
    signature = data.get("razorpay_signature", "")
    rzp = RazorpayOrder.objects.filter(retail_sale=sale, razorpay_order_id=rzp_order_id).first()
    if rzp is None:
        return JsonResponse({"error": "Payment not found"}, status=404)
    settings_obj = PaymentSettings.load()
    if not services.verify_checkout_signature(settings_obj.razorpay_key_secret, rzp_order_id, payment_id, signature):
        return JsonResponse({"error": "We couldn't verify this payment. If money was taken, show this screen at the counter."}, status=400)
    method = "upi"
    client = settings_obj.get_razorpay_client()
    if client is not None:
        try:
            method = client.payment.fetch(payment_id).get("method", "upi")
        except Exception:
            pass
    services.record_retail_payment(rzp, payment_id, method=method, signature=signature)
    return JsonResponse({"ok": True})


def sync_sale(sale):
    """Settle any QR checkout the gateway says was captured. Returns the amount still due."""
    client = PaymentSettings.load().get_razorpay_client()
    if client is not None and sale_due(sale) > 0:
        for rzp in sale.razorpay_orders.filter(status=RazorpayOrder.Status.CREATED)[:3]:
            services.sync_from_gateway(rzp, client)
        sale.refresh_from_db()
    return sale_due(sale)


@require_GET
def pay_sale_status(request, sale_uuid):
    sale = _sale(sale_uuid)
    due = sync_sale(sale)
    return JsonResponse({"paid": sale.payment_status == "paid", "amount_due": str(due), "status": sale.payment_status})
