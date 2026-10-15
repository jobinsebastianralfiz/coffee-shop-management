from django.contrib import admin

from .models import KitchenStation, PrintAgent, PrintJob


@admin.register(KitchenStation)
class KitchenStationAdmin(admin.ModelAdmin):
    list_display = ("name", "outlet", "printer_ip", "printer_port", "paper_width", "is_default", "is_active", "display_order")
    list_filter = ("outlet", "is_active", "is_default")
    search_fields = ("name", "printer_ip")


@admin.register(PrintAgent)
class PrintAgentAdmin(admin.ModelAdmin):
    list_display = ("name", "outlet", "is_active", "last_seen_at", "last_seen_ip")
    list_filter = ("outlet", "is_active")
    readonly_fields = ("token", "last_seen_at", "last_seen_ip", "created_at")


@admin.register(PrintJob)
class PrintJobAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "outlet", "station", "printer_ip", "status", "attempts", "created_at", "printed_at")
    list_filter = ("status", "kind", "outlet")
    search_fields = ("title", "last_error")
    readonly_fields = ("payload", "created_at", "claimed_at", "printed_at")
    raw_id_fields = ("order",)
