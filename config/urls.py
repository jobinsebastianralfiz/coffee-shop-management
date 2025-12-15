"""
URL configuration for Coffee Shop Management System.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.shortcuts import redirect
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

# Override Django admin login to use our custom login
admin.site.login = lambda request, extra_context=None: redirect('dashboard:login')

urlpatterns = [
    # Admin (uses our custom login)
    path("admin/", admin.site.urls),

    # Core (pricing page, etc.)
    path("", include("apps.core.urls")),

    # Dashboard (Custom Admin)
    path("", include("apps.dashboard.urls")),

    # Customer QR Ordering
    path("order/", include("apps.ordering.urls")),

    # Waiter PWA
    path("waiter/", include("apps.waiter.urls")),

    # Printing
    path("printing/", include("apps.printing.urls")),

    # Reports
    path("reports/", include("apps.reports.urls")),

    # API v1
    path("api/v1/", include("apps.accounts.urls")),
    path("api/v1/menu/", include("apps.menu.urls")),
    path("api/v1/tables/", include("apps.tables.urls")),

    # API Documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

    # Debug toolbar
    try:
        import debug_toolbar

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass
