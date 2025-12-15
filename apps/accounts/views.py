"""
API views for the accounts app.
"""

from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import AuditLog, StaffAttendance, User
from .permissions import IsSuperAdmin
from .serializers import (
    AuditLogSerializer,
    ChangePasswordSerializer,
    ClockInSerializer,
    ClockOutSerializer,
    CustomTokenObtainPairSerializer,
    PINLoginSerializer,
    StaffAttendanceSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom JWT login view that returns user info with tokens.
    """

    serializer_class = CustomTokenObtainPairSerializer


class PINLoginView(APIView):
    """
    PIN-based quick login for staff.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PINLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.get_full_name(),
                    "role": user.role,
                    "role_display": user.get_role_display(),
                },
            }
        )


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """
    Get or update the current authenticated user's profile.
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    """
    Change password for the current user.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save()

        return Response({"message": "Password updated successfully."})


class UserViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for users (admin only).
    """

    queryset = User.objects.all().order_by("-created_at")
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return UserUpdateSerializer
        return UserSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by role
        role = self.request.query_params.get("role")
        if role:
            queryset = queryset.filter(role=role)

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        # Filter by on duty status
        is_on_duty = self.request.query_params.get("is_on_duty")
        if is_on_duty is not None:
            queryset = queryset.filter(is_on_duty=is_on_duty.lower() == "true")

        return queryset

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        """Activate a deactivated user."""
        user = self.get_object()
        user.is_active = True
        user.save()
        return Response({"message": f"User {user.username} activated."})

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        """Deactivate a user."""
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({"message": f"User {user.username} deactivated."})

    @action(detail=False, methods=["get"])
    def on_duty(self, request):
        """List staff currently on duty."""
        queryset = self.get_queryset().filter(is_on_duty=True)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class StaffAttendanceViewSet(viewsets.ModelViewSet):
    """
    Staff attendance management.
    """

    queryset = StaffAttendance.objects.all().order_by("-clock_in")
    serializer_class = StaffAttendanceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Staff can only see their own attendance
        if not self.request.user.is_admin:
            queryset = queryset.filter(user=self.request.user)

        # Filter by user
        user_id = self.request.query_params.get("user")
        if user_id and self.request.user.is_admin:
            queryset = queryset.filter(user_id=user_id)

        # Filter by date
        date = self.request.query_params.get("date")
        if date:
            queryset = queryset.filter(clock_in__date=date)

        return queryset


class ClockInView(APIView):
    """
    Clock in for the current user.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ClockInSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check if already clocked in
        active_attendance = StaffAttendance.objects.filter(
            user=request.user, clock_out__isnull=True
        ).first()

        if active_attendance:
            return Response(
                {"error": "Already clocked in. Please clock out first."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attendance = StaffAttendance.objects.create(
            user=request.user,
            clock_in=timezone.now(),
            shift=serializer.validated_data["shift"],
            notes=serializer.validated_data.get("notes", ""),
        )

        # Update user status
        request.user.is_on_duty = True
        request.user.current_shift = serializer.validated_data["shift"]
        request.user.save()

        return Response(
            {
                "message": "Clocked in successfully.",
                "attendance": StaffAttendanceSerializer(attendance).data,
            }
        )


class ClockOutView(APIView):
    """
    Clock out for the current user.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ClockOutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Find active attendance
        attendance = StaffAttendance.objects.filter(
            user=request.user, clock_out__isnull=True
        ).first()

        if not attendance:
            return Response(
                {"error": "Not clocked in."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        attendance.clock_out = timezone.now()
        if serializer.validated_data.get("notes"):
            attendance.notes = (
                f"{attendance.notes}\n{serializer.validated_data['notes']}".strip()
            )
        attendance.save()

        # Update user status
        request.user.is_on_duty = False
        request.user.current_shift = None
        request.user.save()

        return Response(
            {
                "message": "Clocked out successfully.",
                "attendance": StaffAttendanceSerializer(attendance).data,
            }
        )


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for audit logs (admin only).
    """

    queryset = AuditLog.objects.all().order_by("-timestamp")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by user
        user_id = self.request.query_params.get("user")
        if user_id:
            queryset = queryset.filter(user_id=user_id)

        # Filter by action
        action = self.request.query_params.get("action")
        if action:
            queryset = queryset.filter(action=action)

        # Filter by model
        model = self.request.query_params.get("model")
        if model:
            queryset = queryset.filter(model_name=model)

        return queryset
