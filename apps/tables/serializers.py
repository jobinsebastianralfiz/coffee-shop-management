"""
Serializers for the tables app.
"""

from rest_framework import serializers

from .models import Floor, Table, TableSession


class FloorSerializer(serializers.ModelSerializer):
    """
    Serializer for Floor model.
    """

    table_count = serializers.ReadOnlyField()
    available_tables = serializers.ReadOnlyField()

    class Meta:
        model = Floor
        fields = [
            "id",
            "name",
            "description",
            "is_active",
            "display_order",
            "table_count",
            "available_tables",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class TableSerializer(serializers.ModelSerializer):
    """
    Serializer for Table model.
    """

    floor_name = serializers.CharField(source="floor.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    table_type_display = serializers.CharField(source="get_table_type_display", read_only=True)
    display_name = serializers.ReadOnlyField()
    qr_url = serializers.ReadOnlyField()
    has_active_session = serializers.SerializerMethodField()

    class Meta:
        model = Table
        fields = [
            "id",
            "floor",
            "floor_name",
            "number",
            "name",
            "display_name",
            "capacity",
            "table_type",
            "table_type_display",
            "status",
            "status_display",
            "uuid",
            "qr_code",
            "qr_url",
            "position_x",
            "position_y",
            "is_active",
            "has_active_session",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "uuid", "created_at", "updated_at"]

    def get_has_active_session(self, obj):
        return obj.sessions.filter(is_active=True).exists()


class TableCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating tables.
    """

    class Meta:
        model = Table
        fields = [
            "floor",
            "number",
            "name",
            "capacity",
            "table_type",
            "position_x",
            "position_y",
        ]


class TableStatusUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating table status.
    """

    status = serializers.ChoiceField(choices=Table.Status.choices)


class TableSessionSerializer(serializers.ModelSerializer):
    """
    Serializer for TableSession model.
    """

    table_number = serializers.CharField(source="table.number", read_only=True)
    waiter_name = serializers.CharField(source="waiter.get_full_name", read_only=True)
    duration_minutes = serializers.ReadOnlyField()

    class Meta:
        model = TableSession
        fields = [
            "id",
            "table",
            "table_number",
            "waiter",
            "waiter_name",
            "customer_name",
            "customer_phone",
            "guest_count",
            "started_at",
            "ended_at",
            "is_active",
            "notes",
            "duration_minutes",
        ]
        read_only_fields = ["id", "started_at"]


class StartSessionSerializer(serializers.Serializer):
    """
    Serializer for starting a table session.
    """

    customer_name = serializers.CharField(required=False, allow_blank=True)
    customer_phone = serializers.CharField(required=False, allow_blank=True)
    guest_count = serializers.IntegerField(min_value=1, default=1)
    notes = serializers.CharField(required=False, allow_blank=True)


class FloorMapTableSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for floor map display.
    """

    class Meta:
        model = Table
        fields = [
            "id",
            "number",
            "name",
            "capacity",
            "status",
            "table_type",
            "position_x",
            "position_y",
        ]


class FloorMapSerializer(serializers.ModelSerializer):
    """
    Serializer for floor map view.
    """

    tables = FloorMapTableSerializer(many=True, read_only=True)

    class Meta:
        model = Floor
        fields = ["id", "name", "tables"]


# ============================================================================
# Public Table Serializers (for QR ordering)
# ============================================================================


class PublicTableSerializer(serializers.ModelSerializer):
    """
    Public serializer for table info (QR landing page).
    """

    floor_name = serializers.CharField(source="floor.name", read_only=True)

    class Meta:
        model = Table
        fields = [
            "id",
            "number",
            "name",
            "floor_name",
            "capacity",
        ]
