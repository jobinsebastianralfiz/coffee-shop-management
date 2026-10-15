from django.conf import settings
from django.db import models


class QRGuestSession(models.Model):
    """
    One guest phone at one table. A phone may send orders straight to the
    kitchen only once it is confirmed to be at the table, by its location or by
    a staff member. This stops orders from a photo of the QR taken home.
    """

    class Method(models.TextChoices):
        LOCATION = "location", "Location"
        CODE = "code", "Table code"
        STAFF = "staff", "Staff"
        OPEN = "open", "Protection off"

    table = models.ForeignKey("tables.Table", on_delete=models.CASCADE, related_name="guest_sessions")
    session_key = models.CharField(max_length=40, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Confirmed at the table
    verified_at = models.DateTimeField(null=True, blank=True)
    method = models.CharField(max_length=10, choices=Method.choices, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    # A round waiting for staff to confirm the guest is really at the table
    pending_order = models.ForeignKey(
        "orders.Order", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    requested_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    distance_m = models.PositiveIntegerField(null=True, blank=True, help_text="Distance from the outlet when the guest shared location")

    # Call waiter
    called_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ["table", "session_key"]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Guest at {self.table} ({self.session_key[:6]})"
