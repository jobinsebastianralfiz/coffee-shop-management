"""
Table management models for the Coffee Shop Management System.
"""

import uuid

from django.conf import settings
from django.db import models


class Floor(models.Model):
    """
    Floor/section of the restaurant (e.g., Main Floor, Outdoor, Rooftop).
    Each floor belongs to a specific outlet.
    """

    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="floors",
        null=True,
        blank=True,
        help_text="Outlet this floor belongs to",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Floor"
        verbose_name_plural = "Floors"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name

    @property
    def table_count(self):
        """Get total number of tables on this floor."""
        return self.tables.count()

    @property
    def available_tables(self):
        """Get number of vacant tables."""
        return self.tables.filter(status=Table.Status.VACANT).count()


class Table(models.Model):
    """
    Restaurant tables with status tracking and QR code support.
    """

    class Status(models.TextChoices):
        VACANT = "vacant", "Vacant"
        OCCUPIED = "occupied", "Occupied"
        BILLED = "billed", "Billed"
        CLEANING = "cleaning", "Cleaning"
        RESERVED = "reserved", "Reserved"

    class TableType(models.TextChoices):
        TWO_SEATER = "2_seater", "2 Seater"
        FOUR_SEATER = "4_seater", "4 Seater"
        SIX_SEATER = "6_seater", "6 Seater"
        EIGHT_SEATER = "8_seater", "8 Seater"
        BOOTH = "booth", "Booth"
        ROUND = "round", "Round"
        BAR = "bar", "Bar Stool"

    floor = models.ForeignKey(
        Floor,
        on_delete=models.CASCADE,
        related_name="tables",
    )
    number = models.CharField(
        max_length=10,
        help_text="Table number (e.g., T1, T2, A1)",
    )
    name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Optional custom name (e.g., Window Seat)",
    )
    capacity = models.PositiveIntegerField(
        help_text="Maximum seating capacity",
    )
    table_type = models.CharField(
        max_length=20,
        choices=TableType.choices,
        default=TableType.FOUR_SEATER,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.VACANT,
    )

    # QR Code
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
    )
    qr_code = models.ImageField(
        upload_to="qr_codes/",
        null=True,
        blank=True,
    )

    # Floor map positioning
    position_x = models.PositiveIntegerField(default=0)
    position_y = models.PositiveIntegerField(default=0)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Table"
        verbose_name_plural = "Tables"
        unique_together = ["floor", "number"]
        ordering = ["floor", "number"]

    def __str__(self):
        return f"{self.number} ({self.floor.name})"

    @property
    def display_name(self):
        """Get display name (custom name or number)."""
        return self.name or self.number

    @property
    def qr_url(self):
        """Get QR code URL for customer ordering."""
        return f"/order/t/{self.uuid}/"

    @property
    def current_session(self):
        """Get the current active session for this table."""
        return self.sessions.filter(is_active=True).first()

    def set_status(self, status):
        """Update table status."""
        self.status = status
        self.save(update_fields=["status", "updated_at"])

    def clean(self):
        """Validate table creation against plan limits."""
        from django.conf import settings as django_settings
        from django.core.exceptions import ValidationError

        max_tables = getattr(django_settings, "MAX_TABLES_PER_OUTLET", 0)

        # 0 means unlimited
        if max_tables == 0:
            return

        # Check if this is a new table (no pk yet)
        if not self.pk and self.floor and self.floor.outlet:
            outlet = self.floor.outlet
            current_count = Table.objects.filter(floor__outlet=outlet).count()
            if current_count >= max_tables:
                plan_name = getattr(django_settings, "PLAN_NAME", "current")
                raise ValidationError(
                    f"Cannot create more tables. Your {plan_name} plan allows maximum {max_tables} table(s) per outlet. "
                    f"Contact your vendor to upgrade."
                )

    def save(self, *args, **kwargs):
        """Save with validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def can_create_table(cls, outlet):
        """Check if more tables can be created for the given outlet based on plan limits."""
        from django.conf import settings as django_settings

        max_tables = getattr(django_settings, "MAX_TABLES_PER_OUTLET", 0)
        if max_tables == 0:  # Unlimited
            return True
        return cls.objects.filter(floor__outlet=outlet).count() < max_tables

    @classmethod
    def tables_remaining(cls, outlet):
        """Get number of tables that can still be created for the given outlet."""
        from django.conf import settings as django_settings

        max_tables = getattr(django_settings, "MAX_TABLES_PER_OUTLET", 0)
        if max_tables == 0:  # Unlimited
            return float("inf")
        return max(0, max_tables - cls.objects.filter(floor__outlet=outlet).count())

    @classmethod
    def get_max_tables(cls):
        """Get the maximum tables allowed per outlet from plan settings."""
        from django.conf import settings as django_settings

        return getattr(django_settings, "MAX_TABLES_PER_OUTLET", 0)


class TableSession(models.Model):
    """
    Track customer sessions at tables.
    A session starts when customers are seated and ends when they pay and leave.
    """

    table = models.ForeignKey(
        Table,
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    waiter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="table_sessions",
    )

    # Customer info (optional)
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=15, blank=True)
    guest_count = models.PositiveIntegerField(default=1)

    # Session timing
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Table Session"
        verbose_name_plural = "Table Sessions"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.table.number} - {self.started_at.strftime('%Y-%m-%d %H:%M')}"

    @property
    def duration_minutes(self):
        """Calculate session duration in minutes."""
        from django.utils import timezone

        end_time = self.ended_at or timezone.now()
        delta = end_time - self.started_at
        return int(delta.total_seconds() / 60)

    def end_session(self):
        """End the current session."""
        from django.utils import timezone

        self.ended_at = timezone.now()
        self.is_active = False
        self.save(update_fields=["ended_at", "is_active"])

        # Update table status
        self.table.set_status(Table.Status.CLEANING)
