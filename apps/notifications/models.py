"""
Notification models for the Coffee Shop Management System.

Supports:
- Broadcast notifications (all users)
- Role-based notifications (e.g., all waiters)
- Outlet-based notifications
- Individual user notifications
"""

from django.db import models

from apps.accounts.models import User
from apps.core.models import Outlet


class Notification(models.Model):
    """Notification model for storing all types of notifications."""

    class NotificationType(models.TextChoices):
        INFO = "info", "Information"
        ORDER = "order", "Order Update"
        ALERT = "alert", "Alert"
        ANNOUNCEMENT = "announcement", "Announcement"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    # Target options - at least one should be set
    recipient = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="received_notifications",
        help_text="Specific user to receive this notification",
    )
    target_role = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Target all users with this role",
    )
    target_outlet = models.ForeignKey(
        Outlet,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="notifications",
        help_text="Target all users in this outlet",
    )
    is_broadcast = models.BooleanField(
        default=False,
        help_text="Send to all users",
    )

    # Content
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.INFO,
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )

    # Related order (optional - for order notifications)
    related_order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notifications",
    )

    # Metadata
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="sent_notifications",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"

    def __str__(self):
        return f"{self.title} ({self.get_notification_type_display()})"

    def is_for_user(self, user):
        """Check if this notification is relevant for a specific user."""
        # Broadcast - for everyone
        if self.is_broadcast:
            return True

        # Specific recipient
        if self.recipient_id and self.recipient_id == user.id:
            return True

        # Target role
        if self.target_role and user.role == self.target_role:
            # If also targeting outlet, check that too
            if self.target_outlet_id:
                return user.outlet_id == self.target_outlet_id
            return True

        # Target outlet (without role filter)
        if self.target_outlet_id and not self.target_role:
            return user.outlet_id == self.target_outlet_id

        return False


class NotificationRead(models.Model):
    """Track which users have read which notifications."""

    notification = models.ForeignKey(
        Notification,
        on_delete=models.CASCADE,
        related_name="reads",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notification_reads",
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["notification", "user"]
        verbose_name = "Notification Read"
        verbose_name_plural = "Notification Reads"

    def __str__(self):
        return f"{self.user.username} read {self.notification.title}"
