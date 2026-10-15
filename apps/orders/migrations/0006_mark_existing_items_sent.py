"""
Items on orders that already went to the kitchen (before kitchen tickets were
tracked per item) have no kot_sent_at. Mark them sent so a later round does not
print them again, and give finished orders' items a matching status.
"""

from django.db import migrations


def mark_sent(apps, schema_editor):
    OrderItem = apps.get_model("orders", "OrderItem")
    Order = apps.get_model("orders", "Order")
    for order in Order.objects.exclude(status="pending").filter(items__kot_sent_at__isnull=True).distinct():
        order.items.filter(kot_sent_at__isnull=True).update(kot_sent_at=order.confirmed_at or order.created_at)
    for order_status, item_status in (("ready", "ready"), ("served", "served"), ("completed", "served")):
        OrderItem.objects.filter(order__status=order_status, status__in=["pending", "preparing"]).update(
            status=item_status
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0005_orderitem_kot_sent_at_orderitem_station"),
    ]

    operations = [
        migrations.RunPython(mark_sent, migrations.RunPython.noop),
    ]
