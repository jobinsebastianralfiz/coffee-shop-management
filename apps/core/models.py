"""
Core models and utilities for the Coffee Shop Management System.
"""

from django.db import models


class SingletonModel(models.Model):
    """
    Abstract base class for singleton models (only one instance allowed).
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass  # Prevent deletion

    @classmethod
    def load(cls):
        """Load the singleton instance, creating it if necessary."""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class BusinessSettings(SingletonModel):
    """
    Global business configuration settings (singleton).
    """

    # Business Info
    business_name = models.CharField(max_length=200, default="Coffee Shop")
    tagline = models.CharField(max_length=200, blank=True)
    logo = models.ImageField(upload_to="branding/", null=True, blank=True)
    logo_dark = models.ImageField(
        upload_to="branding/",
        null=True,
        blank=True,
        help_text="Logo for dark backgrounds",
    )
    favicon = models.ImageField(upload_to="branding/", null=True, blank=True)

    # Theme Colors (hex values)
    primary_color = models.CharField(
        max_length=7,
        default="#6366f1",
        help_text="Primary brand color (hex)",
    )
    secondary_color = models.CharField(
        max_length=7,
        default="#8b5cf6",
        help_text="Secondary brand color (hex)",
    )
    accent_color = models.CharField(
        max_length=7,
        default="#ec4899",
        help_text="Accent color for highlights (hex)",
    )
    sidebar_color = models.CharField(
        max_length=7,
        default="#0f172a",
        help_text="Sidebar background color (hex)",
    )
    sidebar_text_color = models.CharField(
        max_length=7,
        default="#94a3b8",
        help_text="Sidebar text color (hex)",
    )
    sidebar_active_color = models.CharField(
        max_length=7,
        default="#6366f1",
        help_text="Active menu item color (hex)",
    )

    # Theme Mode
    THEME_CHOICES = [
        ("light", "Light"),
        ("dark", "Dark"),
        ("system", "System Default"),
    ]
    default_theme = models.CharField(
        max_length=10,
        choices=THEME_CHOICES,
        default="light",
    )

    # Login Page Customization
    login_bg_gradient_start = models.CharField(
        max_length=7,
        default="#6366f1",
        help_text="Login page gradient start color",
    )
    login_bg_gradient_end = models.CharField(
        max_length=7,
        default="#8b5cf6",
        help_text="Login page gradient end color",
    )
    login_welcome_text = models.CharField(
        max_length=200,
        default="Welcome back!",
        help_text="Login page welcome message",
    )
    login_subtitle = models.CharField(
        max_length=200,
        default="Sign in to your account",
    )

    # Contact Info
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    website = models.URLField(blank=True)

    # Tax & Legal
    gst_number = models.CharField(max_length=50, blank=True)
    fssai_number = models.CharField(max_length=50, blank=True)

    # Currency
    currency = models.CharField(max_length=10, default="INR")
    currency_symbol = models.CharField(max_length=5, default="₹")

    # Operating Hours
    opening_time = models.TimeField(null=True, blank=True)
    closing_time = models.TimeField(null=True, blank=True)

    # Receipt Customization
    receipt_header = models.TextField(
        blank=True,
        help_text="Text to display at top of receipts",
    )
    receipt_footer = models.TextField(
        blank=True,
        help_text="Text to display at bottom of receipts",
    )

    # Social Media
    facebook_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    twitter_url = models.URLField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Business Settings"
        verbose_name_plural = "Business Settings"

    def __str__(self):
        return self.business_name


class TaxSettings(SingletonModel):
    """
    Tax configuration settings (singleton).
    """

    # GST Settings (India)
    cgst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.5,
        help_text="Central GST rate (%)",
    )
    sgst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.5,
        help_text="State GST rate (%)",
    )

    # Service Charge
    service_charge_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Service charge rate (%)",
    )
    service_charge_enabled = models.BooleanField(default=False)

    # Tax Options
    tax_inclusive_pricing = models.BooleanField(
        default=False,
        help_text="If True, menu prices include tax",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Tax Settings"
        verbose_name_plural = "Tax Settings"

    def __str__(self):
        return f"Tax: CGST {self.cgst_rate}% + SGST {self.sgst_rate}%"

    @property
    def total_tax_rate(self):
        """Get combined tax rate."""
        return self.cgst_rate + self.sgst_rate


class OrderSettings(SingletonModel):
    """
    Order-related configuration settings (singleton).
    """

    # Order Behavior
    auto_accept_orders = models.BooleanField(
        default=False,
        help_text="Automatically accept new orders without manual confirmation",
    )
    default_preparation_time = models.PositiveIntegerField(
        default=10,
        help_text="Default preparation time in minutes",
    )

    # Order Number Format
    order_number_prefix = models.CharField(max_length=10, default="ORD")
    daily_order_reset = models.BooleanField(
        default=True,
        help_text="Reset order numbers daily",
    )

    # Takeaway Settings
    require_phone_takeaway = models.BooleanField(
        default=True,
        help_text="Require phone number for takeaway orders",
    )
    takeaway_token_prefix = models.CharField(max_length=5, default="T")

    # QR Ordering
    allow_qr_ordering = models.BooleanField(
        default=True,
        help_text="Allow customers to order via QR code",
    )
    require_customer_info_qr = models.BooleanField(
        default=False,
        help_text="Require name/phone for QR orders",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order Settings"
        verbose_name_plural = "Order Settings"

    def __str__(self):
        return "Order Settings"


class NotificationSettings(SingletonModel):
    """
    Notification configuration settings (singleton).
    """

    # SMS Settings
    sms_enabled = models.BooleanField(default=False)
    sms_order_ready = models.BooleanField(
        default=True,
        help_text="Send SMS when order is ready",
    )

    # WhatsApp Settings
    whatsapp_enabled = models.BooleanField(default=False)
    whatsapp_order_confirmation = models.BooleanField(default=False)
    whatsapp_order_ready = models.BooleanField(default=False)

    # Email Settings
    email_enabled = models.BooleanField(default=False)
    email_daily_report = models.BooleanField(default=False)
    daily_report_email = models.EmailField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Notification Settings"
        verbose_name_plural = "Notification Settings"

    def __str__(self):
        return "Notification Settings"


class PrinterSettings(SingletonModel):
    """
    Printer configuration settings (singleton).
    """

    # Receipt Printer
    receipt_printer_enabled = models.BooleanField(default=False)
    receipt_printer_name = models.CharField(max_length=100, blank=True)
    receipt_printer_ip = models.GenericIPAddressField(null=True, blank=True)
    receipt_auto_print = models.BooleanField(
        default=False,
        help_text="Automatically print receipt on payment",
    )

    # KOT Printer
    kot_printer_enabled = models.BooleanField(default=False)
    kot_printer_name = models.CharField(max_length=100, blank=True)
    kot_printer_ip = models.GenericIPAddressField(null=True, blank=True)
    kot_auto_print = models.BooleanField(
        default=False,
        help_text="Automatically print KOT on order",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Printer Settings"
        verbose_name_plural = "Printer Settings"

    def __str__(self):
        return "Printer Settings"


class TimeStampedModel(models.Model):
    """
    Abstract base class with created_at and updated_at fields.
    """

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Outlet(TimeStampedModel):
    """
    Represents a physical store/branch location.
    Each outlet can have its own currency, tax rates, operating hours, and branding.
    """

    # Basic Info
    name = models.CharField(max_length=100)
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Unique outlet code (e.g., 'NYC01', 'LA02')",
    )

    # Location
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100, default="India")
    postal_code = models.CharField(max_length=20)
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )

    # Contact
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)

    # Currency Configuration
    currency_code = models.CharField(
        max_length=3,
        default="INR",
        help_text="ISO 4217 currency code (e.g., 'INR', 'USD', 'EUR')",
    )
    currency_symbol = models.CharField(max_length=5, default="₹")
    CURRENCY_POSITION_CHOICES = [
        ("before", "Before amount (e.g., $100)"),
        ("after", "After amount (e.g., 100€)"),
    ]
    currency_position = models.CharField(
        max_length=10,
        choices=CURRENCY_POSITION_CHOICES,
        default="before",
    )

    # Branding
    logo = models.ImageField(upload_to="outlet_logos/", null=True, blank=True)
    receipt_header = models.TextField(
        blank=True,
        help_text="Text to display at top of receipts",
    )
    receipt_footer = models.TextField(
        blank=True,
        help_text="Text to display at bottom of receipts",
    )

    # Operating Hours (JSON field for flexibility)
    # Example: {"monday": {"open": "09:00", "close": "22:00", "closed": false}, ...}
    operating_hours = models.JSONField(
        default=dict,
        blank=True,
        help_text="Operating hours per day of the week",
    )

    # Tax Configuration
    tax_enabled = models.BooleanField(default=True)
    cgst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.50,
        help_text="Central GST rate (%)",
    )
    sgst_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=2.50,
        help_text="State GST rate (%)",
    )
    service_charge_enabled = models.BooleanField(default=False)
    service_charge_rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Service charge rate (%)",
    )
    tax_inclusive_pricing = models.BooleanField(
        default=False,
        help_text="If True, menu prices include tax",
    )

    # Order Settings
    order_prefix = models.CharField(
        max_length=10,
        default="ORD",
        help_text="Prefix for order numbers",
    )
    auto_accept_orders = models.BooleanField(
        default=False,
        help_text="Automatically accept new orders without manual confirmation",
    )
    default_prep_time = models.PositiveIntegerField(
        default=10,
        help_text="Default preparation time in minutes",
    )

    # QR Ordering
    allow_qr_ordering = models.BooleanField(
        default=True,
        help_text="Allow customers to order via QR code",
    )

    # Status
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Outlet"
        verbose_name_plural = "Outlets"

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def total_tax_rate(self):
        """Get combined tax rate."""
        return self.cgst_rate + self.sgst_rate

    def format_currency(self, amount):
        """Format an amount with this outlet's currency settings."""
        formatted = f"{amount:,.2f}"
        if self.currency_position == "before":
            return f"{self.currency_symbol}{formatted}"
        return f"{formatted}{self.currency_symbol}"

    @property
    def full_address(self):
        """Get full formatted address."""
        parts = [self.address, self.city, self.state, self.postal_code, self.country]
        return ", ".join(p for p in parts if p)

    def clean(self):
        """Validate outlet creation against plan limits."""
        from django.conf import settings
        from django.core.exceptions import ValidationError

        max_outlets = getattr(settings, "MAX_OUTLETS", 0)

        # 0 means unlimited
        if max_outlets == 0:
            return

        # Check if this is a new outlet (no pk yet)
        if not self.pk:
            current_count = Outlet.objects.count()
            if current_count >= max_outlets:
                raise ValidationError(
                    f"Cannot create more outlets. Your plan allows maximum {max_outlets} outlet(s). "
                    f"Contact your vendor to upgrade."
                )

    def save(self, *args, **kwargs):
        """Save with validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def can_create_outlet(cls):
        """Check if more outlets can be created based on plan limits."""
        from django.conf import settings

        max_outlets = getattr(settings, "MAX_OUTLETS", 0)
        if max_outlets == 0:  # Unlimited
            return True
        return cls.objects.count() < max_outlets

    @classmethod
    def outlets_remaining(cls):
        """Get number of outlets that can still be created."""
        from django.conf import settings

        max_outlets = getattr(settings, "MAX_OUTLETS", 0)
        if max_outlets == 0:  # Unlimited
            return float("inf")
        return max(0, max_outlets - cls.objects.count())
