"""
API views for the menu app.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin

from .models import AddOn, AddOnGroup, Category, ComboMeal, MenuItem, MenuItemVariant
from .serializers import (
    AddOnGroupSerializer,
    AddOnSerializer,
    CategorySerializer,
    ComboMealSerializer,
    MenuItemCreateUpdateSerializer,
    MenuItemDetailSerializer,
    MenuItemListSerializer,
    MenuItemVariantSerializer,
    PublicCategorySerializer,
    PublicMenuItemSerializer,
)


class CategoryViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for categories.
    """

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset

    @action(detail=False, methods=["post"])
    def reorder(self, request):
        """
        Reorder categories.
        Expects: {"order": [{"id": 1, "display_order": 0}, ...]}
        """
        order_data = request.data.get("order", [])

        for item in order_data:
            Category.objects.filter(id=item["id"]).update(
                display_order=item["display_order"]
            )

        return Response({"message": "Categories reordered successfully."})


class MenuItemViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for menu items.
    """

    queryset = MenuItem.objects.select_related("category").prefetch_related(
        "variants", "addon_groups__addons"
    )
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_serializer_class(self):
        if self.action == "list":
            return MenuItemListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return MenuItemCreateUpdateSerializer
        return MenuItemDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by category
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)

        # Filter by availability
        is_available = self.request.query_params.get("is_available")
        if is_available is not None:
            queryset = queryset.filter(is_available=is_available.lower() == "true")

        # Filter by food type
        food_type = self.request.query_params.get("food_type")
        if food_type:
            queryset = queryset.filter(food_type=food_type)

        # Filter by featured
        is_featured = self.request.query_params.get("is_featured")
        if is_featured is not None:
            queryset = queryset.filter(is_featured=is_featured.lower() == "true")

        # Filter by popular
        is_popular = self.request.query_params.get("is_popular")
        if is_popular is not None:
            queryset = queryset.filter(is_popular=is_popular.lower() == "true")

        # Search by name
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset

    @action(detail=True, methods=["post"])
    def toggle_availability(self, request, pk=None):
        """Toggle item availability."""
        item = self.get_object()
        item.is_available = not item.is_available
        item.save()
        return Response(
            {
                "message": f"Item is now {'available' if item.is_available else 'unavailable'}.",
                "is_available": item.is_available,
            }
        )


class MenuItemVariantViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for menu item variants.
    """

    queryset = MenuItemVariant.objects.all()
    serializer_class = MenuItemVariantSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by menu item
        menu_item = self.request.query_params.get("menu_item")
        if menu_item:
            queryset = queryset.filter(menu_item_id=menu_item)

        return queryset


class AddOnGroupViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for add-on groups.
    """

    queryset = AddOnGroup.objects.prefetch_related("addons")
    serializer_class = AddOnGroupSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]


class AddOnViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for add-ons.
    """

    queryset = AddOn.objects.all()
    serializer_class = AddOnSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by group
        group = self.request.query_params.get("group")
        if group:
            queryset = queryset.filter(group_id=group)

        return queryset


class ComboMealViewSet(viewsets.ModelViewSet):
    """
    CRUD operations for combo meals.
    """

    queryset = ComboMeal.objects.prefetch_related("items__menu_item", "items__variant")
    serializer_class = ComboMealSerializer
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")

        return queryset


# ============================================================================
# Public Menu Views (for QR ordering - no auth required)
# ============================================================================


class PublicMenuView(APIView):
    """
    Public menu for customer QR ordering.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        """Get full menu with categories and items."""
        categories = Category.objects.filter(is_active=True).prefetch_related(
            "items__variants", "items__addon_groups__addons"
        )

        # Apply food type filter
        food_type = request.query_params.get("food_type")

        data = []
        for category in categories:
            items = category.items.filter(is_available=True)
            if food_type:
                items = items.filter(food_type=food_type)

            if items.exists():
                category_data = PublicCategorySerializer(category).data
                category_data["items"] = PublicMenuItemSerializer(items, many=True).data
                data.append(category_data)

        return Response(data)


class PublicMenuItemView(APIView):
    """
    Public view for single menu item details.
    """

    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            item = MenuItem.objects.prefetch_related(
                "variants", "addon_groups__addons"
            ).get(pk=pk, is_available=True)
        except MenuItem.DoesNotExist:
            return Response(
                {"error": "Item not found."}, status=status.HTTP_404_NOT_FOUND
            )

        return Response(PublicMenuItemSerializer(item).data)
