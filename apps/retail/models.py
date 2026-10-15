"""
Retail and Wholesale models for the Coffee Shop Management System.
"""

import datetime
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator


class RetailCategory(models.Model):
    """
    Category for retail products (e.g., Coffee Beans, Equipment, Merchandise).
    """
    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="retail_categories",
        null=True,
        blank=True,
        help_text="Outlet this category belongs to",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subcategories",
    )
    image = models.ImageField(upload_to="retail_categories/", null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Retail Category"
        verbose_name_plural = "Retail Categories"
        ordering = ["display_order", "name"]
        unique_together = ["outlet", "name"]

    def __str__(self):
        return self.name

    @property
    def product_count(self):
        """Get count of active products in this category."""
        return self.products.filter(is_active=True).count()


class RetailProduct(models.Model):
    """
    Retail product that can be sold at retail or wholesale prices.
    Optionally linked to a MenuItem for hybrid cafe+retail items.
    """

    class Unit(models.TextChoices):
        PIECE = "pc", "Piece"
        PACKET = "pkt", "Packet"
        BOX = "box", "Box"
        KILOGRAM = "kg", "Kilogram"
        GRAM = "g", "Gram"
        LITER = "l", "Liter"
        MILLILITER = "ml", "Milliliter"
        DOZEN = "doz", "Dozen"

    class TaxType(models.TextChoices):
        GST_0 = "gst_0", "GST 0%"
        GST_5 = "gst_5", "GST 5%"
        GST_12 = "gst_12", "GST 12%"
        GST_18 = "gst_18", "GST 18%"
        GST_28 = "gst_28", "GST 28%"
        EXEMPT = "exempt", "Tax Exempt"

    # Basic Info
    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="retail_products",
        help_text="Outlet this product belongs to",
    )
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    sku = models.CharField(max_length=50, unique=True, blank=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="retail_products/", null=True, blank=True)

    # Category
    category = models.ForeignKey(
        RetailCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )

    # Hybrid Linking - Connect to cafe menu item
    linked_menu_item = models.OneToOneField(
        "menu.MenuItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retail_product",
        help_text="Link to menu item for hybrid cafe+retail products",
    )

    # Pricing
    cost_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Cost/purchase price per unit",
    )
    mrp = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Maximum Retail Price",
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Retail selling price",
    )
    wholesale_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Price for wholesale/B2B customers",
    )

    # Tax
    tax_type = models.CharField(
        max_length=10,
        choices=TaxType.choices,
        default=TaxType.GST_18,
    )
    hsn_code = models.CharField(
        max_length=20,
        blank=True,
        help_text="Harmonized System Nomenclature code for GST",
    )

    # Stock
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.PIECE)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text="Alert when stock falls below this level",
    )
    track_inventory = models.BooleanField(
        default=True,
        help_text="Enable stock tracking for this product",
    )

    # Supplier
    supplier = models.ForeignKey(
        "inventory.Supplier",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retail_products",
    )

    # Status
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Retail Product"
        verbose_name_plural = "Retail Products"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.sku})"

    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = self._generate_sku()
        super().save(*args, **kwargs)

    def _generate_sku(self):
        """Generate a unique SKU."""
        prefix = "RTL"
        count = RetailProduct.objects.count() + 1
        return f"{prefix}{count:06d}"

    @property
    def primary_barcode(self):
        """Get the primary barcode for this product."""
        return self.barcodes.filter(is_primary=True).first()

    @property
    def tax_rate(self):
        """Get numeric tax rate."""
        rates = {
            "gst_0": Decimal("0"),
            "gst_5": Decimal("5"),
            "gst_12": Decimal("12"),
            "gst_18": Decimal("18"),
            "gst_28": Decimal("28"),
            "exempt": Decimal("0"),
        }
        return rates.get(self.tax_type, Decimal("18"))

    @property
    def is_low_stock(self):
        """Check if stock is below minimum level."""
        return self.track_inventory and self.current_stock <= self.minimum_stock

    @property
    def stock_status(self):
        """Get stock status string."""
        if not self.track_inventory:
            return "not_tracked"
        if self.current_stock <= 0:
            return "out_of_stock"
        if self.current_stock <= self.minimum_stock:
            return "low_stock"
        return "in_stock"

    @property
    def profit_margin(self):
        """Calculate profit margin percentage."""
        if self.cost_price > 0:
            return ((self.selling_price - self.cost_price) / self.cost_price) * 100
        return Decimal("0")

    def get_price_for_customer(self, customer=None):
        """Get the appropriate price based on customer type."""
        if customer and self.wholesale_price:
            return self.wholesale_price
        return self.selling_price


class ProductBarcode(models.Model):
    """
    Barcode records for retail products.
    Supports multiple barcode types per product.
    """

    class BarcodeType(models.TextChoices):
        EAN13 = "ean13", "EAN-13"
        EAN8 = "ean8", "EAN-8"
        CODE128 = "code128", "Code 128"
        CODE39 = "code39", "Code 39"
        UPC_A = "upca", "UPC-A"
        QR = "qr", "QR Code"

    product = models.ForeignKey(
        RetailProduct,
        on_delete=models.CASCADE,
        related_name="barcodes",
    )
    barcode_type = models.CharField(
        max_length=10,
        choices=BarcodeType.choices,
        default=BarcodeType.EAN13,
    )
    barcode_value = models.CharField(
        max_length=100,
        unique=True,
        help_text="Barcode number/value",
    )
    barcode_image = models.ImageField(
        upload_to="barcodes/",
        null=True,
        blank=True,
    )
    is_primary = models.BooleanField(default=False)
    is_generated = models.BooleanField(
        default=False,
        help_text="True if barcode was system-generated",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Product Barcode"
        verbose_name_plural = "Product Barcodes"
        ordering = ["-is_primary", "barcode_type"]

    def __str__(self):
        return f"{self.barcode_value} ({self.get_barcode_type_display()})"

    def save(self, *args, **kwargs):
        # Ensure only one primary barcode per product
        if self.is_primary:
            ProductBarcode.objects.filter(
                product=self.product, is_primary=True
            ).exclude(pk=self.pk).update(is_primary=False)
        super().save(*args, **kwargs)


class WholesaleCustomer(models.Model):
    """
    B2B/Wholesale customer with credit account.
    """

    class CustomerType(models.TextChoices):
        RETAILER = "retailer", "Retailer"
        DISTRIBUTOR = "distributor", "Distributor"
        RESTAURANT = "restaurant", "Restaurant/Cafe"
        CORPORATE = "corporate", "Corporate"
        OTHER = "other", "Other"

    # Basic Info
    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="wholesale_customers",
        help_text="Outlet managing this customer",
    )
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    customer_code = models.CharField(max_length=20, unique=True, blank=True)

    # Contact Person
    name = models.CharField(max_length=100, help_text="Contact person name")
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)

    # Business Info
    business_name = models.CharField(max_length=200)
    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.RETAILER,
    )
    gst_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="GST Identification Number",
    )
    pan_number = models.CharField(max_length=20, blank=True)

    # Address
    address_line1 = models.CharField(max_length=200)
    address_line2 = models.CharField(max_length=200, blank=True)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    postal_code = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default="India")

    # Credit Terms
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Maximum credit amount allowed",
    )
    current_balance = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Current outstanding balance (positive = customer owes)",
    )
    payment_terms_days = models.PositiveIntegerField(
        default=30,
        help_text="Payment due in days from invoice date",
    )

    # Pricing
    price_tier = models.CharField(
        max_length=20,
        default="wholesale",
        help_text="Price tier for this customer",
    )
    discount_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Default discount percentage for this customer",
    )

    # Status
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wholesale Customer"
        verbose_name_plural = "Wholesale Customers"
        ordering = ["business_name"]

    def __str__(self):
        return f"{self.business_name} ({self.customer_code})"

    def save(self, *args, **kwargs):
        if not self.customer_code:
            self.customer_code = self._generate_customer_code()
        super().save(*args, **kwargs)

    def _generate_customer_code(self):
        """Generate unique customer code."""
        prefix = "WSC"
        count = WholesaleCustomer.objects.count() + 1
        return f"{prefix}{count:05d}"

    @property
    def available_credit(self):
        """Calculate remaining available credit."""
        return max(Decimal("0"), self.credit_limit - self.current_balance)

    @property
    def is_credit_exceeded(self):
        """Check if customer has exceeded credit limit."""
        return self.current_balance > self.credit_limit

    @property
    def full_address(self):
        """Get full formatted address."""
        parts = [
            self.address_line1,
            self.address_line2,
            self.city,
            self.state,
            self.postal_code,
            self.country,
        ]
        return ", ".join(p for p in parts if p)

    def update_balance(self):
        """Recalculate current balance from invoices."""
        from django.db.models import Sum, F

        # Sum of all unpaid/partial invoice amounts
        outstanding = self.invoices.filter(
            status__in=[
                WholesaleInvoice.Status.PENDING,
                WholesaleInvoice.Status.PARTIAL,
                WholesaleInvoice.Status.OVERDUE,
            ]
        ).aggregate(
            total=Sum(F("amount") - F("paid_amount"))
        )
        self.current_balance = outstanding["total"] or Decimal("0")
        self.save(update_fields=["current_balance", "updated_at"])


class RetailSale(models.Model):
    """
    Retail/Wholesale sale transaction.
    """

    class SaleType(models.TextChoices):
        RETAIL = "retail", "Retail Sale"
        WHOLESALE = "wholesale", "Wholesale Sale"

    class PaymentStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIAL = "partial", "Partially Paid"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"
        CANCELLED = "cancelled", "Cancelled"

    class PaymentMethod(models.TextChoices):
        # Values for the free-text payment_method field (POS and cafe combined billing)
        CASH = "cash", "Cash"
        CARD = "card", "Card"
        UPI = "upi", "UPI"
        CREDIT = "credit", "Credit (on account)"

    # Basic Info
    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="retail_sales",
    )
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    sale_number = models.CharField(max_length=20, unique=True, editable=False)

    # Sale Type
    sale_type = models.CharField(
        max_length=20,
        choices=SaleType.choices,
        default=SaleType.RETAIL,
    )

    # Customer (optional for retail, required for wholesale)
    wholesale_customer = models.ForeignKey(
        WholesaleCustomer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sales",
    )

    # Link to cafe order (for combined dine-in billing)
    linked_order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="retail_sales",
        help_text="Link retail sale to a dine-in order for combined billing",
    )

    # Walk-in customer info
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=20, blank=True)

    # Amounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    # Tax breakdown
    cgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Payment
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.PENDING,
    )
    payment_method = models.CharField(
        max_length=20,
        blank=True,
        help_text="Payment method for retail sales",
    )

    # Notes
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)

    # User tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="retail_sales_created",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Retail Sale"
        verbose_name_plural = "Retail Sales"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sale #{self.sale_number}"

    def save(self, *args, **kwargs):
        if not self.sale_number:
            self.sale_number = self._generate_sale_number()
        super().save(*args, **kwargs)

    def _generate_sale_number(self):
        """Generate unique sale number."""
        today = timezone.now().date()
        date_str = today.strftime("%y%m%d")
        prefix = "WS" if self.sale_type == self.SaleType.WHOLESALE else "RS"

        count = RetailSale.objects.filter(
            created_at__date=today,
            sale_type=self.sale_type,
        ).count() + 1

        return f"{prefix}{date_str}{count:04d}"

    @property
    def balance_due(self):
        """Calculate remaining balance."""
        return max(Decimal("0"), self.total_amount - self.paid_amount)

    @property
    def is_paid(self):
        """Check if sale is fully paid."""
        return self.paid_amount >= self.total_amount

    @property
    def item_count(self):
        """Get total number of items."""
        return self.items.count()

    @property
    def total_quantity(self):
        """Get total quantity across all items."""
        from django.db.models import Sum
        return self.items.aggregate(total=Sum("quantity"))["total"] or 0

    def calculate_totals(self):
        """Recalculate sale totals from items."""
        from django.db.models import Sum

        items = self.items.all()

        # Get subtotal from items
        self.subtotal = items.aggregate(
            total=Sum("subtotal")
        )["total"] or Decimal("0")

        # Apply discount
        if self.discount_percentage > 0:
            self.discount_amount = (self.subtotal * self.discount_percentage) / 100

        # Calculate taxes from items
        self.cgst_amount = items.aggregate(total=Sum("cgst_amount"))["total"] or Decimal("0")
        self.sgst_amount = items.aggregate(total=Sum("sgst_amount"))["total"] or Decimal("0")
        self.igst_amount = items.aggregate(total=Sum("igst_amount"))["total"] or Decimal("0")

        # Calculate total
        self.total_amount = (
            self.subtotal
            - self.discount_amount
            + self.cgst_amount
            + self.sgst_amount
            + self.igst_amount
        )

        # Update payment status
        if self.paid_amount >= self.total_amount:
            self.payment_status = self.PaymentStatus.PAID
        elif self.paid_amount > 0:
            self.payment_status = self.PaymentStatus.PARTIAL

        self.save()
        return self.total_amount


class RetailSaleItem(models.Model):
    """
    Individual item in a retail sale.
    """
    sale = models.ForeignKey(
        RetailSale,
        on_delete=models.CASCADE,
        related_name="items",
    )
    product = models.ForeignKey(
        RetailProduct,
        on_delete=models.PROTECT,
        related_name="sale_items",
    )

    # Snapshot at sale time
    product_name = models.CharField(max_length=200)
    product_sku = models.CharField(max_length=50)
    hsn_code = models.CharField(max_length=20, blank=True)

    # Quantity & Price
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Calculated subtotal (qty * price - discount)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Tax
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    cgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    igst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Total (subtotal + taxes)
    total = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        verbose_name = "Retail Sale Item"
        verbose_name_plural = "Retail Sale Items"

    def __str__(self):
        return f"{self.quantity} x {self.product_name}"

    def save(self, *args, **kwargs):
        # Store product snapshot
        if not self.product_name:
            self.product_name = self.product.name
            self.product_sku = self.product.sku
            self.hsn_code = self.product.hsn_code
            self.tax_rate = self.product.tax_rate

        # Calculate subtotal
        self.subtotal = (self.quantity * self.unit_price) - self.discount_amount

        # Calculate taxes (assuming intra-state, equal CGST/SGST split)
        tax_amount = (self.subtotal * self.tax_rate) / 100
        self.cgst_amount = tax_amount / 2
        self.sgst_amount = tax_amount / 2

        # Calculate total
        self.total = self.subtotal + tax_amount

        super().save(*args, **kwargs)


class WholesaleInvoice(models.Model):
    """
    Invoice for wholesale sales with payment tracking.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PENDING = "pending", "Pending Payment"
        PARTIAL = "partial", "Partially Paid"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    # Basic Info
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    invoice_number = models.CharField(max_length=30, unique=True, editable=False)

    # Relations
    customer = models.ForeignKey(
        WholesaleCustomer,
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    sale = models.OneToOneField(
        RetailSale,
        on_delete=models.CASCADE,
        related_name="invoice",
    )

    # Dates
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField()

    # Amounts
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    # Notes
    notes = models.TextField(blank=True)
    terms_conditions = models.TextField(blank=True)

    # Tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="invoices_created",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Wholesale Invoice"
        verbose_name_plural = "Wholesale Invoices"
        ordering = ["-invoice_date", "-created_at"]

    def __str__(self):
        return f"Invoice #{self.invoice_number}"

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = self._generate_invoice_number()

        # The field default (timezone.now) is a datetime; keep the date part so
        # due-date arithmetic and comparisons work on dates
        if isinstance(self.invoice_date, datetime.datetime):
            self.invoice_date = timezone.localtime(self.invoice_date).date()

        # Auto-calculate due date if not set
        if not self.due_date:
            from datetime import timedelta
            self.due_date = self.invoice_date + timedelta(
                days=self.customer.payment_terms_days
            )

        # Update status based on payment
        self._update_status()

        super().save(*args, **kwargs)

    def _generate_invoice_number(self):
        """Generate unique invoice number."""
        today = timezone.now().date()
        fiscal_year = f"{today.year % 100}-{(today.year + 1) % 100}"
        count = WholesaleInvoice.objects.filter(
            created_at__year=today.year
        ).count() + 1
        return f"INV/{fiscal_year}/{count:05d}"

    def _update_status(self):
        """Update invoice status based on payment and dates."""
        if self.paid_amount >= self.amount:
            self.status = self.Status.PAID
        elif self.paid_amount > 0:
            self.status = self.Status.PARTIAL
        elif self.due_date and self.due_date < timezone.now().date() and self.status not in [self.Status.PAID, self.Status.CANCELLED]:
            self.status = self.Status.OVERDUE

    @property
    def balance_due(self):
        """Calculate remaining balance."""
        return max(Decimal("0"), self.amount - self.paid_amount)

    def sync_sale_payment(self):
        """Mirror the payments recorded against this invoice onto its sale."""
        sale = self.sale
        if sale.payment_status in [RetailSale.PaymentStatus.CANCELLED, RetailSale.PaymentStatus.REFUNDED]:
            return
        sale.paid_amount = min(self.paid_amount, sale.total_amount)
        if self.paid_amount >= self.amount:
            sale.payment_status = RetailSale.PaymentStatus.PAID
        elif self.paid_amount > 0:
            sale.payment_status = RetailSale.PaymentStatus.PARTIAL
        else:
            sale.payment_status = RetailSale.PaymentStatus.PENDING
        sale.save(update_fields=["paid_amount", "payment_status", "updated_at"])

    @property
    def is_overdue(self):
        """Check if invoice is overdue."""
        return (
            self.due_date < timezone.now().date()
            and self.status not in [self.Status.PAID, self.Status.CANCELLED]
        )


class CustomerPayment(models.Model):
    """
    Payment received from wholesale customer.
    """

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CHEQUE = "cheque", "Cheque"
        UPI = "upi", "UPI"
        CARD = "card", "Card"
        CREDIT_NOTE = "credit_note", "Credit Note"

    # Basic Info
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    receipt_number = models.CharField(max_length=30, unique=True, editable=False)

    # Relations
    customer = models.ForeignKey(
        WholesaleCustomer,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    invoice = models.ForeignKey(
        WholesaleInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
        help_text="Specific invoice this payment is for (optional)",
    )

    # Payment Details
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.now)
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.BANK_TRANSFER,
    )

    # Reference
    reference_number = models.CharField(
        max_length=100,
        blank=True,
        help_text="Transaction ID, Cheque number, etc.",
    )
    bank_name = models.CharField(max_length=100, blank=True)

    # Notes
    notes = models.TextField(blank=True)

    # Tracking
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="payments_received",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Customer Payment"
        verbose_name_plural = "Customer Payments"
        ordering = ["-payment_date", "-created_at"]

    def __str__(self):
        return f"Payment #{self.receipt_number} - {self.customer.business_name}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self._generate_receipt_number()

        super().save(*args, **kwargs)

        # Update invoice paid amount if linked
        if self.invoice:
            from django.db.models import Sum
            total_paid = self.invoice.payments.aggregate(
                total=Sum("amount")
            )["total"] or Decimal("0")
            self.invoice.paid_amount = total_paid
            self.invoice.save()
            self.invoice.sync_sale_payment()

        # Update customer balance
        self.customer.update_balance()

    def _generate_receipt_number(self):
        """Generate unique receipt number."""
        today = timezone.now().date()
        date_str = today.strftime("%y%m%d")
        count = CustomerPayment.objects.filter(
            created_at__date=today
        ).count() + 1
        return f"RCP{date_str}{count:04d}"


class RetailStockMovement(models.Model):
    """
    Track stock movements for retail products.
    """

    class MovementType(models.TextChoices):
        PURCHASE = "purchase", "Purchase/Inward"
        SALE = "sale", "Sale"
        RETURN = "return", "Customer Return"
        ADJUSTMENT = "adjustment", "Stock Adjustment"
        TRANSFER = "transfer", "Transfer"
        DAMAGE = "damage", "Damage/Wastage"

    product = models.ForeignKey(
        RetailProduct,
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )

    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Positive for inward, negative for outward",
    )

    # Stock levels
    stock_before = models.DecimalField(max_digits=10, decimal_places=2)
    stock_after = models.DecimalField(max_digits=10, decimal_places=2)

    # Reference
    reference_type = models.CharField(max_length=50, blank=True)  # e.g., "RetailSale", "PurchaseOrder"
    reference_id = models.PositiveIntegerField(null=True, blank=True)

    reason = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="retail_stock_movements",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Retail Stock Movement"
        verbose_name_plural = "Retail Stock Movements"
        ordering = ["-created_at"]

    def __str__(self):
        direction = "+" if self.quantity > 0 else ""
        return f"{self.product.name}: {direction}{self.quantity}"
