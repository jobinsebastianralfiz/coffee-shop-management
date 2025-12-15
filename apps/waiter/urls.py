"""
URL configuration for the Waiter PWA app.
"""

from django.urls import path

from . import views

app_name = "waiter"

urlpatterns = [
    # Home dashboard
    path("", views.waiter_home, name="home"),

    # Tables / Floor map
    path("tables/", views.waiter_tables, name="tables"),
    path("table/<int:pk>/", views.waiter_table_detail, name="table_detail"),
    path("table/<int:pk>/seat/<int:seat>/", views.waiter_take_order, name="take_order"),
    path("table/<int:pk>/seat/<int:seat>/add/", views.waiter_add_item, name="add_item"),
    path("table/<int:pk>/seat/<int:seat>/submit/", views.waiter_submit_order, name="submit_order"),

    # Orders
    path("orders/", views.waiter_orders, name="orders"),
    path("order/<int:pk>/", views.waiter_order_detail, name="order_detail"),
    path("order/<int:pk>/status/", views.waiter_update_order_status, name="update_order_status"),

    # Offline page
    path("offline/", views.offline_page, name="offline"),

    # API endpoints for offline PWA support
    path("api/menu/", views.api_menu, name="api_menu"),
    path("api/tables/", views.api_tables, name="api_tables"),
    path("api/orders/create/", views.api_create_order, name="api_create_order"),
    path("api/orders/sync/", views.api_sync_orders, name="api_sync_orders"),
]
