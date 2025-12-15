"""
Report data aggregation services.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Sum, F, Q
from django.db.models.functions import TruncDate, TruncHour, ExtractHour
from django.utils import timezone

from apps.orders.models import Order, OrderItem, Payment
from apps.finance.models import Expense, CashDrawer, CashierShift
from apps.menu.models import MenuItem, Category


class SalesReportService:
    """Service for generating sales reports."""

    @staticmethod
    def get_date_range(period='today'):
        """
        Get start and end dates for a given period.

        Args:
            period: 'today', 'yesterday', 'week', 'month', 'year'

        Returns:
            tuple: (start_date, end_date)
        """
        today = timezone.now().date()

        if period == 'today':
            return today, today
        elif period == 'yesterday':
            yesterday = today - timedelta(days=1)
            return yesterday, yesterday
        elif period == 'week':
            start = today - timedelta(days=today.weekday())
            return start, today
        elif period == 'month':
            start = today.replace(day=1)
            return start, today
        elif period == 'year':
            start = today.replace(month=1, day=1)
            return start, today
        else:
            return today, today

    @staticmethod
    def get_sales_summary(start_date, end_date):
        """
        Get sales summary for a date range.

        Returns:
            dict: Sales summary with totals and counts
        """
        orders = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        )

        summary = orders.aggregate(
            total_revenue=Sum('total_amount'),
            total_orders=Count('id'),
            avg_order_value=Avg('total_amount'),
            total_discount=Sum('discount_amount'),
            total_tax=Sum(F('cgst_amount') + F('sgst_amount')),
            total_service_charge=Sum('service_charge'),
        )

        # Clean up None values
        for key in summary:
            if summary[key] is None:
                summary[key] = Decimal('0') if 'total' in key or 'avg' in key else 0

        # Calculate net revenue
        summary['net_revenue'] = summary['total_revenue'] - summary['total_discount']

        # Order type breakdown
        summary['by_type'] = list(orders.values('order_type').annotate(
            count=Count('id'),
            revenue=Sum('total_amount')
        ))

        # Order source breakdown
        summary['by_source'] = list(orders.values('order_source').annotate(
            count=Count('id'),
            revenue=Sum('total_amount')
        ))

        return summary

    @staticmethod
    def get_daily_sales(date):
        """Get sales for a specific date."""
        return SalesReportService.get_sales_summary(date, date)

    @staticmethod
    def get_sales_by_range(start_date, end_date):
        """Get sales summary for a date range."""
        return SalesReportService.get_sales_summary(start_date, end_date)

    @staticmethod
    def get_hourly_breakdown(date):
        """
        Get hourly sales breakdown for a specific date.

        Returns:
            list: Hourly sales data
        """
        orders = Order.objects.filter(
            created_at__date=date,
            status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        ).annotate(
            hour=ExtractHour('created_at')
        ).values('hour').annotate(
            count=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('hour')

        # Fill in missing hours with zero
        hourly_data = {i: {'hour': i, 'count': 0, 'revenue': Decimal('0')} for i in range(24)}
        for item in orders:
            hourly_data[item['hour']] = item

        return list(hourly_data.values())

    @staticmethod
    def get_daily_trend(days=7):
        """
        Get daily sales trend for the last N days.

        Returns:
            list: Daily sales data
        """
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=days - 1)

        orders = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        ).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(
            count=Count('id'),
            revenue=Sum('total_amount')
        ).order_by('date')

        # Fill in missing days
        daily_data = {}
        current = start_date
        while current <= end_date:
            daily_data[current] = {'date': current, 'count': 0, 'revenue': Decimal('0')}
            current += timedelta(days=1)

        for item in orders:
            daily_data[item['date']] = item

        return list(daily_data.values())

    @staticmethod
    def get_payment_breakdown(start_date, end_date):
        """
        Get payment method breakdown.

        Returns:
            list: Payment method statistics
        """
        payments = Payment.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status=Payment.Status.COMPLETED
        ).values('method').annotate(
            count=Count('id'),
            total=Sum('amount')
        ).order_by('-total')

        return list(payments)


class ItemReportService:
    """Service for item-based reports."""

    @staticmethod
    def get_top_selling_items(start_date, end_date, limit=10):
        """
        Get top selling items by quantity.

        Returns:
            list: Top selling items
        """
        items = OrderItem.objects.filter(
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date,
            order__status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        ).values(
            'menu_item__id',
            'menu_item__name',
            'menu_item__category__name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total_price')
        ).order_by('-total_quantity')[:limit]

        return list(items)

    @staticmethod
    def get_top_revenue_items(start_date, end_date, limit=10):
        """
        Get top items by revenue.

        Returns:
            list: Top revenue items
        """
        items = OrderItem.objects.filter(
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date,
            order__status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        ).values(
            'menu_item__id',
            'menu_item__name',
            'menu_item__category__name'
        ).annotate(
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total_price')
        ).order_by('-total_revenue')[:limit]

        return list(items)

    @staticmethod
    def get_category_performance(start_date, end_date):
        """
        Get sales performance by category.

        Returns:
            list: Category sales data
        """
        categories = OrderItem.objects.filter(
            order__created_at__date__gte=start_date,
            order__created_at__date__lte=end_date,
            order__status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        ).values(
            'menu_item__category__id',
            'menu_item__category__name'
        ).annotate(
            item_count=Count('id'),
            total_quantity=Sum('quantity'),
            total_revenue=Sum('total_price')
        ).order_by('-total_revenue')

        return list(categories)


class FinancialReportService:
    """Service for financial reports."""

    @staticmethod
    def get_revenue_summary(start_date, end_date):
        """
        Get comprehensive revenue summary.

        Returns:
            dict: Revenue summary
        """
        orders = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        )

        revenue = orders.aggregate(
            gross_revenue=Sum('total_amount'),
            subtotal=Sum('subtotal'),
            discounts=Sum('discount_amount'),
            cgst=Sum('cgst_amount'),
            sgst=Sum('sgst_amount'),
            service_charge=Sum('service_charge'),
        )

        # Clean up None values
        for key in revenue:
            if revenue[key] is None:
                revenue[key] = Decimal('0')

        revenue['total_tax'] = revenue['cgst'] + revenue['sgst']
        revenue['net_sales'] = revenue['subtotal'] - revenue['discounts']

        return revenue

    @staticmethod
    def get_expense_summary(start_date, end_date):
        """
        Get expense summary by category.

        Returns:
            dict: Expense summary
        """
        expenses = Expense.objects.filter(
            date__gte=start_date,
            date__lte=end_date,
            status=Expense.Status.PAID
        )

        total = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0')

        by_category = list(expenses.values(
            'category__name'
        ).annotate(
            total=Sum('amount'),
            count=Count('id')
        ).order_by('-total'))

        return {
            'total': total,
            'by_category': by_category,
            'count': expenses.count()
        }

    @staticmethod
    def get_tax_collection(start_date, end_date):
        """
        Get tax collection details.

        Returns:
            dict: Tax collection summary
        """
        orders = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        )

        tax = orders.aggregate(
            cgst=Sum('cgst_amount'),
            sgst=Sum('sgst_amount'),
            service_charge=Sum('service_charge'),
            order_count=Count('id')
        )

        for key in tax:
            if tax[key] is None:
                tax[key] = Decimal('0') if key != 'order_count' else 0

        tax['total_gst'] = tax['cgst'] + tax['sgst']
        tax['total_collected'] = tax['total_gst'] + tax['service_charge']

        return tax

    @staticmethod
    def get_cash_drawer_summary(date):
        """
        Get cash drawer summary for a specific date.

        Returns:
            dict: Cash drawer summary
        """
        try:
            drawer = CashDrawer.objects.get(date=date)
            return {
                'date': date,
                'opening_balance': drawer.opening_balance,
                'total_cash_sales': drawer.total_cash_sales,
                'total_cash_in': drawer.total_cash_in,
                'total_cash_out': drawer.total_cash_out,
                'expected_balance': drawer.expected_balance,
                'actual_balance': drawer.actual_balance,
                'variance': drawer.variance,
                'is_closed': drawer.is_closed,
            }
        except CashDrawer.DoesNotExist:
            return None

    @staticmethod
    def get_profit_loss(start_date, end_date):
        """
        Get profit/loss summary.

        Returns:
            dict: P&L summary
        """
        revenue = FinancialReportService.get_revenue_summary(start_date, end_date)
        expenses = FinancialReportService.get_expense_summary(start_date, end_date)

        return {
            'revenue': revenue,
            'expenses': expenses,
            'gross_profit': revenue['net_sales'] - expenses['total'],
            'period': {
                'start': start_date,
                'end': end_date
            }
        }


class StaffReportService:
    """Service for staff performance reports."""

    @staticmethod
    def get_staff_sales(start_date, end_date):
        """
        Get sales by staff member.

        Returns:
            list: Staff sales data
        """
        staff_sales = Order.objects.filter(
            created_at__date__gte=start_date,
            created_at__date__lte=end_date,
            status__in=[Order.Status.COMPLETED, Order.Status.SERVED],
            created_by__isnull=False
        ).values(
            'created_by__id',
            'created_by__first_name',
            'created_by__last_name',
            'created_by__username'
        ).annotate(
            order_count=Count('id'),
            total_revenue=Sum('total_amount'),
            avg_order_value=Avg('total_amount')
        ).order_by('-total_revenue')

        return list(staff_sales)

    @staticmethod
    def get_cashier_shifts(start_date, end_date):
        """
        Get cashier shift summaries.

        Returns:
            list: Shift data
        """
        shifts = CashierShift.objects.filter(
            shift_start__date__gte=start_date,
            shift_start__date__lte=end_date
        ).select_related('cashier', 'drawer').values(
            'id',
            'cashier__first_name',
            'cashier__last_name',
            'shift_start',
            'shift_end',
            'cash_sales',
            'expected_balance',
            'actual_balance',
            'variance'
        ).order_by('-shift_start')

        return list(shifts)
