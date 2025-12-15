"""
Views for thermal printing functionality.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from apps.orders.models import Order
from apps.printing import services


@login_required
@require_POST
def print_receipt_view(request, order_id):
    """Print receipt for an order."""
    order = get_object_or_404(
        Order.objects.select_related('table', 'served_by', 'kitchen_ticket')
        .prefetch_related('items', 'payments'),
        pk=order_id
    )

    success, message = services.print_receipt(order)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': success,
            'message': message
        })

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Redirect back to referring page or order detail
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('dashboard:order_detail', pk=order_id)


@login_required
@require_POST
def print_kot_view(request, order_id):
    """Print Kitchen Order Ticket for an order."""
    order = get_object_or_404(
        Order.objects.select_related('table', 'kitchen_ticket')
        .prefetch_related('items'),
        pk=order_id
    )

    success, message = services.print_kot(order)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': success,
            'message': message
        })

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    # Redirect back to referring page or kitchen
    referer = request.META.get('HTTP_REFERER')
    if referer:
        return redirect(referer)
    return redirect('dashboard:kitchen')


@login_required
def test_printer_view(request, printer_type):
    """Test printer connection."""
    if printer_type == 'receipt':
        success, message = services.test_receipt_printer()
    elif printer_type == 'kot':
        success, message = services.test_kot_printer()
    else:
        success, message = False, "Invalid printer type"

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return JsonResponse({
            'success': success,
            'message': message
        })

    if success:
        messages.success(request, message)
    else:
        messages.error(request, message)

    return redirect('dashboard:settings')


@login_required
def printer_status_view(request):
    """Get status of all printers."""
    receipt_status = services.test_receipt_printer()
    kot_status = services.test_kot_printer()

    return JsonResponse({
        'receipt': {
            'success': receipt_status[0],
            'message': receipt_status[1]
        },
        'kot': {
            'success': kot_status[0],
            'message': kot_status[1]
        }
    })
