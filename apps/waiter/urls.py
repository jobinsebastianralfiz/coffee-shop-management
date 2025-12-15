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
]
