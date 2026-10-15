"""
Kitchen Stations setup page: stations, category routing, print agent and
recent print jobs for one outlet.
"""

import ipaddress
import secrets
from functools import wraps
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.core.models import Outlet
from apps.kitchen.models import KitchenStation, PrintAgent, PrintJob
from apps.menu.models import Category

ALLOWED_ROLES = (User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER)


def station_manager_required(view):
    """Super admins and outlet managers only."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.role not in ALLOWED_ROLES:
            messages.error(request, "You don't have permission to manage kitchen stations.")
            return redirect("dashboard:home")
        return view(request, *args, **kwargs)

    return wrapper


def _resolve_outlet(request):
    """Outlet being managed: the manager's own, or ?outlet= for super admins."""
    user = request.user
    if user.role == User.Role.SUPER_ADMIN:
        outlet_id = request.POST.get("outlet") or request.GET.get("outlet")
        qs = Outlet.objects.filter(is_active=True).order_by("name")
        if outlet_id:
            outlet = Outlet.objects.filter(pk=outlet_id).first() if str(outlet_id).isdigit() else None
            if outlet:
                return outlet
        return qs.first()
    return user.outlet


def _back(outlet, request, anchor=""):
    url = reverse("kitchen:stations")
    if request.user.role == User.Role.SUPER_ADMIN and outlet:
        url += f"?outlet={outlet.pk}"
    return redirect(url + (f"#{anchor}" if anchor else ""))


def _int(value, default, lo=None, hi=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    if lo is not None and n < lo:
        n = lo
    if hi is not None and n > hi:
        n = hi
    return n


@station_manager_required
def stations(request):
    outlet = _resolve_outlet(request)
    outlets = None
    if request.user.role == User.Role.SUPER_ADMIN:
        outlets = Outlet.objects.filter(is_active=True).order_by("name")

    context = {
        "page_title": "Kitchen Stations",
        "outlet": outlet,
        "outlets": outlets,
        "paper_widths": KitchenStation.PaperWidth.choices,
    }
    if outlet is None:
        return render(request, "dashboard/kitchen/stations.html", context)

    station_list = list(
        KitchenStation.objects.filter(outlet=outlet).annotate(category_count=Count("categories", distinct=True))
    )
    last_jobs = {}
    for job in PrintJob.objects.filter(outlet=outlet, station__in=station_list).order_by("-created_at")[:200]:
        last_jobs.setdefault(job.station_id, job)
    for st in station_list:
        st.last_job = last_jobs.get(st.pk)

    categories = (
        Category.objects.filter(Q(outlet=outlet) | Q(outlet__isnull=True))
        .select_related("kitchen_station")
        .annotate(
            override_count=Count(
                "items",
                filter=Q(items__kitchen_station__isnull=False),
                distinct=True,
            )
        )
        .order_by("display_order", "name")
    )

    agent = PrintAgent.objects.filter(outlet=outlet).order_by("-is_active", "-last_seen_at", "pk").first()
    server_url = request.build_absolute_uri("/").rstrip("/")
    jobs = (
        PrintJob.objects.filter(outlet=outlet)
        .select_related("station")
        .order_by("-created_at")[:30]
    )

    context.update(
        {
            "stations": station_list,
            "categories": categories,
            "agent": agent,
            "server_url": server_url,
            "run_command": f"python3 kaffero_print_agent.py --server {server_url} --token {agent.token}" if agent else "",
            "jobs": jobs,
            "has_printer_station": any(s.printer_ip for s in station_list),
        }
    )
    return render(request, "dashboard/kitchen/stations.html", context)


@station_manager_required
@require_POST
def station_save(request, pk=None):
    outlet = _resolve_outlet(request)
    if outlet is None:
        messages.error(request, "No outlet selected.")
        return redirect("kitchen:stations")

    station = None
    if pk is not None:
        station = get_object_or_404(KitchenStation, pk=pk, outlet=outlet)

    name = (request.POST.get("name") or "").strip()
    printer_ip = (request.POST.get("printer_ip") or "").strip()
    errors = []
    if not name:
        errors.append("Station name is required.")
    elif len(name) > 60:
        errors.append("Station name must be 60 characters or fewer.")
    else:
        dupes = KitchenStation.objects.filter(outlet=outlet, name__iexact=name)
        if station:
            dupes = dupes.exclude(pk=station.pk)
        if dupes.exists():
            errors.append(f'A station named "{name}" already exists at this outlet.')
    if printer_ip:
        try:
            printer_ip = str(ipaddress.ip_address(printer_ip))
        except ValueError:
            errors.append(f'"{printer_ip}" is not a valid IP address (e.g. 192.168.1.50).')
    port = _int(request.POST.get("printer_port"), 9100)
    if not 1 <= port <= 65535:
        errors.append("Printer port must be between 1 and 65535.")
    paper_width = _int(request.POST.get("paper_width"), KitchenStation.PaperWidth.MM_80)
    if paper_width not in KitchenStation.PaperWidth.values:
        errors.append("Choose a paper width.")

    if errors:
        for e in errors:
            messages.error(request, e)
        return _back(outlet, request, "stations")

    if station is None:
        station = KitchenStation(outlet=outlet)
    station.name = name
    station.printer_ip = printer_ip or None
    station.printer_port = port
    station.paper_width = paper_width
    station.copies = _int(request.POST.get("copies"), 1, 1, 5)
    station.is_default = bool(request.POST.get("is_default"))
    station.is_active = bool(request.POST.get("is_active"))
    station.display_order = _int(request.POST.get("display_order"), 0, 0)
    created = station.pk is None
    station.save()
    messages.success(request, f'Station "{station.name}" {"added" if created else "updated"}.')
    return _back(outlet, request, "stations")


@station_manager_required
@require_POST
def station_delete(request, pk):
    outlet = _resolve_outlet(request)
    station = get_object_or_404(KitchenStation, pk=pk, outlet=outlet)
    name = station.name
    station.delete()
    messages.success(request, f'Station "{name}" deleted. Its categories now go to the default station.')
    return _back(outlet, request, "stations")


@station_manager_required
@require_POST
def station_test_print(request, pk):
    from apps.kitchen.routing import queue_test_print

    outlet = _resolve_outlet(request)
    station = get_object_or_404(KitchenStation, pk=pk, outlet=outlet)
    if not station.printer_ip:
        messages.error(request, f'"{station.name}" has no printer IP. Add one to test printing.')
        return _back(outlet, request, "stations")
    queue_test_print(station)
    agents = PrintAgent.objects.filter(outlet=outlet, is_active=True)
    if any(a.is_online for a in agents):
        messages.success(request, f'Test ticket sent to "{station.name}". It should print in a few seconds.')
    else:
        messages.warning(
            request,
            f'Test ticket queued for "{station.name}". It will print once the print agent is running at the outlet.',
        )
    return _back(outlet, request, "jobs")


@station_manager_required
@require_POST
def routing_save(request):
    outlet = _resolve_outlet(request)
    if outlet is None:
        return redirect("kitchen:stations")
    valid = {str(s.pk): s for s in KitchenStation.objects.filter(outlet=outlet)}
    changed = 0
    for cat in Category.objects.filter(Q(outlet=outlet) | Q(outlet__isnull=True)):
        key = f"station_{cat.pk}"
        if key not in request.POST:
            continue
        value = request.POST.get(key) or ""
        new_station = valid.get(value)
        if cat.kitchen_station_id != (new_station.pk if new_station else None):
            cat.kitchen_station = new_station
            cat.save(update_fields=["kitchen_station", "updated_at"])
            changed += 1
    messages.success(request, f"Routing saved ({changed} categor{'y' if changed == 1 else 'ies'} changed).")
    return _back(outlet, request, "routing")


@station_manager_required
@require_POST
def agent_create(request):
    outlet = _resolve_outlet(request)
    if outlet is None:
        return redirect("kitchen:stations")
    if PrintAgent.objects.filter(outlet=outlet).exists():
        messages.info(request, "This outlet already has a print agent.")
    else:
        PrintAgent.objects.create(outlet=outlet, created_by=request.user)
        messages.success(request, "Print agent created. Follow the steps below to start it.")
    return _back(outlet, request, "agent")


@station_manager_required
@require_POST
def agent_regenerate(request, pk):
    outlet = _resolve_outlet(request)
    agent = get_object_or_404(PrintAgent, pk=pk, outlet=outlet)
    agent.token = secrets.token_urlsafe(32)
    agent.save(update_fields=["token"])
    messages.success(request, "New token generated. Restart the print agent with the new command.")
    return _back(outlet, request, "agent")


@station_manager_required
def agent_download(request):
    path = Path(settings.BASE_DIR) / "print_agent" / "kaffero_print_agent.py"
    if not path.is_file():
        raise Http404("Print agent script not found")
    return FileResponse(
        open(path, "rb"),
        as_attachment=True,
        filename="kaffero_print_agent.py",
        content_type="text/x-python",
    )


@station_manager_required
@require_POST
def job_retry(request, pk):
    outlet = _resolve_outlet(request)
    job = get_object_or_404(PrintJob, pk=pk, outlet=outlet)
    if job.status in (PrintJob.Status.FAILED, PrintJob.Status.CANCELLED):
        job.status = PrintJob.Status.QUEUED
        job.attempts = 0
        job.last_error = ""
        job.claimed_by = None
        job.claimed_at = None
        job.save(update_fields=["status", "attempts", "last_error", "claimed_by", "claimed_at"])
        messages.success(request, f'"{job.title or "Print job"}" queued again.')
    else:
        messages.info(request, "Only failed or cancelled jobs can be retried.")
    return _back(outlet, request, "jobs")


@station_manager_required
@require_POST
def job_cancel(request, pk):
    outlet = _resolve_outlet(request)
    job = get_object_or_404(PrintJob, pk=pk, outlet=outlet)
    if job.status in (PrintJob.Status.QUEUED, PrintJob.Status.FAILED):
        job.status = PrintJob.Status.CANCELLED
        job.save(update_fields=["status"])
        messages.success(request, f'"{job.title or "Print job"}" cancelled.')
    else:
        messages.info(request, "Only queued or failed jobs can be cancelled.")
    return _back(outlet, request, "jobs")
