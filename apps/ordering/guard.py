"""
Table presence check for QR ordering.

The printed QR only holds the table's id, so a photo of it works from anywhere.
Before a guest phone's first order goes to the kitchen, the phone must be
confirmed to be at the table:

- by location, when the outlet has a map location set and the guest shares
  theirs (within `qr_radius_m`),
- by the table code, a 4-digit number staff tell the guests (it changes every
  time the table is freed), or
- by a staff member, who sees the request on the dashboard / waiter app and
  taps "Guest is here".

A confirmation lasts for the current seating: it ends when the table is freed
(Table.guests_reset_at) or after CONFIRM_HOURS. Later rounds from a confirmed
phone go straight through. Everything is also rate limited.
"""

import math
from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone

from apps.ordering.models import QRGuestSession

CONFIRM_HOURS = 5
REQUEST_MINUTES = 30  # an unanswered request expires after this
MAX_QTY_PER_LINE = 20
MAX_ITEMS_PER_ROUND = 60
MAX_WAITING_PER_TABLE = 3  # unconfirmed phones waiting at one table


def outlet_of(table):
    return getattr(table.floor, "outlet", None)


def mode(table):
    outlet = outlet_of(table)
    value = getattr(outlet, "qr_guard", "location_or_staff") or "location_or_staff"
    return value


def location_enabled(table):
    outlet = outlet_of(table)
    return (
        mode(table) == "location_or_staff"
        and outlet is not None
        and outlet.latitude is not None
        and outlet.longitude is not None
    )


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() or request.META.get("REMOTE_ADDR")) or None


def guest(request, table, create=True):
    """This phone's guest session at the table."""
    if not request.session.session_key:
        if not create:
            return None
        request.session.save()
    key = request.session.session_key
    if not create:
        return QRGuestSession.objects.filter(table=table, session_key=key).first()
    g, _ = QRGuestSession.objects.get_or_create(
        table=table,
        session_key=key,
        defaults={"ip_address": _client_ip(request), "user_agent": request.META.get("HTTP_USER_AGENT", "")[:200]},
    )
    return g


def is_confirmed(g, table):
    if mode(table) == "off":
        return True
    if g is None or g.verified_at is None:
        return False
    if table.guests_reset_at and g.verified_at < table.guests_reset_at:
        return False
    return timezone.now() - g.verified_at < timedelta(hours=CONFIRM_HOURS)


def distance_m(lat1, lng1, lat2, lng2):
    """Great-circle distance in metres."""
    r = 6371000
    p1, p2 = math.radians(float(lat1)), math.radians(float(lat2))
    dp = p2 - p1
    dl = math.radians(float(lng2) - float(lng1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return int(2 * r * math.asin(math.sqrt(a)))


def check_location(g, table, lat, lng, accuracy=None):
    """Confirm the phone if it is near the outlet. Returns True when confirmed."""
    if not location_enabled(table):
        return False
    try:
        lat, lng = float(lat), float(lng)
        accuracy = float(accuracy) if accuracy not in (None, "") else 0.0
    except (TypeError, ValueError):
        return False
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return False
    outlet = outlet_of(table)
    dist = distance_m(outlet.latitude, outlet.longitude, lat, lng)
    g.distance_m = min(dist, 2_000_000_000)
    # A very rough fix (e.g. 2 km accuracy) can't prove the guest is inside
    near = dist <= outlet.qr_radius_m and accuracy <= max(outlet.qr_radius_m * 2, 300)
    if near:
        confirm(g, QRGuestSession.Method.LOCATION)
    else:
        g.save(update_fields=["distance_m"])
    return near


def code_enabled(table):
    return mode(table) in ("location_or_staff", "code")


def check_code(g, table, code):
    """Confirm the phone if it entered the table's current code."""
    import hmac

    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    if not code_enabled(table) or len(code) != 4 or not table.guest_code:
        return False
    if hmac.compare_digest(code, table.guest_code):
        confirm(g, QRGuestSession.Method.CODE)
        return True
    return False


def confirm(g, method, user=None):
    g.verified_at = timezone.now()
    g.method = method
    g.verified_by = user
    g.rejected_at = None
    g.save(update_fields=["verified_at", "method", "verified_by", "rejected_at", "distance_m"])


def waiting_count(table, exclude=None):
    qs = QRGuestSession.objects.filter(
        table=table,
        requested_at__gte=timezone.now() - timedelta(minutes=REQUEST_MINUTES),
        verified_at__isnull=True,
        rejected_at__isnull=True,
    )
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs.count()


def request_staff(g, order):
    """Hold this round until a staff member confirms the guest is at the table."""
    g.pending_order = order
    g.requested_at = timezone.now()
    g.rejected_at = None
    g.save(update_fields=["pending_order", "requested_at", "rejected_at"])


def is_waiting(g):
    return bool(
        g
        and g.requested_at
        and g.verified_at is None
        and g.rejected_at is None
        and timezone.now() - g.requested_at < timedelta(minutes=REQUEST_MINUTES)
    )


def throttle(key, limit, seconds):
    """True when `key` has been used `limit` times in the window (and counts this use)."""
    full = f"qrg:{key}"
    added = cache.add(full, 1, seconds)
    if added:
        return False
    try:
        count = cache.incr(full)
    except ValueError:
        cache.set(full, 1, seconds)
        return False
    return count > limit


def pending_requests(user):
    """Open 'is the guest at the table?' requests and waiter calls for a staff member's outlet."""
    from apps.kitchen.routing import OPEN_STATUSES

    since = timezone.now() - timedelta(minutes=REQUEST_MINUTES)
    base = QRGuestSession.objects.select_related("table", "table__floor", "pending_order")
    outlet_id = getattr(user, "outlet_id", None)
    if outlet_id and getattr(user, "role", "") != "super_admin":
        base = base.filter(table__floor__outlet_id=outlet_id)
    orders = base.filter(
        requested_at__gte=since,
        verified_at__isnull=True,
        rejected_at__isnull=True,
        pending_order__status__in=OPEN_STATUSES,
    ).order_by("requested_at")
    calls = base.filter(called_at__gte=since).order_by("called_at")
    return orders, calls
