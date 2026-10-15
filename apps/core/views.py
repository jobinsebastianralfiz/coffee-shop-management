"""
Core views for the Coffee Shop Management System.
"""

from django.conf import settings
from django.views.generic import TemplateView

from .models import Outlet


class PlanInfoView(TemplateView):
    """
    Display current plan information (read-only, from settings).
    This shows the plan configured by the vendor via environment variables.
    """

    template_name = "core/plan_info.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # Get plan info from settings (configured by vendor in .env)
        max_outlets = getattr(settings, "MAX_OUTLETS", 1)
        max_staff = getattr(settings, "MAX_STAFF_PER_OUTLET", 0)
        max_managers = getattr(settings, "MAX_OUTLET_MANAGERS_PER_OUTLET", 0)
        max_tables = getattr(settings, "MAX_TABLES_PER_OUTLET", 0)

        context["plan"] = {
            "name": getattr(settings, "PLAN_NAME", "Basic"),
            "max_outlets": max_outlets,
            "max_outlets_display": "Unlimited" if max_outlets == 0 else max_outlets,
            "max_staff_per_outlet": max_staff,
            "max_staff_display": "Unlimited" if max_staff == 0 else max_staff,
            "max_managers_per_outlet": max_managers,
            "max_managers_display": "Unlimited" if max_managers == 0 else max_managers,
            "max_tables_per_outlet": max_tables,
            "max_tables_display": "Unlimited" if max_tables == 0 else max_tables,
            "features": getattr(settings, "PLAN_FEATURES", []),
        }

        # Current usage
        context["usage"] = {
            "outlets_used": Outlet.objects.count(),
            "outlets_remaining": Outlet.outlets_remaining(),
            "can_create_outlet": Outlet.can_create_outlet(),
        }

        return context


plan_info_view = PlanInfoView.as_view()
