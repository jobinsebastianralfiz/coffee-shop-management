"""
Order management models for the Coffee Shop Management System.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class Order(models.Model):
    """
    Main order model representing a customer's order.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready"
        SERVED = "served", "Served"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    class OrderType(models.TextChoices):
        DINE_IN = "dine_in", "Dine In"
        TAKEAWAY = "takeaway", "Takeaway"
        DELIVERY = "delivery", "Delivery"

    class OrderSource(models.TextChoices):
        POS = "pos", "POS"
        QR_CODE = "qr_code", "QR Code"
        ONLINE = "online", "Online"

    # Unique identifiers
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order_number = models.CharField(max_length=20, unique=True, editable=False)

    # Outlet
    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.PROTECT,
        related_name="orders",
        null=True,
        blank=True,
        help_text="Outlet this order belongs to",
    )

    # Relationships
    table = models.ForeignKey(
        "tables.Table",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Primary table for this order",
    )
    combined_tables = models.ManyToManyField(
        "tables.Table",
        blank=True,
        related_name="combined_orders",
        help_text="Additional tables combined for large parties",
    )
    table_session = models.ForeignKey(
        "tables.TableSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_created",
    )
    served_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_served",
    )

    # Order details
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    order_type = models.CharField(
        max_length=20,
        choices=OrderType.choices,
        default=OrderType.DINE_IN,
    )
    order_source = models.CharField(
        max_length=20,
        choices=OrderSource.choices,
        default=OrderSource.POS,
    )

    # Party/Guest identification (for multiple orders per table)
    party_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Label for this party/group (e.g., 'Party A', 'Window Side')",
    )

    # Customer info (for QR/online orders or takeaway)
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)
    customer_email = models.EmailField(blank=True)

    # Financial
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_reason = models.CharField(max_length=200, blank=True)
    cgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Notes
    customer_notes = models.TextField(blank=True, help_text="Special requests from customer")
    kitchen_notes = models.TextField(blank=True, help_text="Notes for kitchen staff")
    internal_notes = models.TextField(blank=True, help_text="Internal staff notes")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    prepared_at = models.DateTimeField(null=True, blank=True)
    served_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    # Estimated time
    estimated_prep_time = models.PositiveIntegerField(
        default=15,
        help_text="Estimated preparation time in minutes",
    )

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Order #{self.order_number}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    def _generate_order_number(self):
        """Generate unique order number using outlet prefix."""
        # Use outlet prefix if available, otherwise fall back to global settings
        if self.outlet:
            prefix = self.outlet.order_prefix or self.outlet.code or "ORD"
        else:
            from apps.core.models import OrderSettings
            settings = OrderSettings.load()
            prefix = settings.order_number_prefix or "ORD"

        # Get today's date for daily numbering
        today = timezone.now().date()
        date_str = today.strftime("%y%m%d")

        # Count today's orders for this outlet
        if self.outlet:
            today_count = Order.objects.filter(
                created_at__date=today,
                outlet=self.outlet
            ).count() + 1
        else:
            today_count = Order.objects.filter(
                created_at__date=today
            ).count() + 1

        return f"{prefix}{date_str}{today_count:04d}"

    def calculate_totals(self):
        """Recalculate order totals based on items using outlet or global tax settings."""
        # Use outlet tax settings if available, otherwise fall back to global settings
        if self.outlet and self.outlet.tax_enabled:
            cgst_rate = self.outlet.cgst_rate
            sgst_rate = self.outlet.sgst_rate
            service_charge_enabled = self.outlet.service_charge_enabled
            service_charge_rate = self.outlet.service_charge_rate
        else:
            from apps.core.models import TaxSettings
            tax_settings = TaxSettings.load()
            cgst_rate = tax_settings.cgst_rate
            sgst_rate = tax_settings.sgst_rate
            service_charge_enabled = tax_settings.service_charge_enabled
            service_charge_rate = tax_settings.service_charge_rate

        # Calculate subtotal from items
        self.subtotal = sum(
            item.total_price for item in self.items.all()
        )

        # Apply discount
        if self.discount_percentage > 0:
            self.discount_amount = (self.subtotal * self.discount_percentage) / 100

        taxable_amount = self.subtotal - self.discount_amount

        # Calculate taxes
        self.cgst_amount = (taxable_amount * cgst_rate) / 100
        self.sgst_amount = (taxable_amount * sgst_rate) / 100

        # Service charge
        if service_charge_enabled:
            self.service_charge = (taxable_amount * service_charge_rate) / 100
        else:
            self.service_charge = 0

        # Total
        self.total_amount = (
            taxable_amount +
            self.cgst_amount +
            self.sgst_amount +
            self.service_charge
        )

        return self.total_amount

    def update_status(self, new_status, user=None):
        """Update order status with timestamp."""
        self.status = new_status
        now = timezone.now()

        if new_status == self.Status.CONFIRMED:
            self.confirmed_at = now
        elif new_status == self.Status.PREPARING:
            pass  # No specific timestamp
        elif new_status == self.Status.READY:
            self.prepared_at = now
        elif new_status == self.Status.SERVED:
            self.served_at = now
            if user:
                self.served_by = user
        elif new_status == self.Status.COMPLETED:
            self.completed_at = now
        elif new_status == self.Status.CANCELLED:
            self.cancelled_at = now

        self.save()

    @property
    def is_paid(self):
        """Check if order is fully paid."""
        return self.paid_amount >= self.total_amount

    @property
    def balance_due(self):
        """Calculate remaining balance."""
        return max(self.total_amount - self.paid_amount, Decimal("0"))

    @property
    def item_count(self):
        """Total number of items."""
        return sum(item.quantity for item in self.items.all())

    @property
    def all_tables(self):
        """Get all tables (primary + combined) for this order."""
        tables = []
        if self.table:
            tables.append(self.table)
        tables.extend(self.combined_tables.all())
        return tables

    @property
    def all_table_numbers(self):
        """Get comma-separated table numbers."""
        numbers = []
        if self.table:
            numbers.append(str(self.table.number))
        numbers.extend([str(t.number) for t in self.combined_tables.all()])
        return ", ".join(numbers) if numbers else ""


class OrderItem(models.Model):
    """
    Individual item in an order.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready"
        SERVED = "served", "Served"
        CANCELLED = "cancelled", "Cancelled"

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="items",
    )
    menu_item = models.ForeignKey(
        "menu.MenuItem",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    variant = models.ForeignKey(
        "menu.MenuItemVariant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_items",
    )

    # Seat tracking for split bills
    seat_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Seat number for split billing (1, 2, 3...)",
    )

    # Item details (stored at order time for historical accuracy)
    item_name = models.CharField(max_length=200)
    variant_name = models.CharField(max_length=50, blank=True)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1)

    # Add-ons (stored as JSON for flexibility)
    addons = models.JSONField(default=list, blank=True)
    addons_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Total
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Notes
    special_instructions = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order Item"
        verbose_name_plural = "Order Items"
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.quantity}x {self.item_name} (Order #{self.order.order_number})"

    def save(self, *args, **kwargs):
        # Store item details at order time
        if not self.item_name and self.menu_item:
            self.item_name = self.menu_item.name
        if not self.variant_name and self.variant:
            self.variant_name = self.variant.name
        if not self.unit_price:
            if self.variant:
                self.unit_price = self.variant.price
            elif self.menu_item:
                self.unit_price = self.menu_item.base_price

        # Calculate total
        self.total_price = (self.unit_price * self.quantity) + self.addons_total

        super().save(*args, **kwargs)


class Payment(models.Model):
    """
    Payment record for an order.
    """

    class Method(models.TextChoices):
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        UPI = "upi", "UPI"
        WALLET = "wallet", "Wallet"
        SPLIT = "split", "Split Payment"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="payments",
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    method = models.CharField(
        max_length=20,
        choices=Method.choices,
        default=Method.CASH,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Transaction details
    transaction_id = models.CharField(max_length=100, blank=True)
    reference_number = models.CharField(max_length=100, blank=True)

    # Cash handling
    amount_tendered = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Amount given by customer (for cash payments)",
    )
    change_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Change returned to customer",
    )

    # User
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payments_processed",
    )

    notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment of ₹{self.amount} for Order #{self.order.order_number}"

    def save(self, *args, **kwargs):
        # Calculate change for cash payments
        if self.method == self.Method.CASH and self.amount_tendered:
            self.change_amount = self.amount_tendered - self.amount

        super().save(*args, **kwargs)

        # Update order paid amount
        if self.status == self.Status.COMPLETED:
            total_paid = self.order.payments.filter(
                status=self.Status.COMPLETED
            ).aggregate(
                total=models.Sum("amount")
            )["total"] or 0

            self.order.paid_amount = total_paid
            self.order.save(update_fields=["paid_amount", "updated_at"])


class KitchenOrderTicket(models.Model):
    """
    Kitchen ticket for tracking order preparation.
    """

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        RUSH = "rush", "Rush"

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name="kitchen_ticket",
    )

    ticket_number = models.CharField(max_length=10)
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
    )

    # Kitchen workflow
    printed_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Assignment
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kitchen_tickets",
    )

    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Kitchen Order Ticket"
        verbose_name_plural = "Kitchen Order Tickets"
        ordering = ["-order__created_at"]

    def __str__(self):
        return f"KOT #{self.ticket_number} - Order #{self.order.order_number}"

    def save(self, *args, **kwargs):
        if not self.ticket_number:
            # Generate KOT number
            today = timezone.now().date()
            today_count = KitchenOrderTicket.objects.filter(
                order__created_at__date=today
            ).count() + 1
            self.ticket_number = f"K{today_count:03d}"
        super().save(*args, **kwargs)
