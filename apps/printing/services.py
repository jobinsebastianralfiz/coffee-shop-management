"""
Thermal printing services for receipts and kitchen order tickets.
"""

import socket
import logging
from datetime import datetime
from decimal import Decimal

from django.utils import timezone

from apps.core.models import BusinessSettings, PrinterSettings, TaxSettings
from apps.printing.escpos import ReceiptBuilder, KOTBuilder

logger = logging.getLogger(__name__)


class PrinterError(Exception):
    """Exception raised for printer errors."""
    pass


class ThermalPrinter:
    """Base class for thermal printer communication."""

    def __init__(self, ip_address, port=9100, timeout=5):
        """
        Initialize thermal printer connection.

        Args:
            ip_address: Printer IP address
            port: Printer port (default 9100)
            timeout: Socket timeout in seconds
        """
        self.ip_address = ip_address
        self.port = port
        self.timeout = timeout
        self.socket = None

    def connect(self):
        """Establish connection to printer."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.ip_address, self.port))
            logger.info(f"Connected to printer at {self.ip_address}:{self.port}")
            return True
        except socket.error as e:
            logger.error(f"Failed to connect to printer: {e}")
            raise PrinterError(f"Could not connect to printer at {self.ip_address}:{self.port}: {e}")

    def disconnect(self):
        """Close printer connection."""
        if self.socket:
            try:
                self.socket.close()
            except Exception as e:
                logger.warning(f"Error closing socket: {e}")
            finally:
                self.socket = None

    def send(self, data):
        """Send data to printer."""
        if not self.socket:
            raise PrinterError("Printer not connected")

        try:
            self.socket.sendall(data)
            return True
        except socket.error as e:
            logger.error(f"Failed to send data to printer: {e}")
            raise PrinterError(f"Failed to send data to printer: {e}")

    def print_data(self, data):
        """
        Connect, send data, and disconnect.

        Args:
            data: Bytes to send to printer
        """
        try:
            self.connect()
            self.send(data)
            return True
        finally:
            self.disconnect()

    @classmethod
    def test_connection(cls, ip_address, port=9100, timeout=3):
        """
        Test if printer is reachable.

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip_address, port))
            sock.close()

            if result == 0:
                return True, f"Printer at {ip_address}:{port} is reachable"
            else:
                return False, f"Printer at {ip_address}:{port} is not reachable (error: {result})"
        except socket.error as e:
            return False, f"Connection test failed: {e}"


class ReceiptPrinter:
    """Service for printing customer receipts."""

    def __init__(self):
        """Initialize receipt printer service."""
        self.settings = PrinterSettings.load()
        self.business = BusinessSettings.load()
        self.tax_settings = TaxSettings.load()

    def is_enabled(self):
        """Check if receipt printing is enabled."""
        return self.settings.receipt_printer_enabled and self.settings.receipt_printer_ip

    def get_printer(self):
        """Get configured thermal printer instance."""
        if not self.is_enabled():
            raise PrinterError("Receipt printer is not configured")
        return ThermalPrinter(self.settings.receipt_printer_ip)

    def build_receipt(self, order):
        """
        Build receipt data for an order.

        Args:
            order: Order model instance

        Returns:
            bytes: ESC/POS receipt data
        """
        builder = ReceiptBuilder(width=32)
        now = timezone.now()

        # Header
        builder.init()
        builder.align_center()
        builder.bold_on()
        builder.double_size()
        builder.line(self.business.name or "Coffee Shop")
        builder.normal_size()
        builder.bold_off()

        if self.business.address:
            builder.line(self.business.address)
        if self.business.phone:
            builder.line(f"Tel: {self.business.phone}")

        builder.newline()
        builder.horizontal_line()

        # Order Info
        builder.align_left()
        builder.row("Order:", f"#{order.order_number}")
        builder.row("Date:", now.strftime("%d/%m/%Y"))
        builder.row("Time:", now.strftime("%H:%M:%S"))

        if order.table:
            builder.row("Table:", str(order.table.number))
        elif order.order_type == "takeaway":
            builder.row("Type:", "Takeaway")

        if order.customer_name:
            builder.row("Customer:", order.customer_name)

        if order.served_by:
            builder.row("Server:", order.served_by.get_full_name())

        builder.horizontal_line()

        # Items
        builder.bold_on()
        builder.line("ITEMS")
        builder.bold_off()
        builder.newline()

        for item in order.items.all():
            price_str = f"{order.total_amount.normalize():,.2f}" if hasattr(item, 'total_price') else ""
            builder.item_row(
                qty=item.quantity,
                name=item.item_name,
                price=f"{item.total_price:,.2f}"
            )
            if item.variant_name:
                builder.line(f"   ({item.variant_name})")
            if item.special_instructions:
                builder.line(f"   Note: {item.special_instructions}")

        builder.horizontal_line()

        # Totals
        currency = self.business.currency_symbol or "Rs."

        builder.row("Subtotal:", f"{currency}{order.subtotal:,.2f}")

        if order.discount_amount > 0:
            builder.row("Discount:", f"-{currency}{order.discount_amount:,.2f}")

        if order.cgst_amount > 0:
            builder.row(f"CGST ({self.tax_settings.cgst_rate}%):", f"{currency}{order.cgst_amount:,.2f}")

        if order.sgst_amount > 0:
            builder.row(f"SGST ({self.tax_settings.sgst_rate}%):", f"{currency}{order.sgst_amount:,.2f}")

        if order.service_charge > 0:
            builder.row("Service Charge:", f"{currency}{order.service_charge:,.2f}")

        builder.double_horizontal_line()
        builder.bold_on()
        builder.row("TOTAL:", f"{currency}{order.total_amount:,.2f}")
        builder.bold_off()
        builder.double_horizontal_line()

        # Payment Info
        if order.payments.exists():
            builder.newline()
            for payment in order.payments.filter(status="completed"):
                builder.row(f"Paid ({payment.method}):", f"{currency}{payment.amount:,.2f}")

            if order.balance_due > 0:
                builder.row("Balance Due:", f"{currency}{order.balance_due:,.2f}")

        # Footer
        builder.newline()
        builder.horizontal_line()
        builder.align_center()

        if self.business.receipt_footer:
            builder.line(self.business.receipt_footer)
        else:
            builder.line("Thank you for visiting!")
            builder.line("Please come again")

        builder.newline()

        if self.business.gst_number:
            builder.line(f"GST: {self.business.gst_number}")

        builder.newline()
        builder.cut()

        return builder.get_data()

    def print_receipt(self, order):
        """
        Print receipt for an order.

        Args:
            order: Order model instance

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            if not self.is_enabled():
                return False, "Receipt printer is not configured"

            receipt_data = self.build_receipt(order)
            printer = self.get_printer()
            printer.print_data(receipt_data)

            logger.info(f"Receipt printed for order #{order.order_number}")
            return True, "Receipt printed successfully"

        except PrinterError as e:
            logger.error(f"Receipt print failed: {e}")
            return False, str(e)
        except Exception as e:
            logger.exception(f"Unexpected error printing receipt: {e}")
            return False, f"Print error: {e}"


class KOTPrinter:
    """Service for printing Kitchen Order Tickets."""

    def __init__(self):
        """Initialize KOT printer service."""
        self.settings = PrinterSettings.load()

    def is_enabled(self):
        """Check if KOT printing is enabled."""
        return self.settings.kot_printer_enabled and self.settings.kot_printer_ip

    def get_printer(self):
        """Get configured thermal printer instance."""
        if not self.is_enabled():
            raise PrinterError("KOT printer is not configured")
        return ThermalPrinter(self.settings.kot_printer_ip)

    def build_kot(self, order):
        """
        Build KOT data for an order.

        Args:
            order: Order model instance

        Returns:
            bytes: ESC/POS KOT data
        """
        builder = KOTBuilder(width=32)
        now = timezone.now()

        # Get ticket info
        ticket_number = "---"
        priority = "NORMAL"
        if hasattr(order, 'kitchen_ticket') and order.kitchen_ticket:
            ticket_number = order.kitchen_ticket.ticket_number
            priority = order.kitchen_ticket.priority

        # Table info
        if order.table:
            table_info = f"Table {order.table.number}"
            if order.party_name:
                table_info += f" - {order.party_name}"
        else:
            table_info = f"Takeaway - {order.customer_name or order.order_number}"

        # Build KOT
        builder.header(
            ticket_number=ticket_number,
            table_info=table_info,
            priority=priority
        )

        # Items
        items_list = [
            {
                "quantity": item.quantity,
                "name": item.item_name + (f" ({item.variant_name})" if item.variant_name else ""),
                "special_instructions": item.special_instructions,
            }
            for item in order.items.all()
        ]
        builder.items(items_list)

        # Notes
        if order.kitchen_notes:
            builder.notes(order.kitchen_notes)

        # Footer
        builder.footer(now.strftime("%d/%m/%Y %H:%M:%S"))

        return builder.get_data()

    def print_kot(self, order):
        """
        Print KOT for an order.

        Args:
            order: Order model instance

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            if not self.is_enabled():
                return False, "KOT printer is not configured"

            kot_data = self.build_kot(order)
            printer = self.get_printer()
            printer.print_data(kot_data)

            # Update printed_at timestamp
            if hasattr(order, 'kitchen_ticket') and order.kitchen_ticket:
                order.kitchen_ticket.printed_at = timezone.now()
                order.kitchen_ticket.save(update_fields=['printed_at'])

            logger.info(f"KOT printed for order #{order.order_number}")
            return True, "KOT printed successfully"

        except PrinterError as e:
            logger.error(f"KOT print failed: {e}")
            return False, str(e)
        except Exception as e:
            logger.exception(f"Unexpected error printing KOT: {e}")
            return False, f"Print error: {e}"


def print_receipt(order):
    """Convenience function to print a receipt."""
    service = ReceiptPrinter()
    return service.print_receipt(order)


def print_kot(order):
    """Convenience function to print a KOT."""
    service = KOTPrinter()
    return service.print_kot(order)


def test_receipt_printer():
    """Test receipt printer connection."""
    settings = PrinterSettings.load()
    if not settings.receipt_printer_ip:
        return False, "Receipt printer IP not configured"
    return ThermalPrinter.test_connection(settings.receipt_printer_ip)


def test_kot_printer():
    """Test KOT printer connection."""
    settings = PrinterSettings.load()
    if not settings.kot_printer_ip:
        return False, "KOT printer IP not configured"
    return ThermalPrinter.test_connection(settings.kot_printer_ip)
