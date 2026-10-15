"""
API for the outlet print agent (print_agent/kaffero_print_agent.py).

The agent authenticates with its token (Authorization: Token <token>), polls for
queued kitchen tickets, sends them to the Wi-Fi printers on the restaurant
network and reports the result. A ticket that is claimed but never reported
(agent crashed, network dropped) goes back to the queue after CLAIM_TIMEOUT.
"""

import json
from datetime import timedelta

from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.kitchen.models import PrintAgent, PrintJob

CLAIM_TIMEOUT = timedelta(seconds=90)
BATCH_SIZE = 10


def _agent_from_request(request):
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Token "):
        return None
    token = header[len("Token "):].strip()
    if not token:
        return None
    return PrintAgent.objects.select_related("outlet").filter(token=token, is_active=True).first()


def _client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None


@csrf_exempt
@require_POST
def agent_poll(request):
    """Claim the next queued tickets for this agent's outlet."""
    agent = _agent_from_request(request)
    if agent is None:
        return JsonResponse({"error": "Invalid or inactive print agent token"}, status=401)

    now = timezone.now()
    PrintAgent.objects.filter(pk=agent.pk).update(last_seen_at=now, last_seen_ip=_client_ip(request))

    with transaction.atomic():
        # Requeue tickets claimed earlier but never reported
        PrintJob.objects.filter(
            outlet=agent.outlet, status=PrintJob.Status.SENDING, claimed_at__lt=now - CLAIM_TIMEOUT
        ).update(status=PrintJob.Status.QUEUED)

        # Failed tickets are queued again with claimed_at set; wait before retrying
        candidates = (
            PrintJob.objects.select_for_update()
            .filter(outlet=agent.outlet, status=PrintJob.Status.QUEUED)
            .order_by("created_at")[: BATCH_SIZE * 5]
        )
        jobs = [
            job for job in candidates
            if job.claimed_at is None or job.claimed_at + PrintJob.retry_delay(job.attempts) <= now
        ][:BATCH_SIZE]
        for job in jobs:
            job.status = PrintJob.Status.SENDING
            job.claimed_by = agent
            job.claimed_at = now
            job.attempts += 1
        PrintJob.objects.bulk_update(jobs, ["status", "claimed_by", "claimed_at", "attempts"])

    return JsonResponse({
        "jobs": [
            {
                "id": job.pk,
                "title": job.title,
                "printer_ip": job.printer_ip,
                "printer_port": job.printer_port,
                "copies": job.copies,
                "payload": job.payload,
            }
            for job in jobs
        ]
    })


@csrf_exempt
@require_POST
def agent_report(request, job_id):
    """Record whether a claimed ticket printed."""
    agent = _agent_from_request(request)
    if agent is None:
        return JsonResponse({"error": "Invalid or inactive print agent token"}, status=401)

    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    job = PrintJob.objects.filter(pk=job_id, outlet=agent.outlet).first()
    if job is None:
        return JsonResponse({"error": "Job not found"}, status=404)
    if job.status != PrintJob.Status.SENDING:
        return JsonResponse({"ok": True, "status": job.status})  # already settled

    if body.get("ok"):
        job.status = PrintJob.Status.PRINTED
        job.printed_at = timezone.now()
        job.last_error = ""
    else:
        job.last_error = str(body.get("error") or "Unknown printer error")[:255]
        job.status = PrintJob.Status.FAILED if job.attempts >= PrintJob.MAX_ATTEMPTS else PrintJob.Status.QUEUED
        job.claimed_at = timezone.now()  # retry clock starts now
    job.save(update_fields=["status", "printed_at", "last_error", "claimed_at"])
    return JsonResponse({"ok": True, "status": job.status})
