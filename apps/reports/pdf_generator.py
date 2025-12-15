"""
PDF report generation using ReportLab.
"""

from io import BytesIO
from datetime import datetime
from decimal import Decimal

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image, HRFlowable
)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT

from django.utils import timezone

from apps.core.models import BusinessSettings


class BasePDFReport:
    """Base class for PDF report generation."""

    def __init__(self, title, subtitle=None):
        """Initialize PDF report."""
        self.title = title
        self.subtitle = subtitle
        self.buffer = BytesIO()
        self.elements = []
        self.styles = getSampleStyleSheet()
        self.business = BusinessSettings.load()

        # Custom styles
        self.styles.add(ParagraphStyle(
            name='ReportTitle',
            parent=self.styles['Heading1'],
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=6
        ))
        self.styles.add(ParagraphStyle(
            name='ReportSubtitle',
            parent=self.styles['Normal'],
            fontSize=12,
            alignment=TA_CENTER,
            textColor=colors.grey,
            spaceAfter=20
        ))
        self.styles.add(ParagraphStyle(
            name='SectionTitle',
            parent=self.styles['Heading2'],
            fontSize=14,
            spaceBefore=15,
            spaceAfter=10
        ))
        self.styles.add(ParagraphStyle(
            name='TableHeader',
            parent=self.styles['Normal'],
            fontSize=10,
            textColor=colors.white,
            alignment=TA_CENTER
        ))
        self.styles.add(ParagraphStyle(
            name='RightAlign',
            parent=self.styles['Normal'],
            alignment=TA_RIGHT
        ))

    def add_header(self):
        """Add report header with business info."""
        # Business name
        self.elements.append(Paragraph(
            self.business.name or "Coffee Shop",
            self.styles['ReportTitle']
        ))

        # Title
        self.elements.append(Paragraph(self.title, self.styles['Heading1']))

        if self.subtitle:
            self.elements.append(Paragraph(self.subtitle, self.styles['ReportSubtitle']))

        # Generation time
        now = timezone.now()
        self.elements.append(Paragraph(
            f"Generated: {now.strftime('%d %b %Y, %I:%M %p')}",
            self.styles['ReportSubtitle']
        ))

        self.elements.append(Spacer(1, 0.3 * inch))

    def add_section(self, title):
        """Add a section title."""
        self.elements.append(Paragraph(title, self.styles['SectionTitle']))

    def add_table(self, data, col_widths=None, header_color=colors.HexColor('#4F46E5')):
        """Add a formatted table."""
        if not data:
            return

        table = Table(data, colWidths=col_widths)

        style = TableStyle([
            # Header row
            ('BACKGROUND', (0, 0), (-1, 0), header_color),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            ('TOPPADDING', (0, 0), (-1, 0), 8),

            # Data rows
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('TOPPADDING', (0, 1), (-1, -1), 6),

            # Grid
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),

            # Alternating row colors
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F9FA')]),
        ])

        table.setStyle(style)
        self.elements.append(table)
        self.elements.append(Spacer(1, 0.2 * inch))

    def add_summary_box(self, items):
        """Add a summary box with key-value pairs."""
        data = [[k, v] for k, v in items]
        table = Table(data, colWidths=[3 * inch, 2 * inch])

        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F3F4F6')),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
            ('TEXTCOLOR', (1, 0), (1, -1), colors.black),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('PADDING', (0, 0), (-1, -1), 8),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#E5E7EB')),
        ]))

        self.elements.append(table)
        self.elements.append(Spacer(1, 0.2 * inch))

    def add_horizontal_line(self):
        """Add a horizontal line."""
        self.elements.append(HRFlowable(
            width="100%",
            thickness=1,
            color=colors.lightgrey,
            spaceBefore=10,
            spaceAfter=10
        ))

    def add_spacer(self, height=0.2):
        """Add vertical space."""
        self.elements.append(Spacer(1, height * inch))

    def add_text(self, text, style='Normal'):
        """Add a paragraph of text."""
        self.elements.append(Paragraph(text, self.styles[style]))

    def add_page_break(self):
        """Add a page break."""
        self.elements.append(PageBreak())

    def generate(self):
        """Generate the PDF document."""
        doc = SimpleDocTemplate(
            self.buffer,
            pagesize=A4,
            rightMargin=0.5 * inch,
            leftMargin=0.5 * inch,
            topMargin=0.5 * inch,
            bottomMargin=0.5 * inch
        )

        doc.build(self.elements)
        self.buffer.seek(0)
        return self.buffer


class SalesReportPDF(BasePDFReport):
    """Sales report PDF generator."""

    def __init__(self, start_date, end_date):
        """Initialize sales report."""
        if start_date == end_date:
            date_str = start_date.strftime('%d %b %Y')
        else:
            date_str = f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b %Y')}"

        super().__init__(
            title="Sales Report",
            subtitle=date_str
        )
        self.start_date = start_date
        self.end_date = end_date

    def generate_report(self, sales_data, items_data, payment_data):
        """Generate complete sales report."""
        self.add_header()

        # Summary Section
        self.add_section("Sales Summary")
        currency = self.business.currency_symbol or "Rs."

        summary_items = [
            ("Total Orders", str(sales_data.get('total_orders', 0))),
            ("Gross Revenue", f"{currency}{sales_data.get('total_revenue', 0):,.2f}"),
            ("Discounts", f"-{currency}{sales_data.get('total_discount', 0):,.2f}"),
            ("Net Revenue", f"{currency}{sales_data.get('net_revenue', 0):,.2f}"),
            ("Total Tax", f"{currency}{sales_data.get('total_tax', 0):,.2f}"),
            ("Average Order Value", f"{currency}{sales_data.get('avg_order_value', 0):,.2f}"),
        ]
        self.add_summary_box(summary_items)

        # Order Type Breakdown
        if sales_data.get('by_type'):
            self.add_section("Orders by Type")
            data = [["Order Type", "Count", "Revenue"]]
            for item in sales_data['by_type']:
                data.append([
                    item['order_type'].replace('_', ' ').title(),
                    str(item['count']),
                    f"{currency}{item['revenue']:,.2f}"
                ])
            self.add_table(data, col_widths=[2.5 * inch, 1.5 * inch, 2 * inch])

        # Payment Method Breakdown
        if payment_data:
            self.add_section("Payment Methods")
            data = [["Method", "Transactions", "Amount"]]
            for item in payment_data:
                data.append([
                    item['method'].upper(),
                    str(item['count']),
                    f"{currency}{item['total']:,.2f}"
                ])
            self.add_table(data, col_widths=[2.5 * inch, 1.5 * inch, 2 * inch])

        # Top Selling Items
        if items_data:
            self.add_section("Top Selling Items")
            data = [["Item", "Category", "Qty Sold", "Revenue"]]
            for item in items_data[:10]:
                data.append([
                    item.get('menu_item__name', 'N/A'),
                    item.get('menu_item__category__name', 'N/A'),
                    str(item.get('total_quantity', 0)),
                    f"{currency}{item.get('total_revenue', 0):,.2f}"
                ])
            self.add_table(data, col_widths=[2.2 * inch, 1.5 * inch, 1 * inch, 1.3 * inch])

        return self.generate()


class EODReportPDF(BasePDFReport):
    """End of Day report PDF generator."""

    def __init__(self, date):
        """Initialize EOD report."""
        super().__init__(
            title="End of Day Report",
            subtitle=date.strftime('%A, %d %B %Y')
        )
        self.date = date

    def generate_report(self, sales_data, cash_data, staff_data):
        """Generate EOD report."""
        self.add_header()
        currency = self.business.currency_symbol or "Rs."

        # Sales Summary
        self.add_section("Today's Sales")
        summary_items = [
            ("Total Orders", str(sales_data.get('total_orders', 0))),
            ("Gross Sales", f"{currency}{sales_data.get('total_revenue', 0):,.2f}"),
            ("Net Sales", f"{currency}{sales_data.get('net_revenue', 0):,.2f}"),
            ("Total Tax Collected", f"{currency}{sales_data.get('total_tax', 0):,.2f}"),
        ]
        self.add_summary_box(summary_items)

        # Cash Drawer Summary
        if cash_data:
            self.add_section("Cash Drawer")
            drawer_items = [
                ("Opening Balance", f"{currency}{cash_data.get('opening_balance', 0):,.2f}"),
                ("Cash Sales", f"{currency}{cash_data.get('total_cash_sales', 0):,.2f}"),
                ("Cash In", f"+{currency}{cash_data.get('total_cash_in', 0):,.2f}"),
                ("Cash Out", f"-{currency}{cash_data.get('total_cash_out', 0):,.2f}"),
                ("Expected Balance", f"{currency}{cash_data.get('expected_balance', 0):,.2f}"),
                ("Actual Balance", f"{currency}{cash_data.get('actual_balance', 0):,.2f}"),
                ("Variance", f"{currency}{cash_data.get('variance', 0):,.2f}"),
            ]
            self.add_summary_box(drawer_items)

        # Staff Performance
        if staff_data:
            self.add_section("Staff Performance")
            data = [["Staff", "Orders", "Revenue"]]
            for staff in staff_data:
                name = f"{staff.get('created_by__first_name', '')} {staff.get('created_by__last_name', '')}".strip()
                if not name:
                    name = staff.get('created_by__username', 'Unknown')
                data.append([
                    name,
                    str(staff.get('order_count', 0)),
                    f"{currency}{staff.get('total_revenue', 0):,.2f}"
                ])
            self.add_table(data, col_widths=[2.5 * inch, 1.5 * inch, 2 * inch])

        return self.generate()


class TaxReportPDF(BasePDFReport):
    """Tax collection report PDF generator."""

    def __init__(self, start_date, end_date):
        """Initialize tax report."""
        super().__init__(
            title="Tax Collection Report",
            subtitle=f"{start_date.strftime('%d %b')} - {end_date.strftime('%d %b %Y')}"
        )
        self.start_date = start_date
        self.end_date = end_date

    def generate_report(self, tax_data):
        """Generate tax report."""
        self.add_header()
        currency = self.business.currency_symbol or "Rs."

        # Tax Summary
        self.add_section("GST Collection Summary")
        summary_items = [
            ("Total Orders", str(tax_data.get('order_count', 0))),
            ("CGST Collected", f"{currency}{tax_data.get('cgst', 0):,.2f}"),
            ("SGST Collected", f"{currency}{tax_data.get('sgst', 0):,.2f}"),
            ("Total GST", f"{currency}{tax_data.get('total_gst', 0):,.2f}"),
            ("Service Charge", f"{currency}{tax_data.get('service_charge', 0):,.2f}"),
            ("Total Tax Collected", f"{currency}{tax_data.get('total_collected', 0):,.2f}"),
        ]
        self.add_summary_box(summary_items)

        # Business Info
        self.add_spacer(0.5)
        self.add_section("Business Information")
        if self.business.gst_number:
            self.add_text(f"GST Number: {self.business.gst_number}")
        if self.business.fssai_number:
            self.add_text(f"FSSAI Number: {self.business.fssai_number}")
        if self.business.address:
            self.add_text(f"Address: {self.business.address}")

        return self.generate()
