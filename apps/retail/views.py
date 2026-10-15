"""
Views for Retail & Wholesale module.
"""

import json
from decimal import Decimal

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum, F
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.models import User

from .models import (
    CustomerPayment,
    ProductBarcode,
    RetailCategory,
    RetailProduct,
    RetailSale,
    RetailSaleItem,
    RetailStockMovement,
    WholesaleCustomer,
    WholesaleInvoice,
)
from .services import barcode_service


# ============================================================================
# Permission Helpers
# ============================================================================


def is_admin_user(user):
    """Check if user has admin-level access (super admin or outlet manager)."""
    return user.role in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER]


def get_user_outlet(user):
    """Get the outlet a user is restricted to (None for super admin = all outlets)."""
    if user.role == User.Role.SUPER_ADMIN:
        return None
    return user.outlet


def filter_by_outlet(queryset, user, outlet_field="outlet"):
    """Filter a queryset by the user's outlet if they're not a super admin."""
    outlet = get_user_outlet(user)
    if outlet:
        return queryset.filter(**{outlet_field: outlet})
    return queryset


def retail_required(view_func):
    """Decorator to check if retail module is enabled."""
    def wrapper(request, *args, **kwargs):
        if not getattr(settings, 'ENABLE_RETAIL', False):
            messages.error(request, "Retail module is not enabled.")
            return redirect("dashboard:home")
        return view_func(request, *args, **kwargs)
    return wrapper


# ============================================================================
# Dashboard
# ============================================================================


@login_required
@retail_required
def retail_dashboard(request):
    """Main retail dashboard with overview stats."""
    user = request.user
    outlet = get_user_outlet(user)

    # Base querysets filtered by outlet
    products = RetailProduct.objects.all()
    sales = RetailSale.objects.all()
    customers = WholesaleCustomer.objects.all()

    if outlet:
        products = products.filter(outlet=outlet)
        sales = sales.filter(outlet=outlet)
        customers = customers.filter(outlet=outlet)

    # Calculate stats
    today = timezone.now().date()
    today_sales = sales.filter(created_at__date=today)

    context = {
        "total_products": products.filter(is_active=True).count(),
        "low_stock_products": products.filter(
            is_active=True,
            track_inventory=True,
            current_stock__lte=F('minimum_stock')
        ).count(),
        "today_sales_count": today_sales.count(),
        "today_sales_total": today_sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0'),
        "total_customers": customers.filter(is_active=True).count(),
        "outstanding_amount": customers.aggregate(total=Sum('current_balance'))['total'] or Decimal('0'),
        "recent_sales": sales.select_related('wholesale_customer', 'created_by').order_by('-created_at')[:10],
        "low_stock_items": products.filter(
            is_active=True,
            track_inventory=True,
            current_stock__lte=F('minimum_stock')
        ).order_by('current_stock')[:10],
    }

    return render(request, "dashboard/retail/dashboard.html", context)


# ============================================================================
# Products
# ============================================================================


@login_required
@retail_required
def product_list(request):
    """List all retail products."""
    user = request.user
    products = filter_by_outlet(RetailProduct.objects.all(), user)

    # Search filter
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(sku__icontains=search) |
            Q(barcodes__barcode_value__icontains=search)
        ).distinct()

    # Category filter
    category_id = request.GET.get('category')
    if category_id:
        products = products.filter(category_id=category_id)

    # Stock filter
    stock_filter = request.GET.get('stock')
    if stock_filter == 'low':
        products = products.filter(
            track_inventory=True,
            current_stock__lte=F('minimum_stock'),
            current_stock__gt=0
        )
    elif stock_filter == 'out':
        products = products.filter(track_inventory=True, current_stock=0)

    # Active filter
    is_active = request.GET.get('active')
    if is_active == '1':
        products = products.filter(is_active=True)
    elif is_active == '0':
        products = products.filter(is_active=False)

    products = products.select_related('category', 'outlet').prefetch_related('barcodes').order_by('-created_at')

    # Pagination
    paginator = Paginator(products, 20)
    page = request.GET.get('page')
    products = paginator.get_page(page)

    # Categories for filter dropdown
    categories = filter_by_outlet(RetailCategory.objects.filter(is_active=True), user)

    context = {
        "products": products,
        "categories": categories,
        "search": search,
        "selected_category": category_id,
        "stock_filter": stock_filter,
        "active_filter": is_active,
    }

    return render(request, "dashboard/retail/products/list.html", context)


@login_required
@retail_required
def product_create(request):
    """Create a new retail product."""
    from .forms import RetailProductForm

    user = request.user
    outlet = get_user_outlet(user)

    if request.method == 'POST':
        form = RetailProductForm(request.POST, request.FILES, user=user)
        if form.is_valid():
            product = form.save(commit=False)
            if outlet:
                product.outlet = outlet
            product.save()

            # Generate barcode if requested
            if request.POST.get('generate_barcode'):
                barcode_value = barcode_service.generate_ean13(product.id)
                ProductBarcode.objects.create(
                    product=product,
                    barcode_type='EAN13',
                    barcode_value=barcode_value,
                    is_primary=True
                )

            messages.success(request, f"Product '{product.name}' created successfully.")
            return redirect('retail:product_detail', pk=product.pk)
    else:
        form = RetailProductForm(user=user)

    context = {
        "form": form,
        "is_create": True,
    }

    return render(request, "dashboard/retail/products/form.html", context)


@login_required
@retail_required
def product_detail(request, pk):
    """View product details."""
    user = request.user
    products = filter_by_outlet(RetailProduct.objects.all(), user)
    product = get_object_or_404(products.select_related('category', 'outlet', 'supplier', 'linked_menu_item'), pk=pk)

    # Get stock movements
    movements = product.stock_movements.order_by('-created_at')[:20]

    # Get sales containing this product
    sale_items = RetailSaleItem.objects.filter(product=product).select_related('sale').order_by('-sale__created_at')[:20]

    context = {
        "product": product,
        "barcodes": product.barcodes.all(),
        "movements": movements,
        "sale_items": sale_items,
    }

    return render(request, "dashboard/retail/products/detail.html", context)


@login_required
@retail_required
def product_edit(request, pk):
    """Edit an existing product."""
    from .forms import RetailProductForm

    user = request.user
    products = filter_by_outlet(RetailProduct.objects.all(), user)
    product = get_object_or_404(products, pk=pk)

    if request.method == 'POST':
        form = RetailProductForm(request.POST, request.FILES, instance=product, user=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Product '{product.name}' updated successfully.")
            return redirect('retail:product_detail', pk=product.pk)
    else:
        form = RetailProductForm(instance=product, user=user)

    context = {
        "form": form,
        "product": product,
        "is_create": False,
    }

    return render(request, "dashboard/retail/products/form.html", context)


@login_required
@retail_required
@require_POST
def product_delete(request, pk):
    """Delete a product (soft delete by setting inactive)."""
    user = request.user
    products = filter_by_outlet(RetailProduct.objects.all(), user)
    product = get_object_or_404(products, pk=pk)

    # Soft delete
    product.is_active = False
    product.save()

    messages.success(request, f"Product '{product.name}' has been deactivated.")
    return redirect('retail:products')


# ============================================================================
# Categories
# ============================================================================


@login_required
@retail_required
def category_list(request):
    """List retail categories."""
    user = request.user
    categories = filter_by_outlet(RetailCategory.objects.all(), user)
    categories = categories.select_related('parent', 'outlet').order_by('display_order', 'name')

    context = {
        "categories": categories,
    }

    return render(request, "dashboard/retail/categories/list.html", context)


@login_required
@retail_required
def category_create(request):
    """Create a new category."""
    from .forms import RetailCategoryForm

    user = request.user
    outlet = get_user_outlet(user)

    if request.method == 'POST':
        form = RetailCategoryForm(request.POST, user=user)
        if form.is_valid():
            category = form.save(commit=False)
            if outlet:
                category.outlet = outlet
            category.save()
            messages.success(request, f"Category '{category.name}' created successfully.")
            return redirect('retail:categories')
    else:
        form = RetailCategoryForm(user=user)

    context = {
        "form": form,
        "is_create": True,
    }

    return render(request, "dashboard/retail/categories/form.html", context)


@login_required
@retail_required
def category_edit(request, pk):
    """Edit a category."""
    from .forms import RetailCategoryForm

    user = request.user
    categories = filter_by_outlet(RetailCategory.objects.all(), user)
    category = get_object_or_404(categories, pk=pk)

    if request.method == 'POST':
        form = RetailCategoryForm(request.POST, instance=category, user=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Category '{category.name}' updated successfully.")
            return redirect('retail:categories')
    else:
        form = RetailCategoryForm(instance=category, user=user)

    context = {
        "form": form,
        "category": category,
        "is_create": False,
    }

    return render(request, "dashboard/retail/categories/form.html", context)


@login_required
@retail_required
@require_POST
def category_delete(request, pk):
    """Delete a category."""
    user = request.user
    categories = filter_by_outlet(RetailCategory.objects.all(), user)
    category = get_object_or_404(categories, pk=pk)

    # Check if category has products
    if category.products.exists():
        messages.error(request, f"Cannot delete category '{category.name}' - it has products.")
        return redirect('retail:categories')

    category.delete()
    messages.success(request, f"Category '{category.name}' deleted.")
    return redirect('retail:categories')


# ============================================================================
# Barcodes
# ============================================================================


@login_required
@retail_required
def barcode_generate(request, pk):
    """Generate or regenerate barcode for a product."""
    user = request.user
    products = filter_by_outlet(RetailProduct.objects.all(), user)
    product = get_object_or_404(products, pk=pk)

    barcode_type = request.GET.get('type', 'EAN13')

    try:
        if barcode_type == 'EAN13':
            barcode_value = barcode_service.generate_ean13(product.id)
        elif barcode_type == 'EAN8':
            barcode_value = barcode_service.generate_ean8(product.id)
        elif barcode_type == 'CODE128':
            barcode_value = barcode_service.generate_code128(product.sku or str(product.id))
        else:
            barcode_value = barcode_service.generate_ean13(product.id)

        # Create or update barcode
        barcode, created = ProductBarcode.objects.update_or_create(
            product=product,
            barcode_type=barcode_type,
            defaults={
                'barcode_value': barcode_value,
                'is_primary': not product.barcodes.filter(is_primary=True).exists()
            }
        )

        # Generate barcode image
        try:
            image_bytes, filename = barcode_service.generate_barcode_image(barcode_value, barcode_type)
            from django.core.files.base import ContentFile
            barcode.barcode_image.save(filename, ContentFile(image_bytes))
        except ImportError:
            pass  # Barcode library not installed

        messages.success(request, f"Barcode generated: {barcode_value}")
    except Exception as e:
        messages.error(request, f"Error generating barcode: {str(e)}")

    return redirect('retail:product_detail', pk=pk)


@login_required
@retail_required
def barcode_print_batch(request):
    """Batch print barcodes/labels for multiple products."""
    user = request.user
    products = filter_by_outlet(RetailProduct.objects.filter(is_active=True), user)

    if request.method == 'POST':
        product_ids = request.POST.getlist('products')
        label_size = request.POST.get('label_size', 'medium')

        selected_products = products.filter(pk__in=product_ids).prefetch_related('barcodes')

        # Build product list for PDF generation
        label_products = []
        for product in selected_products:
            barcode = product.primary_barcode
            if barcode:
                # Get individual quantity for this product
                qty_key = f'qty_{product.pk}'
                quantity = int(request.POST.get(qty_key, 1))
                if quantity > 0:
                    label_products.append({
                        'name': product.name,
                        'barcode': barcode.barcode_value,
                        'barcode_type': barcode.barcode_type,
                        'price': product.selling_price,
                        'mrp': product.mrp if product.mrp > product.selling_price else None,
                        'quantity': quantity,
                    })

        if label_products:
            try:
                pdf_bytes, filename = barcode_service.generate_batch_labels_pdf(
                    label_products,
                    label_size=label_size
                )

                response = HttpResponse(pdf_bytes, content_type='application/pdf')
                response['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            except ImportError as e:
                messages.error(request, f"PDF generation requires reportlab library: {e}")
            except Exception as e:
                messages.error(request, f"Error generating labels: {e}")

        return redirect('retail:barcode_print_batch')

    context = {
        "products": products.prefetch_related('barcodes').order_by('name')[:100],
        "label_sizes": barcode_service.LABEL_SIZES,
    }

    return render(request, "dashboard/retail/barcodes/print_batch.html", context)


@login_required
@retail_required
def barcode_scan_lookup(request):
    """Look up product by barcode or SKU (AJAX endpoint)."""
    barcode_value = request.GET.get('barcode', '').strip()

    if not barcode_value:
        return JsonResponse({'error': 'No barcode provided'}, status=400)

    user = request.user
    products = filter_by_outlet(RetailProduct.objects.filter(is_active=True), user)

    product = None

    # First, try exact barcode match
    barcode = ProductBarcode.objects.filter(
        barcode_value=barcode_value,
        product__in=products
    ).select_related('product').first()

    if barcode:
        product = barcode.product
    else:
        # Try SKU match
        product = products.filter(sku__iexact=barcode_value).first()

    if product:
        return JsonResponse({
            'found': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'sku': product.sku,
                'price': float(product.selling_price),  # Use 'price' for JS compatibility
                'selling_price': float(product.selling_price),
                'mrp': float(product.mrp),
                'tax_rate': float(product.tax_rate),
                'current_stock': float(product.current_stock) if product.track_inventory else None,
                'stock': float(product.current_stock) if product.track_inventory else 999,
                'unit': product.unit,
            }
        })

    return JsonResponse({'found': False, 'error': 'Product not found'})


# ============================================================================
# Retail POS
# ============================================================================


@login_required
@retail_required
def retail_pos(request):
    """Main POS interface for retail sales."""
    user = request.user
    outlet = get_user_outlet(user)

    products = filter_by_outlet(RetailProduct.objects.filter(is_active=True), user)
    products = products.select_related('category').prefetch_related('barcodes').order_by('name')

    categories = filter_by_outlet(RetailCategory.objects.filter(is_active=True), user).order_by('display_order', 'name')

    # Wholesale customers for B2B sales
    customers = []
    if getattr(settings, 'ENABLE_WHOLESALE', False):
        customers = filter_by_outlet(WholesaleCustomer.objects.filter(is_active=True), user).order_by('business_name')

    context = {
        "products": products,
        "categories": categories,
        "customers": customers,
        "currency_symbol": getattr(settings, 'DEFAULT_CURRENCY_SYMBOL', '₹'),
        "enable_wholesale": getattr(settings, 'ENABLE_WHOLESALE', False),
    }

    return render(request, "dashboard/retail/pos/index.html", context)


@login_required
@retail_required
def pos_barcode_lookup(request):
    """Quick barcode lookup for POS (alias to barcode_scan_lookup)."""
    return barcode_scan_lookup(request)


class SaleRejected(Exception):
    """Business rule failure while completing a POS sale (rolls the sale back)."""


@login_required
@retail_required
@require_POST
def pos_complete_sale(request):
    """Complete a retail sale transaction."""
    user = request.user
    outlet = get_user_outlet(user) or user.outlet

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    items = data.get('items', [])
    if not items:
        return JsonResponse({'error': 'No items in cart'}, status=400)

    # Super admins are not tied to an outlet: sell from the outlet the products belong to
    if outlet is None:
        first = RetailProduct.objects.filter(pk=items[0].get('product_id')).select_related('outlet').first()
        if first is None:
            return JsonResponse({'error': 'Product not found'}, status=404)
        outlet = first.outlet

    # Choice values are stored lowercase; accept any case from the client
    sale_type = str(data.get('sale_type') or RetailSale.SaleType.RETAIL).lower()
    if sale_type not in RetailSale.SaleType.values:
        return JsonResponse({'error': 'Unknown sale type'}, status=400)
    payment_method = str(data.get('payment_method') or RetailSale.PaymentMethod.CASH).lower()
    if payment_method not in RetailSale.PaymentMethod.values:
        return JsonResponse({'error': 'Unknown payment method'}, status=400)
    on_credit = payment_method == RetailSale.PaymentMethod.CREDIT
    # "Show QR": the customer scans and pays from their phone; the sale stays
    # pending until the payment comes in
    collect_qr = bool(data.get('collect_qr'))
    if collect_qr:
        if sale_type == RetailSale.SaleType.WHOLESALE:
            return JsonResponse({'error': 'Scan-to-pay QR is for retail sales'}, status=400)
        if _qr_mode() is None:
            return JsonResponse({'error': 'Set up Razorpay or a UPI ID in Settings → Payment Gateway to show a payment QR'}, status=400)
        payment_method = RetailSale.PaymentMethod.UPI
    customer_id = data.get('customer_id')
    payment_reference = data.get('payment_reference', '')
    discount_amount = Decimal(str(data.get('discount', 0)))

    customer = None
    if sale_type == RetailSale.SaleType.WHOLESALE:
        if not customer_id:
            return JsonResponse({'error': 'Choose a wholesale customer for a wholesale sale'}, status=400)
        customer = WholesaleCustomer.objects.filter(pk=customer_id, is_active=True).first()
        if customer is None or (outlet and customer.outlet_id and customer.outlet_id != outlet.pk):
            return JsonResponse({'error': 'Wholesale customer not found'}, status=400)
    elif on_credit:
        return JsonResponse({'error': 'Credit is only available for wholesale customers'}, status=400)

    try:
        with transaction.atomic():
            # Create sale
            sale = RetailSale.objects.create(
                outlet=outlet,
                sale_type=sale_type,
                wholesale_customer=customer,
                discount_amount=discount_amount,
                payment_method=payment_method,
                # RetailSale has no reference field; keep card/UPI references in the internal notes
                internal_notes=f"Payment reference: {payment_reference}" if payment_reference else "",
                payment_status=RetailSale.PaymentStatus.PENDING if (on_credit or collect_qr) else RetailSale.PaymentStatus.PAID,
                created_by=user,
            )

            subtotal = Decimal('0')
            total_cgst = Decimal('0')
            total_sgst = Decimal('0')

            for item in items:
                product_id = item.get('product_id')
                quantity = Decimal(str(item.get('quantity', 1)))
                unit_price = Decimal(str(item.get('unit_price', 0)))
                discount = Decimal(str(item.get('discount', 0)))

                product = RetailProduct.objects.get(pk=product_id, outlet=outlet)

                # Calculate line total
                line_subtotal = (unit_price * quantity) - discount
                tax_rate = product.tax_rate
                tax_amount = line_subtotal * tax_rate / 100
                line_total = line_subtotal + tax_amount

                # Create sale item
                cgst = tax_amount / 2
                sgst = tax_amount / 2
                RetailSaleItem.objects.create(
                    sale=sale,
                    product=product,
                    product_name=product.name,
                    product_sku=product.sku or '',
                    hsn_code=product.hsn_code or '',
                    quantity=quantity,
                    unit_price=unit_price,
                    discount_amount=discount,
                    subtotal=line_subtotal,
                    tax_rate=tax_rate,
                    cgst_amount=cgst,
                    sgst_amount=sgst,
                    total=line_total,
                )

                subtotal += line_subtotal

                # Split tax into CGST and SGST
                total_cgst += tax_amount / 2
                total_sgst += tax_amount / 2

                # Update stock
                if product.track_inventory:
                    stock_before = product.current_stock
                    product.current_stock -= quantity
                    product.save()

                    RetailStockMovement.objects.create(
                        product=product,
                        movement_type=RetailStockMovement.MovementType.SALE,
                        quantity=-quantity,
                        stock_before=stock_before,
                        stock_after=product.current_stock,
                        reference_type="RetailSale",
                        reference_id=sale.pk,
                        reason=f"Sale {sale.sale_number}",
                        created_by=user,
                    )

            # Update sale totals
            sale.subtotal = subtotal
            sale.cgst_amount = total_cgst
            sale.sgst_amount = total_sgst
            sale.total_amount = subtotal + total_cgst + total_sgst - discount_amount
            sale.paid_amount = Decimal('0') if (on_credit or collect_qr) else sale.total_amount
            sale.save()

            # Wholesale sales get a tax invoice; credit sales stay open against the
            # customer's credit limit, paid ones are invoiced as paid
            if customer:
                if on_credit and customer.current_balance + sale.total_amount > customer.credit_limit:
                    raise SaleRejected(
                        f"{customer.business_name} has {customer.available_credit} credit available "
                        f"(limit {customer.credit_limit}). Collect payment or raise the credit limit."
                    )
                WholesaleInvoice.objects.create(
                    customer=customer,
                    sale=sale,
                    invoice_date=timezone.localdate(),
                    amount=sale.total_amount,
                    paid_amount=Decimal('0') if on_credit else sale.total_amount,
                    created_by=user,
                )
                customer.update_balance()

            result = {
                'success': True,
                'sale_id': sale.id,
                'sale_number': sale.sale_number,
                'total': str(sale.total_amount),
            }
            if collect_qr:
                result['qr'] = _qr_info(request, sale)
                _show_on_display(user, sale)
            return JsonResponse(result)

    except SaleRejected as e:
        return JsonResponse({'error': str(e)}, status=400)
    except RetailProduct.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


# ============================================================================
# Sales
# ============================================================================


@login_required
@retail_required
def sale_list(request):
    """List all retail sales."""
    user = request.user
    sales = filter_by_outlet(RetailSale.objects.all(), user)

    # Date filter
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    if date_from:
        sales = sales.filter(created_at__date__gte=date_from)
    if date_to:
        sales = sales.filter(created_at__date__lte=date_to)

    # Type filter
    sale_type = request.GET.get('type')
    if sale_type:
        sales = sales.filter(sale_type=sale_type)

    # Payment status filter
    payment_status = request.GET.get('status')
    if payment_status:
        sales = sales.filter(payment_status=payment_status)

    sales = sales.select_related('wholesale_customer', 'created_by', 'outlet').order_by('-created_at')

    # Pagination
    paginator = Paginator(sales, 25)
    page = request.GET.get('page')
    sales = paginator.get_page(page)

    context = {
        "sales": sales,
        "date_from": date_from,
        "date_to": date_to,
        "sale_type": sale_type,
        "payment_status": payment_status,
    }

    return render(request, "dashboard/retail/sales/list.html", context)


@login_required
@retail_required
def sale_detail(request, pk):
    """View sale details."""
    user = request.user
    sales = filter_by_outlet(RetailSale.objects.all(), user)
    sale = get_object_or_404(sales.select_related('wholesale_customer', 'created_by', 'outlet'), pk=pk)

    items = sale.items.select_related('product').all()

    context = {
        "sale": sale,
        "items": items,
    }

    return render(request, "dashboard/retail/sales/detail.html", context)


@login_required
@retail_required
def sale_receipt(request, pk):
    """Print sale receipt."""
    user = request.user
    sales = filter_by_outlet(RetailSale.objects.all(), user)
    sale = get_object_or_404(sales.select_related('wholesale_customer', 'created_by', 'outlet'), pk=pk)

    items = sale.items.select_related('product').all()

    context = {
        "sale": sale,
        "items": items,
    }

    return render(request, "dashboard/retail/sales/receipt.html", context)


# ============================================================================
# Wholesale Customers
# ============================================================================


@login_required
@retail_required
def customer_list(request):
    """List wholesale customers."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    customers = filter_by_outlet(WholesaleCustomer.objects.all(), user)

    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(business_name__icontains=search) |
            Q(name__icontains=search) |
            Q(phone__icontains=search) |
            Q(gst_number__icontains=search)
        )

    customers = customers.order_by('business_name')

    # Pagination
    paginator = Paginator(customers, 20)
    page = request.GET.get('page')
    customers = paginator.get_page(page)

    context = {
        "customers": customers,
        "search": search,
    }

    return render(request, "dashboard/retail/customers/list.html", context)


@login_required
@retail_required
def customer_create(request):
    """Create a new wholesale customer."""
    from .forms import WholesaleCustomerForm

    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    outlet = get_user_outlet(user)

    if request.method == 'POST':
        form = WholesaleCustomerForm(request.POST, user=user)
        if form.is_valid():
            customer = form.save(commit=False)
            if outlet:
                customer.outlet = outlet
            customer.save()
            messages.success(request, f"Customer '{customer.business_name}' created successfully.")
            return redirect('retail:customer_detail', pk=customer.pk)
    else:
        form = WholesaleCustomerForm(user=user)

    context = {
        "form": form,
        "is_create": True,
    }

    return render(request, "dashboard/retail/customers/form.html", context)


@login_required
@retail_required
def customer_detail(request, pk):
    """View customer details."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    customers = filter_by_outlet(WholesaleCustomer.objects.all(), user)
    customer = get_object_or_404(customers, pk=pk)

    # Recent sales
    sales = customer.sales.order_by('-created_at')[:10]

    # Recent payments
    payments = customer.payments.order_by('-payment_date')[:10]

    # Unpaid invoices
    invoices = customer.invoices.exclude(
        status__in=[WholesaleInvoice.Status.PAID, WholesaleInvoice.Status.CANCELLED, WholesaleInvoice.Status.DRAFT]
    ).order_by('due_date')

    context = {
        "customer": customer,
        "sales": sales,
        "payments": payments,
        "invoices": invoices,
    }

    return render(request, "dashboard/retail/customers/detail.html", context)


@login_required
@retail_required
def customer_edit(request, pk):
    """Edit a customer."""
    from .forms import WholesaleCustomerForm

    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    customers = filter_by_outlet(WholesaleCustomer.objects.all(), user)
    customer = get_object_or_404(customers, pk=pk)

    if request.method == 'POST':
        form = WholesaleCustomerForm(request.POST, instance=customer, user=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Customer '{customer.business_name}' updated successfully.")
            return redirect('retail:customer_detail', pk=customer.pk)
    else:
        form = WholesaleCustomerForm(instance=customer, user=user)

    context = {
        "form": form,
        "customer": customer,
        "is_create": False,
    }

    return render(request, "dashboard/retail/customers/form.html", context)


@login_required
@retail_required
def customer_statement(request, pk):
    """Generate customer statement."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    customers = filter_by_outlet(WholesaleCustomer.objects.all(), user)
    customer = get_object_or_404(customers, pk=pk)

    # Date range
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')

    # Get all transactions
    sales = customer.sales.all()
    payments = customer.payments.all()

    if date_from:
        sales = sales.filter(created_at__date__gte=date_from)
        payments = payments.filter(payment_date__gte=date_from)
    if date_to:
        sales = sales.filter(created_at__date__lte=date_to)
        payments = payments.filter(payment_date__lte=date_to)

    context = {
        "customer": customer,
        "sales": sales.order_by('-created_at'),
        "payments": payments.order_by('-payment_date'),
        "date_from": date_from,
        "date_to": date_to,
    }

    return render(request, "dashboard/retail/customers/statement.html", context)


# ============================================================================
# Invoices
# ============================================================================


@login_required
@retail_required
def invoice_list(request):
    """List wholesale invoices."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    invoices = filter_by_outlet(WholesaleInvoice.objects.all(), user, outlet_field='customer__outlet')

    status = request.GET.get('status')
    if status:
        invoices = invoices.filter(status=status)

    invoices = invoices.select_related('customer', 'sale').order_by('-created_at')

    # Pagination
    paginator = Paginator(invoices, 25)
    page = request.GET.get('page')
    invoices = paginator.get_page(page)

    context = {
        "invoices": invoices,
        "status_filter": status,
    }

    return render(request, "dashboard/retail/invoices/list.html", context)


@login_required
@retail_required
def invoice_detail(request, pk):
    """View invoice details."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    invoices = filter_by_outlet(WholesaleInvoice.objects.all(), user, outlet_field='customer__outlet')
    invoice = get_object_or_404(invoices.select_related('customer', 'sale'), pk=pk)

    # Get sale items
    items = invoice.sale.items.all() if invoice.sale else []

    # Get payments applied to this invoice
    payments = invoice.payments.order_by('-payment_date')

    context = {
        "invoice": invoice,
        "items": items,
        "payments": payments,
    }

    return render(request, "dashboard/retail/invoices/detail.html", context)


@login_required
@retail_required
def invoice_print(request, pk):
    """Print invoice."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    invoices = filter_by_outlet(WholesaleInvoice.objects.all(), user, outlet_field='customer__outlet')
    invoice = get_object_or_404(invoices.select_related('customer', 'sale'), pk=pk)

    items = invoice.sale.items.all() if invoice.sale else []

    context = {
        "invoice": invoice,
        "items": items,
    }

    return render(request, "dashboard/retail/invoices/print.html", context)


# ============================================================================
# Payments
# ============================================================================


@login_required
@retail_required
def payment_list(request):
    """List customer payments."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    payments = filter_by_outlet(CustomerPayment.objects.all(), user, outlet_field='customer__outlet')

    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    if date_from:
        payments = payments.filter(payment_date__gte=date_from)
    if date_to:
        payments = payments.filter(payment_date__lte=date_to)

    payments = payments.select_related('customer', 'received_by').order_by('-payment_date')

    # Pagination
    paginator = Paginator(payments, 25)
    page = request.GET.get('page')
    payments = paginator.get_page(page)

    context = {
        "payments": payments,
        "date_from": date_from,
        "date_to": date_to,
    }

    return render(request, "dashboard/retail/payments/list.html", context)


@login_required
@retail_required
def payment_receive(request):
    """Record a customer payment."""
    from .forms import CustomerPaymentForm

    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user

    if request.method == 'POST':
        form = CustomerPaymentForm(request.POST, user=user)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.received_by = user
            # save() updates the invoice's paid amount and status, the linked sale,
            # and recalculates the customer's balance
            payment.save()
            customer = payment.customer

            messages.success(request, f"Payment of {payment.amount} received from {customer.business_name}.")
            return redirect('retail:payment_receipt', pk=payment.pk)
    else:
        initial = {}
        if request.GET.get('customer'):
            initial['customer'] = request.GET['customer']
        if request.GET.get('invoice'):
            initial['invoice'] = request.GET['invoice']
        form = CustomerPaymentForm(user=user, initial=initial)

    context = {
        "form": form,
    }

    return render(request, "dashboard/retail/payments/receive.html", context)


@login_required
@retail_required
def payment_receipt(request, pk):
    """Print payment receipt."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    payments = filter_by_outlet(CustomerPayment.objects.all(), user, outlet_field='customer__outlet')
    payment = get_object_or_404(payments.select_related('customer', 'received_by', 'invoice'), pk=pk)

    context = {
        "payment": payment,
    }

    return render(request, "dashboard/retail/payments/receipt.html", context)


# ============================================================================
# Outstanding
# ============================================================================


@login_required
@retail_required
def outstanding_dashboard(request):
    """Dashboard showing outstanding amounts."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    customers = filter_by_outlet(WholesaleCustomer.objects.filter(current_balance__gt=0), user)
    customers = customers.order_by('-current_balance')

    total_outstanding = customers.aggregate(total=Sum('current_balance'))['total'] or Decimal('0')

    # Overdue invoices
    today = timezone.now().date()
    overdue_invoices = filter_by_outlet(
        WholesaleInvoice.objects.filter(
            status__in=[
                WholesaleInvoice.Status.PENDING,
                WholesaleInvoice.Status.PARTIAL,
                WholesaleInvoice.Status.OVERDUE,
            ],
            due_date__lt=today
        ),
        user,
        outlet_field='customer__outlet'
    ).select_related('customer')

    context = {
        "customers": customers,
        "total_outstanding": total_outstanding,
        "overdue_invoices": overdue_invoices,
    }

    return render(request, "dashboard/retail/outstanding/dashboard.html", context)


@login_required
@retail_required
def aging_report(request):
    """Aging report for outstanding amounts."""
    if not getattr(settings, 'ENABLE_WHOLESALE', False):
        messages.error(request, "Wholesale module is not enabled.")
        return redirect("retail:dashboard")

    user = request.user
    today = timezone.now().date()

    invoices = filter_by_outlet(
        WholesaleInvoice.objects.exclude(
            status__in=[WholesaleInvoice.Status.PAID, WholesaleInvoice.Status.CANCELLED, WholesaleInvoice.Status.DRAFT]
        ),
        user,
        outlet_field='customer__outlet'
    ).select_related('customer')

    # Categorize by aging
    current = []  # Not yet due
    days_30 = []  # 1-30 days overdue
    days_60 = []  # 31-60 days overdue
    days_90 = []  # 61-90 days overdue
    over_90 = []  # 90+ days overdue

    for invoice in invoices:
        days_overdue = (today - invoice.due_date).days
        balance = invoice.amount - invoice.paid_amount

        entry = {
            'invoice': invoice,
            'balance': balance,
            'days_overdue': days_overdue,
        }

        if days_overdue <= 0:
            current.append(entry)
        elif days_overdue <= 30:
            days_30.append(entry)
        elif days_overdue <= 60:
            days_60.append(entry)
        elif days_overdue <= 90:
            days_90.append(entry)
        else:
            over_90.append(entry)

    context = {
        "current": current,
        "days_30": days_30,
        "days_60": days_60,
        "days_90": days_90,
        "over_90": over_90,
        "total_current": sum(e['balance'] for e in current),
        "total_30": sum(e['balance'] for e in days_30),
        "total_60": sum(e['balance'] for e in days_60),
        "total_90": sum(e['balance'] for e in days_90),
        "total_over_90": sum(e['balance'] for e in over_90),
    }

    return render(request, "dashboard/retail/outstanding/aging.html", context)


# ============================================================================
# Stock Management
# ============================================================================


@login_required
@retail_required
def stock_list(request):
    """List product stock levels."""
    user = request.user
    products = filter_by_outlet(
        RetailProduct.objects.filter(is_active=True, track_inventory=True),
        user
    )

    # Filter by stock status
    stock_filter = request.GET.get('filter')
    if stock_filter == 'low':
        products = products.filter(current_stock__lte=F('minimum_stock'), current_stock__gt=0)
    elif stock_filter == 'out':
        products = products.filter(current_stock=0)
    elif stock_filter == 'ok':
        products = products.filter(current_stock__gt=F('minimum_stock'))

    products = products.select_related('category').order_by('current_stock')

    # Pagination
    paginator = Paginator(products, 25)
    page = request.GET.get('page')
    products = paginator.get_page(page)

    context = {
        "products": products,
        "stock_filter": stock_filter,
    }

    return render(request, "dashboard/retail/stock/list.html", context)


@login_required
@retail_required
def stock_adjust(request):
    """Adjust stock levels."""
    from .forms import StockAdjustmentForm

    user = request.user

    if request.method == 'POST':
        form = StockAdjustmentForm(request.POST, user=user)
        if form.is_valid():
            product = form.cleaned_data['product']
            adjustment_type = form.cleaned_data['adjustment_type']
            quantity = form.cleaned_data['quantity']
            reason = form.cleaned_data['reason']

            stock_before = product.current_stock

            if adjustment_type == 'add':
                product.current_stock += quantity
                movement_type = RetailStockMovement.MovementType.PURCHASE
            else:
                product.current_stock -= quantity
                movement_type = RetailStockMovement.MovementType.ADJUSTMENT

            product.save()

            RetailStockMovement.objects.create(
                product=product,
                movement_type=movement_type,
                quantity=quantity if adjustment_type == 'add' else -quantity,
                stock_before=stock_before,
                stock_after=product.current_stock,
                reason=reason[:200],
                created_by=user,
            )

            messages.success(request, f"Stock adjusted for {product.name}. New stock: {product.current_stock}")
            return redirect('retail:stock')
    else:
        product_id = request.GET.get('product')
        initial = {'product': product_id} if product_id else {}
        form = StockAdjustmentForm(user=user, initial=initial)

    context = {
        "form": form,
    }

    return render(request, "dashboard/retail/stock/adjust.html", context)


@login_required
@retail_required
def stock_movements(request):
    """View stock movement history."""
    user = request.user
    movements = filter_by_outlet(RetailStockMovement.objects.all(), user, outlet_field='product__outlet')

    # Filter by product
    product_id = request.GET.get('product')
    if product_id:
        movements = movements.filter(product_id=product_id)

    # Filter by type
    movement_type = request.GET.get('type')
    if movement_type:
        movements = movements.filter(movement_type=movement_type)

    movements = movements.select_related('product', 'created_by').order_by('-created_at')

    # Pagination
    paginator = Paginator(movements, 50)
    page = request.GET.get('page')
    movements = paginator.get_page(page)

    context = {
        "movements": movements,
        "product_id": product_id,
        "movement_type": movement_type,
    }

    return render(request, "dashboard/retail/stock/movements.html", context)


# ============================================================================
# POS: scan-to-pay QR
# ============================================================================


def _qr_mode():
    """'razorpay' (auto-confirmed), 'upi' (plain UPI QR, cashier confirms) or None."""
    from apps.payments.models import PaymentSettings

    ps = PaymentSettings.load()
    if ps.get_razorpay_client() is not None:
        return 'razorpay'
    if ps.upi_id:
        return 'upi'
    return None


def _qr_info(request, sale):
    from django.urls import reverse

    from apps.payments.services import public_url

    mode = _qr_mode()
    info = {
        'mode': mode,
        'uuid': str(sale.uuid),
        'amount': f"{sale.total_amount:.2f}",
        'status_url': reverse('retail:pos_sale_status', args=[sale.uuid]),
        'settle_url': reverse('retail:pos_sale_settle', args=[sale.uuid]),
    }
    if mode == 'razorpay':
        info['qr_url'] = reverse('payments:pay_sale_qr', args=[sale.uuid])
        info['pay_url'] = public_url(request, reverse('payments:pay_sale', args=[sale.uuid]))
    else:
        info['qr_url'] = reverse('retail:pos_sale_upi_qr', args=[sale.uuid])
    return info


def _upi_link(sale):
    from urllib.parse import quote

    from apps.core.models import BusinessSettings
    from apps.payments.models import PaymentSettings

    ps = PaymentSettings.load()
    name = ps.upi_merchant_name or BusinessSettings.load().business_name
    return (
        f"upi://pay?pa={quote(ps.upi_id)}&pn={quote(name)}&am={sale.total_amount - sale.paid_amount:.2f}"
        f"&cu=INR&tn={quote('Bill ' + sale.sale_number)}&tr={quote(sale.sale_number)}"
    )


def _show_on_display(user, sale):
    """Put the sale and its QR on the customer-facing screen."""
    from apps.dashboard.billing import _display_key
    from apps.orders.models import CounterDisplay

    CounterDisplay.objects.update_or_create(
        key=_display_key(user), defaults={'mode': CounterDisplay.Mode.BILL, 'order': None, 'retail_sale': sale}
    )


def _pos_sale(request, sale_uuid):
    sale = get_object_or_404(RetailSale, uuid=sale_uuid)
    outlet = get_user_outlet(request.user)
    if outlet is not None and sale.outlet_id != outlet.pk:
        return None
    return sale


@login_required
@retail_required
def pos_sale_upi_qr(request, sale_uuid):
    from apps.tables.qr_svg import qr_svg

    sale = _pos_sale(request, sale_uuid)
    if sale is None:
        return HttpResponse(status=404)
    return HttpResponse(qr_svg(_upi_link(sale), logo_hole=False), content_type='image/svg+xml')


@login_required
@retail_required
def pos_sale_status(request, sale_uuid):
    from apps.payments.views import sync_sale

    sale = _pos_sale(request, sale_uuid)
    if sale is None:
        return JsonResponse({'error': 'Not found'}, status=404)
    due = sync_sale(sale)
    return JsonResponse({'status': sale.payment_status, 'paid': sale.payment_status == 'paid', 'amount_due': f"{due:.2f}",
                         'method': sale.payment_method})


@login_required
@retail_required
@require_POST
def pos_sale_settle(request, sale_uuid):
    """Cashier closes a QR sale: payment received (plain UPI), paid another way, or cancel."""
    from apps.payments.views import sync_sale

    if request.user.role not in ('super_admin', 'outlet_manager', 'staff_cashier'):
        return JsonResponse({'error': 'Only the counter can settle a sale'}, status=403)
    sale = _pos_sale(request, sale_uuid)
    if sale is None:
        return JsonResponse({'error': 'Not found'}, status=404)
    try:
        action = json.loads(request.body or b'{}').get('action', '')
    except json.JSONDecodeError:
        action = ''
    if sync_sale(sale) <= 0 and sale.payment_status == 'paid':
        return JsonResponse({'ok': True, 'status': 'paid'})
    if sale.payment_status not in ('pending', 'partial'):
        return JsonResponse({'error': 'This sale is already closed'}, status=400)

    with transaction.atomic():
        sale = RetailSale.objects.select_for_update().get(pk=sale.pk)
        if action in ('upi_received', 'cash', 'card'):
            sale.payment_method = {'upi_received': 'upi', 'cash': 'cash', 'card': 'card'}[action]
            sale.paid_amount = sale.total_amount
            sale.payment_status = RetailSale.PaymentStatus.PAID
            sale.internal_notes = (sale.internal_notes + f"\nPayment confirmed by {request.user.get_full_name() or request.user.username}").strip()
            sale.save(update_fields=['payment_method', 'paid_amount', 'payment_status', 'internal_notes', 'updated_at'])
        elif action == 'cancel':
            if sale.paid_amount > 0:
                return JsonResponse({'error': 'Part of this sale is already paid; refund it from Sales'}, status=400)
            for item in sale.items.select_related('product'):
                product = item.product
                if product is not None and product.track_inventory:
                    before = product.current_stock
                    product.current_stock += item.quantity
                    product.save(update_fields=['current_stock', 'updated_at'])
                    RetailStockMovement.objects.create(
                        product=product,
                        movement_type=RetailStockMovement.MovementType.RETURN,
                        quantity=item.quantity,
                        stock_before=before,
                        stock_after=product.current_stock,
                        reference_type="RetailSale",
                        reference_id=sale.pk,
                        reason=f"Cancelled QR sale {sale.sale_number}",
                        created_by=request.user,
                    )
            sale.payment_status = RetailSale.PaymentStatus.CANCELLED
            sale.save(update_fields=['payment_status', 'updated_at'])
        else:
            return JsonResponse({'error': 'Unknown action'}, status=400)
    return JsonResponse({'ok': True, 'status': sale.payment_status})
