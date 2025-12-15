"""
URL configuration for the tables app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    EndSessionView,
    FloorMapView,
    FloorViewSet,
    PublicTableView,
    StartSessionView,
    TableSessionViewSet,
    TableViewSet,
)

router = DefaultRouter()
router.register(r"floors", FloorViewSet, basename="floor")
router.register(r"tables", TableViewSet, basename="table")
router.register(r"sessions", TableSessionViewSet, basename="session")

urlpatterns = [
    # Floor map
    path("floor-map/", FloorMapView.as_view(), name="floor_map"),
    # Session management
    path("<int:table_id>/session/start/", StartSessionView.as_view(), name="start_session"),
    path("<int:table_id>/session/end/", EndSessionView.as_view(), name="end_session"),
    # Public QR landing
    path("qr/<uuid:table_uuid>/", PublicTableView.as_view(), name="public_table"),
    # Router URLs
    path("", include(router.urls)),
]
