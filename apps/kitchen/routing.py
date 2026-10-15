"""
Kitchen station routing: split an order into per-station tickets and queue them
for the outlet's print agent.

Routing order for each item: the item's own station, then its category's station,
then the outlet's default station. Items with no station fall back to the legacy
single KOT printer in PrinterSettings (if enabled), so outlets without stations
keep working.
"""

import base64
import logging
from collections import OrderedDict

from django.db import transaction
from django.utils import timezone

from apps.kitchen.models import KitchenStation, PrintJob

logger = logging.getLogger(__name__)


def order_outlet(order):
    """Outlet an order belongs to (orders created before outlets existed may lack one)."""
    if order.outlet_id:
        return order.outlet
    table = order.table
    if table and table.floor_id and table.floor.outlet_id:
        return table.floor.outlet
    if order.created_by_id and getattr(order.created_by, "outlet_id", None):
        return order.created_by.outlet
    return None


def station_for_item(item, outlet, default_station=None):
    """Station that prepares an order item, or None if nothing is routed."""
    menu_item = item.menu_item
    if menu_item is not None:
        for station in (menu_item.kitchen_station, menu_item.category.kitchen_station if menu_item.category_id else None):
            if station is not None and station.is_active and (outlet is None or station.outlet_id == outlet.pk):
                return station
    return default_station


def build_kot(order, items, station_name="", width=48, is_addition=False, reprint=False):
    """ESC/POS bytes for one station's kitchen ticket."""
    from apps.printing.escpos import KOTBuilder

    b = KOTBuilder(width=width)
    b.init()
    b.align_center()
    b.double_size()
    b.bold_on()
    b.line((station_name or "KITCHEN").upper()[: width // 2])
    b.normal_size()
    if is_addition:
        b.line("** ADDITIONAL ITEMS **")
    if reprint:
        b.line("** REPRINT **")
    b.bold_off()
    b.align_left()
    b.horizontal_line()

    ticket = getattr(order, "kitchen_ticket", None)
    b.bold_on()
    b.line(f"Order: #{order.order_number}" + (f"   KOT {ticket.ticket_number}" if ticket else ""))
    if order.table_id:
        tables = order.all_table_numbers or str(order.table.number)
        where = f"Table {tables}"
        if order.party_name:
            where += f" - {order.party_name}"
    else:
        where = f"{order.get_order_type_display()}" + (f" - {order.customer_name}" if order.customer_name else "")
    b.line(where[:width])
    if ticket and ticket.priority and ticket.priority != "normal":
        b.double_size()
        b.line(f"!! {ticket.priority.upper()} !!")
        b.normal_size()
    b.bold_off()
    b.horizontal_line()

    b.double_height()
    for item in items:
        name = item.item_name + (f" ({item.variant_name})" if item.variant_name else "")
        seat = f" [S{item.seat_number}]" if item.seat_number else ""
        b.line(f"{item.quantity} x {name}{seat}")
        b.normal_size()
        for addon in item.addons or []:
            label = addon.get("name") if isinstance(addon, dict) else str(addon)
            if label:
                b.line(f"    + {label}")
        if item.special_instructions:
            b.line(f"    >> {item.special_instructions}")
        b.double_height()
    b.normal_size()

    if order.kitchen_notes:
        b.horizontal_line()
        b.bold_on()
        b.line("NOTE:")
        b.bold_off()
        b.line(order.kitchen_notes)

    b.horizontal_line()
    b.align_center()
    by = order.created_by.get_full_name() if order.created_by_id else ""
    b.line(timezone.localtime().strftime("%d/%m/%Y %H:%M") + (f"  {by}" if by else ""))
    b.cut()
    return b.get_data()


def _queue(outlet, order, title, printer_ip, printer_port, copies, data, station=None, kind=PrintJob.Kind.KOT):
    return PrintJob.objects.create(
        outlet=outlet,
        station=station,
        order=order,
        kind=kind,
        title=title[:120],
        printer_ip=printer_ip,
        printer_port=printer_port,
        copies=max(1, copies),
        payload=base64.b64encode(data).decode("ascii"),
    )


def dispatch_kitchen_tickets(order):
    """
    Route the order's not-yet-sent items to their stations and queue one ticket per
    station. Safe to call repeatedly: items already sent are skipped, so sending
    an order again only prints the newly added items.

    Returns the list of PrintJobs queued.
    """
    from apps.core.models import PrinterSettings
    from apps.orders.models import OrderItem

    outlet = order_outlet(order)
    jobs = []

    with transaction.atomic():
        items = list(
            order.items.select_for_update(of=("self",))
            .filter(kot_sent_at__isnull=True)
            .exclude(status=OrderItem.Status.CANCELLED)
            .select_related("menu_item__kitchen_station", "menu_item__category__kitchen_station")
        )
        if not items:
            return jobs

        is_addition = order.items.filter(kot_sent_at__isnull=False).exists()
        default_station = None
        if outlet is not None:
            default_station = KitchenStation.objects.filter(outlet=outlet, is_active=True, is_default=True).first()

        groups = OrderedDict()  # station (or None) -> items
        for item in items:
            station = station_for_item(item, outlet, default_station)
            item.station = station
            groups.setdefault(station, []).append(item)

        now = timezone.now()
        for item in items:
            item.kot_sent_at = now
        OrderItem.objects.bulk_update(items, ["station", "kot_sent_at"])

        if outlet is None:
            logger.warning("Order %s has no outlet; kitchen tickets not queued", order.pk)
            return jobs

        title_base = f"#{order.order_number}" + (f" T{order.table.number}" if order.table_id else "")
        for station, station_items in groups.items():
            if station is not None:
                if not station.has_printer:
                    continue  # display-only station
                data = build_kot(order, station_items, station.name, station.paper_width, is_addition)
                jobs.append(_queue(outlet, order, f"{station.name} {title_base}", station.printer_ip,
                                   station.printer_port, station.copies, data, station=station))
            else:
                legacy = PrinterSettings.load()
                if legacy.kot_printer_enabled and legacy.kot_auto_print and legacy.kot_printer_ip:
                    data = build_kot(order, station_items, "Kitchen", 32, is_addition)
                    jobs.append(_queue(outlet, order, f"Kitchen {title_base}", legacy.kot_printer_ip, 9100, 1, data))

        ticket = getattr(order, "kitchen_ticket", None)
        if jobs and ticket is not None and not ticket.printed_at:
            ticket.printed_at = now
            ticket.save(update_fields=["printed_at"])

    return jobs


def reprint_order(order, station=None):
    """Queue a fresh copy of an order's tickets (all stations, or one)."""
    from apps.orders.models import OrderItem

    outlet = order_outlet(order)
    if outlet is None:
        return []
    items = order.items.filter(kot_sent_at__isnull=False).exclude(status=OrderItem.Status.CANCELLED).select_related("station")
    if station is not None:
        items = items.filter(station=station)
    groups = OrderedDict()
    for item in items:
        if item.station_id and item.station.has_printer:
            groups.setdefault(item.station, []).append(item)
    jobs = []
    for st, st_items in groups.items():
        data = build_kot(order, st_items, st.name, st.paper_width, reprint=True)
        jobs.append(_queue(outlet, order, f"{st.name} #{order.order_number} (reprint)", st.printer_ip,
                           st.printer_port, 1, data, station=st))
    return jobs


def queue_test_print(station):
    """Queue a short test ticket for a station's printer."""
    from apps.printing.escpos import KOTBuilder

    b = KOTBuilder(width=station.paper_width)
    b.init()
    b.align_center()
    b.double_size()
    b.bold_on()
    b.line(station.name.upper()[: station.paper_width // 2])
    b.normal_size()
    b.bold_off()
    b.line("Test print")
    b.line(timezone.localtime().strftime("%d/%m/%Y %H:%M"))
    b.line(f"{station.printer_ip}:{station.printer_port}")
    b.line("If you can read this, tickets for")
    b.line(f"{station.name} will print here.")
    b.cut()
    return _queue(station.outlet, None, f"Test {station.name}", station.printer_ip, station.printer_port, 1,
                  b.get_data(), station=station, kind=PrintJob.Kind.TEST)


# ---------------------------------------------------------------------------
# Running tab: more rounds, voids and parcels
# ---------------------------------------------------------------------------

# Orders that can still take items (until paid or cancelled)
OPEN_STATUSES = ("pending", "confirmed", "preparing", "ready", "served")


def send_order_to_kitchen(order, user=None):
    """
    Send an order's unsent items to the kitchen. Used for the first round and
    every later one, from the dashboard, waiter app and QR menu.

    - pending order: becomes confirmed (the normal first send)
    - ready/served order getting a new round: goes back to confirmed so the
      kitchen sees it again; items already served are marked served
    - confirmed/preparing order: keeps its status, new items join it

    Tickets are queued after the transaction commits. Returns the number of
    items sent.
    """
    from apps.orders.models import Order, OrderItem
    from apps.orders.signals import queue_station_tickets

    unsent = order.items.filter(kot_sent_at__isnull=True).exclude(status=OrderItem.Status.CANCELLED)
    count = unsent.count()
    if not count:
        return 0

    if order.status in (Order.Status.READY, Order.Status.SERVED):
        # Earlier rounds have left the kitchen: record them as served
        order.items.filter(kot_sent_at__isnull=False).exclude(
            status__in=[OrderItem.Status.CANCELLED, OrderItem.Status.SERVED]
        ).update(status=OrderItem.Status.SERVED)
        order.update_status(Order.Status.CONFIRMED, user=user)
    elif order.status == Order.Status.PENDING:
        order.update_status(Order.Status.CONFIRMED, user=user)

    queue_station_tickets(order)
    return count


def _small_ticket(order, station, heading, lines, width):
    from apps.printing.escpos import KOTBuilder

    b = KOTBuilder(width=width)
    b.init()
    b.align_center()
    b.double_size()
    b.bold_on()
    b.line(heading[: width // 2])
    b.normal_size()
    b.line((station.name if station else "Kitchen").upper())
    b.bold_off()
    b.align_left()
    b.horizontal_line()
    where = f"Table {order.all_table_numbers}" if order.table_id else order.get_order_type_display()
    if order.party_name:
        where += f" - {order.party_name}"
    b.bold_on()
    b.line(f"Order: #{order.order_number}")
    b.line(where[:width])
    b.bold_off()
    b.horizontal_line()
    b.double_height()
    for text in lines:
        b.line(text[:width])
    b.normal_size()
    b.horizontal_line()
    b.align_center()
    b.line(timezone.localtime().strftime("%d/%m/%Y %H:%M"))
    b.cut()
    return b.get_data()


def _station_target(order, station):
    """Printer for a station, or the legacy single KOT printer as a fallback."""
    from apps.core.models import PrinterSettings

    if station is not None and station.has_printer:
        return station.printer_ip, station.printer_port, station.paper_width
    if station is None:
        legacy = PrinterSettings.load()
        if legacy.kot_printer_enabled and legacy.kot_printer_ip:
            return legacy.kot_printer_ip, 9100, 32
    return None


def queue_void_ticket(item, reason=""):
    """Tell the item's station to stop making a voided item."""
    order = item.order
    outlet = order_outlet(order)
    target = _station_target(order, item.station)
    if outlet is None or target is None:
        return None
    ip, port, width = target
    name = item.item_name + (f" ({item.variant_name})" if item.variant_name else "")
    lines = [f"{item.quantity} x {name}"]
    if reason:
        lines.append(f"Reason: {reason}")
    data = _small_ticket(order, item.station, "** CANCELLED **", lines, width)
    return _queue(outlet, order, f"Cancel {name} #{order.order_number}", ip, port, 1, data, station=item.station)


def queue_parcel_tickets(order, items, note=""):
    """Ask the kitchen to pack leftovers: one PARCEL ticket per station."""
    outlet = order_outlet(order)
    if outlet is None:
        return []
    groups = OrderedDict()
    for item in items:
        groups.setdefault(item.station, []).append(item)
    jobs = []
    for station, st_items in groups.items():
        target = _station_target(order, station)
        if target is None:
            continue
        ip, port, width = target
        lines = [f"{i.quantity} x {i.item_name}" + (f" ({i.variant_name})" if i.variant_name else "") for i in st_items]
        if note:
            lines.append(f">> {note}")
        data = _small_ticket(order, station, "** PARCEL **", lines, width)
        jobs.append(_queue(outlet, order, f"Parcel #{order.order_number}", ip, port, 1, data, station=station))
    return jobs
