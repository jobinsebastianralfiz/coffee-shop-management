"""
URL configuration for core app.
"""

from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    # Plan info page (read-only, shows vendor-configured plan)
    path("plan/", views.plan_info_view, name="plan_info"),
]
