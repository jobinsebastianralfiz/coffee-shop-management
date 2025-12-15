"""
WebSocket consumers for real-time updates in the Coffee Shop Management System.
"""

import json

from channels.generic.websocket import AsyncJsonWebsocketConsumer


class BaseConsumer(AsyncJsonWebsocketConsumer):
    """Base consumer with common functionality."""

    group_name = None

    async def connect(self):
        """Join the room group on connection."""
        if self.group_name:
            await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        """Leave the room group on disconnect."""
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def send_event(self, event):
        """Send event data to WebSocket."""
        await self.send_json(event["data"])


class OrderConsumer(BaseConsumer):
    """Consumer for order-related real-time updates."""

    async def connect(self):
        self.group_name = "cafe_orders"
        await super().connect()

    async def order_created(self, event):
        await self.send_event(event)

    async def order_updated(self, event):
        await self.send_event(event)

    async def order_status_changed(self, event):
        await self.send_event(event)


class TableConsumer(BaseConsumer):
    """Consumer for table-related real-time updates."""

    async def connect(self):
        self.group_name = "cafe_tables"
        await super().connect()

    async def table_status_changed(self, event):
        await self.send_event(event)

    async def session_started(self, event):
        await self.send_event(event)

    async def session_ended(self, event):
        await self.send_event(event)


class KitchenConsumer(BaseConsumer):
    """Consumer for kitchen display system updates."""

    async def connect(self):
        self.group_name = "cafe_kitchen"
        await super().connect()
        # Send initial connection confirmation
        await self.send_json({
            "type": "connection_established",
            "message": "Connected to kitchen display"
        })

    async def receive_json(self, content):
        """
        Handle incoming messages from the kitchen display client.
        Supports commands like bump, recall, set_priority.
        """
        command = content.get("command")
        order_id = content.get("order_id")

        if command == "ping":
            # Keep-alive ping
            await self.send_json({"type": "pong"})
            return

        if command == "request_orders":
            # Client requesting current orders
            await self.send_current_orders()
            return

        # Commands that require order_id
        if not order_id:
            await self.send_json({
                "type": "error",
                "message": "order_id is required"
            })
            return

        # Handle order commands via database sync
        from asgiref.sync import sync_to_async
        from apps.orders.models import Order
        from apps.kitchen import services as kitchen_services

        try:
            order = await sync_to_async(Order.objects.select_related(
                "table", "kitchen_ticket"
            ).prefetch_related("items").get)(pk=order_id)
        except Order.DoesNotExist:
            await self.send_json({
                "type": "error",
                "message": "Order not found"
            })
            return

        if command == "bump":
            success, message = await sync_to_async(kitchen_services.bump_order)(order)
            await self.send_json({
                "type": "command_result",
                "command": "bump",
                "success": success,
                "message": message
            })

        elif command == "recall":
            success, message = await sync_to_async(kitchen_services.recall_order)(order)
            await self.send_json({
                "type": "command_result",
                "command": "recall",
                "success": success,
                "message": message
            })

        elif command == "start_preparing":
            success, message = await sync_to_async(kitchen_services.start_preparing)(order)
            await self.send_json({
                "type": "command_result",
                "command": "start_preparing",
                "success": success,
                "message": message
            })

        elif command == "set_priority":
            priority = content.get("priority", "normal")
            success, message = await sync_to_async(kitchen_services.set_order_priority)(
                order, priority
            )
            await self.send_json({
                "type": "command_result",
                "command": "set_priority",
                "success": success,
                "message": message
            })

    async def send_current_orders(self):
        """Send current kitchen orders to the client."""
        from asgiref.sync import sync_to_async
        from apps.kitchen import services as kitchen_services

        orders_data = await sync_to_async(kitchen_services.get_kitchen_orders)()

        # Serialize orders
        serialized = {
            "pending": [],
            "preparing": [],
            "ready": [],
        }

        for status, queryset in orders_data.items():
            orders_list = await sync_to_async(list)(queryset)
            for order in orders_list:
                order_data = await sync_to_async(kitchen_services.get_order_data)(order)
                serialized[status].append(order_data)

        await self.send_json({
            "type": "orders_list",
            "orders": serialized
        })

    # Event handlers for broadcasts
    async def new_order(self, event):
        """Handle new order broadcast."""
        await self.send_event(event)

    async def order_updated(self, event):
        """Handle order updated broadcast."""
        await self.send_event(event)

    async def order_status_changed(self, event):
        """Handle order status change broadcast."""
        await self.send_event(event)

    async def order_bumped(self, event):
        """Handle order bumped broadcast."""
        await self.send_event(event)

    async def priority_changed(self, event):
        """Handle priority change broadcast."""
        await self.send_event(event)

    async def item_flagged(self, event):
        """Handle item flagged broadcast."""
        await self.send_event(event)


class WaiterConsumer(BaseConsumer):
    """Consumer for waiter-specific notifications."""

    async def connect(self):
        self.user_id = self.scope["url_route"]["kwargs"]["user_id"]
        self.group_name = f"waiter_{self.user_id}"
        await super().connect()

    async def order_ready(self, event):
        await self.send_event(event)

    async def table_assigned(self, event):
        await self.send_event(event)


class CustomerConsumer(BaseConsumer):
    """Consumer for customer order tracking via QR."""

    async def connect(self):
        self.table_uuid = self.scope["url_route"]["kwargs"]["table_uuid"]
        self.group_name = f"table_{self.table_uuid}"
        await super().connect()

    async def order_status(self, event):
        await self.send_event(event)

    async def order_ready(self, event):
        await self.send_event(event)
