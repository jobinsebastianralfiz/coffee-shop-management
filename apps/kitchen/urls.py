from django.urls import path

from . import views

app_name = "kitchen"

urlpatterns = [
    path("", views.stations, name="stations"),
    path("stations/add/", views.station_save, name="station_add"),
    path("stations/<int:pk>/edit/", views.station_save, name="station_edit"),
    path("stations/<int:pk>/delete/", views.station_delete, name="station_delete"),
    path("stations/<int:pk>/test-print/", views.station_test_print, name="station_test_print"),
    path("routing/", views.routing_save, name="routing_save"),
    path("agent/create/", views.agent_create, name="agent_create"),
    path("agent/<int:pk>/regenerate/", views.agent_regenerate, name="agent_regenerate"),
    path("agent/download/", views.agent_download, name="agent_download"),
    path("jobs/<int:pk>/retry/", views.job_retry, name="job_retry"),
    path("jobs/<int:pk>/cancel/", views.job_cancel, name="job_cancel"),
]
