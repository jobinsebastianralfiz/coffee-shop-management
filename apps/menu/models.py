"""
Menu management models for the Coffee Shop Management System.
"""

from django.db import models


class Category(models.Model):
    """
    Menu categories (e.g., Hot Beverages, Cold Beverages, Snacks, Desserts).
    Each category belongs to a specific outlet.
    """

    outlet = models.ForeignKey(
        "core.Outlet",
        on_delete=models.CASCADE,
        related_name="menu_categories",
        null=True,
        blank=True,
        help_text="Outlet this category belongs to",
    )
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    # Time-based availability (e.g., Breakfast only 7am-11am)
    available_from = models.TimeField(null=True, blank=True)
    available_until = models.TimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    """
    Individual menu items (e.g., Cappuccino, Latte, Croissant).
    """

    class FoodType(models.TextChoices):
        VEG = "veg", "Vegetarian"
        NON_VEG = "non_veg", "Non-Vegetarian"
        VEGAN = "vegan", "Vegan"

    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name="items",
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="menu_items/", null=True, blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    food_type = models.CharField(
        max_length=10,
        choices=FoodType.choices,
        default=FoodType.VEG,
    )
    preparation_time = models.PositiveIntegerField(
        default=10,
        help_text="Estimated preparation time in minutes",
    )
    calories = models.PositiveIntegerField(null=True, blank=True)

    # Availability & display
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_popular = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Menu Item"
        verbose_name_plural = "Menu Items"
        ordering = ["display_order", "name"]

    def __str__(self):
        return f"{self.name} - ₹{self.base_price}"

    @property
    def default_variant(self):
        """Get the default variant or first available."""
        return self.variants.filter(is_default=True).first() or self.variants.first()


class MenuItemVariant(models.Model):
    """
    Size variants for menu items (e.g., Small, Medium, Large).
    """

    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
        related_name="variants",
    )
    name = models.CharField(max_length=50)  # Small, Medium, Large, Regular
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_default = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Menu Item Variant"
        verbose_name_plural = "Menu Item Variants"
        unique_together = ["menu_item", "name"]
        ordering = ["price"]

    def __str__(self):
        return f"{self.menu_item.name} - {self.name} (₹{self.price})"

    def save(self, *args, **kwargs):
        # Ensure only one default variant per menu item
        if self.is_default:
            MenuItemVariant.objects.filter(
                menu_item=self.menu_item, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)


class AddOnGroup(models.Model):
    """
    Group of add-ons (e.g., "Milk Options", "Extra Toppings", "Sweeteners").
    """

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    is_required = models.BooleanField(
        default=False,
        help_text="Customer must select at least one option",
    )
    is_multi_select = models.BooleanField(
        default=True,
        help_text="Allow multiple selections",
    )
    max_selections = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Maximum number of selections (null = unlimited)",
    )
    menu_items = models.ManyToManyField(
        MenuItem,
        related_name="addon_groups",
        blank=True,
    )
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Add-On Group"
        verbose_name_plural = "Add-On Groups"
        ordering = ["display_order", "name"]

    def __str__(self):
        return self.name


class AddOn(models.Model):
    """
    Individual add-on items (e.g., Extra Shot, Oat Milk, Whipped Cream).
    """

    group = models.ForeignKey(
        AddOnGroup,
        on_delete=models.CASCADE,
        related_name="addons",
    )
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_available = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "Add-On"
        verbose_name_plural = "Add-Ons"
        ordering = ["display_order", "name"]

    def __str__(self):
        if self.price > 0:
            return f"{self.name} (+₹{self.price})"
        return self.name


class ComboMeal(models.Model):
    """
    Combo/bundle meals with discounted pricing.
    """

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="combos/", null=True, blank=True)
    original_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Sum of individual item prices",
    )
    combo_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Discounted combo price",
    )
    is_active = models.BooleanField(default=True)

    # Time-based availability
    available_from = models.TimeField(null=True, blank=True)
    available_until = models.TimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Combo Meal"
        verbose_name_plural = "Combo Meals"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} - ₹{self.combo_price}"

    @property
    def savings(self):
        """Calculate savings compared to individual items."""
        return self.original_price - self.combo_price


class ComboItem(models.Model):
    """
    Items included in a combo meal.
    """

    combo = models.ForeignKey(
        ComboMeal,
        on_delete=models.CASCADE,
        related_name="items",
    )
    menu_item = models.ForeignKey(
        MenuItem,
        on_delete=models.CASCADE,
    )
    variant = models.ForeignKey(
        MenuItemVariant,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    quantity = models.PositiveIntegerField(default=1)

    class Meta:
        verbose_name = "Combo Item"
        verbose_name_plural = "Combo Items"

    def __str__(self):
        return f"{self.quantity}x {self.menu_item.name} in {self.combo.name}"
