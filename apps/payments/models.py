"""
Payment settings and gateway integration models.
"""

from django.db import models
from django.core.cache import cache


class PaymentSettings(models.Model):
    """
    Singleton model for payment gateway settings.
    """

    class Gateway(models.TextChoices):
        RAZORPAY = "razorpay", "Razorpay"
        PAYU = "payu", "PayU"
        MANUAL = "manual", "Manual Entry"

    # Gateway selection
    gateway = models.CharField(
        max_length=20,
        choices=Gateway.choices,
        default=Gateway.RAZORPAY,
    )

    # Razorpay settings
    razorpay_key_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="Razorpay Key ID (starts with rzp_)",
    )
    razorpay_key_secret = models.CharField(
        max_length=100,
        blank=True,
        help_text="Razorpay Key Secret",
    )
    razorpay_webhook_secret = models.CharField(
        max_length=100,
        blank=True,
        help_text="Razorpay Webhook Secret for signature verification",
    )

    # UPI settings (for static QR fallback)
    upi_id = models.CharField(
        max_length=100,
        blank=True,
        help_text="UPI ID for static QR (e.g., shop@paytm)",
    )
    upi_merchant_name = models.CharField(
        max_length=100,
        blank=True,
        help_text="Merchant name to display on UPI apps",
    )

    # General settings
    is_live_mode = models.BooleanField(
        default=False,
        help_text="Use live API keys (uncheck for test mode)",
    )
    auto_verify_payments = models.BooleanField(
        default=True,
        help_text="Automatically verify payment status via API",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payment Settings"
        verbose_name_plural = "Payment Settings"

    def __str__(self):
        return f"Payment Settings ({self.get_gateway_display()})"

    def save(self, *args, **kwargs):
        # Ensure only one instance exists (singleton)
        self.pk = 1
        super().save(*args, **kwargs)
        # Clear cache
        cache.delete("payment_settings")

    @classmethod
    def load(cls):
        """Load the singleton instance, creating if necessary."""
        cached = cache.get("payment_settings")
        if cached:
            return cached

        obj, created = cls.objects.get_or_create(pk=1)
        cache.set("payment_settings", obj, 300)  # Cache for 5 minutes
        return obj

    def get_razorpay_client(self):
        """Get configured Razorpay client."""
        if not self.razorpay_key_id or not self.razorpay_key_secret:
            return None

        import razorpay
        return razorpay.Client(auth=(self.razorpay_key_id, self.razorpay_key_secret))


class RazorpayOrder(models.Model):
    """
    Track Razorpay orders for QR payments.
    """

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        PAID = "paid", "Paid"
        FAILED = "failed", "Failed"
        EXPIRED = "expired", "Expired"

    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.CASCADE,
        related_name="razorpay_orders",
    )

    # Razorpay details
    razorpay_order_id = models.CharField(max_length=100, unique=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True)
    razorpay_signature = models.CharField(max_length=200, blank=True)

    # Amount (in paise for Razorpay)
    amount = models.PositiveIntegerField(help_text="Amount in paise")
    currency = models.CharField(max_length=3, default="INR")

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )

    # QR data
    qr_code_url = models.URLField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Razorpay Order"
        verbose_name_plural = "Razorpay Orders"
        ordering = ["-created_at"]

    def __str__(self):
        return f"RZP: {self.razorpay_order_id} - ₹{self.amount / 100}"

    @property
    def amount_in_rupees(self):
        return self.amount / 100
