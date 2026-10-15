"""
URL configuration for the customer ordering app.
"""

from django.urls import path

from . import views

app_name = "ordering"

urlpatterns = [
    # QR code landing page
    path("t/<uuid:table_uuid>/", views.landing, name="landing"),

    # Order on the table's shared bill (default) / choose a separate seat bill
    path("t/<uuid:table_uuid>/order-here/", views.order_here, name="order_here"),
    path("t/<uuid:table_uuid>/seat/", views.select_seat, name="select_seat"),

    # Table presence check (see apps.ordering.guard)
    path("t/<uuid:table_uuid>/guest/status/", views.guest_status, name="guest_status"),
    path("t/<uuid:table_uuid>/guest/locate/", views.guest_locate, name="guest_locate"),
    path("t/<uuid:table_uuid>/guest/code/", views.guest_code, name="guest_code"),

    # Main menu
    path("t/<uuid:table_uuid>/menu/", views.table_menu, name="menu"),

    # Change seat
    path("t/<uuid:table_uuid>/change-seat/", views.change_seat, name="change_seat"),

    # Order management
    path("t/<uuid:table_uuid>/create/", views.create_order, name="create_order"),
    path("t/<uuid:table_uuid>/add/", views.add_item, name="add_item"),
    path("t/<uuid:table_uuid>/update/", views.update_item_quantity, name="update_item"),
    path("t/<uuid:table_uuid>/submit/", views.submit_order, name="submit_order"),

    # Order detail/tracking
    path("t/<uuid:table_uuid>/order/<uuid:order_uuid>/", views.order_detail, name="order_detail"),

    # Call waiter
    path("t/<uuid:table_uuid>/call-waiter/", views.call_waiter, name="call_waiter"),
]
