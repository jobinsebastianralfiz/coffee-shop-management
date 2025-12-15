"""
URL patterns for the reports app.
"""

from django.urls import path

from apps.reports import views

app_name = "reports"

urlpatterns = [
    # API Endpoints
    path("api/sales/", views.sales_report_api, name="api_sales"),
    path("api/items/", views.items_report_api, name="api_items"),
    path("api/hourly/", views.hourly_report_api, name="api_hourly"),
    path("api/daily-trend/", views.daily_trend_api, name="api_daily_trend"),

    # PDF Downloads
    path("download/pdf/sales/", views.download_sales_pdf, name="download_sales_pdf"),
    path("download/pdf/eod/", views.download_eod_pdf, name="download_eod_pdf"),
    path("download/pdf/tax/", views.download_tax_pdf, name="download_tax_pdf"),

    # Excel Downloads
    path("download/excel/sales/", views.download_sales_excel, name="download_sales_excel"),
    path("download/excel/items/", views.download_items_excel, name="download_items_excel"),
    path("download/excel/financial/", views.download_financial_excel, name="download_financial_excel"),
]
