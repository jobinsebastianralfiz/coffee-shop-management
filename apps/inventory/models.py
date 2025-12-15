"""
Inventory management models for the Coffee Shop Management System.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class InventoryCategory(models.Model):
    """
    Category for inventory items (e.g., Coffee Beans, Dairy, Syrups).
    Each category belongs to a specific outlet.
    """
    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="inventory_categories",
        null=True,
        blank=True,
        help_text="Outlet this category belongs to",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inventory Category"
        verbose_name_plural = "Inventory Categories"
        ordering = ["display_order", "name"]
        unique_together = ["outlet", "name"]

    def __str__(self):
        return self.name


class InventoryItem(models.Model):
    """
    Individual inventory item/ingredient.
    """

    class Unit(models.TextChoices):
        KILOGRAM = "kg", "Kilogram"
        GRAM = "g", "Gram"
        LITER = "l", "Liter"
        MILLILITER = "ml", "Milliliter"
        PIECE = "pc", "Piece"
        PACKET = "pkt", "Packet"
        BOX = "box", "Box"
        DOZEN = "doz", "Dozen"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    category = models.ForeignKey(
        InventoryCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )

    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True, blank=True)
    description = models.TextField(blank=True)

    # Stock levels
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PIECE)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Alert when stock falls below this level",
    )
    maximum_stock = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Maximum storage capacity",
    )

    # Pricing
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Cost per unit",
    )
    last_purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Supplier info
    supplier = models.ForeignKey(
        "Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="items",
    )
    supplier_sku = models.CharField(max_length=100, blank=True)

    # Tracking
    is_active = models.BooleanField(default=True)
    is_perishable = models.BooleanField(default=False)
    expiry_alert_days = models.PositiveIntegerField(
        default=7,
        help_text="Days before expiry to trigger alert",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inventory Item"
        verbose_name_plural = "Inventory Items"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.current_stock} {self.unit})"

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = self._generate_sku()
        super().save(*args, **kwargs)

    def _generate_sku(self):
        """Generate a unique SKU."""
        prefix = "INV"
        count = InventoryItem.objects.count() + 1
        return f"{prefix}{count:05d}"

    @property
    def is_low_stock(self):
        """Check if stock is below minimum level."""
        return self.current_stock <= self.minimum_stock

    @property
    def stock_status(self):
        """Get stock status."""
        if self.current_stock <= 0:
            return "out_of_stock"
        elif self.current_stock <= self.minimum_stock:
            return "low_stock"
        elif self.maximum_stock > 0 and self.current_stock >= self.maximum_stock:
            return "overstocked"
        else:
            return "in_stock"

    @property
    def stock_value(self):
        """Calculate current stock value."""
        return self.current_stock * self.cost_price


class Supplier(models.Model):
    """
    Supplier/vendor information.
    Each supplier belongs to a specific outlet.
    """
    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="suppliers",
        null=True,
        blank=True,
        help_text="Outlet this supplier is associated with",
    )
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)
    gst_number = models.CharField(max_length=20, blank=True)

    # Payment terms
    payment_terms = models.CharField(max_length=100, blank=True)
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Supplier"
        verbose_name_plural = "Suppliers"
        ordering = ["name"]

    def __str__(self):
        return self.name


class StockMovement(models.Model):
    """
    Record of all stock movements (in/out).
    """

    class MovementType(models.TextChoices):
        PURCHASE = "purchase", "Purchase"
        SALE = "sale", "Sale"
        ADJUSTMENT = "adjustment", "Adjustment"
        WASTAGE = "wastage", "Wastage"
        TRANSFER = "transfer", "Transfer"
        RETURN = "return", "Return"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name="movements",
    )

    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
    )
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Stock levels at time of movement
    stock_before = models.DecimalField(max_digits=10, decimal_places=2)
    stock_after = models.DecimalField(max_digits=10, decimal_places=2)

    # Reference
    reference_number = models.CharField(max_length=50, blank=True)
    purchase_order = models.ForeignKey(
        "PurchaseOrder",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movements",
    )

    reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    # Who made the movement
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="stock_movements",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Stock Movement"
        verbose_name_plural = "Stock Movements"
        ordering = ["-created_at"]

    def __str__(self):
        direction = "+" if self.quantity > 0 else ""
        return f"{self.item.name}: {direction}{self.quantity} ({self.get_movement_type_display()})"


class PurchaseOrder(models.Model):
    """
    Purchase order for restocking inventory.
    Each purchase order belongs to a specific outlet.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending Approval"
        APPROVED = "approved", "Approved"
        ORDERED = "ordered", "Ordered"
        PARTIAL = "partial", "Partially Received"
        RECEIVED = "received", "Received"
        CANCELLED = "cancelled", "Cancelled"

    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="purchase_orders",
        null=True,
        blank=True,
        help_text="Outlet this purchase order is for",
    )
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order_number = models.CharField(max_length=20, unique=True, editable=False)

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    # Dates
    order_date = models.DateField(null=True, blank=True)
    expected_date = models.DateField(null=True, blank=True)
    received_date = models.DateField(null=True, blank=True)

    # Totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True)

    # User tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="purchase_orders_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchase_orders_approved",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Purchase Order"
        verbose_name_plural = "Purchase Orders"
        ordering = ["-created_at"]

    def __str__(self):
        return f"PO #{self.order_number} - {self.supplier.name}"

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = self._generate_order_number()
        super().save(*args, **kwargs)

    def _generate_order_number(self):
        """Generate unique PO number."""
        today = timezone.now().date()
        date_str = today.strftime("%y%m%d")
        count = PurchaseOrder.objects.filter(
            created_at__date=today
        ).count() + 1
        return f"PO{date_str}{count:03d}"

    def calculate_totals(self):
        """Calculate order totals from items."""
        self.subtotal = sum(item.total_price for item in self.items.all())
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        return self.total_amount


class PurchaseOrderItem(models.Model):
    """
    Individual item in a purchase order.
    """
    purchase_order = models.ForeignKey(
        PurchaseOrder,
        on_delete=models.CASCADE,
        related_name="items",
    )
    inventory_item = models.ForeignKey(
        InventoryItem,
        on_delete=models.PROTECT,
        related_name="purchase_order_items",
    )

    quantity_ordered = models.DecimalField(max_digits=10, decimal_places=2)
    quantity_received = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        verbose_name = "Purchase Order Item"
        verbose_name_plural = "Purchase Order Items"

    def __str__(self):
        return f"{self.quantity_ordered} x {self.inventory_item.name}"

    def save(self, *args, **kwargs):
        self.total_price = self.quantity_ordered * self.unit_price
        super().save(*args, **kwargs)


class StockAlert(models.Model):
    """
    Alerts for low stock, expiring items, etc.
    """

    class AlertType(models.TextChoices):
        LOW_STOCK = "low_stock", "Low Stock"
        OUT_OF_STOCK = "out_of_stock", "Out of Stock"
        EXPIRING = "expiring", "Expiring Soon"
        EXPIRED = "expired", "Expired"
        OVERSTOCK = "overstock", "Overstocked"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    item = models.ForeignKey(
        InventoryItem,
        on_delete=models.CASCADE,
        related_name="alerts",
    )

    alert_type = models.CharField(max_length=20, choices=AlertType.choices)
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.MEDIUM,
    )

    message = models.CharField(max_length=500)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_alerts",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Stock Alert"
        verbose_name_plural = "Stock Alerts"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_alert_type_display()}: {self.item.name}"

    def resolve(self, user=None):
        """Mark alert as resolved."""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.save()
