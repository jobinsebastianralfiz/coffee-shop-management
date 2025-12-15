"""
URL configuration for the customer ordering app.
"""

from django.urls import path

from . import views

app_name = "ordering"

urlpatterns = [
    # Seat selection (QR code landing page)
    path("t/<uuid:table_uuid>/", views.select_seat, name="select_seat"),

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
