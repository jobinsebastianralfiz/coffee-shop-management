"""
Django admin configuration for Retail & Wholesale models.
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    CustomerPayment,
    ProductBarcode,
    RetailCategory,
    RetailProduct,
    RetailSale,
    RetailSaleItem,
    RetailStockMovement,
    WholesaleCustomer,
    WholesaleInvoice,
)


class ProductBarcodeInline(admin.TabularInline):
    """Inline admin for product barcodes."""
    model = ProductBarcode
    extra = 1
    readonly_fields = ('barcode_image_preview',)
    fields = ('barcode_type', 'barcode_value', 'is_primary', 'barcode_image_preview')

    def barcode_image_preview(self, obj):
        if obj.barcode_image:
            return format_html('<img src="{}" height="40" />', obj.barcode_image.url)
        return "-"
    barcode_image_preview.short_description = "Preview"


@admin.register(RetailCategory)
class RetailCategoryAdmin(admin.ModelAdmin):
    """Admin for retail categories."""
    list_display = ('name', 'outlet', 'parent', 'display_order', 'is_active', 'product_count')
    list_filter = ('outlet', 'is_active', 'parent')
    search_fields = ('name', 'description')
    ordering = ('outlet', 'display_order', 'name')

    def product_count(self, obj):
        return obj.products.count()
    product_count.short_description = "Products"


@admin.register(RetailProduct)
class RetailProductAdmin(admin.ModelAdmin):
    """Admin for retail products."""
    list_display = (
        'name', 'sku', 'barcode_display', 'category', 'outlet',
        'selling_price', 'current_stock', 'stock_status_display', 'is_active'
    )
    list_filter = ('outlet', 'category', 'is_active', 'track_inventory', 'tax_type')
    search_fields = ('name', 'sku', 'description')
    readonly_fields = ('created_at', 'updated_at', 'stock_status', 'profit_margin')
    inlines = [ProductBarcodeInline]
    ordering = ('-created_at',)

    fieldsets = (
        ('Basic Information', {
            'fields': ('outlet', 'category', 'name', 'description', 'sku')
        }),
        ('Pricing', {
            'fields': ('unit', 'cost_price', 'mrp', 'selling_price', 'wholesale_price', 'profit_margin')
        }),
        ('Tax & Compliance', {
            'fields': ('tax_type', 'hsn_code')
        }),
        ('Inventory', {
            'fields': ('track_inventory', 'current_stock', 'minimum_stock', 'stock_status')
        }),
        ('Links', {
            'fields': ('linked_menu_item', 'supplier'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active', 'created_at', 'updated_at')
        }),
    )

    def barcode_display(self, obj):
        barcode = obj.primary_barcode
        if barcode:
            return barcode.barcode_value
        return "-"
    barcode_display.short_description = "Primary Barcode"

    def stock_status_display(self, obj):
        status = obj.stock_status
        colors = {
            'in_stock': 'green',
            'low_stock': 'orange',
            'out_of_stock': 'red',
        }
        return format_html(
            '<span style="color: {};">{}</span>',
            colors.get(status, 'black'),
            status.replace('_', ' ').title()
        )
    stock_status_display.short_description = "Stock Status"


@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    """Admin for product barcodes."""
    list_display = ('barcode_value', 'product', 'barcode_type', 'is_primary', 'created_at')
    list_filter = ('barcode_type', 'is_primary', 'product__outlet')
    search_fields = ('barcode_value', 'product__name', 'product__sku')
    raw_id_fields = ('product',)


@admin.register(WholesaleCustomer)
class WholesaleCustomerAdmin(admin.ModelAdmin):
    """Admin for wholesale customers."""
    list_display = (
        'business_name', 'name', 'outlet', 'phone',
        'credit_limit', 'current_balance', 'balance_status', 'is_active'
    )
    list_filter = ('outlet', 'is_active', 'payment_terms_days')
    search_fields = ('business_name', 'name', 'phone', 'email', 'gst_number')
    readonly_fields = ('current_balance', 'created_at', 'updated_at')
    ordering = ('business_name',)

    fieldsets = (
        ('Business Information', {
            'fields': ('outlet', 'business_name', 'name', 'phone', 'email', 'address_line1', 'city', 'state', 'postal_code')
        }),
        ('Tax Information', {
            'fields': ('gst_number', 'pan_number')
        }),
        ('Credit Settings', {
            'fields': ('credit_limit', 'current_balance', 'payment_terms_days', 'discount_percentage')
        }),
        ('Status', {
            'fields': ('is_active', 'notes', 'created_at', 'updated_at')
        }),
    )

    def balance_status(self, obj):
        if obj.current_balance > obj.credit_limit > 0:
            return format_html('<span style="color: red;">Over Limit</span>')
        elif obj.current_balance > 0:
            return format_html('<span style="color: orange;">Outstanding</span>')
        return format_html('<span style="color: green;">Clear</span>')
    balance_status.short_description = "Balance Status"


class RetailSaleItemInline(admin.TabularInline):
    """Inline admin for sale items."""
    model = RetailSaleItem
    extra = 0
    readonly_fields = ('product_name', 'product_sku', 'total')
    fields = ('product', 'product_name', 'product_sku', 'quantity', 'unit_price', 'discount_amount', 'tax_rate', 'total')


@admin.register(RetailSale)
class RetailSaleAdmin(admin.ModelAdmin):
    """Admin for retail sales."""
    list_display = (
        'sale_number', 'sale_type', 'outlet', 'subtotal',
        'total_amount', 'payment_status', 'payment_method', 'created_at'
    )
    list_filter = ('outlet', 'sale_type', 'payment_status', 'payment_method', 'created_at')
    search_fields = ('sale_number', 'wholesale_customer__business_name')
    readonly_fields = ('sale_number', 'subtotal', 'discount_amount', 'cgst_amount', 'sgst_amount', 'igst_amount', 'total_amount', 'created_at')
    inlines = [RetailSaleItemInline]
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

    fieldsets = (
        ('Sale Information', {
            'fields': ('outlet', 'sale_number', 'sale_type', 'wholesale_customer')
        }),
        ('Amounts', {
            'fields': ('subtotal', 'discount_amount', 'cgst_amount', 'sgst_amount', 'igst_amount', 'total_amount')
        }),
        ('Payment', {
            'fields': ('payment_status', 'payment_method')
        }),
        ('Staff', {
            'fields': ('created_by',)
        }),
    )


@admin.register(WholesaleInvoice)
class WholesaleInvoiceAdmin(admin.ModelAdmin):
    """Admin for wholesale invoices."""
    list_display = (
        'invoice_number', 'customer', 'sale', 'amount',
        'paid_amount', 'balance', 'status', 'due_date'
    )
    list_filter = ('status', 'customer__outlet', 'due_date')
    search_fields = ('invoice_number', 'customer__business_name')
    readonly_fields = ('balance', 'created_at', 'updated_at')
    date_hierarchy = 'due_date'
    ordering = ('-created_at',)

    def balance(self, obj):
        return obj.amount - obj.paid_amount
    balance.short_description = "Balance"


@admin.register(CustomerPayment)
class CustomerPaymentAdmin(admin.ModelAdmin):
    """Admin for customer payments."""
    list_display = (
        'receipt_number', 'customer', 'amount',
        'payment_method', 'payment_date', 'received_by'
    )
    list_filter = ('payment_method', 'customer__outlet', 'payment_date')
    search_fields = ('receipt_number', 'customer__business_name', 'reference_number')
    readonly_fields = ('created_at',)
    date_hierarchy = 'payment_date'
    ordering = ('-payment_date',)


@admin.register(RetailStockMovement)
class RetailStockMovementAdmin(admin.ModelAdmin):
    """Admin for stock movements."""
    list_display = (
        'product', 'movement_type', 'quantity',
        'stock_before', 'stock_after', 'created_at'
    )
    list_filter = ('movement_type', 'product__outlet', 'created_at')
    search_fields = ('product__name', 'product__sku', 'reference', 'notes')
    readonly_fields = ('stock_before', 'stock_after', 'created_at')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
