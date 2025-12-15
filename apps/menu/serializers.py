"""
Serializers for the menu app.
"""

from rest_framework import serializers

from .models import (
    AddOn,
    AddOnGroup,
    Category,
    ComboItem,
    ComboMeal,
    MenuItem,
    MenuItemVariant,
)


class CategorySerializer(serializers.ModelSerializer):
    """
    Serializer for Category model.
    """

    items_count = serializers.IntegerField(source="items.count", read_only=True)

    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "description",
            "image",
            "display_order",
            "is_active",
            "available_from",
            "available_until",
            "items_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MenuItemVariantSerializer(serializers.ModelSerializer):
    """
    Serializer for MenuItemVariant model.
    """

    class Meta:
        model = MenuItemVariant
        fields = [
            "id",
            "name",
            "price",
            "is_default",
            "is_available",
        ]
        read_only_fields = ["id"]


class AddOnSerializer(serializers.ModelSerializer):
    """
    Serializer for AddOn model.
    """

    class Meta:
        model = AddOn
        fields = [
            "id",
            "name",
            "price",
            "is_available",
            "display_order",
        ]
        read_only_fields = ["id"]


class AddOnGroupSerializer(serializers.ModelSerializer):
    """
    Serializer for AddOnGroup model.
    """

    addons = AddOnSerializer(many=True, read_only=True)

    class Meta:
        model = AddOnGroup
        fields = [
            "id",
            "name",
            "description",
            "is_required",
            "is_multi_select",
            "max_selections",
            "display_order",
            "addons",
        ]
        read_only_fields = ["id"]


class MenuItemListSerializer(serializers.ModelSerializer):
    """
    Serializer for MenuItem list view (minimal data).
    """

    category_name = serializers.CharField(source="category.name", read_only=True)
    food_type_display = serializers.CharField(source="get_food_type_display", read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "name",
            "category",
            "category_name",
            "image",
            "base_price",
            "food_type",
            "food_type_display",
            "is_available",
            "is_featured",
            "is_popular",
        ]
        read_only_fields = ["id"]


class MenuItemDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for MenuItem detail view (full data with variants and add-ons).
    """

    category_name = serializers.CharField(source="category.name", read_only=True)
    food_type_display = serializers.CharField(source="get_food_type_display", read_only=True)
    variants = MenuItemVariantSerializer(many=True, read_only=True)
    addon_groups = AddOnGroupSerializer(many=True, read_only=True)

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "name",
            "description",
            "category",
            "category_name",
            "image",
            "base_price",
            "food_type",
            "food_type_display",
            "preparation_time",
            "calories",
            "is_available",
            "is_featured",
            "is_popular",
            "display_order",
            "variants",
            "addon_groups",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class MenuItemCreateUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating/updating MenuItem.
    """

    class Meta:
        model = MenuItem
        fields = [
            "name",
            "description",
            "category",
            "image",
            "base_price",
            "food_type",
            "preparation_time",
            "calories",
            "is_available",
            "is_featured",
            "is_popular",
            "display_order",
        ]


class ComboItemSerializer(serializers.ModelSerializer):
    """
    Serializer for ComboItem model.
    """

    menu_item_name = serializers.CharField(source="menu_item.name", read_only=True)
    variant_name = serializers.CharField(source="variant.name", read_only=True)

    class Meta:
        model = ComboItem
        fields = [
            "id",
            "menu_item",
            "menu_item_name",
            "variant",
            "variant_name",
            "quantity",
        ]
        read_only_fields = ["id"]


class ComboMealSerializer(serializers.ModelSerializer):
    """
    Serializer for ComboMeal model.
    """

    items = ComboItemSerializer(many=True, read_only=True)
    savings = serializers.ReadOnlyField()

    class Meta:
        model = ComboMeal
        fields = [
            "id",
            "name",
            "description",
            "image",
            "original_price",
            "combo_price",
            "savings",
            "is_active",
            "available_from",
            "available_until",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ============================================================================
# Public Menu Serializers (for QR ordering - no auth required)
# ============================================================================


class PublicAddOnSerializer(serializers.ModelSerializer):
    """
    Public serializer for add-ons (customer view).
    """

    class Meta:
        model = AddOn
        fields = ["id", "name", "price"]


class PublicAddOnGroupSerializer(serializers.ModelSerializer):
    """
    Public serializer for add-on groups (customer view).
    """

    addons = PublicAddOnSerializer(many=True, source="addons.filter(is_available=True)")

    class Meta:
        model = AddOnGroup
        fields = [
            "id",
            "name",
            "is_required",
            "is_multi_select",
            "max_selections",
            "addons",
        ]


class PublicVariantSerializer(serializers.ModelSerializer):
    """
    Public serializer for variants (customer view).
    """

    class Meta:
        model = MenuItemVariant
        fields = ["id", "name", "price", "is_default"]


class PublicMenuItemSerializer(serializers.ModelSerializer):
    """
    Public serializer for menu items (customer view).
    """

    variants = serializers.SerializerMethodField()
    addon_groups = serializers.SerializerMethodField()

    class Meta:
        model = MenuItem
        fields = [
            "id",
            "name",
            "description",
            "image",
            "base_price",
            "food_type",
            "preparation_time",
            "variants",
            "addon_groups",
        ]

    def get_variants(self, obj):
        variants = obj.variants.filter(is_available=True)
        return PublicVariantSerializer(variants, many=True).data

    def get_addon_groups(self, obj):
        return PublicAddOnGroupSerializer(obj.addon_groups.all(), many=True).data


class PublicCategorySerializer(serializers.ModelSerializer):
    """
    Public serializer for categories (customer view).
    """

    items = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = ["id", "name", "description", "image", "items"]

    def get_items(self, obj):
        items = obj.items.filter(is_available=True)
        return PublicMenuItemSerializer(items, many=True).data
