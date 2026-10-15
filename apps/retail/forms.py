"""
Forms for Retail & Wholesale module.
"""

from decimal import Decimal

from django import forms
from django.conf import settings

from apps.accounts.models import User
from apps.core.models import Outlet
from apps.inventory.models import Supplier
from apps.menu.models import MenuItem

from .models import (
    CustomerPayment,
    RetailCategory,
    RetailProduct,
    WholesaleCustomer,
    WholesaleInvoice,
)


class RetailCategoryForm(forms.ModelForm):
    """Form for creating/editing retail categories."""

    class Meta:
        model = RetailCategory
        fields = ['outlet', 'name', 'description', 'parent', 'display_order', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Category name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Description'}),
            'outlet': forms.Select(attrs={'class': 'form-select'}),
            'parent': forms.Select(attrs={'class': 'form-select'}),
            'display_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter outlets based on user permissions
        if user and user.role != User.Role.SUPER_ADMIN:
            self.fields['outlet'].queryset = Outlet.objects.filter(pk=user.outlet_id)
            self.fields['outlet'].initial = user.outlet
            self.fields['outlet'].widget = forms.HiddenInput()

        # Filter parent categories by outlet
        if self.instance and self.instance.pk:
            self.fields['parent'].queryset = RetailCategory.objects.filter(
                outlet=self.instance.outlet
            ).exclude(pk=self.instance.pk)
        elif user and user.outlet:
            self.fields['parent'].queryset = RetailCategory.objects.filter(outlet=user.outlet)


class RetailProductForm(forms.ModelForm):
    """Form for creating/editing retail products."""

    generate_barcode = forms.BooleanField(
        required=False,
        initial=True,
        label="Auto-generate barcode",
        widget=forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-blue-600 border-slate-300 rounded focus:ring-blue-500'})
    )

    class Meta:
        model = RetailProduct
        fields = [
            'outlet', 'category', 'name', 'description', 'sku', 'image',
            'unit', 'cost_price', 'mrp', 'selling_price', 'wholesale_price',
            'tax_type', 'hsn_code',
            'track_inventory', 'current_stock', 'minimum_stock',
            'linked_menu_item', 'supplier', 'is_active'
        ]
        widgets = {
            'outlet': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'category': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'name': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'placeholder': 'Product name'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'rows': 3, 'placeholder': 'Description'}),
            'sku': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'placeholder': 'SKU (optional)'}),
            'image': forms.ClearableFileInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'unit': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'cost_price': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'step': '0.01', 'min': '0'}),
            'mrp': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'step': '0.01', 'min': '0'}),
            'selling_price': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'step': '0.01', 'min': '0'}),
            'wholesale_price': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'step': '0.01', 'min': '0'}),
            'tax_type': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'hsn_code': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'placeholder': 'HSN Code'}),
            'track_inventory': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-blue-600 border-slate-300 rounded focus:ring-blue-500'}),
            'current_stock': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'step': '0.01', 'min': '0'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500', 'step': '0.01', 'min': '0'}),
            'linked_menu_item': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'supplier': forms.Select(attrs={'class': 'w-full px-3 py-2 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'w-4 h-4 text-blue-600 border-slate-300 rounded focus:ring-blue-500'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter outlets based on user permissions
        if user and user.role != User.Role.SUPER_ADMIN:
            self.fields['outlet'].queryset = Outlet.objects.filter(pk=user.outlet_id)
            self.fields['outlet'].initial = user.outlet
            self.fields['outlet'].widget = forms.HiddenInput()

            # Filter categories by outlet
            self.fields['category'].queryset = RetailCategory.objects.filter(
                outlet=user.outlet, is_active=True
            )

            # Filter menu items by outlet
            self.fields['linked_menu_item'].queryset = MenuItem.objects.filter(
                category__outlet=user.outlet, is_available=True
            )

            # Filter suppliers by outlet
            self.fields['supplier'].queryset = Supplier.objects.filter(outlet=user.outlet)
        else:
            self.fields['category'].queryset = RetailCategory.objects.filter(is_active=True)
            self.fields['linked_menu_item'].queryset = MenuItem.objects.filter(is_available=True)
            self.fields['supplier'].queryset = Supplier.objects.all()

        # Make linked_menu_item and supplier optional
        self.fields['linked_menu_item'].required = False
        self.fields['supplier'].required = False

        # Don't show generate_barcode on edit
        if self.instance and self.instance.pk:
            del self.fields['generate_barcode']

    def clean(self):
        cleaned_data = super().clean()
        mrp = cleaned_data.get('mrp', Decimal('0'))
        selling_price = cleaned_data.get('selling_price', Decimal('0'))

        if selling_price > mrp:
            self.add_error('selling_price', 'Selling price cannot exceed MRP.')

        return cleaned_data


class WholesaleCustomerForm(forms.ModelForm):
    """Form for creating/editing wholesale customers."""

    class Meta:
        model = WholesaleCustomer
        fields = [
            'outlet', 'business_name', 'name', 'phone', 'email',
            'address_line1', 'city', 'state', 'postal_code',
            'gst_number', 'pan_number',
            'credit_limit', 'payment_terms_days', 'discount_percentage',
            'notes', 'is_active'
        ]
        widgets = {
            'outlet': forms.Select(attrs={'class': 'form-select'}),
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Business name'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Contact person name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email address'}),
            'address_line1': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Address line 1'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'City'}),
            'state': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'State'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Postal code'}),
            'gst_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'GST Number (e.g., 29AABCU9603R1ZM)'}),
            'pan_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'PAN Number'}),
            'credit_limit': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'payment_terms_days': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
            'discount_percentage': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Notes'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter outlets based on user permissions
        if user and user.role != User.Role.SUPER_ADMIN:
            self.fields['outlet'].queryset = Outlet.objects.filter(pk=user.outlet_id)
            self.fields['outlet'].initial = user.outlet
            self.fields['outlet'].widget = forms.HiddenInput()

        # Set defaults from settings
        if not self.instance.pk:
            self.fields['credit_limit'].initial = getattr(settings, 'DEFAULT_CREDIT_LIMIT', 0)
            self.fields['payment_terms_days'].initial = getattr(settings, 'DEFAULT_PAYMENT_TERMS_DAYS', 30)

    def clean_gst_number(self):
        gst = self.cleaned_data.get('gst_number', '').strip().upper()
        if gst:
            # Basic GST format validation (15 characters)
            if len(gst) != 15:
                raise forms.ValidationError("GST number must be 15 characters.")
            # Check alphanumeric
            if not gst.isalnum():
                raise forms.ValidationError("GST number must be alphanumeric.")
        return gst

    def clean_pan_number(self):
        pan = self.cleaned_data.get('pan_number', '').strip().upper()
        if pan:
            # Basic PAN format validation (10 characters)
            if len(pan) != 10:
                raise forms.ValidationError("PAN number must be 10 characters.")
            if not pan.isalnum():
                raise forms.ValidationError("PAN number must be alphanumeric.")
        return pan


class CustomerPaymentForm(forms.ModelForm):
    """Form for recording customer payments."""

    class Meta:
        model = CustomerPayment
        fields = [
            'customer', 'invoice', 'amount',
            'payment_method', 'reference_number', 'payment_date', 'notes'
        ]
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'invoice': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'reference_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Reference/Transaction ID'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Notes'}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter customers based on user outlet
        if user and user.role != User.Role.SUPER_ADMIN:
            self.fields['customer'].queryset = WholesaleCustomer.objects.filter(
                outlet=user.outlet, is_active=True
            )
        else:
            self.fields['customer'].queryset = WholesaleCustomer.objects.filter(is_active=True)

        # Invoice is optional; offer only open invoices the user can see
        self.fields['invoice'].required = False
        invoices = WholesaleInvoice.objects.filter(
            status__in=[
                WholesaleInvoice.Status.PENDING,
                WholesaleInvoice.Status.PARTIAL,
                WholesaleInvoice.Status.OVERDUE,
            ]
        ).select_related('customer')
        if user and user.role != User.Role.SUPER_ADMIN:
            invoices = invoices.filter(customer__outlet=user.outlet)
        self.fields['invoice'].queryset = invoices.order_by('due_date')

        # Set initial date
        from django.utils import timezone
        self.fields['payment_date'].initial = timezone.now().date()

    def clean(self):
        cleaned_data = super().clean()
        customer = cleaned_data.get('customer')
        invoice = cleaned_data.get('invoice')

        # If invoice is selected, verify it belongs to the customer
        if invoice and invoice.customer != customer:
            self.add_error('invoice', 'This invoice does not belong to the selected customer.')

        # A payment against an invoice cannot exceed what is still due on it
        amount = cleaned_data.get('amount')
        if invoice and amount and amount > invoice.balance_due:
            self.add_error(
                'amount',
                f'Only {invoice.balance_due} is due on {invoice.invoice_number}. '
                'Record the rest without an invoice to keep it on account.',
            )

        return cleaned_data


class StockAdjustmentForm(forms.Form):
    """Form for stock adjustments."""

    product = forms.ModelChoiceField(
        queryset=RetailProduct.objects.none(),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    adjustment_type = forms.ChoiceField(
        choices=[('add', 'Add Stock'), ('remove', 'Remove Stock')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    quantity = forms.DecimalField(
        min_value=Decimal('0.01'),
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'})
    )
    reason = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Reason for adjustment'})
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

        # Filter products based on user outlet
        if user and user.role != User.Role.SUPER_ADMIN:
            self.fields['product'].queryset = RetailProduct.objects.filter(
                outlet=user.outlet, is_active=True, track_inventory=True
            ).order_by('name')
        else:
            self.fields['product'].queryset = RetailProduct.objects.filter(
                is_active=True, track_inventory=True
            ).order_by('name')

    def clean(self):
        cleaned_data = super().clean()
        product = cleaned_data.get('product')
        adjustment_type = cleaned_data.get('adjustment_type')
        quantity = cleaned_data.get('quantity')

        if product and adjustment_type == 'remove' and quantity:
            if quantity > product.current_stock:
                self.add_error('quantity', f'Cannot remove more than current stock ({product.current_stock}).')

        return cleaned_data


class ProductBarcodeForm(forms.Form):
    """Form for adding a barcode to a product."""

    barcode_type = forms.ChoiceField(
        choices=[
            ('EAN13', 'EAN-13 (Standard)'),
            ('EAN8', 'EAN-8 (Short)'),
            ('CODE128', 'CODE-128 (Alphanumeric)'),
            ('CODE39', 'CODE-39'),
            ('QR', 'QR Code'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    barcode_value = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Leave empty to auto-generate'}),
        help_text='Leave empty to auto-generate based on product ID'
    )
    is_primary = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
