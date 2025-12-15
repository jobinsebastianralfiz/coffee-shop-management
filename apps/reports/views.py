"""
Views for report generation and download.
"""

from datetime import datetime, timedelta

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.models import Order
from apps.reports.services import (
    SalesReportService,
    ItemReportService,
    FinancialReportService,
    StaffReportService,
)
from apps.reports.pdf_generator import SalesReportPDF, EODReportPDF, TaxReportPDF
from apps.reports.excel_generator import (
    SalesExcelReport,
    FinancialExcelReport,
    ItemSalesExcelReport,
)


def parse_date(date_str, default=None):
    """Parse date string to date object."""
    if not date_str:
        return default or timezone.now().date()
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return default or timezone.now().date()


# =============================================================================
# API ENDPOINTS
# =============================================================================

@login_required
def sales_report_api(request):
    """API endpoint for sales report data."""
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))

    sales_data = SalesReportService.get_sales_summary(start_date, end_date)
    payment_data = SalesReportService.get_payment_breakdown(start_date, end_date)
    items_data = ItemReportService.get_top_selling_items(start_date, end_date, limit=10)

    # Convert Decimal to float for JSON
    def convert_decimals(obj):
        if isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_decimals(i) for i in obj]
        elif hasattr(obj, 'as_integer_ratio'):  # Decimal or float
            return float(obj)
        return obj

    return JsonResponse({
        'sales': convert_decimals(sales_data),
        'payments': convert_decimals(payment_data),
        'items': convert_decimals(items_data),
        'period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        }
    })


@login_required
def items_report_api(request):
    """API endpoint for item sales data."""
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))
    limit = int(request.GET.get('limit', 20))

    items_data = ItemReportService.get_top_selling_items(start_date, end_date, limit=limit)
    category_data = ItemReportService.get_category_performance(start_date, end_date)

    def convert_decimals(obj):
        if isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_decimals(i) for i in obj]
        elif hasattr(obj, 'as_integer_ratio'):
            return float(obj)
        return obj

    return JsonResponse({
        'items': convert_decimals(items_data),
        'categories': convert_decimals(category_data),
        'period': {
            'start': start_date.isoformat(),
            'end': end_date.isoformat()
        }
    })


@login_required
def hourly_report_api(request):
    """API endpoint for hourly breakdown."""
    date = parse_date(request.GET.get('date'))
    hourly_data = SalesReportService.get_hourly_breakdown(date)

    def convert_decimals(obj):
        if isinstance(obj, dict):
            return {k: convert_decimals(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [convert_decimals(i) for i in obj]
        elif hasattr(obj, 'as_integer_ratio'):
            return float(obj)
        return obj

    return JsonResponse({
        'hourly': convert_decimals(hourly_data),
        'date': date.isoformat()
    })


@login_required
def daily_trend_api(request):
    """API endpoint for daily trend."""
    days = int(request.GET.get('days', 7))
    daily_data = SalesReportService.get_daily_trend(days=days)

    def convert_decimals(obj):
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if hasattr(v, 'isoformat'):  # date object
                    result[k] = v.isoformat()
                else:
                    result[k] = convert_decimals(v)
            return result
        elif isinstance(obj, list):
            return [convert_decimals(i) for i in obj]
        elif hasattr(obj, 'as_integer_ratio'):
            return float(obj)
        return obj

    return JsonResponse({
        'daily': convert_decimals(daily_data),
        'days': days
    })


# =============================================================================
# PDF DOWNLOAD ENDPOINTS
# =============================================================================

@login_required
def download_sales_pdf(request):
    """Download sales report as PDF."""
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))

    sales_data = SalesReportService.get_sales_summary(start_date, end_date)
    items_data = ItemReportService.get_top_selling_items(start_date, end_date)
    payment_data = SalesReportService.get_payment_breakdown(start_date, end_date)

    pdf = SalesReportPDF(start_date, end_date)
    buffer = pdf.generate_report(sales_data, items_data, payment_data)

    filename = f"sales_report_{start_date}_{end_date}.pdf"
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_eod_pdf(request):
    """Download End of Day report as PDF."""
    date = parse_date(request.GET.get('date'))

    sales_data = SalesReportService.get_daily_sales(date)
    cash_data = FinancialReportService.get_cash_drawer_summary(date)
    staff_data = StaffReportService.get_staff_sales(date, date)

    pdf = EODReportPDF(date)
    buffer = pdf.generate_report(sales_data, cash_data, staff_data)

    filename = f"eod_report_{date}.pdf"
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_tax_pdf(request):
    """Download tax report as PDF."""
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))

    tax_data = FinancialReportService.get_tax_collection(start_date, end_date)

    pdf = TaxReportPDF(start_date, end_date)
    buffer = pdf.generate_report(tax_data)

    filename = f"tax_report_{start_date}_{end_date}.pdf"
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# =============================================================================
# EXCEL DOWNLOAD ENDPOINTS
# =============================================================================

@login_required
def download_sales_excel(request):
    """Download sales report as Excel."""
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))

    sales_data = SalesReportService.get_sales_summary(start_date, end_date)
    items_data = ItemReportService.get_top_selling_items(start_date, end_date, limit=50)
    payment_data = SalesReportService.get_payment_breakdown(start_date, end_date)

    # Get orders list
    orders = Order.objects.filter(
        created_at__date__gte=start_date,
        created_at__date__lte=end_date,
        status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
    ).select_related('table').prefetch_related('items').order_by('-created_at')

    excel = SalesExcelReport(start_date, end_date)
    buffer = excel.generate_report(sales_data, items_data, list(orders), payment_data)

    filename = f"sales_report_{start_date}_{end_date}.xlsx"
    response = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_items_excel(request):
    """Download item sales report as Excel."""
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))

    items_data = ItemReportService.get_top_selling_items(start_date, end_date, limit=100)
    category_data = ItemReportService.get_category_performance(start_date, end_date)

    excel = ItemSalesExcelReport(start_date, end_date)
    buffer = excel.generate_report(items_data, category_data)

    filename = f"item_sales_{start_date}_{end_date}.xlsx"
    response = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
def download_financial_excel(request):
    """Download financial report as Excel."""
    start_date = parse_date(request.GET.get('start_date'))
    end_date = parse_date(request.GET.get('end_date'))

    revenue_data = FinancialReportService.get_revenue_summary(start_date, end_date)
    expense_data = FinancialReportService.get_expense_summary(start_date, end_date)
    pnl_data = FinancialReportService.get_profit_loss(start_date, end_date)

    excel = FinancialExcelReport(start_date, end_date)
    buffer = excel.generate_report(revenue_data, expense_data, pnl_data)

    filename = f"financial_report_{start_date}_{end_date}.xlsx"
    response = HttpResponse(
        buffer.read(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
