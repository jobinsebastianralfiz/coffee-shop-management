"""
URL configuration for the menu app.
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AddOnGroupViewSet,
    AddOnViewSet,
    CategoryViewSet,
    ComboMealViewSet,
    MenuItemVariantViewSet,
    MenuItemViewSet,
    PublicMenuItemView,
    PublicMenuView,
)

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"items", MenuItemViewSet, basename="menu-item")
router.register(r"variants", MenuItemVariantViewSet, basename="variant")
router.register(r"addon-groups", AddOnGroupViewSet, basename="addon-group")
router.register(r"addons", AddOnViewSet, basename="addon")
router.register(r"combos", ComboMealViewSet, basename="combo")

urlpatterns = [
    # Public menu (no auth)
    path("public/", PublicMenuView.as_view(), name="public_menu"),
    path("public/items/<int:pk>/", PublicMenuItemView.as_view(), name="public_menu_item"),
    # Router URLs
    path("", include(router.urls)),
]
