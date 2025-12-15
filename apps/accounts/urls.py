"""
URL configuration for the accounts app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    AuditLogViewSet,
    ChangePasswordView,
    ClockInView,
    ClockOutView,
    CurrentUserView,
    CustomTokenObtainPairView,
    PINLoginView,
    StaffAttendanceViewSet,
    UserViewSet,
)

router = DefaultRouter()
router.register(r"users", UserViewSet, basename="user")
router.register(r"attendance", StaffAttendanceViewSet, basename="attendance")
router.register(r"audit-logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    # Authentication
    path("auth/login/", CustomTokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/login/pin/", PINLoginView.as_view(), name="pin_login"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    # Current user
    path("auth/me/", CurrentUserView.as_view(), name="current_user"),
    path("auth/password/change/", ChangePasswordView.as_view(), name="change_password"),
    # Attendance
    path("attendance/clock-in/", ClockInView.as_view(), name="clock_in"),
    path("attendance/clock-out/", ClockOutView.as_view(), name="clock_out"),
    # Router URLs
    path("", include(router.urls)),
]
