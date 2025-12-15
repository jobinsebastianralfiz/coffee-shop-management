"""
Finance models for expense tracking and cash drawer management.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class ExpenseCategory(models.Model):
    """
    Category for expenses (supports both default and custom categories).
    """

    class CategoryType(models.TextChoices):
        RENT = "rent", "Rent"
        UTILITIES = "utilities", "Utilities"
        SALARIES = "salaries", "Salaries"
        SUPPLIES = "supplies", "Supplies"
        MAINTENANCE = "maintenance", "Maintenance"
        MARKETING = "marketing", "Marketing"
        INSURANCE = "insurance", "Insurance"
        TAXES = "taxes", "Taxes & Licenses"
        EQUIPMENT = "equipment", "Equipment"
        CUSTOM = "custom", "Custom"

    name = models.CharField(max_length=100)
    category_type = models.CharField(
        max_length=20,
        choices=CategoryType.choices,
        default=CategoryType.CUSTOM,
    )
    description = models.TextField(blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Expense Category"
        verbose_name_plural = "Expense Categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class Expense(models.Model):
    """
    Individual expense record.
    Each expense belongs to a specific outlet.
    """

    class PaymentMethod(models.TextChoices):
        CASH = "cash", "Cash"
        BANK_TRANSFER = "bank_transfer", "Bank Transfer"
        CHEQUE = "cheque", "Cheque"
        CARD = "card", "Card"
        UPI = "upi", "UPI"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        PAID = "paid", "Paid"
        CANCELLED = "cancelled", "Cancelled"

    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="expenses",
        null=True,
        blank=True,
        help_text="Outlet this expense belongs to",
    )
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    expense_number = models.CharField(max_length=20, unique=True, editable=False)

    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        related_name="expenses",
    )

    # Expense details
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.TextField()
    payment_method = models.CharField(
        max_length=20,
        choices=PaymentMethod.choices,
        default=PaymentMethod.CASH,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PAID,
    )

    # Reference (invoice, receipt number, etc.)
    reference_number = models.CharField(max_length=100, blank=True)
    vendor_name = models.CharField(max_length=200, blank=True)

    # Attachments (receipt image/PDF)
    receipt = models.FileField(upload_to="expenses/receipts/", null=True, blank=True)

    # Notes
    notes = models.TextField(blank=True)

    # Tracking
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="expenses_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses_approved",
    )

    # Cash drawer link (for cash expenses)
    cash_drawer_transaction = models.ForeignKey(
        "CashDrawerTransaction",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="expenses",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.expense_number} - {self.category.name} - {self.amount}"

    def save(self, *args, **kwargs):
        if not self.expense_number:
            self.expense_number = self._generate_expense_number()
        super().save(*args, **kwargs)

    def _generate_expense_number(self):
        """Generate unique expense number."""
        today = timezone.now().date()
        date_str = today.strftime("%y%m%d")
        count = Expense.objects.filter(created_at__date=today).count() + 1
        return f"EXP{date_str}{count:04d}"


class CashDrawer(models.Model):
    """
    Daily cash drawer tracking.
    Each cash drawer belongs to a specific outlet.
    """

    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="cash_drawers",
        null=True,
        blank=True,
        help_text="Outlet this cash drawer belongs to",
    )
    date = models.DateField()

    # Opening
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cash_drawers_opened",
    )
    opened_at = models.DateTimeField(null=True, blank=True)

    # Calculated fields (updated from transactions)
    total_cash_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cash_in = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cash_out = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Closing
    expected_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_balance = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    variance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_drawers_closed",
    )
    closed_at = models.DateTimeField(null=True, blank=True)

    is_closed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cash Drawer"
        verbose_name_plural = "Cash Drawers"
        ordering = ["-date"]
        unique_together = ["outlet", "date"]

    def __str__(self):
        status = "Closed" if self.is_closed else "Open"
        return f"Cash Drawer {self.date} ({status})"

    def calculate_expected(self):
        """Calculate expected balance."""
        self.expected_balance = (
            self.opening_balance
            + self.total_cash_sales
            + self.total_cash_in
            - self.total_cash_out
        )
        return self.expected_balance

    def calculate_variance(self):
        """Calculate variance between expected and actual."""
        if self.actual_balance is not None:
            self.variance = self.actual_balance - self.expected_balance
        return self.variance

    def update_totals(self):
        """Update totals from transactions."""
        from django.db.models import Sum

        transactions = self.transactions.all()

        # Cash sales (from payments)
        self.total_cash_sales = (
            transactions.filter(transaction_type=CashDrawerTransaction.TransactionType.SALE).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        # Cash in (manual deposits)
        self.total_cash_in = (
            transactions.filter(transaction_type=CashDrawerTransaction.TransactionType.CASH_IN).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        # Cash out (withdrawals, expenses, refunds)
        cash_out_types = [
            CashDrawerTransaction.TransactionType.CASH_OUT,
            CashDrawerTransaction.TransactionType.EXPENSE,
            CashDrawerTransaction.TransactionType.REFUND,
        ]
        self.total_cash_out = abs(
            transactions.filter(transaction_type__in=cash_out_types).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        self.calculate_expected()
        self.save()


class CashierShift(models.Model):
    """
    Shift-based cash drawer tracking for individual cashiers.
    """

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    cash_drawer = models.ForeignKey(
        CashDrawer,
        on_delete=models.CASCADE,
        related_name="shifts",
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="cashier_shifts",
    )

    # Shift timing
    shift_start = models.DateTimeField()
    shift_end = models.DateTimeField(null=True, blank=True)

    # Opening
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2)

    # Calculated during shift
    cash_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cash_in = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cash_out = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Closing
    expected_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_balance = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    variance = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    is_closed = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cashier Shift"
        verbose_name_plural = "Cashier Shifts"
        ordering = ["-shift_start"]

    def __str__(self):
        return f"{self.cashier.get_full_name() or self.cashier.username} - {self.shift_start.date()}"

    @property
    def duration(self):
        """Calculate shift duration in hours."""
        if self.shift_end:
            delta = self.shift_end - self.shift_start
            return round(delta.total_seconds() / 3600, 2)
        return None

    def calculate_expected(self):
        """Calculate expected balance for this shift."""
        self.expected_balance = (
            self.opening_balance + self.cash_sales + self.cash_in - self.cash_out
        )
        return self.expected_balance

    def calculate_variance(self):
        """Calculate variance between expected and actual."""
        if self.actual_balance is not None:
            self.variance = self.actual_balance - self.expected_balance
        return self.variance

    def update_totals(self):
        """Update totals from transactions."""
        from django.db.models import Sum

        transactions = self.transactions.all()

        self.cash_sales = (
            transactions.filter(transaction_type=CashDrawerTransaction.TransactionType.SALE).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        self.cash_in = (
            transactions.filter(transaction_type=CashDrawerTransaction.TransactionType.CASH_IN).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        cash_out_types = [
            CashDrawerTransaction.TransactionType.CASH_OUT,
            CashDrawerTransaction.TransactionType.EXPENSE,
            CashDrawerTransaction.TransactionType.REFUND,
        ]
        self.cash_out = abs(
            transactions.filter(transaction_type__in=cash_out_types).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )

        self.calculate_expected()
        self.save()


class CashDrawerTransaction(models.Model):
    """
    Individual cash drawer transactions (in/out).
    """

    class TransactionType(models.TextChoices):
        SALE = "sale", "Sale Payment"
        CASH_IN = "cash_in", "Cash In"
        CASH_OUT = "cash_out", "Cash Out"
        EXPENSE = "expense", "Expense Payment"
        PETTY_CASH = "petty_cash", "Petty Cash"
        FLOAT = "float", "Float Adjustment"
        REFUND = "refund", "Refund"

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    cash_drawer = models.ForeignKey(
        CashDrawer,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    cashier_shift = models.ForeignKey(
        CashierShift,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="transactions",
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TransactionType.choices,
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)

    # Reference to order payment if applicable
    payment = models.ForeignKey(
        "orders.Payment",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cash_transactions",
    )

    description = models.CharField(max_length=500)
    reference = models.CharField(max_length=100, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="cash_transactions",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Cash Drawer Transaction"
        verbose_name_plural = "Cash Drawer Transactions"
        ordering = ["-created_at"]

    def __str__(self):
        direction = "+" if self.amount > 0 else ""
        return f"{direction}{self.amount} - {self.get_transaction_type_display()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Update cash drawer totals
        if self.cash_drawer:
            self.cash_drawer.update_totals()
        if self.cashier_shift:
            self.cashier_shift.update_totals()
