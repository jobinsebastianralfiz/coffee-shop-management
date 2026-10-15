"""
Billing counter: guests bring the bill the waiter printed to a single counter,
the cashier adds anything they pick up there (sweets, packed snacks...) and
collects payment by cash, card, UPI or wallet.
"""

from decimal import Decimal

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.kitchen.routing import OPEN_STATUSES
from apps.menu.models import MenuItem
from apps.orders.models import CounterDisplay, Order, OrderItem, Payment
from apps.payments.services import public_url

try:
    from apps.retail.models import RetailProduct, RetailSale, RetailSaleItem, RetailStockMovement

    RETAIL_AVAILABLE = True
except ImportError:  # pragma: no cover
    RETAIL_AVAILABLE = False

COUNTER_ROLES = [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]


def _user_outlet(user):
    return None if user.role == User.Role.SUPER_ADMIN else user.outlet


def _open_bills(user, query=""):
    """Open orders that still owe money, bills already given to guests first."""
    orders = (
        Order.objects.filter(status__in=OPEN_STATUSES)
        .exclude(items__isnull=True)
        .select_related("table", "created_by")
        .prefetch_related("combined_tables")
        .distinct()
    )
    outlet = _user_outlet(user)
    if outlet is not None:
        orders = orders.filter(Q(outlet=outlet) | Q(table__floor__outlet=outlet))
    if query:
        q = query.strip().lstrip("#")
        orders = orders.filter(
            Q(order_number__icontains=q)
            | Q(table__number__iexact=q)
            | Q(combined_tables__number__iexact=q)
            | Q(party_name__icontains=q)
            | Q(customer_name__icontains=q)
            | Q(customer_phone__icontains=q)
        ).distinct()
    bills = []
    from datetime import timedelta

    from apps.payments.models import RazorpayOrder

    paying_since = timezone.now() - timedelta(minutes=15)
    paying_online = set(
        RazorpayOrder.objects.filter(
            paid_by_guest=True, status=RazorpayOrder.Status.CREATED, created_at__gte=paying_since
        ).values_list("order_id", flat=True)
    )
    for order in orders:
        order.paying_online = order.pk in paying_online
        retail_due = _retail_due(order)
        due = order.balance_due + retail_due
        if due <= 0:
            continue
        order.counter_due = due
        bills.append(order)
    # Bills the waiter has printed are the ones guests are bringing to the counter
    bills.sort(key=lambda o: (o.bill_printed_at is None, -(o.bill_printed_at or o.created_at).timestamp()))
    return bills


def _retail_sales(order):
    return list(order.retail_sales.all()) if RETAIL_AVAILABLE else []


def _retail_due(order):
    if not RETAIL_AVAILABLE:
        return Decimal("0")
    return sum(
        (s.total_amount - s.paid_amount for s in order.retail_sales.all()
         if s.payment_status not in [RetailSale.PaymentStatus.PAID, RetailSale.PaymentStatus.CANCELLED]),
        Decimal("0"),
    )


@login_required
def billing_counter(request):
    """The cashier's screen: open bills on the left, checkout for the chosen one."""
    if request.user.role not in COUNTER_ROLES:
        messages.error(request, "The billing counter is for cashiers and managers.")
        return redirect("dashboard:home")

    query = request.GET.get("q", "").strip()
    bills = _open_bills(request.user, query)

    selected = None
    order_param = request.GET.get("order", "")
    if order_param.isdigit():
        selected = next((b for b in bills if b.pk == int(order_param)), None)
        if selected is None:
            # Not owing anything any more (just paid) or not visible to this user
            selected_paid = Order.objects.filter(pk=order_param).first()
            if selected_paid and selected_paid.status == Order.Status.COMPLETED:
                messages.info(request, f"Order #{selected_paid.order_number} is fully paid.")
    elif query and len(bills) == 1:
        # Searching a bill number usually finds exactly one bill: open it
        selected = bills[0]

    # The customer-facing screen follows what the cashier has open
    if selected is not None:
        _set_display(request.user, CounterDisplay.Mode.BILL, selected)
    elif request.GET.get("paid", "").isdigit():
        paid_order = Order.objects.filter(pk=request.GET["paid"]).first()
        if paid_order is not None and _retail_due(paid_order) + paid_order.balance_due <= 0:
            _set_display(request.user, CounterDisplay.Mode.PAID, paid_order)

    context = {
        "page_title": "Billing Counter",
        "bills": bills,
        "query": query,
        "selected": selected,
        "payment_methods": [(m, label) for m, label in Payment.Method.choices if m != Payment.Method.SPLIT],
        "just_paid": request.GET.get("paid", ""),
    }

    if selected is not None:
        items = list(selected.items.all())
        retail_sales = _retail_sales(selected)
        retail_due = _retail_due(selected)
        from apps.payments.models import PaymentSettings

        context.update({
            "pay_url": public_url(request, reverse("payments:pay", args=[selected.uuid])),
            "online_pay": PaymentSettings.load().get_razorpay_client() is not None,
            "items": items,
            "retail_sales": retail_sales,
            "retail_due": retail_due,
            "amount_due": selected.balance_due + retail_due,
            "paid_so_far": selected.paid_amount + sum((s.paid_amount for s in retail_sales), Decimal("0")),
            "unsent_count": sum(1 for i in items if i.kot_sent_at is None and i.status != OrderItem.Status.CANCELLED),
            "counter_menu": MenuItem.objects.filter(is_available=True).select_related("category").order_by("category__display_order", "name"),
        })
        if RETAIL_AVAILABLE and getattr(django_settings, "ENABLE_RETAIL", False):
            products = RetailProduct.objects.filter(is_active=True)
            outlet = _user_outlet(request.user) or selected.outlet
            if outlet is not None:
                products = products.filter(outlet=outlet)
            context["counter_products"] = products.order_by("name")[:300]

    return render(request, "dashboard/billing/counter.html", context)


@login_required
@require_http_methods(["POST"])
def order_add_retail_item(request, pk):
    """
    Add a shop product (packed sweets, snacks...) to a cafe bill. It is kept on a
    retail sale linked to the order, so stock and retail reports stay correct, and
    is paid together with the order.
    """
    back = request.POST.get("next") or reverse("dashboard:order_detail", args=[pk])
    if not back.startswith("/"):
        back = reverse("dashboard:order_detail", args=[pk])

    if not (RETAIL_AVAILABLE and getattr(django_settings, "ENABLE_RETAIL", False)):
        messages.error(request, "Retail is not enabled.")
        return redirect(back)

    order = Order.objects.filter(pk=pk, status__in=OPEN_STATUSES).first()
    if order is None:
        messages.error(request, "This order is closed.")
        return redirect(back)

    try:
        quantity = Decimal(request.POST.get("quantity", "1") or "1")
    except Exception:
        quantity = Decimal("1")
    if quantity <= 0:
        messages.error(request, "Quantity must be more than zero.")
        return redirect(back)

    product = RetailProduct.objects.filter(pk=request.POST.get("product"), is_active=True).first()
    if product is None:
        messages.error(request, "Product not found.")
        return redirect(back)
    if product.track_inventory and product.current_stock < quantity:
        messages.error(request, f"Only {product.current_stock} {product.name} in stock.")
        return redirect(back)

    with transaction.atomic():
        sale = order.retail_sales.filter(
            payment_status__in=[RetailSale.PaymentStatus.PENDING, RetailSale.PaymentStatus.PARTIAL]
        ).first()
        if sale is None:
            sale = RetailSale.objects.create(
                outlet=product.outlet,
                sale_type=RetailSale.SaleType.RETAIL,
                linked_order=order,
                payment_status=RetailSale.PaymentStatus.PENDING,
                created_by=request.user,
                customer_name=order.customer_name,
                customer_phone=order.customer_phone,
            )
        RetailSaleItem.objects.create(
            sale=sale,
            product=product,
            quantity=quantity,
            unit_price=product.selling_price,
        )
        sale.calculate_totals()
        if product.track_inventory:
            before = product.current_stock
            product.current_stock -= quantity
            product.save(update_fields=["current_stock", "updated_at"])
            RetailStockMovement.objects.create(
                product=product,
                movement_type=RetailStockMovement.MovementType.SALE,
                quantity=-quantity,
                stock_before=before,
                stock_after=product.current_stock,
                reference_type="RetailSale",
                reference_id=sale.pk,
                reason=f"Counter sale on order {order.order_number}",
                created_by=request.user,
            )

    messages.success(request, f"Added {quantity:g} × {product.name} to the bill.")
    return redirect(back)


@login_required
def billing_tips(request):
    """Tips left by guests, per staff member, for a date range (default: today)."""
    from datetime import date, timedelta

    from django.db.models import Count, Sum

    if request.user.role not in COUNTER_ROLES:
        messages.error(request, "Tips are visible to cashiers and managers.")
        return redirect("dashboard:home")

    today = timezone.localdate()
    period = request.GET.get("period", "today")
    start = {"today": today, "week": today - timedelta(days=6), "month": today.replace(day=1)}.get(period, today)

    tips = Payment.objects.filter(
        status=Payment.Status.COMPLETED, tip_amount__gt=0, created_at__date__gte=start, created_at__date__lte=today
    )
    outlet = _user_outlet(request.user)
    if outlet is not None:
        tips = tips.filter(Q(order__outlet=outlet) | Q(order__table__floor__outlet=outlet))

    by_staff = (
        tips.values("tip_for", "tip_for__first_name", "tip_for__last_name", "tip_for__username")
        .annotate(total=Sum("tip_amount"), count=Count("pk"))
        .order_by("-total")
    )
    context = {
        "page_title": "Tips",
        "period": period,
        "start": start,
        "total": tips.aggregate(t=Sum("tip_amount"))["t"] or Decimal("0"),
        "count": tips.count(),
        "by_staff": by_staff,
        "recent": tips.select_related("order", "tip_for").order_by("-created_at")[:50],
    }
    return render(request, "dashboard/billing/tips.html", context)


# ---------------------------------------------------------------------------
# Customer-facing display (a tablet or monitor turned towards the guest)
# ---------------------------------------------------------------------------

DISPLAY_THANKS_SECONDS = 10


def _display_key(user):
    outlet = _user_outlet(user)
    return f"outlet-{outlet.pk}" if outlet is not None else f"user-{user.pk}"


def _set_display(user, mode, order=None):
    CounterDisplay.objects.update_or_create(key=_display_key(user), defaults={"mode": mode, "order": order, "retail_sale": None})


@login_required
def customer_display(request):
    """Full-screen page for the screen facing the guest. Leave it open on that device."""
    if request.user.role not in COUNTER_ROLES:
        messages.error(request, "The customer display is for the billing counter.")
        return redirect("dashboard:home")
    from apps.core.models import BusinessSettings

    return render(request, "dashboard/billing/customer_display.html", {"business": BusinessSettings.load()})


@login_required
def customer_display_state(request):
    """What the customer screen should show right now (polled every couple of seconds)."""
    from django.http import JsonResponse

    from apps.payments.models import PaymentSettings

    if request.user.role not in COUNTER_ROLES:
        return JsonResponse({"error": "forbidden"}, status=403)

    state = CounterDisplay.objects.filter(key=_display_key(request.user)).select_related("order", "order__table", "retail_sale").first()
    if state is not None and state.retail_sale_id and state.mode != CounterDisplay.Mode.IDLE:
        return _display_retail_sale(state)
    if state is None or state.order is None or state.mode == CounterDisplay.Mode.IDLE:
        return JsonResponse({"mode": "idle"})

    order = state.order
    due = order.balance_due + _retail_due(order)
    if state.mode == CounterDisplay.Mode.BILL and (due <= 0 or order.status not in OPEN_STATUSES):
        # Paid meanwhile (e.g. the guest scanned the QR): say thank you
        state.mode = CounterDisplay.Mode.PAID
        state.save(update_fields=["mode", "updated_at"])
    if state.mode == CounterDisplay.Mode.PAID:
        if (timezone.now() - state.updated_at).total_seconds() > DISPLAY_THANKS_SECONDS:
            state.mode = CounterDisplay.Mode.IDLE
            state.order = None
            state.save(update_fields=["mode", "order", "updated_at"])
            return JsonResponse({"mode": "idle"})
        tip = sum((p.tip_amount for p in order.payments.filter(status="completed")), Decimal("0"))
        return JsonResponse({"mode": "paid", "order_number": order.order_number, "tip": str(tip)})

    lines = [
        {"name": i.item_name + (f" ({i.variant_name})" if i.variant_name else ""), "qty": i.quantity, "total": str(i.total_price)}
        for i in order.items.all() if i.status != OrderItem.Status.CANCELLED
    ]
    for sale in _retail_sales(order):
        if sale.payment_status == RetailSale.PaymentStatus.CANCELLED:
            continue
        for ri in sale.items.all():
            lines.append({"name": ri.product_name, "qty": float(ri.quantity), "total": f"{ri.total:.2f}"})

    online = PaymentSettings.load().get_razorpay_client() is not None
    return JsonResponse({
        "mode": "bill",
        "order_id": order.pk,
        "order_number": order.order_number,
        "where": (f"Table {order.all_table_numbers or order.table.number}" if order.table_id else order.get_order_type_display()),
        "party": order.party_name,
        "lines": lines,
        "subtotal": str(order.subtotal),
        "tax": str(order.tax_amount),
        "service": str(order.service_charge),
        "discount": str(order.discount_amount),
        "paid": str(order.paid_amount),
        "due": f"{due:.2f}",
        "online": online,
        "qr_url": reverse("payments:pay_qr", args=[order.uuid]) if online else "",
        "updated": state.updated_at.isoformat(),
    })


def _display_retail_sale(state):
    """Customer screen for a Retail POS sale waiting to be paid by QR."""
    from django.http import JsonResponse

    from apps.payments.views import sale_due, sync_sale

    sale = state.retail_sale
    if state.mode == CounterDisplay.Mode.BILL:
        sync_sale(sale)
        if sale.payment_status in (RetailSale.PaymentStatus.PAID, RetailSale.PaymentStatus.CANCELLED):
            state.mode = CounterDisplay.Mode.PAID if sale.payment_status == RetailSale.PaymentStatus.PAID else CounterDisplay.Mode.IDLE
            state.save(update_fields=["mode", "updated_at"])
    if state.mode == CounterDisplay.Mode.IDLE:
        return JsonResponse({"mode": "idle"})
    if state.mode == CounterDisplay.Mode.PAID:
        if (timezone.now() - state.updated_at).total_seconds() > DISPLAY_THANKS_SECONDS:
            state.mode = CounterDisplay.Mode.IDLE
            state.retail_sale = None
            state.save(update_fields=["mode", "retail_sale", "updated_at"])
            return JsonResponse({"mode": "idle"})
        return JsonResponse({"mode": "paid", "order_number": sale.sale_number, "tip": "0"})

    from apps.retail.views import _qr_mode

    mode = _qr_mode()
    qr = ""
    if mode == "razorpay":
        qr = reverse("payments:pay_sale_qr", args=[sale.uuid])
    elif mode == "upi":
        qr = reverse("retail:pos_sale_upi_qr", args=[sale.uuid])
    return JsonResponse({
        "mode": "bill",
        "order_id": f"s{sale.pk}",
        "order_number": sale.sale_number,
        "where": "Shop",
        "party": sale.customer_name,
        "lines": [{"name": i.product_name, "qty": float(i.quantity), "total": f"{i.total:.2f}"} for i in sale.items.all()],
        "subtotal": str(sale.subtotal),
        "tax": str(sale.cgst_amount + sale.sgst_amount),
        "service": "0",
        "discount": str(sale.discount_amount),
        "paid": str(sale.paid_amount),
        "due": f"{sale_due(sale):.2f}",
        "online": bool(qr),
        "qr_url": qr,
        "updated": state.updated_at.isoformat(),
    })


@login_required
@require_http_methods(["POST"])
def customer_display_clear(request):
    """Cashier blanks the customer screen (back to the welcome message)."""
    if request.user.role in COUNTER_ROLES:
        _set_display(request.user, CounterDisplay.Mode.IDLE, None)
    back = request.POST.get("next", "")
    return redirect(back if back.startswith("/") else reverse("dashboard:billing_counter"))


def _collection_period(request):
    """
    Period from the query string: ?period=day&date=YYYY-MM-DD (default today),
    ?period=month&month=YYYY-MM, ?period=all, or ?period=range&from=...&to=...
    Returns (period, start, end, label) with start/end as dates (start None = all time).
    """
    from calendar import monthrange
    from datetime import date as date_cls

    today = timezone.localdate()
    period = request.GET.get("period", "day")

    def parse(value, default):
        try:
            return date_cls.fromisoformat(value) if value else default
        except ValueError:
            return default

    if period == "month":
        try:
            y, m = (int(x) for x in request.GET.get("month", "").split("-"))
            start = date_cls(y, m, 1)
        except ValueError:
            start = today.replace(day=1)
        end = min(start.replace(day=monthrange(start.year, start.month)[1]), today)
        return "month", start, end, start.strftime("%B %Y")
    if period == "all":
        return "all", None, today, "All time"
    if period == "range":
        start = parse(request.GET.get("from"), today.replace(day=1))
        end = parse(request.GET.get("to"), today)
        if end < start:
            start, end = end, start
        return "range", start, end, f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"
    day = parse(request.GET.get("date"), today)
    return "day", day, day, day.strftime("%A, %d %b %Y")


def _collections_data(user, start, end):
    """Money collected between start and end (inclusive; start None = all time)."""
    from collections import OrderedDict

    from django.db.models import Count, Sum
    from django.db.models.functions import TruncDate

    outlet = _user_outlet(user)
    payments = Payment.objects.filter(status=Payment.Status.COMPLETED, created_at__date__lte=end).select_related(
        "order", "order__table", "processed_by", "tip_for"
    )
    if start is not None:
        payments = payments.filter(created_at__date__gte=start)
    if outlet is not None:
        payments = payments.filter(Q(order__outlet=outlet) | Q(order__table__floor__outlet=outlet))

    labels = dict(Payment.Method.choices)
    by_method = [
        {"key": row["method"], "method": labels.get(row["method"], row["method"]), "total": row["total"], "tips": row["tips"], "count": row["count"]}
        for row in payments.values("method").annotate(total=Sum("amount"), tips=Sum("tip_amount"), count=Count("pk")).order_by("-total")
    ]
    online = payments.filter(notes__startswith="Paid online")
    totals = payments.aggregate(bills=Sum("amount"), tips=Sum("tip_amount"))
    online_total = online.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    tips_by_staff = list(
        payments.filter(tip_amount__gt=0)
        .values("tip_for", "tip_for__first_name", "tip_for__last_name", "tip_for__username")
        .annotate(total=Sum("tip_amount"), count=Count("pk"))
        .order_by("-total")
    )

    sales = None
    retail_by_method, retail_total = [], Decimal("0")
    if RETAIL_AVAILABLE:
        sales = RetailSale.objects.filter(
            created_at__date__lte=end, linked_order__isnull=True, payment_status=RetailSale.PaymentStatus.PAID
        )
        if start is not None:
            sales = sales.filter(created_at__date__gte=start)
        if outlet is not None:
            sales = sales.filter(outlet=outlet)
        retail_by_method = list(sales.values("payment_method").annotate(total=Sum("total_amount"), count=Count("pk")).order_by("-total"))
        retail_total = sales.aggregate(t=Sum("total_amount"))["t"] or Decimal("0")

    # Day-by-day breakdown (for months, ranges and all time)
    days = OrderedDict()
    for row in payments.annotate(d=TruncDate("created_at")).values("d", "method").annotate(total=Sum("amount"), tips=Sum("tip_amount"), bills=Count("order", distinct=True)):
        day = days.setdefault(row["d"], {"date": row["d"], "cash": Decimal("0"), "card": Decimal("0"), "upi": Decimal("0"), "wallet": Decimal("0"), "tips": Decimal("0"), "retail": Decimal("0"), "bills": 0})
        if row["method"] in ("cash", "card", "upi", "wallet"):
            day[row["method"]] += row["total"] or 0
        else:
            day["card"] += row["total"] or 0
        day["tips"] += row["tips"] or 0
        day["bills"] += row["bills"]
    if sales is not None:
        for row in sales.annotate(d=TruncDate("created_at")).values("d").annotate(total=Sum("total_amount")):
            day = days.setdefault(row["d"], {"date": row["d"], "cash": Decimal("0"), "card": Decimal("0"), "upi": Decimal("0"), "wallet": Decimal("0"), "tips": Decimal("0"), "retail": Decimal("0"), "bills": 0})
            day["retail"] += row["total"] or 0
    daily = sorted(days.values(), key=lambda d: d["date"], reverse=True)
    for d in daily:
        d["total"] = d["cash"] + d["card"] + d["upi"] + d["wallet"] + d["tips"] + d["retail"]

    bills = totals["bills"] or Decimal("0")
    tips = totals["tips"] or Decimal("0")
    return {
        "bills_total": bills,
        "tips_total": tips,
        "grand_total": bills + tips + retail_total,
        "orders_paid": payments.values("order").distinct().count(),
        "by_method": by_method,
        "online_total": online_total,
        "online_count": online.count(),
        "counter_total": bills - online_total,
        "tips_by_staff": tips_by_staff,
        "retail_by_method": retail_by_method,
        "retail_total": retail_total,
        "daily": daily,
        "payments": payments.order_by("-created_at"),
        "outlet": outlet,
    }


@login_required
def daily_collections(request):
    """Money collected for a day, a month, a custom range or all time."""
    from datetime import timedelta

    if request.user.role not in COUNTER_ROLES:
        messages.error(request, "Collections are visible to cashiers and managers.")
        return redirect("dashboard:home")

    period, start, end, label = _collection_period(request)
    today = timezone.localdate()
    context = {
        "page_title": "Collections",
        "period": period,
        "start": start,
        "end": end,
        "label": label,
        "is_today": period == "day" and start == today,
        "today": today,
        "prev_day": (start or today) - timedelta(days=1),
        "next_day": (start or today) + timedelta(days=1),
        "month_value": (start or today).strftime("%Y-%m"),
        "query": request.GET.urlencode(),
        **_collections_data(request.user, start, end),
    }
    return render(request, "dashboard/billing/collections.html", context)


@login_required
def daily_collections_pdf(request):
    """The same summary as a PDF (day, month, range or all time)."""
    from django.http import HttpResponse

    from apps.reports.pdf_generator import BasePDFReport
    from reportlab.lib import colors
    from reportlab.lib.units import inch

    if request.user.role not in COUNTER_ROLES:
        messages.error(request, "Collections are visible to cashiers and managers.")
        return redirect("dashboard:home")

    period, start, end, label = _collection_period(request)
    data = _collections_data(request.user, start, end)
    dark = colors.HexColor("#2A2A2C")

    def rs(value):
        # The built-in PDF fonts have no rupee glyph
        return f"Rs. {Decimal(value or 0):,.2f}"

    outlet = data["outlet"]
    report = BasePDFReport("Collections", f"{label}" + (f" · {outlet.name}" if outlet else ""))
    report.add_header()
    report.add_summary_box([
        ("Total collected", rs(data["grand_total"])),
        ("Restaurant bills", f"{rs(data['bills_total'])}  ({data['orders_paid']} paid)"),
        ("Tips", rs(data["tips_total"])),
        ("Retail POS sales", rs(data["retail_total"])),
        ("Paid online by guests", f"{rs(data['online_total'])}  ({data['online_count']})"),
        ("Collected at the counter", rs(data["counter_total"])),
    ])

    report.add_section("By payment method (restaurant bills)")
    if data["by_method"]:
        rows = [["Method", "Payments", "Amount", "Tips on top"]]
        rows += [[m["method"], str(m["count"]), rs(m["total"]), rs(m["tips"])] for m in data["by_method"]]
        report.add_table(rows, col_widths=[2.2 * inch, 1.2 * inch, 1.8 * inch, 1.8 * inch], header_color=dark)
    else:
        report.add_text("No restaurant payments in this period.")

    if data["retail_by_method"]:
        report.add_section("Retail POS")
        rows = [["Method", "Sales", "Amount"]] + [
            [(r["payment_method"] or "Other").title(), str(r["count"]), rs(r["total"])] for r in data["retail_by_method"]
        ]
        report.add_table(rows, col_widths=[2.2 * inch, 1.2 * inch, 1.8 * inch], header_color=dark)

    report.add_section("Tips by staff")
    if data["tips_by_staff"]:
        rows = [["Staff", "Tips", "Amount"]]
        for t in data["tips_by_staff"]:
            name = f"{t['tip_for__first_name'] or t['tip_for__username'] or 'Not assigned'} {t['tip_for__last_name'] or ''}".strip()
            rows.append([name, str(t["count"]), rs(t["total"])])
        report.add_table(rows, col_widths=[3 * inch, 1.2 * inch, 1.8 * inch], header_color=dark)
    else:
        report.add_text("No tips in this period.")

    if period != "day" and data["daily"]:
        report.add_section("Day by day")
        rows = [["Date", "Bills", "Cash", "Card", "UPI", "Wallet", "Tips", "Retail", "Total"]]
        for d in data["daily"]:
            rows.append([d["date"].strftime("%d %b %Y"), str(d["bills"])] + [f"{d[k]:,.2f}" for k in ("cash", "card", "upi", "wallet", "tips", "retail", "total")])
        report.add_table(rows, col_widths=[0.95 * inch, 0.5 * inch] + [0.82 * inch] * 7, header_color=dark)

    report.add_section("All payments")
    payments = list(data["payments"][:1000])
    if payments:
        rows = [["Date / time", "Bill", "Table", "Method", "Reference", "Amount", "Tip"]]
        for p in payments:
            online_tag = " (online)" if (p.notes or "").startswith("Paid online") else ""
            rows.append([
                timezone.localtime(p.created_at).strftime("%d %b %H:%M"),
                p.order.order_number,
                str(p.order.table.number) if p.order.table_id else p.order.get_order_type_display(),
                p.get_method_display() + online_tag,
                (p.transaction_id or "-")[:20],
                rs(p.amount),
                rs(p.tip_amount) if p.tip_amount else "-",
            ])
        report.add_table(rows, col_widths=[0.95 * inch, 1.35 * inch, 0.6 * inch, 1.15 * inch, 1.45 * inch, 0.9 * inch, 0.75 * inch], header_color=dark)
        if len(data["payments"]) > 1000:
            report.add_text("Only the latest 1,000 payments are listed; totals above include all of them.")
    else:
        report.add_text("No payments in this period.")

    pdf = report.generate()
    if period == "all" or start is None:
        slug = "all-time"
    elif period == "day":
        slug = start.isoformat()
    elif period == "month":
        slug = start.strftime("%Y-%m")
    else:
        slug = f"{start.isoformat()}_to_{end.isoformat()}"
    response = HttpResponse(pdf.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="collections-{slug}.pdf"'
    return response
