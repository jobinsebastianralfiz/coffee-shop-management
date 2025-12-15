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
        context["plan"] = {
            "name": getattr(settings, "PLAN_NAME", "Basic"),
            "max_outlets": max_outlets,
            "max_outlets_display": "Unlimited" if max_outlets == 0 else max_outlets,
            "max_staff_per_outlet": getattr(settings, "MAX_STAFF_PER_OUTLET", 0),
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
