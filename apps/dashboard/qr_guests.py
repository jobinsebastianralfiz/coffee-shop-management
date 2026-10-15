"""
Staff side of the QR table presence check: the 'is this guest at the table?'
requests and waiter calls that pop up on the dashboard and waiter app.
"""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.kitchen.routing import OPEN_STATUSES
from apps.ordering import guard
from apps.ordering.models import QRGuestSession

STAFF_ROLES = ("super_admin", "outlet_manager", "staff_cashier", "waiter")


def _allowed(user):
    return getattr(user, "role", "") in STAFF_ROLES


def _mine(user, pk):
    g = get_object_or_404(QRGuestSession.objects.select_related("table__floor", "pending_order"), pk=pk)
    if user.role != "super_admin" and user.outlet_id and g.table.floor.outlet_id != user.outlet_id:
        return None
    return g


def _ago(dt):
    return max(0, int((timezone.now() - dt).total_seconds() // 60))


@login_required
@require_GET
def guest_requests(request):
    if not _allowed(request.user):
        return JsonResponse({"orders": [], "calls": []})
    orders, calls = guard.pending_requests(request.user)
    out = []
    for g in orders[:20]:
        order = g.pending_order
        items = order.items.filter(kot_sent_at__isnull=True).exclude(status="cancelled")
        out.append({
            "id": g.pk,
            "table": g.table.number,
            "code": g.table.guest_code if guard.code_enabled(g.table) else "",
            "seat": order.party_name,
            "order_number": order.order_number,
            "items": [{"qty": i.quantity, "name": i.item_name} for i in items[:12]],
            "total": str(sum((i.total_price for i in items), 0)),
            "minutes": _ago(g.requested_at),
            "distance_m": g.distance_m,
        })
    return JsonResponse({
        "orders": out,
        "calls": [{"id": g.pk, "table": g.table.number, "minutes": _ago(g.called_at)} for g in calls[:20]],
    })


@login_required
@require_POST
def guest_request_accept(request, pk):
    from apps.ordering.views import send_round

    if not _allowed(request.user):
        return JsonResponse({"error": "Not allowed"}, status=403)
    g = _mine(request.user, pk)
    if g is None:
        return JsonResponse({"error": "Not your outlet"}, status=403)
    with transaction.atomic():
        guard.confirm(g, QRGuestSession.Method.STAFF, user=request.user)
        order = g.pending_order
        if order is not None and order.status in OPEN_STATUSES:
            send_round(order, user=request.user)
        g.requested_at = None
        g.save(update_fields=["requested_at"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def guest_request_reject(request, pk):
    if not _allowed(request.user):
        return JsonResponse({"error": "Not allowed"}, status=403)
    g = _mine(request.user, pk)
    if g is None:
        return JsonResponse({"error": "Not your outlet"}, status=403)
    with transaction.atomic():
        order = g.pending_order
        if order is not None and order.status in OPEN_STATUSES:
            # Drop the held round; cancel the bill if nothing else is on it
            order.items.filter(kot_sent_at__isnull=True).delete()
            if not order.items.exclude(status="cancelled").exists():
                order.update_status(order.Status.CANCELLED, user=request.user)
            else:
                order.calculate_totals()
                order.save()
        g.rejected_at = timezone.now()
        g.save(update_fields=["rejected_at"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def guest_call_done(request, pk):
    if not _allowed(request.user):
        return JsonResponse({"error": "Not allowed"}, status=403)
    g = _mine(request.user, pk)
    if g is None:
        return JsonResponse({"error": "Not your outlet"}, status=403)
    g.called_at = None
    g.save(update_fields=["called_at"])
    return JsonResponse({"ok": True})


@login_required
@require_POST
def table_new_code(request, pk):
    """Give a table a fresh guest code (e.g. if someone overheard it)."""
    from django.contrib import messages
    from django.shortcuts import redirect

    from apps.tables.models import Table

    if not _allowed(request.user):
        return JsonResponse({"error": "Not allowed"}, status=403)
    table = get_object_or_404(Table.objects.select_related("floor"), pk=pk)
    if request.user.role != "super_admin" and request.user.outlet_id and table.floor.outlet_id != request.user.outlet_id:
        return JsonResponse({"error": "Not your outlet"}, status=403)
    code = table.new_guest_code()
    messages.success(request, f"Table {table.number} has a new code: {code}. Phones confirmed before must be confirmed again.")
    back = request.POST.get("next", "")
    return redirect(back if back.startswith("/") else "dashboard:tables")
