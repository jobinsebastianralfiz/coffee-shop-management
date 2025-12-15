"""
Admin configuration for finance app.
"""

from django.contrib import admin

from .models import (
    CashDrawer,
    CashDrawerTransaction,
    CashierShift,
    Expense,
    ExpenseCategory,
)


@admin.register(ExpenseCategory)
class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "category_type", "is_default", "is_active", "display_order"]
    list_filter = ["category_type", "is_default", "is_active"]
    search_fields = ["name", "description"]
    ordering = ["display_order", "name"]


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = [
        "expense_number",
        "category",
        "date",
        "amount",
        "payment_method",
        "status",
        "vendor_name",
        "created_by",
    ]
    list_filter = ["category", "payment_method", "status", "date"]
    search_fields = ["expense_number", "description", "vendor_name", "reference_number"]
    date_hierarchy = "date"
    readonly_fields = ["expense_number", "uuid", "created_at", "updated_at"]


@admin.register(CashDrawer)
class CashDrawerAdmin(admin.ModelAdmin):
    list_display = [
        "date",
        "opening_balance",
        "total_cash_sales",
        "total_cash_in",
        "total_cash_out",
        "expected_balance",
        "actual_balance",
        "variance",
        "is_closed",
    ]
    list_filter = ["is_closed", "date"]
    date_hierarchy = "date"
    readonly_fields = [
        "total_cash_sales",
        "total_cash_in",
        "total_cash_out",
        "expected_balance",
        "variance",
        "created_at",
        "updated_at",
    ]


@admin.register(CashierShift)
class CashierShiftAdmin(admin.ModelAdmin):
    list_display = [
        "cashier",
        "cash_drawer",
        "shift_start",
        "shift_end",
        "opening_balance",
        "cash_sales",
        "expected_balance",
        "actual_balance",
        "variance",
        "is_closed",
    ]
    list_filter = ["is_closed", "cashier", "cash_drawer__date"]
    search_fields = ["cashier__username", "cashier__first_name", "cashier__last_name"]
    readonly_fields = [
        "uuid",
        "cash_sales",
        "cash_in",
        "cash_out",
        "expected_balance",
        "variance",
        "created_at",
        "updated_at",
    ]


@admin.register(CashDrawerTransaction)
class CashDrawerTransactionAdmin(admin.ModelAdmin):
    list_display = [
        "created_at",
        "transaction_type",
        "amount",
        "cash_drawer",
        "cashier_shift",
        "description",
        "created_by",
    ]
    list_filter = ["transaction_type", "cash_drawer__date"]
    search_fields = ["description", "reference"]
    readonly_fields = ["uuid", "created_at"]
