from django.contrib import admin, messages

from .models import Floor, Table


@admin.register(Floor)
class FloorAdmin(admin.ModelAdmin):
    list_display = ["name", "outlet", "display_order", "is_active"]
    list_filter = ["outlet", "is_active"]
    search_fields = ["name"]


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ["number", "name", "floor", "capacity", "status", "guest_code", "is_active"]
    list_filter = ["floor__outlet", "floor", "status", "is_active"]
    search_fields = ["number", "name"]
    readonly_fields = ["uuid", "guest_code", "guests_reset_at", "qr_url"]
    actions = ["give_new_code"]
    fieldsets = (
        (None, {"fields": ("floor", "number", "name", "capacity", "table_type", "status", "is_active")}),
        (
            "QR ordering",
            {
                "fields": ("uuid", "qr_url", "guest_code", "guests_reset_at"),
                "description": "The guest code is the 4-digit table code staff tell guests ordering by QR. "
                "It changes automatically every time the table is freed.",
            },
        ),
        ("Floor map", {"fields": ("position_x", "position_y"), "classes": ("collapse",)}),
    )

    @admin.action(description="Give the selected tables a new guest code")
    def give_new_code(self, request, queryset):
        for table in queryset:
            table.new_guest_code()
        messages.success(request, f"New codes issued for {queryset.count()} table(s).")
