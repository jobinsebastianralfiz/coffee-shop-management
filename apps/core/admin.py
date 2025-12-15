from django.contrib import admin
from django.conf import settings as django_settings

from .models import (
    BusinessSettings,
    NotificationSettings,
    OrderSettings,
    Outlet,
    PrinterSettings,
    TaxSettings,
)


@admin.register(Outlet)
class OutletAdmin(admin.ModelAdmin):
    """Admin configuration for Outlet model."""

    list_display = [
        "name",
        "code",
        "city",
        "currency_code",
        "currency_symbol",
        "is_active",
    ]
    list_filter = ["is_active", "city", "state", "country"]
    search_fields = ["name", "code", "city", "address"]
    ordering = ["name"]

    fieldsets = (
        (
            "Basic Info",
            {
                "fields": ("name", "code", "is_active"),
            },
        ),
        (
            "Location",
            {
                "fields": (
                    "address",
                    "city",
                    "state",
                    "country",
                    "postal_code",
                    "latitude",
                    "longitude",
                ),
            },
        ),
        (
            "Contact",
            {
                "fields": ("phone", "email"),
            },
        ),
        (
            "Currency",
            {
                "fields": ("currency_code", "currency_symbol", "currency_position"),
            },
        ),
        (
            "Branding",
            {
                "fields": ("logo", "receipt_header", "receipt_footer"),
            },
        ),
        (
            "Operating Hours",
            {
                "fields": ("operating_hours",),
                "classes": ("collapse",),
            },
        ),
        (
            "Tax Settings",
            {
                "fields": (
                    "tax_enabled",
                    "cgst_rate",
                    "sgst_rate",
                    "service_charge_enabled",
                    "service_charge_rate",
                    "tax_inclusive_pricing",
                ),
            },
        ),
        (
            "Order Settings",
            {
                "fields": (
                    "order_prefix",
                    "auto_accept_orders",
                    "default_prep_time",
                    "allow_qr_ordering",
                ),
            },
        ),
    )


@admin.register(BusinessSettings)
class BusinessSettingsAdmin(admin.ModelAdmin):
    """Admin for global business settings (singleton)."""

    def has_add_permission(self, request):
        # Only allow one instance
        return not BusinessSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(TaxSettings)
class TaxSettingsAdmin(admin.ModelAdmin):
    """Admin for tax settings (singleton)."""

    def has_add_permission(self, request):
        return not TaxSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderSettings)
class OrderSettingsAdmin(admin.ModelAdmin):
    """Admin for order settings (singleton)."""

    def has_add_permission(self, request):
        return not OrderSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationSettings)
class NotificationSettingsAdmin(admin.ModelAdmin):
    """Admin for notification settings (singleton)."""

    def has_add_permission(self, request):
        return not NotificationSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PrinterSettings)
class PrinterSettingsAdmin(admin.ModelAdmin):
    """Admin for printer settings (singleton)."""

    def has_add_permission(self, request):
        return not PrinterSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
