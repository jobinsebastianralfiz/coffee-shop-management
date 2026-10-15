"""Printable table QR cards (table tents and stickers)."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.safestring import mark_safe

from apps.core.models import BusinessSettings, Outlet
from apps.payments.services import public_url
from apps.tables.models import Floor, Table
from apps.tables.qr_svg import qr_svg

MANAGER_ROLES = ("super_admin", "outlet_manager")
STYLES = {"tent": "Table tent (A6)", "sticker": "Square sticker (80 mm)"}


def _tables_for(user):
    qs = Table.objects.filter(is_active=True).select_related("floor", "floor__outlet").order_by("floor__display_order", "number")
    if user.role != "super_admin":
        qs = qs.filter(floor__outlet_id=user.outlet_id)
    return qs


@login_required
def table_qr_cards(request):
    if request.user.role not in MANAGER_ROLES:
        messages.error(request, "Only managers can print table QR codes.")
        return redirect("dashboard:home")

    tables = _tables_for(request.user)
    outlet_id = request.GET.get("outlet", "")
    if outlet_id and request.user.role == "super_admin":
        tables = tables.filter(floor__outlet_id=outlet_id)
    floor_id = request.GET.get("floor", "")
    if floor_id:
        tables = tables.filter(floor_id=floor_id)
    all_tables = list(tables)
    picked = request.GET.getlist("t")
    if picked:
        tables = [t for t in all_tables if str(t.pk) in picked]
    else:
        tables = all_tables

    style = request.GET.get("style", "tent")
    if style not in STYLES:
        style = "tent"

    cards = [{"table": t, "url": public_url(request, t.qr_url), "svg": mark_safe(qr_svg(public_url(request, t.qr_url)))} for t in tables]
    floors = Floor.objects.filter(is_active=True).order_by("display_order")
    if request.user.role != "super_admin":
        floors = floors.filter(outlet_id=request.user.outlet_id)
    return render(request, "dashboard/tables/qr_cards.html", {
        "cards": cards,
        "all_tables": all_tables,
        "picked": picked,
        "style": style,
        "styles": STYLES,
        "floors": floors,
        "floor_id": floor_id,
        "outlets": Outlet.objects.filter(is_active=True).order_by("name") if request.user.role == "super_admin" else None,
        "outlet_id": outlet_id,
        "business": BusinessSettings.load(),
        "headline": request.GET.get("headline", "").strip()[:60] or "Scan to see the menu",
        "subline": request.GET.get("subline", "").strip()[:80] or "& order right from your table",
        "wifi_name": request.GET.get("wifi", "").strip()[:40],
        "wifi_pass": request.GET.get("wifipass", "").strip()[:40],
    })


VIEW_ROLES = ("super_admin", "outlet_manager", "staff_cashier", "waiter")


@login_required
def table_qr_card_png(request, pk):
    """Branded table card (A6, 300 dpi PNG) with the table's QR, for download or a print shop."""
    from apps.tables.qr_card import render_table_card

    if request.user.role not in VIEW_ROLES:
        return HttpResponse(status=403)
    table = get_object_or_404(_tables_for(request.user), pk=pk)
    png = render_table_card(table, public_url(request, table.qr_url), BusinessSettings.load())
    resp = HttpResponse(png, content_type="image/png")
    resp["Cache-Control"] = "private, no-cache"
    if request.GET.get("download"):
        resp["Content-Disposition"] = f'attachment; filename="table-{table.number}-qr-card.png"'
    return resp


@login_required
def table_qr_svg(request, pk):
    """The styled QR on its own, for downloading or sending to a print shop."""
    if request.user.role not in VIEW_ROLES:
        return HttpResponse(status=403)
    table = get_object_or_404(_tables_for(request.user), pk=pk)
    resp = HttpResponse(qr_svg(public_url(request, table.qr_url), logo_hole=False), content_type="image/svg+xml")
    if request.GET.get("download"):
        resp["Content-Disposition"] = f'attachment; filename="table-{table.number}-qr.svg"'
    return resp
