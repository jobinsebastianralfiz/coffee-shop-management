from django.contrib import admin

from .models import QRGuestSession


@admin.register(QRGuestSession)
class QRGuestSessionAdmin(admin.ModelAdmin):
    """Phones that scanned a table QR: who was confirmed, how, and who was turned away."""

    list_display = ["table", "created_at", "method", "verified_at", "verified_by", "requested_at", "rejected_at", "distance_m", "ip_address"]
    list_filter = ["method", "table__floor__outlet", "table"]
    search_fields = ["ip_address", "session_key", "table__number"]
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in QRGuestSession._meta.fields]

    def has_add_permission(self, request):
        return False
