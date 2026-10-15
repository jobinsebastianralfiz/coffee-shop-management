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
        OUTLET_MANAGER = "outlet_manager", "Outlet Manager"
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
    def is_super_admin(self):
        """Check if user has super admin role."""
        return self.role == self.Role.SUPER_ADMIN

    @property
    def is_admin(self):
        """Check if user has admin-level role (super admin or outlet manager)."""
        return self.role in [self.Role.SUPER_ADMIN, self.Role.OUTLET_MANAGER]

    @property
    def is_outlet_manager(self):
        """Check if user has outlet manager role."""
        return self.role == self.Role.OUTLET_MANAGER

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

    def can_manage_outlet(self, outlet):
        """Check if user can manage a specific outlet."""
        if self.is_super_admin:
            return True
        if self.is_outlet_manager and self.outlet_id == outlet.id:
            return True
        return False

    def get_managed_outlet(self):
        """Get the outlet this user manages (for outlet managers)."""
        if self.is_super_admin:
            return None  # Super admin can access all
        return self.outlet

    @classmethod
    def can_create_user(cls, outlet=None, role=None):
        """Check if more users can be created based on plan limits.

        Args:
            outlet: The outlet to check limits for (required for per-outlet limits)
            role: The role being created (determines which limit to check)

        Returns:
            bool: True if user can be created, False otherwise
        """
        from django.conf import settings as django_settings

        # Super admin has no limits
        if role == cls.Role.SUPER_ADMIN:
            return True

        # Outlet manager limit
        if role == cls.Role.OUTLET_MANAGER:
            max_managers = getattr(django_settings, "MAX_OUTLET_MANAGERS_PER_OUTLET", 0)
            if max_managers == 0:  # Unlimited
                return True
            if outlet:
                current_count = cls.objects.filter(
                    outlet=outlet,
                    role=cls.Role.OUTLET_MANAGER
                ).count()
            else:
                # Global count if no outlet specified
                current_count = cls.objects.filter(role=cls.Role.OUTLET_MANAGER).count()
            return current_count < max_managers

        # Staff roles (waiter, kitchen, cashier) - shared pool
        staff_roles = [cls.Role.STAFF_CASHIER, cls.Role.STAFF_KITCHEN, cls.Role.WAITER]
        if role in staff_roles:
            max_staff = getattr(django_settings, "MAX_STAFF_PER_OUTLET", 0)
            if max_staff == 0:  # Unlimited
                return True
            if outlet:
                current_count = cls.objects.filter(
                    outlet=outlet,
                    role__in=staff_roles
                ).count()
            else:
                current_count = cls.objects.filter(role__in=staff_roles).count()
            return current_count < max_staff

        # Default: allow
        return True

    @classmethod
    def users_remaining(cls, outlet=None, role=None):
        """Get number of users that can still be created.

        Args:
            outlet: The outlet to check limits for
            role: The role type to check (outlet_manager or staff roles)
        """
        from django.conf import settings as django_settings

        # Outlet manager
        if role == cls.Role.OUTLET_MANAGER:
            max_managers = getattr(django_settings, "MAX_OUTLET_MANAGERS_PER_OUTLET", 0)
            if max_managers == 0:
                return float("inf")
            if outlet:
                current_count = cls.objects.filter(
                    outlet=outlet,
                    role=cls.Role.OUTLET_MANAGER
                ).count()
            else:
                current_count = cls.objects.filter(role=cls.Role.OUTLET_MANAGER).count()
            return max(0, max_managers - current_count)

        # Staff roles
        staff_roles = [cls.Role.STAFF_CASHIER, cls.Role.STAFF_KITCHEN, cls.Role.WAITER]
        max_staff = getattr(django_settings, "MAX_STAFF_PER_OUTLET", 0)
        if max_staff == 0:
            return float("inf")
        if outlet:
            current_count = cls.objects.filter(
                outlet=outlet,
                role__in=staff_roles
            ).count()
        else:
            current_count = cls.objects.filter(role__in=staff_roles).count()
        return max(0, max_staff - current_count)

    @classmethod
    def get_max_staff(cls):
        """Get the maximum staff allowed per outlet from plan settings."""
        from django.conf import settings as django_settings
        return getattr(django_settings, "MAX_STAFF_PER_OUTLET", 0)

    @classmethod
    def get_max_managers(cls):
        """Get the maximum outlet managers allowed per outlet from plan settings."""
        from django.conf import settings as django_settings
        return getattr(django_settings, "MAX_OUTLET_MANAGERS_PER_OUTLET", 0)


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


class EmployeePoints(models.Model):
    """
    Track employee points for incentive system.
    Points are earned per completed order and reset monthly.
    """

    class Reason(models.TextChoices):
        ORDER_COMPLETED = "order_completed", "Order Completed"
        BONUS = "bonus", "Bonus"
        MANUAL_ADJUSTMENT = "manual_adjustment", "Manual Adjustment"
        DEDUCTION = "deduction", "Deduction"

    employee = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="points_history",
        help_text="Employee who earned the points",
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points_awarded",
        help_text="Order that earned these points (if applicable)",
    )
    points = models.IntegerField(
        default=0,
        help_text="Points earned (positive) or deducted (negative)",
    )
    reason = models.CharField(
        max_length=30,
        choices=Reason.choices,
        default=Reason.ORDER_COMPLETED,
        help_text="Reason for points transaction",
    )
    description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Additional description",
    )
    month = models.DateField(
        help_text="First day of the month (for monthly grouping)",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="points_awarded_by",
        help_text="User who awarded/adjusted points (null for system)",
    )

    class Meta:
        verbose_name = "Employee Points"
        verbose_name_plural = "Employee Points"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employee", "month"]),
            models.Index(fields=["month"]),
        ]

    def __str__(self):
        return f"{self.employee.username} - {self.points} pts ({self.reason})"

    def save(self, *args, **kwargs):
        # Auto-set month to first day of current month if not set
        if not self.month:
            from datetime import date
            today = date.today()
            self.month = today.replace(day=1)
        super().save(*args, **kwargs)

    @classmethod
    def get_employee_points_for_month(cls, employee, month=None):
        """Get total points for an employee for a specific month."""
        from datetime import date
        from django.db.models import Sum

        if month is None:
            month = date.today().replace(day=1)

        result = cls.objects.filter(
            employee=employee,
            month=month
        ).aggregate(total=Sum("points"))

        return result["total"] or 0

    @classmethod
    def get_monthly_leaderboard(cls, outlet=None, month=None, limit=10):
        """Get top employees by points for a month."""
        from datetime import date
        from django.db.models import Sum

        if month is None:
            month = date.today().replace(day=1)

        queryset = cls.objects.filter(month=month)

        if outlet:
            queryset = queryset.filter(employee__outlet=outlet)

        leaderboard = queryset.values(
            "employee__id",
            "employee__username",
            "employee__first_name",
            "employee__last_name",
            "employee__role",
        ).annotate(
            total_points=Sum("points")
        ).order_by("-total_points")[:limit]

        return list(leaderboard)
