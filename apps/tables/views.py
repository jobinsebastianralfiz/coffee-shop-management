"""
API views for the tables app.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminOrWaiter, IsSuperAdmin

from .models import Floor, Table, TableSession
from .serializers import (
    FloorMapSerializer,
    FloorSerializer,
    PublicTableSerializer,
    StartSessionSerializer,
    TableCreateSerializer,
    TableSerializer,
    TableSessionSerializer,
    TableStatusUpdateSerializer,
)


class FloorViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for floors.
    """

    queryset = Floor.objects.all()
    serializer_class = FloorSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset


class TableViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for tables.
    """

    queryset = Table.objects.select_related("floor").all()
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == "create":
            return TableCreateSerializer
        return TableSerializer

    def get_permissions(self):
        if self.action in ["create", "update", "partial_update", "destroy"]:
            return [IsAuthenticated(), IsSuperAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by floor
        floor = self.request.query_params.get("floor")
        if floor:
            queryset = queryset.filter(floor_id=floor)

        # Filter by status
        table_status = self.request.query_params.get("status")
        if table_status:
            queryset = queryset.filter(status=table_status)

        # Filter by active
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    @action(detail=True, methods=["post"])
    def update_status(self, request, pk=None):
        """Update table status."""
        table = self.get_object()
        serializer = TableStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        table.set_status(serializer.validated_data["status"])

        return Response(
            {
                "message": f"Table {table.number} status updated.",
                "status": table.status,
                "status_display": table.get_status_display(),
            }
        )

    @action(detail=True, methods=["get"])
    def qr_code(self, request, pk=None):
        """Get or generate QR code for table."""
        table = self.get_object()

        # TODO: Generate QR code if not exists

        return Response(
            {
                "table": table.number,
                "uuid": str(table.uuid),
                "qr_url": table.qr_url,
                "qr_code": table.qr_code.url if table.qr_code else None,
            }
        )

    @action(detail=True, methods=["post"])
    def regenerate_qr(self, request, pk=None):
        """Regenerate QR code for table."""
        import uuid

        table = self.get_object()
        table.uuid = uuid.uuid4()
        table.qr_code = None  # Will be regenerated
        table.save()

        return Response(
            {
                "message": f"QR code regenerated for table {table.number}.",
                "uuid": str(table.uuid),
                "qr_url": table.qr_url,
            }
        )


class FloorMapView(APIView):
    """
    Get floor map data with all tables.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        floors = Floor.objects.filter(is_active=True).prefetch_related("tables")
        serializer = FloorMapSerializer(floors, many=True)
        return Response(serializer.data)


class TableSessionViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for table sessions.
    """

    queryset = TableSession.objects.select_related("table", "waiter").all()
    serializer_class = TableSessionSerializer
    permission_classes = [IsAuthenticated, IsAdminOrWaiter]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by table
        table = self.request.query_params.get("table")
        if table:
            queryset = queryset.filter(table_id=table)

        # Filter by active sessions only
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        # Filter by waiter
        waiter = self.request.query_params.get("waiter")
        if waiter:
            queryset = queryset.filter(waiter_id=waiter)

        return queryset


class StartSessionView(APIView):
    """
    Start a new session for a table.
    """

    permission_classes = [IsAuthenticated, IsAdminOrWaiter]

    def post(self, request, table_id):
        try:
            table = Table.objects.get(pk=table_id, is_active=True)
        except Table.DoesNotExist:
            return Response(
                {"error": "Table not found."}, status=status.HTTP_404_NOT_FOUND
            )

        # Check if table already has active session
        if table.current_session:
            return Response(
                {"error": "Table already has an active session."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = StartSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        session = TableSession.objects.create(
            table=table,
            waiter=request.user,
            customer_name=serializer.validated_data.get("customer_name", ""),
            customer_phone=serializer.validated_data.get("customer_phone", ""),
            guest_count=serializer.validated_data.get("guest_count", 1),
            notes=serializer.validated_data.get("notes", ""),
        )

        # Update table status
        table.set_status(Table.Status.OCCUPIED)

        return Response(
            {
                "message": f"Session started for table {table.number}.",
                "session": TableSessionSerializer(session).data,
            },
            status=status.HTTP_201_CREATED,
        )


class EndSessionView(APIView):
    """
    End the current session for a table.
    """

    permission_classes = [IsAuthenticated, IsAdminOrWaiter]

    def post(self, request, table_id):
        try:
            table = Table.objects.get(pk=table_id)
        except Table.DoesNotExist:
            return Response(
                {"error": "Table not found."}, status=status.HTTP_404_NOT_FOUND
            )

        session = table.current_session
        if not session:
            return Response(
                {"error": "No active session for this table."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.end_session()

        return Response(
            {
                "message": f"Session ended for table {table.number}.",
                "session": TableSessionSerializer(session).data,
            }
        )


# ============================================================================
# Public Table Views (for QR ordering)
# ============================================================================


class PublicTableView(APIView):
    """
    Public view to validate QR code and get table info.
    """

    permission_classes = [AllowAny]

    def get(self, request, table_uuid):
        try:
            table = Table.objects.select_related("floor").get(
                uuid=table_uuid, is_active=True
            )
        except Table.DoesNotExist:
            return Response(
                {"error": "Invalid QR code or table not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "table": PublicTableSerializer(table).data,
                "can_order": table.status
                in [Table.Status.OCCUPIED, Table.Status.VACANT],
            }
        )
