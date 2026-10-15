"""
Kitchen stations and the kitchen-ticket print queue.

A station is a preparation area (Grill, Broast, Bar...) with its own Wi-Fi
printer and its own kitchen display. Menu categories (and, optionally,
individual items) are routed to a station; when an order is sent to the
kitchen, each station gets a ticket with only its own items.

Printers sit on the restaurant's local network, which a hosted server cannot
reach, so tickets are queued as PrintJobs and a small print agent running at
the outlet (print_agent/kaffero_print_agent.py) fetches and prints them.
"""

import secrets

from django.conf import settings
from django.db import models


class KitchenStation(models.Model):
    """A preparation area with its own printer and kitchen display."""

    class PaperWidth(models.IntegerChoices):
        MM_58 = 32, "58 mm (32 characters)"
        MM_80 = 48, "80 mm (48 characters)"

    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="kitchen_stations",
    )
    name = models.CharField(max_length=60, help_text="e.g. Grill, Broast, Bar")
    printer_ip = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="Wi-Fi printer address on the restaurant network. Leave empty for display only.",
    )
    printer_port = models.PositiveIntegerField(default=9100)
    paper_width = models.PositiveSmallIntegerField(
        choices=PaperWidth.choices,
        default=PaperWidth.MM_80,
    )
    copies = models.PositiveSmallIntegerField(default=1)
    is_default = models.BooleanField(
        default=False,
        help_text="Receives items whose category has no station.",
    )
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["outlet", "display_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["outlet", "name"], name="unique_station_name_per_outlet"),
        ]

    def __str__(self):
        return f"{self.name} ({self.outlet.code})" if self.outlet_id else self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Only one default station per outlet
        if self.is_default:
            KitchenStation.objects.filter(outlet=self.outlet, is_default=True).exclude(pk=self.pk).update(
                is_default=False
            )

    @property
    def has_printer(self):
        return bool(self.printer_ip)


class PrintAgent(models.Model):
    """A print agent installed at an outlet; authenticates with its token."""

    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="print_agents",
    )
    name = models.CharField(max_length=60, default="Kitchen print agent")
    token = models.CharField(max_length=64, unique=True, editable=False)
    is_active = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_seen_ip = models.GenericIPAddressField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["outlet", "name"]

    def __str__(self):
        return f"{self.name} ({self.outlet.code})"

    def save(self, *args, **kwargs):
        if not self.token:
            self.token = secrets.token_urlsafe(32)
        super().save(*args, **kwargs)

    @property
    def is_online(self):
        """Seen in the last minute (the agent polls every few seconds)."""
        from datetime import timedelta

        from django.utils import timezone

        return bool(self.last_seen_at and timezone.now() - self.last_seen_at < timedelta(minutes=1))


class PrintJob(models.Model):
    """One ticket waiting to be printed by an outlet's print agent."""

    class Kind(models.TextChoices):
        KOT = "kot", "Kitchen ticket"
        TEST = "test", "Test print"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        SENDING = "sending", "Sending"
        PRINTED = "printed", "Printed"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"

    # Failed sends are retried with a growing wait (see retry_delay), so a printer
    # that is off or out of paper for ~15 minutes still gets its tickets.
    MAX_ATTEMPTS = 20

    @staticmethod
    def retry_delay(attempts):
        from datetime import timedelta

        return timedelta(seconds=min(60, 10 * max(1, attempts)))

    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="print_jobs",
    )
    station = models.ForeignKey(
        KitchenStation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="print_jobs",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="print_jobs",
    )
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.KOT)
    title = models.CharField(max_length=120, blank=True)

    # Destination is copied from the station when queued, so editing a station
    # later does not redirect tickets already in the queue.
    printer_ip = models.GenericIPAddressField()
    printer_port = models.PositiveIntegerField(default=9100)
    copies = models.PositiveSmallIntegerField(default=1)

    # Raw ESC/POS bytes, base64-encoded
    payload = models.TextField()

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True)
    claimed_by = models.ForeignKey(
        PrintAgent,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)
    printed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["outlet", "status", "created_at"])]

    def __str__(self):
        return f"{self.get_kind_display()} {self.title} [{self.status}]"
