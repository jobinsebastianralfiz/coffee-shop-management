"""
User and authentication models for the Coffee Shop Management System.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model with role-based access control.

    Roles:
    - super_admin: Full access to everything (Owner/GM)
    - staff_cashier: Orders, payments, limited reports
    - staff_kitchen: Order viewing & status update only (KDS)
    - waiter: Tables, orders (create/view), menu
    """

    # Outlet assignment
    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.PROTECT,
        related_name="staff",
        null=True,
        blank=True,
        help_text="Outlet this staff member is assigned to",
    )

    class Role(models.TextChoices):
        SUPER_ADMIN = "super_admin", "Super Admin"
        STAFF_CASHIER = "staff_cashier", "Cashier"
        STAFF_KITCHEN = "staff_kitchen", "Kitchen Staff"
        WAITER = "waiter", "Waiter"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.WAITER,
        help_text="User role determines access permissions",
    )
    phone = models.CharField(
        max_length=15,
        unique=True,
        null=True,
        blank=True,
        help_text="Phone number for login and notifications",
    )
    pin = models.CharField(
        max_length=6,
        null=True,
        blank=True,
        help_text="4-6 digit PIN for quick login",
    )
    employee_id = models.CharField(
        max_length=20,
        unique=True,
        null=True,
        blank=True,
        help_text="Unique employee identifier",
    )
    profile_photo = models.ImageField(
        upload_to="profiles/",
        null=True,
        blank=True,
    )
    is_on_duty = models.BooleanField(
        default=False,
        help_text="Whether the staff member is currently on duty",
    )
    current_shift = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        help_text="Current shift: morning, evening, night",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"

    @property
    def is_admin(self):
        """Check if user has admin role."""
        return self.role == self.Role.SUPER_ADMIN

    @property
    def is_cashier(self):
        """Check if user has cashier role."""
        return self.role == self.Role.STAFF_CASHIER

    @property
    def is_kitchen(self):
        """Check if user has kitchen staff role."""
        return self.role == self.Role.STAFF_KITCHEN

    @property
    def is_waiter(self):
        """Check if user has waiter role."""
        return self.role == self.Role.WAITER

    @classmethod
    def can_create_user(cls):
        """Check if more users can be created based on plan limits."""
        from django.conf import settings as django_settings

        max_users = getattr(django_settings, "MAX_STAFF_PER_OUTLET", 0)
        if max_users == 0:  # Unlimited
            return True
        # Count all non-superadmin users (staff)
        return cls.objects.exclude(role=cls.Role.SUPER_ADMIN).count() < max_users

    @classmethod
    def users_remaining(cls):
        """Get number of users that can still be created."""
        from django.conf import settings as django_settings

        max_users = getattr(django_settings, "MAX_STAFF_PER_OUTLET", 0)
        if max_users == 0:  # Unlimited
            return float("inf")
        return max(0, max_users - cls.objects.exclude(role=cls.Role.SUPER_ADMIN).count())

    @classmethod
    def get_max_users(cls):
        """Get the maximum users allowed from plan settings."""
        from django.conf import settings as django_settings

        return getattr(django_settings, "MAX_STAFF_PER_OUTLET", 0)


class StaffAttendance(models.Model):
    """
    Track staff clock in/out times for attendance management.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="attendance_records",
    )
    clock_in = models.DateTimeField(
        help_text="Time when staff clocked in",
    )
    clock_out = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Time when staff clocked out",
    )
    shift = models.CharField(
        max_length=20,
        help_text="Shift name: morning, evening, night",
    )
    notes = models.TextField(
        blank=True,
        help_text="Optional notes about the shift",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Staff Attendance"
        verbose_name_plural = "Staff Attendance Records"
        ordering = ["-clock_in"]

    def __str__(self):
        return f"{self.user.username} - {self.clock_in.date()} ({self.shift})"

    @property
    def duration(self):
        """Calculate shift duration in hours."""
        if self.clock_out:
            delta = self.clock_out - self.clock_in
            return round(delta.total_seconds() / 3600, 2)
        return None


class AuditLog(models.Model):
    """
    Track user actions for security and debugging purposes.
    """

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="audit_logs",
    )
    action = models.CharField(
        max_length=100,
        help_text="Action performed: create, update, delete, login, etc.",
    )
    model_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Model that was affected",
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="ID of the affected object",
    )
    changes = models.JSONField(
        default=dict,
        help_text="JSON representation of changes made",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text="IP address of the user",
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Browser/client user agent",
    )
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user} - {self.action} - {self.timestamp}"
