"""
URL configuration for Retail & Wholesale module.
"""

from django.urls import path

from . import views

app_name = "retail"

urlpatterns = [
    # Dashboard
    path("dashboard/", views.retail_dashboard, name="dashboard"),

    # Products
    path("products/", views.product_list, name="products"),
    path("products/create/", views.product_create, name="product_create"),
    path("products/<int:pk>/", views.product_detail, name="product_detail"),
    path("products/<int:pk>/edit/", views.product_edit, name="product_edit"),
    path("products/<int:pk>/delete/", views.product_delete, name="product_delete"),

    # Categories
    path("categories/", views.category_list, name="categories"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),

    # Barcodes
    path("products/<int:pk>/barcode/generate/", views.barcode_generate, name="barcode_generate"),
    path("barcodes/print/", views.barcode_print_batch, name="barcode_print_batch"),
    path("barcodes/scan/", views.barcode_scan_lookup, name="barcode_scan"),

    # Retail POS
    path("pos/", views.retail_pos, name="pos"),
    path("pos/barcode-lookup/", views.pos_barcode_lookup, name="pos_barcode_lookup"),
    path("pos/complete-sale/", views.pos_complete_sale, name="pos_complete_sale"),
    path("pos/sale/<uuid:sale_uuid>/status/", views.pos_sale_status, name="pos_sale_status"),
    path("pos/sale/<uuid:sale_uuid>/settle/", views.pos_sale_settle, name="pos_sale_settle"),
    path("pos/sale/<uuid:sale_uuid>/upi-qr.svg", views.pos_sale_upi_qr, name="pos_sale_upi_qr"),

    # Sales
    path("sales/", views.sale_list, name="sales"),
    path("sales/<int:pk>/", views.sale_detail, name="sale_detail"),
    path("sales/<int:pk>/receipt/", views.sale_receipt, name="sale_receipt"),

    # Wholesale Customers
    path("customers/", views.customer_list, name="customers"),
    path("customers/create/", views.customer_create, name="customer_create"),
    path("customers/<int:pk>/", views.customer_detail, name="customer_detail"),
    path("customers/<int:pk>/edit/", views.customer_edit, name="customer_edit"),
    path("customers/<int:pk>/statement/", views.customer_statement, name="customer_statement"),

    # Invoices
    path("invoices/", views.invoice_list, name="invoices"),
    path("invoices/<int:pk>/", views.invoice_detail, name="invoice_detail"),
    path("invoices/<int:pk>/print/", views.invoice_print, name="invoice_print"),

    # Payments
    path("payments/", views.payment_list, name="payments"),
    path("payments/receive/", views.payment_receive, name="payment_receive"),
    path("payments/<int:pk>/receipt/", views.payment_receipt, name="payment_receipt"),

    # Outstanding
    path("outstanding/", views.outstanding_dashboard, name="outstanding"),
    path("outstanding/aging/", views.aging_report, name="aging_report"),

    # Stock
    path("stock/", views.stock_list, name="stock"),
    path("stock/adjust/", views.stock_adjust, name="stock_adjust"),
    path("stock/movements/", views.stock_movements, name="stock_movements"),
]
