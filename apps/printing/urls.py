"""
URL patterns for the printing app.
"""

from django.urls import path

from apps.printing import agent_api, views

app_name = "printing"

urlpatterns = [
    path("receipt/<int:order_id>/", views.print_receipt_view, name="print_receipt"),
    path("kot/<int:order_id>/", views.print_kot_view, name="print_kot"),
    path("test/<str:printer_type>/", views.test_printer_view, name="test_printer"),
    path("status/", views.printer_status_view, name="printer_status"),
    # Outlet print agent
    path("agent/poll/", agent_api.agent_poll, name="agent_poll"),
    path("agent/jobs/<int:job_id>/report/", agent_api.agent_report, name="agent_report"),
]
