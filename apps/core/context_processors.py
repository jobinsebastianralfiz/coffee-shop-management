"""
Context processors for the Coffee Shop Management System.
Makes business settings and branding available in all templates.
"""

from django.conf import settings as django_settings

from .models import BusinessSettings, TaxSettings, OrderSettings


def business_settings(request):
    """
    Add business settings to template context.
    This makes branding, theme colors, and business info
    available in all templates.
    """
    try:
        business = BusinessSettings.load()
    except Exception:
        # Return defaults if database not ready
        business = None

    if business:
        return {
            "business": business,
            "business_name": business.business_name,
            "business_tagline": business.tagline,
            "business_logo": business.logo.url if business.logo else None,
            "business_logo_dark": business.logo_dark.url if business.logo_dark else None,
            "business_favicon": business.favicon.url if business.favicon else None,
            # Theme colors
            "theme": {
                "primary": business.primary_color,
                "secondary": business.secondary_color,
                "accent": business.accent_color,
                "sidebar_bg": business.sidebar_color,
                "sidebar_text": business.sidebar_text_color,
                "sidebar_active": business.sidebar_active_color,
                "default_mode": business.default_theme,
                # Login page
                "login_gradient_start": business.login_bg_gradient_start,
                "login_gradient_end": business.login_bg_gradient_end,
                "login_welcome": business.login_welcome_text,
                "login_subtitle": business.login_subtitle,
            },
            # Contact info
            "business_address": business.address,
            "business_phone": business.phone,
            "business_email": business.email,
            # Currency
            "currency": business.currency,
            "currency_symbol": business.currency_symbol,
        }

    # Default values if no settings exist
    return {
        "business": None,
        "business_name": "Coffee Shop",
        "business_tagline": "Management System",
        "business_logo": None,
        "business_logo_dark": None,
        "business_favicon": None,
        "theme": {
            "primary": "#f59e0b",
            "secondary": "#ea580c",
            "accent": "#dc2626",
            "sidebar_bg": "#ffffff",
            "sidebar_text": "#374151",
            "sidebar_active": "#6366f1",
            "default_mode": "light",
            "login_gradient_start": "#f59e0b",
            "login_gradient_end": "#dc2626",
            "login_welcome": "Welcome back!",
            "login_subtitle": "Sign in to your account",
        },
        "business_address": "",
        "business_phone": "",
        "business_email": "",
        "currency": "INR",
        "currency_symbol": "₹",
    }


def app_settings(request):
    """
    Add app-level settings to template context.
    """
    return {
        "DEBUG": django_settings.DEBUG,
        "MEDIA_URL": django_settings.MEDIA_URL,
    }


def notifications_context(request):
    """
    Add unread notification count to template context.
    This makes the notification badge count available in all templates.
    """
    if not request.user.is_authenticated:
        return {"unread_notifications_count": 0}

    try:
        from django.db.models import Q

        from apps.notifications.models import Notification, NotificationRead

        user = request.user

        # Build query for notifications relevant to this user
        query = Q(is_broadcast=True)
        query |= Q(recipient=user)
        query |= Q(target_role=user.role)

        if user.outlet_id:
            query |= Q(target_outlet_id=user.outlet_id)

        # Count notifications not read by this user
        read_ids = NotificationRead.objects.filter(
            user=user
        ).values_list("notification_id", flat=True)

        unread_count = Notification.objects.filter(query).exclude(
            pk__in=read_ids
        ).count()

        return {"unread_notifications_count": unread_count}
    except Exception:
        # Return 0 if database not ready or any error
        return {"unread_notifications_count": 0}
