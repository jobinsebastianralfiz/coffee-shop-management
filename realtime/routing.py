"""
WebSocket URL routing for the Coffee Shop Management System.
"""

from django.urls import path

from . import consumers

websocket_urlpatterns = [
    path("ws/orders/", consumers.OrderConsumer.as_asgi()),
    path("ws/tables/", consumers.TableConsumer.as_asgi()),
    path("ws/kitchen/", consumers.KitchenConsumer.as_asgi()),
    path("ws/waiter/<int:user_id>/", consumers.WaiterConsumer.as_asgi()),
    path("ws/customer/<str:table_uuid>/", consumers.CustomerConsumer.as_asgi()),
]
