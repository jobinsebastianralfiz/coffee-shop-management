"""
Dashboard views for the Coffee Shop Management System.
"""

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.accounts.models import User
from apps.menu.models import Category, MenuItem
from apps.orders.models import Order, OrderItem, Payment, KitchenOrderTicket
from apps.tables.models import Floor, Table, TableSession


# ============================================================================
# Permission Helpers
# ============================================================================


def is_admin_user(user):
    """Check if user has admin-level access (super admin or outlet manager)."""
    return user.role in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER]


def get_user_outlet(user):
    """Get the outlet a user is restricted to (None for super admin = all outlets)."""
    if user.role == User.Role.SUPER_ADMIN:
        return None  # Can access all outlets
    return user.outlet


def filter_by_outlet(queryset, user, outlet_field="outlet"):
    """Filter a queryset by the user's outlet if they're not a super admin."""
    outlet = get_user_outlet(user)
    if outlet:
        return queryset.filter(**{outlet_field: outlet})
    return queryset


def can_manage_user(manager, target_user):
    """Check if manager can manage target user."""
    if manager.role == User.Role.SUPER_ADMIN:
        return True
    if manager.role == User.Role.OUTLET_MANAGER:
        # Can only manage staff in their outlet
        if target_user.role in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER]:
            return False
        return target_user.outlet_id == manager.outlet_id
    return False


# ============================================================================
# Authentication Views
# ============================================================================


def login_view(request):
    """Handle user login."""
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        remember = request.POST.get("remember")

        user = authenticate(request, username=username, password=password)

        if user is not None:
            login(request, user)
            if not remember:
                request.session.set_expiry(0)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}!")
            return redirect("dashboard:home")
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "auth/login.html")


def pin_login_view(request):
    """Handle PIN-based login for staff."""
    if request.user.is_authenticated:
        return redirect("dashboard:home")

    if request.method == "POST":
        pin = request.POST.get("pin")

        try:
            user = User.objects.get(pin=pin, is_active=True)
            login(request, user)
            request.session.set_expiry(0)  # Session expires on browser close
            messages.success(request, f"Welcome, {user.get_full_name() or user.username}!")
            return redirect("dashboard:home")
        except User.DoesNotExist:
            messages.error(request, "Invalid PIN.")

    return render(request, "auth/pin_login.html")


@login_required
def logout_view(request):
    """Handle user logout."""
    logout(request)
    messages.info(request, "You have been logged out successfully.")
    return redirect("dashboard:login")


# ============================================================================
# Dashboard Home
# ============================================================================


@login_required
def dashboard_home(request):
    """Dashboard home with statistics."""
    from django.conf import settings as django_settings
    from apps.core.models import Outlet

    today = timezone.now().date()

    # Get order stats
    today_orders = Order.objects.filter(created_at__date=today)
    completed_orders = today_orders.filter(status__in=[Order.Status.COMPLETED, Order.Status.SERVED])

    # Get plan info from settings (only for super admin)
    max_outlets = getattr(django_settings, "MAX_OUTLETS", 1)
    plan_info = None
    if request.user.role == "super_admin":
        plan_info = {
            "name": getattr(django_settings, "PLAN_NAME", "Basic"),
            "max_outlets": max_outlets,
            "max_outlets_display": "Unlimited" if max_outlets == 0 else max_outlets,
            "outlets_used": Outlet.objects.count(),
            "outlets_remaining": Outlet.outlets_remaining(),
            "can_create_outlet": Outlet.can_create_outlet(),
            "features": getattr(django_settings, "PLAN_FEATURES", []),
        }

    # Get stats
    context = {
        "page_title": "Dashboard",
        "stats": {
            "total_orders_today": today_orders.count(),
            "revenue_today": completed_orders.aggregate(total=Sum("total_amount"))["total"] or 0,
            "active_tables": Table.objects.filter(status=Table.Status.OCCUPIED).count(),
            "pending_orders": today_orders.filter(status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING]).count(),
        },
        "tables": {
            "total": Table.objects.filter(is_active=True).count(),
            "vacant": Table.objects.filter(is_active=True, status=Table.Status.VACANT).count(),
            "occupied": Table.objects.filter(is_active=True, status=Table.Status.OCCUPIED).count(),
            "reserved": Table.objects.filter(is_active=True, status=Table.Status.RESERVED).count(),
        },
        "menu": {
            "total_categories": Category.objects.filter(is_active=True).count(),
            "total_items": MenuItem.objects.filter(is_available=True).count(),
        },
        "recent_sessions": TableSession.objects.select_related("table", "waiter").order_by("-started_at")[:5],
        "plan_info": plan_info,
    }

    return render(request, "dashboard/home.html", context)


# ============================================================================
# Profile
# ============================================================================


@login_required
def profile_view(request):
    """User profile view."""
    if request.method == "POST":
        user = request.user
        user.first_name = request.POST.get("first_name", "")
        user.last_name = request.POST.get("last_name", "")
        user.email = request.POST.get("email", "")
        user.phone = request.POST.get("phone", "")
        user.save()
        messages.success(request, "Profile updated successfully.")
        return redirect("dashboard:profile")

    return render(request, "dashboard/profile.html", {"page_title": "Profile"})


@login_required
@require_http_methods(["POST"])
def change_password_view(request):
    """Change user password."""
    user = request.user
    current_password = request.POST.get("current_password")
    new_password = request.POST.get("new_password")
    confirm_password = request.POST.get("confirm_password")

    if not user.check_password(current_password):
        messages.error(request, "Current password is incorrect.")
        return redirect("dashboard:profile")

    if new_password != confirm_password:
        messages.error(request, "New passwords do not match.")
        return redirect("dashboard:profile")

    if len(new_password) < 8:
        messages.error(request, "Password must be at least 8 characters.")
        return redirect("dashboard:profile")

    user.set_password(new_password)
    user.save()
    messages.success(request, "Password changed successfully. Please log in again.")
    return redirect("dashboard:login")


# ============================================================================
# Menu Management
# ============================================================================


@login_required
def menu_list(request):
    """Menu management - list categories and items."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    categories = Category.objects.prefetch_related("items").order_by("display_order")

    context = {
        "page_title": "Menu Management",
        "categories": categories,
        "total_items": MenuItem.objects.count(),
        "available_items": MenuItem.objects.filter(is_available=True).count(),
        "food_types": MenuItem.FoodType.choices,
    }
    return render(request, "dashboard/menu/list.html", context)


@login_required
def category_detail(request, pk):
    """View category details and its items."""
    try:
        category = Category.objects.prefetch_related("items").get(pk=pk)
    except Category.DoesNotExist:
        messages.error(request, "Category not found.")
        return redirect("dashboard:menu")

    context = {
        "page_title": f"Category: {category.name}",
        "category": category,
        "items": category.items.all().order_by("display_order"),
    }
    return render(request, "dashboard/menu/category_detail.html", context)


@login_required
def menu_item_detail(request, pk):
    """View menu item details."""
    try:
        item = MenuItem.objects.select_related("category").prefetch_related(
            "variants", "addon_groups__addons"
        ).get(pk=pk)
    except MenuItem.DoesNotExist:
        messages.error(request, "Menu item not found.")
        return redirect("dashboard:menu")

    context = {
        "page_title": item.name,
        "item": item,
        "categories": Category.objects.filter(is_active=True).order_by("display_order"),
        "food_types": MenuItem.FoodType.choices,
    }
    return render(request, "dashboard/menu/item_detail.html", context)


# ============================================================================
# Category CRUD (Super Admin only)
# ============================================================================


@login_required
def category_create(request):
    """Create a new category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:menu")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        display_order = request.POST.get("display_order", 0)

        if not name:
            messages.error(request, "Category name is required.")
        elif Category.objects.filter(name=name).exists():
            messages.error(request, "A category with this name already exists.")
        else:
            category = Category.objects.create(
                name=name,
                description=description,
                display_order=int(display_order) if display_order else 0,
            )
            # Handle image upload
            if "image" in request.FILES:
                category.image = request.FILES["image"]
                category.save()
            messages.success(request, f"Category '{name}' created successfully.")

    return redirect("dashboard:menu")


@login_required
def category_edit(request, pk):
    """Edit a category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:menu")

    try:
        category = Category.objects.get(pk=pk)
    except Category.DoesNotExist:
        messages.error(request, "Category not found.")
        return redirect("dashboard:menu")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        display_order = request.POST.get("display_order", 0)
        is_active = request.POST.get("is_active") == "on"

        if not name:
            messages.error(request, "Category name is required.")
        elif Category.objects.filter(name=name).exclude(pk=pk).exists():
            messages.error(request, "A category with this name already exists.")
        else:
            category.name = name
            category.description = description
            category.display_order = int(display_order) if display_order else 0
            category.is_active = is_active
            # Handle image upload
            if "image" in request.FILES:
                category.image = request.FILES["image"]
            category.save()
            messages.success(request, f"Category '{name}' updated successfully.")

    return redirect("dashboard:menu")


@login_required
@require_http_methods(["POST"])
def category_delete(request, pk):
    """Delete a category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:menu")

    try:
        category = Category.objects.get(pk=pk)
        if category.items.exists():
            messages.error(request, f"Cannot delete category '{category.name}' - it has menu items. Delete the items first.")
        else:
            name = category.name
            # Delete image if exists
            if category.image:
                try:
                    category.image.delete(save=False)
                except Exception:
                    pass
            category.delete()
            messages.success(request, f"Category '{name}' deleted successfully.")
    except Category.DoesNotExist:
        messages.error(request, "Category not found.")

    return redirect("dashboard:menu")


# ============================================================================
# Menu Item CRUD (Super Admin only)
# ============================================================================


@login_required
def menu_item_create(request):
    """Create a new menu item."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:menu")

    if request.method == "POST":
        category_id = request.POST.get("category")
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        base_price = request.POST.get("base_price", "0")
        food_type = request.POST.get("food_type", MenuItem.FoodType.VEG)
        preparation_time = request.POST.get("preparation_time", 10)
        is_available = request.POST.get("is_available") == "on"
        is_featured = request.POST.get("is_featured") == "on"

        if not category_id:
            messages.error(request, "Please select a category.")
        elif not name:
            messages.error(request, "Item name is required.")
        elif not base_price:
            messages.error(request, "Base price is required.")
        else:
            try:
                category = Category.objects.get(pk=category_id)
                item = MenuItem.objects.create(
                    category=category,
                    name=name,
                    description=description,
                    base_price=float(base_price),
                    food_type=food_type,
                    preparation_time=int(preparation_time) if preparation_time else 10,
                    is_available=is_available,
                    is_featured=is_featured,
                )
                # Handle image upload
                if "image" in request.FILES:
                    item.image = request.FILES["image"]
                    item.save()
                messages.success(request, f"Menu item '{name}' created successfully.")
            except Category.DoesNotExist:
                messages.error(request, "Selected category not found.")
            except ValueError:
                messages.error(request, "Invalid price value.")

    return redirect("dashboard:menu")


@login_required
def menu_item_edit(request, pk):
    """Edit a menu item."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:menu")

    try:
        item = MenuItem.objects.get(pk=pk)
    except MenuItem.DoesNotExist:
        messages.error(request, "Menu item not found.")
        return redirect("dashboard:menu")

    if request.method == "POST":
        category_id = request.POST.get("category")
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        base_price = request.POST.get("base_price", "0")
        food_type = request.POST.get("food_type", item.food_type)
        preparation_time = request.POST.get("preparation_time", 10)
        is_available = request.POST.get("is_available") == "on"
        is_featured = request.POST.get("is_featured") == "on"

        if not category_id:
            messages.error(request, "Please select a category.")
        elif not name:
            messages.error(request, "Item name is required.")
        elif not base_price:
            messages.error(request, "Base price is required.")
        else:
            try:
                category = Category.objects.get(pk=category_id)
                item.category = category
                item.name = name
                item.description = description
                item.base_price = float(base_price)
                item.food_type = food_type
                item.preparation_time = int(preparation_time) if preparation_time else 10
                item.is_available = is_available
                item.is_featured = is_featured
                # Handle image upload
                if "image" in request.FILES:
                    item.image = request.FILES["image"]
                item.save()
                messages.success(request, f"Menu item '{name}' updated successfully.")
            except Category.DoesNotExist:
                messages.error(request, "Selected category not found.")
            except ValueError:
                messages.error(request, "Invalid price value.")

    return redirect("dashboard:menu")


@login_required
@require_http_methods(["POST"])
def menu_item_delete(request, pk):
    """Delete a menu item."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:menu")

    try:
        item = MenuItem.objects.get(pk=pk)
        name = item.name
        # Delete image if exists
        if item.image:
            try:
                item.image.delete(save=False)
            except Exception:
                pass
        item.delete()
        messages.success(request, f"Menu item '{name}' deleted successfully.")
    except MenuItem.DoesNotExist:
        messages.error(request, "Menu item not found.")

    return redirect("dashboard:menu")


@login_required
@require_http_methods(["POST"])
def menu_item_toggle_availability(request, pk):
    """Toggle menu item availability."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:menu")

    try:
        item = MenuItem.objects.get(pk=pk)
        item.is_available = not item.is_available
        item.save(update_fields=["is_available", "updated_at"])
        status = "available" if item.is_available else "unavailable"
        messages.success(request, f"'{item.name}' is now {status}.")
    except MenuItem.DoesNotExist:
        messages.error(request, "Menu item not found.")

    return redirect("dashboard:menu")


# ============================================================================
# Table Management
# ============================================================================


@login_required
def table_list(request):
    """Table management - role-based views."""
    from django.db.models import Prefetch
    from apps.core.models import Outlet

    # Get outlets for filter (super admin only)
    outlets = None
    selected_outlet = ""
    if request.user.role == User.Role.SUPER_ADMIN:
        outlets = Outlet.objects.filter(is_active=True).order_by("name")
        selected_outlet = request.GET.get("outlet", "")

    # Prefetch active orders for each table (as primary table)
    active_order_prefetch = Prefetch(
        "orders",
        queryset=Order.objects.filter(
            status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
        ).order_by("-created_at"),
        to_attr="active_orders"
    )

    # Prefetch combined orders (where table is in combined_tables)
    combined_order_prefetch = Prefetch(
        "combined_orders",
        queryset=Order.objects.filter(
            status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
        ).order_by("-created_at"),
        to_attr="active_combined_orders"
    )

    floors = Floor.objects.filter(is_active=True).prefetch_related(
        Prefetch("tables", queryset=Table.objects.prefetch_related(active_order_prefetch, combined_order_prefetch))
    ).order_by("display_order")

    # Filter by outlet if selected (super admin)
    tables_qs = Table.objects.filter(is_active=True)
    if selected_outlet:
        floors = floors.filter(outlet_id=selected_outlet)
        tables_qs = tables_qs.filter(floor__outlet_id=selected_outlet)

    context = {
        "page_title": "Tables",
        "floors": floors,
        "stats": {
            "total": tables_qs.count(),
            "vacant": tables_qs.filter(status=Table.Status.VACANT).count(),
            "occupied": tables_qs.filter(status=Table.Status.OCCUPIED).count(),
            "reserved": tables_qs.filter(status=Table.Status.RESERVED).count(),
        },
        "outlets": outlets,
        "selected_outlet": selected_outlet,
    }

    # Route to different templates based on role
    user = request.user
    view_mode = request.GET.get("view", "")

    # Super Admin: Can switch between management and floor map view
    if user.role == User.Role.SUPER_ADMIN:
        if view_mode == "manage":
            context["page_title"] = "Table Management"
            return render(request, "dashboard/tables/list.html", context)
        else:
            context["page_title"] = "Floor Map"
            return render(request, "dashboard/tables/floor_map.html", context)

    # Cashier: Table-wise billing view
    elif user.role == User.Role.STAFF_CASHIER:
        context["page_title"] = "Table Billing"
        return render(request, "dashboard/tables/billing_view.html", context)

    # Waiter: Floor map view for taking orders
    elif user.role == User.Role.WAITER:
        context["page_title"] = "Floor Map"
        return render(request, "dashboard/tables/floor_map.html", context)

    # Default: Floor map view
    else:
        return render(request, "dashboard/tables/floor_map.html", context)


@login_required
def table_detail(request, pk):
    """View table details and current session."""
    try:
        table = Table.objects.select_related("floor").get(pk=pk)
    except Table.DoesNotExist:
        messages.error(request, "Table not found.")
        return redirect("dashboard:tables")

    context = {
        "page_title": f"Table {table.number}",
        "table": table,
        "current_session": table.current_session,
        "recent_sessions": table.sessions.order_by("-started_at")[:10],
    }
    return render(request, "dashboard/tables/detail.html", context)


@login_required
def table_take_order(request, pk):
    """
    Waiter clicks table -> show active orders or create new one.
    Supports multiple parties/orders per table and combined tables.
    """
    from django.db.models import Q

    try:
        table = Table.objects.get(pk=pk)
    except Table.DoesNotExist:
        messages.error(request, "Table not found.")
        return redirect("dashboard:tables")

    # Get all active orders for this table (as primary or combined)
    active_orders = Order.objects.filter(
        Q(table=table) | Q(combined_tables=table),
        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
    ).distinct().order_by("created_at")

    # If POST request with new_party, create new order
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "new_party":
            party_count = active_orders.count() + 1
            party_name = request.POST.get("party_name") or f"Party {chr(64 + party_count)}"  # Party A, B, C...
            combine_tables = request.POST.getlist("combine_tables")

            order = Order.objects.create(
                table=table,
                created_by=request.user,
                order_type=Order.OrderType.DINE_IN,
                order_source=Order.OrderSource.POS,
                party_name=party_name,
            )

            # Add combined tables
            if combine_tables:
                combined = Table.objects.filter(pk__in=combine_tables).exclude(pk=table.pk)
                order.combined_tables.set(combined)
                # Mark combined tables as occupied
                combined.update(status=Table.Status.OCCUPIED)

            # Create kitchen ticket
            KitchenOrderTicket.objects.create(order=order)

            # Mark primary table as occupied
            table.status = Table.Status.OCCUPIED
            table.save(update_fields=["status", "updated_at"])

            table_info = f"Tables {order.all_table_numbers}" if order.combined_tables.exists() else f"Table {table.number}"
            messages.success(request, f"Order #{order.order_number} ({party_name}) created for {table_info}.")
            return redirect("dashboard:order_detail", pk=order.pk)

    # If only one order exists and it's still pending with no items, go directly to it
    if active_orders.count() == 1:
        single_order = active_orders.first()
        if single_order.status == Order.Status.PENDING and single_order.items.count() == 0:
            return redirect("dashboard:order_detail", pk=single_order.pk)

    # If multiple orders exist or table is part of combined order, show selection screen
    if active_orders.exists():
        # Get available tables for combining (vacant tables on same floor)
        available_tables = Table.objects.filter(
            floor=table.floor,
            status=Table.Status.VACANT
        ).exclude(pk=table.pk).order_by("number")

        context = {
            "page_title": f"Table {table.number} - Select Order",
            "table": table,
            "active_orders": active_orders,
            "available_tables": available_tables,
        }
        return render(request, "dashboard/tables/select_order.html", context)

    # No active orders - show create order screen with combine option
    available_tables = Table.objects.filter(
        floor=table.floor,
        status=Table.Status.VACANT
    ).exclude(pk=table.pk).order_by("number")

    if available_tables.exists():
        # Show option to combine tables
        context = {
            "page_title": f"Table {table.number} - New Order",
            "table": table,
            "active_orders": [],
            "available_tables": available_tables,
            "is_new_order": True,
        }
        return render(request, "dashboard/tables/select_order.html", context)

    # No available tables to combine - create order directly
    order = Order.objects.create(
        table=table,
        created_by=request.user,
        order_type=Order.OrderType.DINE_IN,
        order_source=Order.OrderSource.POS,
        party_name="Party A",
    )

    # Create kitchen ticket
    KitchenOrderTicket.objects.create(order=order)

    # Mark table as occupied
    table.status = Table.Status.OCCUPIED
    table.save(update_fields=["status", "updated_at"])

    messages.success(request, f"Order #{order.order_number} created for Table {table.number}.")
    return redirect("dashboard:order_detail", pk=order.pk)


# ============================================================================
# User Management (Super Admin only)
# ============================================================================


@login_required
def user_list(request):
    """User management - list all users."""
    from apps.core.models import Outlet
    from django.conf import settings

    # Check permission - allow super admin and outlet managers
    if not is_admin_user(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    # Outlet manager must have an outlet assigned
    if request.user.role == User.Role.OUTLET_MANAGER and not request.user.outlet:
        messages.error(request, "You are not assigned to an outlet.")
        return redirect("dashboard:home")

    is_outlet_mgr = request.user.role == User.Role.OUTLET_MANAGER
    user_outlet = get_user_outlet(request.user)

    # Get outlets based on role
    if is_outlet_mgr:
        outlets = Outlet.objects.filter(pk=user_outlet.pk)
    else:
        outlets = Outlet.objects.filter(is_active=True).order_by("name")

    # Define available roles based on who is creating
    if is_outlet_mgr:
        # Outlet managers can only create staff roles
        available_roles = [
            (User.Role.STAFF_CASHIER, "Cashier"),
            (User.Role.STAFF_KITCHEN, "Kitchen Staff"),
            (User.Role.WAITER, "Waiter"),
        ]
    else:
        available_roles = User.Role.choices

    # Handle user creation
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        email = request.POST.get("email", "").strip()
        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        phone = request.POST.get("phone", "").strip()
        role = request.POST.get("role", User.Role.WAITER)
        pin = request.POST.get("pin", "").strip()
        outlet_id = request.POST.get("outlet", "").strip()

        # Outlet managers can only create staff roles
        if is_outlet_mgr and role in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER]:
            messages.error(request, "You cannot create admin users.")
        elif not username:
            messages.error(request, "Username is required.")
        elif User.objects.filter(username=username).exists():
            messages.error(request, "Username already exists.")
        # Check user limit (only for non-super_admin users)
        elif role != User.Role.SUPER_ADMIN and not User.can_create_user():
            max_users = User.get_max_users()
            plan_name = getattr(settings, "PLAN_NAME", "current")
            messages.error(
                request,
                f"Cannot create more users. Your {plan_name} plan allows maximum {max_users} user(s). "
                f"Contact your vendor to upgrade."
            )
        else:
            # Get outlet - for outlet managers, force their outlet
            outlet = None
            if is_outlet_mgr:
                outlet = user_outlet
            elif outlet_id:
                try:
                    outlet = Outlet.objects.get(pk=outlet_id)
                except Outlet.DoesNotExist:
                    pass

            # Create user
            user = User.objects.create_user(
                username=username,
                email=email,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                role=role,
                pin=pin if pin else None,
                outlet=outlet,
            )
            # Set a default password
            user.set_password("changeme123")
            user.save()
            messages.success(request, f"User '{username}' created successfully. Default password: changeme123")
            return redirect("dashboard:users")

    # Filter users based on role
    if is_outlet_mgr:
        # Outlet managers see only their outlet's staff (not other managers)
        users = User.objects.filter(
            outlet=user_outlet
        ).exclude(
            role__in=[User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER]
        ).order_by("-date_joined")
        selected_outlet = str(user_outlet.pk)
    else:
        # Super admin sees all users
        users = User.objects.all().order_by("-date_joined")
        selected_outlet = request.GET.get("outlet", "")
        if selected_outlet:
            users = users.filter(outlet_id=selected_outlet)

    context = {
        "page_title": "User Management",
        "users": users,
        "roles": available_roles,
        "outlets": outlets,
        "selected_outlet": selected_outlet,
        "is_outlet_manager": is_outlet_mgr,
    }
    return render(request, "dashboard/users/list.html", context)


@login_required
def user_detail(request, pk):
    """View/edit user details."""
    from apps.core.models import Outlet

    # Check permission - allow super admin and outlet managers
    if not is_admin_user(request.user):
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    try:
        user = User.objects.get(pk=pk)
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        return redirect("dashboard:users")

    # Outlet managers can only manage staff in their outlet
    if not can_manage_user(request.user, user):
        messages.error(request, "You do not have permission to manage this user.")
        return redirect("dashboard:users")

    is_outlet_mgr = request.user.role == User.Role.OUTLET_MANAGER
    user_outlet = get_user_outlet(request.user)

    # Get outlets based on role
    if is_outlet_mgr:
        outlets = Outlet.objects.filter(pk=user_outlet.pk)
        available_roles = [
            (User.Role.STAFF_CASHIER, "Cashier"),
            (User.Role.STAFF_KITCHEN, "Kitchen Staff"),
            (User.Role.WAITER, "Waiter"),
        ]
    else:
        outlets = Outlet.objects.filter(is_active=True).order_by("name")
        available_roles = User.Role.choices

    if request.method == "POST":
        user.first_name = request.POST.get("first_name", "")
        user.last_name = request.POST.get("last_name", "")
        user.email = request.POST.get("email", "")
        user.phone = request.POST.get("phone", "")

        new_role = request.POST.get("role", user.role)
        # Outlet managers cannot change role to admin roles
        if is_outlet_mgr and new_role in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER]:
            messages.error(request, "You cannot assign admin roles.")
            return redirect("dashboard:user_detail", pk=pk)

        user.role = new_role
        user.is_active = request.POST.get("is_active") == "on"

        # Handle outlet assignment - outlet managers cannot change outlet
        if not is_outlet_mgr:
            outlet_id = request.POST.get("outlet", "").strip()
            if outlet_id:
                try:
                    user.outlet = Outlet.objects.get(pk=outlet_id)
                except Outlet.DoesNotExist:
                    user.outlet = None
            else:
                user.outlet = None

        user.save()
        messages.success(request, "User updated successfully.")
        return redirect("dashboard:user_detail", pk=pk)

    context = {
        "page_title": f"User: {user.get_full_name() or user.username}",
        "user_obj": user,
        "roles": available_roles,
        "outlets": outlets,
        "is_outlet_manager": is_outlet_mgr,
    }
    return render(request, "dashboard/users/detail.html", context)


@login_required
@require_http_methods(["POST"])
def user_toggle_status(request, pk):
    """Toggle user active status."""
    if not is_admin_user(request.user):
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    try:
        user = User.objects.get(pk=pk)
        if user == request.user:
            messages.error(request, "You cannot deactivate yourself.")
        elif not can_manage_user(request.user, user):
            messages.error(request, "You do not have permission to manage this user.")
        else:
            user.is_active = not user.is_active
            user.save(update_fields=["is_active"])
            status = "activated" if user.is_active else "deactivated"
            messages.success(request, f"User '{user.username}' {status}.")
    except User.DoesNotExist:
        messages.error(request, "User not found.")

    return redirect("dashboard:users")


@login_required
@require_http_methods(["POST"])
def user_reset_pin(request, pk):
    """Reset user PIN."""
    if not is_admin_user(request.user):
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    try:
        user = User.objects.get(pk=pk)
        if not can_manage_user(request.user, user):
            messages.error(request, "You do not have permission to manage this user.")
            return redirect("dashboard:users")

        new_pin = request.POST.get("new_pin", "").strip()
        if len(new_pin) == 6 and new_pin.isdigit():
            user.pin = new_pin
            user.save(update_fields=["pin"])
            messages.success(request, f"PIN updated for '{user.username}'.")
        else:
            messages.error(request, "PIN must be 6 digits.")
    except User.DoesNotExist:
        messages.error(request, "User not found.")

    return redirect("dashboard:users")


@login_required
@require_http_methods(["POST"])
def user_reset_password(request, pk):
    """Reset user password."""
    if not is_admin_user(request.user):
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    try:
        user = User.objects.get(pk=pk)
        if not can_manage_user(request.user, user):
            messages.error(request, "You do not have permission to manage this user.")
            return redirect("dashboard:users")

        user.set_password("changeme123")
        user.save()
        messages.success(request, f"Password reset for '{user.username}'. New password: changeme123")
    except User.DoesNotExist:
        messages.error(request, "User not found.")

    return redirect("dashboard:users")


@login_required
@require_http_methods(["POST"])
def user_delete(request, pk):
    """Delete a user."""
    if not is_admin_user(request.user):
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    try:
        user = User.objects.get(pk=pk)
        if user == request.user:
            messages.error(request, "You cannot delete yourself.")
        elif not can_manage_user(request.user, user):
            messages.error(request, "You do not have permission to delete this user.")
        else:
            username = user.username
            user.delete()
            messages.success(request, f"User '{username}' deleted.")
    except User.DoesNotExist:
        messages.error(request, "User not found.")

    return redirect("dashboard:users")


# ============================================================================
# Floor Management (Super Admin only)
# ============================================================================


@login_required
def floor_create(request):
    """Create a new floor."""
    from apps.core.models import Outlet

    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:tables")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        display_order = request.POST.get("display_order", 0)
        outlet_id = request.POST.get("outlet", "").strip()

        if not name:
            messages.error(request, "Floor name is required.")
        else:
            # Get outlet
            outlet = None
            if outlet_id:
                try:
                    outlet = Outlet.objects.get(pk=outlet_id)
                except Outlet.DoesNotExist:
                    pass

            # Check for duplicate name within same outlet
            existing = Floor.objects.filter(name=name, outlet=outlet)
            if existing.exists():
                messages.error(request, "A floor with this name already exists in this outlet.")
            else:
                Floor.objects.create(
                    name=name,
                    description=description,
                    display_order=int(display_order) if display_order else 0,
                    outlet=outlet,
                )
                messages.success(request, f"Floor '{name}' created successfully.")

    return HttpResponseRedirect(reverse("dashboard:tables") + "?view=manage")


@login_required
def floor_edit(request, pk):
    """Edit a floor."""
    from apps.core.models import Outlet

    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:tables")

    try:
        floor = Floor.objects.get(pk=pk)
    except Floor.DoesNotExist:
        messages.error(request, "Floor not found.")
        return redirect("dashboard:tables")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        display_order = request.POST.get("display_order", 0)
        is_active = request.POST.get("is_active") == "on"
        outlet_id = request.POST.get("outlet", "").strip()

        # Get outlet
        outlet = None
        if outlet_id:
            try:
                outlet = Outlet.objects.get(pk=outlet_id)
            except Outlet.DoesNotExist:
                pass

        if not name:
            messages.error(request, "Floor name is required.")
        elif Floor.objects.filter(name=name, outlet=outlet).exclude(pk=pk).exists():
            messages.error(request, "A floor with this name already exists in this outlet.")
        else:
            floor.name = name
            floor.description = description
            floor.display_order = int(display_order) if display_order else 0
            floor.is_active = is_active
            floor.outlet = outlet
            floor.save()
            messages.success(request, f"Floor '{name}' updated successfully.")

    return HttpResponseRedirect(reverse("dashboard:tables") + "?view=manage")


@login_required
@require_http_methods(["POST"])
def floor_delete(request, pk):
    """Delete a floor."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:tables")

    try:
        floor = Floor.objects.get(pk=pk)
        if floor.tables.exists():
            messages.error(request, f"Cannot delete floor '{floor.name}' - it has tables. Delete or move the tables first.")
        else:
            name = floor.name
            floor.delete()
            messages.success(request, f"Floor '{name}' deleted successfully.")
    except Floor.DoesNotExist:
        messages.error(request, "Floor not found.")

    return HttpResponseRedirect(reverse("dashboard:tables") + "?view=manage")


# ============================================================================
# Table CRUD (Super Admin only)
# ============================================================================


@login_required
def table_create(request):
    """Create a new table with QR code generation."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:tables")

    if request.method == "POST":
        floor_id = request.POST.get("floor")
        number = request.POST.get("number", "").strip()
        name = request.POST.get("name", "").strip()
        capacity = request.POST.get("capacity", 4)
        table_type = request.POST.get("table_type", Table.TableType.FOUR_SEATER)

        if not floor_id:
            messages.error(request, "Please select a floor.")
        elif not number:
            messages.error(request, "Table number is required.")
        else:
            try:
                floor = Floor.objects.get(pk=floor_id)

                # Check table limit for the outlet
                if floor.outlet and not Table.can_create_table(floor.outlet):
                    max_tables = Table.get_max_tables()
                    plan_name = getattr(settings, "PLAN_NAME", "current")
                    messages.error(
                        request,
                        f"Cannot create more tables. Your {plan_name} plan allows maximum {max_tables} table(s) per outlet. "
                        f"Contact your vendor to upgrade."
                    )
                    return HttpResponseRedirect(reverse("dashboard:tables") + "?view=manage")

                if Table.objects.filter(floor=floor, number=number).exists():
                    messages.error(request, f"Table '{number}' already exists on {floor.name}.")
                else:
                    # Create the table
                    table = Table.objects.create(
                        floor=floor,
                        number=number,
                        name=name,
                        capacity=int(capacity) if capacity else 4,
                        table_type=table_type,
                    )
                    # Generate QR code
                    from apps.tables.utils import generate_table_qr_code
                    try:
                        qr_file = generate_table_qr_code(table)
                        table.qr_code.save(qr_file.name, qr_file, save=True)
                    except Exception as e:
                        # Log error but don't fail table creation
                        pass
                    messages.success(request, f"Table '{number}' created on {floor.name} with QR code.")
            except Floor.DoesNotExist:
                messages.error(request, "Selected floor not found.")

    return HttpResponseRedirect(reverse("dashboard:tables") + "?view=manage")


@login_required
def table_edit(request, pk):
    """Edit a table."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:tables")

    try:
        table = Table.objects.select_related("floor").get(pk=pk)
    except Table.DoesNotExist:
        messages.error(request, "Table not found.")
        return redirect("dashboard:tables")

    if request.method == "POST":
        floor_id = request.POST.get("floor")
        number = request.POST.get("number", "").strip()
        name = request.POST.get("name", "").strip()
        capacity = request.POST.get("capacity", 4)
        table_type = request.POST.get("table_type", table.table_type)
        is_active = request.POST.get("is_active") == "on"

        if not floor_id:
            messages.error(request, "Please select a floor.")
        elif not number:
            messages.error(request, "Table number is required.")
        else:
            try:
                floor = Floor.objects.get(pk=floor_id)
                if Table.objects.filter(floor=floor, number=number).exclude(pk=pk).exists():
                    messages.error(request, f"Table '{number}' already exists on {floor.name}.")
                else:
                    table.floor = floor
                    table.number = number
                    table.name = name
                    table.capacity = int(capacity) if capacity else 4
                    table.table_type = table_type
                    table.is_active = is_active
                    table.save()
                    messages.success(request, f"Table '{number}' updated successfully.")
            except Floor.DoesNotExist:
                messages.error(request, "Selected floor not found.")

    return HttpResponseRedirect(reverse("dashboard:tables") + "?view=manage")


@login_required
@require_http_methods(["POST"])
def table_delete(request, pk):
    """Delete a table."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:tables")

    try:
        table = Table.objects.get(pk=pk)
        if table.status == Table.Status.OCCUPIED:
            messages.error(request, f"Cannot delete table '{table.number}' - it is currently occupied.")
        elif table.sessions.filter(is_active=True).exists():
            messages.error(request, f"Cannot delete table '{table.number}' - it has an active session.")
        else:
            number = table.number
            # Delete QR code file if exists
            if table.qr_code:
                try:
                    table.qr_code.delete(save=False)
                except Exception:
                    pass
            table.delete()
            messages.success(request, f"Table '{number}' deleted successfully.")
    except Table.DoesNotExist:
        messages.error(request, "Table not found.")

    return HttpResponseRedirect(reverse("dashboard:tables") + "?view=manage")


@login_required
@require_http_methods(["POST"])
def table_update_status(request, pk):
    """Update table status."""
    try:
        table = Table.objects.get(pk=pk)
        new_status = request.POST.get("status")
        if new_status in dict(Table.Status.choices):
            table.status = new_status
            table.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Table '{table.number}' status changed to {table.get_status_display()}.")
        else:
            messages.error(request, "Invalid status.")
    except Table.DoesNotExist:
        messages.error(request, "Table not found.")

    return redirect("dashboard:tables")


@login_required
@require_http_methods(["POST"])
def table_regenerate_qr(request, pk):
    """Regenerate QR code for a table."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:tables")

    try:
        table = Table.objects.get(pk=pk)
        from apps.tables.utils import regenerate_table_qr_code
        regenerate_table_qr_code(table)
        messages.success(request, f"QR code regenerated for table '{table.number}'.")
    except Table.DoesNotExist:
        messages.error(request, "Table not found.")

    return HttpResponseRedirect(reverse("dashboard:tables") + "?view=manage")


# ============================================================================
# Kitchen Display (Kitchen Staff)
# ============================================================================


@login_required
def kitchen_display(request):
    """Kitchen display for order management."""
    # Handle status updates via POST
    if request.method == "POST":
        order_id = request.POST.get("order_id")
        new_status = request.POST.get("status")

        try:
            order = Order.objects.get(pk=order_id)
            order.update_status(new_status, user=request.user)

            # Update kitchen ticket
            if hasattr(order, "kitchen_ticket"):
                ticket = order.kitchen_ticket
                if new_status == Order.Status.PREPARING and not ticket.started_at:
                    ticket.started_at = timezone.now()
                    ticket.assigned_to = request.user
                    ticket.save()
                elif new_status == Order.Status.READY:
                    ticket.completed_at = timezone.now()
                    ticket.save()

            messages.success(request, f"Order #{order.order_number} updated to {order.get_status_display()}.")
        except Order.DoesNotExist:
            messages.error(request, "Order not found.")

        return redirect("dashboard:kitchen")

    # Get orders by status
    today = timezone.now().date()

    pending_orders = Order.objects.filter(
        status=Order.Status.CONFIRMED,
        created_at__date=today
    ).select_related("table", "kitchen_ticket").prefetch_related("items").order_by("created_at")

    preparing_orders = Order.objects.filter(
        status=Order.Status.PREPARING,
        created_at__date=today
    ).select_related("table", "kitchen_ticket").prefetch_related("items").order_by("created_at")

    ready_orders = Order.objects.filter(
        status=Order.Status.READY,
        created_at__date=today
    ).select_related("table", "kitchen_ticket").prefetch_related("items").order_by("-prepared_at")[:10]

    context = {
        "page_title": "Kitchen Display",
        "pending_orders": pending_orders,
        "preparing_orders": preparing_orders,
        "ready_orders": ready_orders,
    }
    return render(request, "dashboard/kitchen/display.html", context)


# ============================================================================
# Reports (Super Admin only)
# ============================================================================


@login_required
def reports_view(request):
    """Reports and analytics dashboard."""
    from apps.core.models import Outlet

    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER]:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    from datetime import timedelta
    from django.db.models.functions import TruncDate, TruncHour
    from collections import defaultdict

    # Get all outlets for filter
    outlets = Outlet.objects.filter(is_active=True).order_by("name")
    selected_outlet = request.GET.get("outlet", "")

    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_start = today.replace(day=1)

    # Base querysets
    base_orders = Order.objects.all()
    base_payments = Payment.objects.all()
    base_order_items = OrderItem.objects.all()

    # Apply outlet filter if selected
    if selected_outlet:
        base_orders = base_orders.filter(outlet_id=selected_outlet)
        base_payments = base_payments.filter(order__outlet_id=selected_outlet)
        base_order_items = base_order_items.filter(order__outlet_id=selected_outlet)

    # Sales summary
    today_orders = base_orders.filter(
        created_at__date=today,
        status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
    )
    week_orders = base_orders.filter(
        created_at__date__gte=week_ago,
        status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
    )
    month_orders = base_orders.filter(
        created_at__date__gte=month_start,
        status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
    )

    sales_summary = {
        "today": {
            "orders": today_orders.count(),
            "revenue": today_orders.aggregate(total=Sum("total_amount"))["total"] or 0,
        },
        "week": {
            "orders": week_orders.count(),
            "revenue": week_orders.aggregate(total=Sum("total_amount"))["total"] or 0,
        },
        "month": {
            "orders": month_orders.count(),
            "revenue": month_orders.aggregate(total=Sum("total_amount"))["total"] or 0,
        },
    }

    # Top selling items (this month)
    top_items = base_order_items.filter(
        order__created_at__date__gte=month_start,
        order__status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
    ).values("item_name").annotate(
        total_qty=Sum("quantity"),
        total_revenue=Sum("total_price")
    ).order_by("-total_qty")[:10]

    # Sales by payment method
    payment_stats = base_payments.filter(
        created_at__date__gte=month_start,
        status=Payment.Status.COMPLETED
    ).values("method").annotate(
        count=Count("id"),
        total=Sum("amount")
    ).order_by("-total")

    # Daily sales for chart (last 7 days)
    daily_sales = base_orders.filter(
        created_at__date__gte=week_ago,
        status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
    ).annotate(
        date=TruncDate("created_at")
    ).values("date").annotate(
        orders=Count("id"),
        revenue=Sum("total_amount")
    ).order_by("date")

    # Convert to chart-friendly format
    dates = []
    revenues = []
    order_counts = []
    for entry in daily_sales:
        dates.append(entry["date"].strftime("%b %d"))
        revenues.append(float(entry["revenue"] or 0))
        order_counts.append(entry["orders"])

    # Orders by hour (today)
    hourly_orders = base_orders.filter(
        created_at__date=today
    ).annotate(
        hour=TruncHour("created_at")
    ).values("hour").annotate(
        count=Count("id")
    ).order_by("hour")

    hours = []
    hourly_counts = []
    for entry in hourly_orders:
        hours.append(entry["hour"].strftime("%H:00"))
        hourly_counts.append(entry["count"])

    # Order type breakdown
    order_types = base_orders.filter(
        created_at__date__gte=month_start,
        status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
    ).values("order_type").annotate(
        count=Count("id"),
        revenue=Sum("total_amount")
    )

    # Average order value
    avg_order = month_orders.aggregate(avg=Sum("total_amount") / Count("id") if month_orders.count() > 0 else 0)

    context = {
        "page_title": "Reports & Analytics",
        "sales_summary": sales_summary,
        "top_items": top_items,
        "payment_stats": payment_stats,
        "order_types": order_types,
        "avg_order_value": avg_order.get("avg") or 0,
        "chart_data": {
            "dates": dates,
            "revenues": revenues,
            "order_counts": order_counts,
            "hours": hours,
            "hourly_counts": hourly_counts,
        },
        "outlets": outlets,
        "selected_outlet": selected_outlet,
    }
    return render(request, "dashboard/reports/index.html", context)


# ============================================================================
# Settings (Super Admin only)
# ============================================================================


@login_required
def settings_view(request):
    """System settings."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    from apps.core.models import BusinessSettings, TaxSettings, OrderSettings

    business = BusinessSettings.load()
    tax = TaxSettings.load()
    order_settings = OrderSettings.load()

    if request.method == "POST":
        setting_type = request.POST.get("setting_type")

        if setting_type == "branding":
            # Update branding settings
            business.business_name = request.POST.get("business_name", business.business_name)
            business.tagline = request.POST.get("tagline", "")
            business.primary_color = request.POST.get("primary_color", business.primary_color)
            business.secondary_color = request.POST.get("secondary_color", business.secondary_color)
            business.accent_color = request.POST.get("accent_color", business.accent_color)
            business.sidebar_color = request.POST.get("sidebar_color", business.sidebar_color)
            business.sidebar_text_color = request.POST.get("sidebar_text_color", business.sidebar_text_color)
            business.sidebar_active_color = request.POST.get("sidebar_active_color", business.sidebar_active_color)
            business.login_bg_gradient_start = request.POST.get("login_gradient_start", business.login_bg_gradient_start)
            business.login_bg_gradient_end = request.POST.get("login_gradient_end", business.login_bg_gradient_end)
            business.login_welcome_text = request.POST.get("login_welcome_text", business.login_welcome_text)
            business.login_subtitle = request.POST.get("login_subtitle", business.login_subtitle)
            business.default_theme = request.POST.get("default_theme", business.default_theme)

            # Handle logo uploads
            if "logo" in request.FILES:
                business.logo = request.FILES["logo"]
            if "logo_dark" in request.FILES:
                business.logo_dark = request.FILES["logo_dark"]
            if "favicon" in request.FILES:
                business.favicon = request.FILES["favicon"]

            business.save()
            messages.success(request, "Branding settings updated successfully.")

        elif setting_type == "business":
            # Update business info
            business.address = request.POST.get("address", "")
            business.phone = request.POST.get("phone", "")
            business.email = request.POST.get("email", "")
            business.website = request.POST.get("website", "")
            business.gst_number = request.POST.get("gst_number", "")
            business.fssai_number = request.POST.get("fssai_number", "")
            business.currency = request.POST.get("currency", business.currency)
            business.currency_symbol = request.POST.get("currency_symbol", business.currency_symbol)
            business.save()
            messages.success(request, "Business settings updated successfully.")

        elif setting_type == "tax":
            # Update tax settings
            tax.cgst_rate = request.POST.get("cgst_rate", tax.cgst_rate)
            tax.sgst_rate = request.POST.get("sgst_rate", tax.sgst_rate)
            tax.service_charge_rate = request.POST.get("service_charge_rate", tax.service_charge_rate)
            tax.service_charge_enabled = request.POST.get("service_charge_enabled") == "on"
            tax.tax_inclusive_pricing = request.POST.get("tax_inclusive_pricing") == "on"
            tax.save()
            messages.success(request, "Tax settings updated successfully.")

        elif setting_type == "orders":
            # Update order settings
            order_settings.order_number_prefix = request.POST.get("order_number_prefix", order_settings.order_number_prefix)
            order_settings.default_preparation_time = request.POST.get("default_preparation_time", order_settings.default_preparation_time)
            order_settings.allow_qr_ordering = request.POST.get("allow_qr_ordering") == "on"
            order_settings.require_customer_info_qr = request.POST.get("require_customer_info_qr") == "on"
            order_settings.auto_accept_orders = request.POST.get("auto_accept_orders") == "on"
            order_settings.save()
            messages.success(request, "Order settings updated successfully.")

        return redirect("dashboard:settings")

    context = {
        "page_title": "Settings",
        "business": business,
        "tax": tax,
        "order_settings": order_settings,
    }
    return render(request, "dashboard/settings/index.html", context)


# ============================================================================
# Orders / POS
# ============================================================================


@login_required
def order_list(request):
    """List all orders with filtering."""
    status_filter = request.GET.get("status", "")
    date_filter = request.GET.get("date", "today")

    orders = Order.objects.select_related("table", "created_by", "served_by").order_by("-created_at")

    # Filter by status
    if status_filter:
        orders = orders.filter(status=status_filter)

    # Filter by date
    today = timezone.now().date()
    if date_filter == "today":
        orders = orders.filter(created_at__date=today)
    elif date_filter == "week":
        from datetime import timedelta
        week_ago = today - timedelta(days=7)
        orders = orders.filter(created_at__date__gte=week_ago)
    elif date_filter == "month":
        orders = orders.filter(created_at__year=today.year, created_at__month=today.month)

    # Calculate stats
    today_orders = Order.objects.filter(created_at__date=today)
    stats = {
        "total_today": today_orders.count(),
        "pending": today_orders.filter(status=Order.Status.PENDING).count(),
        "preparing": today_orders.filter(status=Order.Status.PREPARING).count(),
        "completed": today_orders.filter(status=Order.Status.COMPLETED).count(),
        "revenue_today": today_orders.filter(
            status__in=[Order.Status.COMPLETED, Order.Status.SERVED]
        ).aggregate(total=Sum("total_amount"))["total"] or 0,
    }

    context = {
        "page_title": "Orders",
        "orders": orders[:100],  # Limit to recent 100
        "stats": stats,
        "status_choices": Order.Status.choices,
        "current_status": status_filter,
        "current_date": date_filter,
    }
    return render(request, "dashboard/orders/list.html", context)


@login_required
def pos_view(request, table_pk=None):
    """POS interface for creating orders."""
    table = None
    current_order = None

    if table_pk:
        try:
            table = Table.objects.get(pk=table_pk)
            # Get any pending/confirmed order for this table
            current_order = Order.objects.filter(
                table=table,
                status__in=[Order.Status.PENDING, Order.Status.CONFIRMED]
            ).first()
        except Table.DoesNotExist:
            messages.error(request, "Table not found.")
            return redirect("dashboard:pos")

    # Handle order creation
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create_order":
            # Create new order
            order_type = request.POST.get("order_type", Order.OrderType.DINE_IN)
            customer_name = request.POST.get("customer_name", "").strip()
            customer_phone = request.POST.get("customer_phone", "").strip()

            order = Order.objects.create(
                table=table,
                created_by=request.user,
                order_type=order_type,
                order_source=Order.OrderSource.POS,
                customer_name=customer_name,
                customer_phone=customer_phone,
            )

            # Create kitchen ticket
            KitchenOrderTicket.objects.create(order=order)

            # Update table status
            if table:
                table.status = Table.Status.OCCUPIED
                table.save(update_fields=["status", "updated_at"])

            messages.success(request, f"Order #{order.order_number} created.")
            return redirect("dashboard:order_detail", pk=order.pk)

    # Get menu categories and items
    categories = Category.objects.filter(is_active=True).prefetch_related(
        "items"
    ).order_by("display_order")

    # Get tables for selection
    floors = Floor.objects.filter(is_active=True).prefetch_related("tables").order_by("display_order")

    context = {
        "page_title": "POS",
        "table": table,
        "current_order": current_order,
        "categories": categories,
        "floors": floors,
        "order_types": Order.OrderType.choices,
    }
    return render(request, "dashboard/orders/pos.html", context)


@login_required
def order_detail(request, pk):
    """View and manage a specific order."""
    try:
        order = Order.objects.select_related(
            "table", "created_by", "served_by"
        ).prefetch_related(
            "items__menu_item", "payments"
        ).get(pk=pk)
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect("dashboard:orders")

    # Get menu for adding items
    categories = Category.objects.filter(is_active=True).prefetch_related(
        "items"
    ).order_by("display_order")

    # Generate seat numbers based on table capacity (default 4 if no table)
    seat_count = order.table.capacity if order.table else 4
    seat_numbers = list(range(1, seat_count + 1))

    context = {
        "page_title": f"Order #{order.order_number}",
        "order": order,
        "categories": categories,
        "status_choices": Order.Status.choices,
        "payment_methods": Payment.Method.choices,
        "seat_numbers": seat_numbers,
    }
    return render(request, "dashboard/orders/detail.html", context)


@login_required
@require_http_methods(["POST"])
def order_update_status(request, pk):
    """Update order status."""
    try:
        order = Order.objects.get(pk=pk)
        new_status = request.POST.get("status")

        if new_status in dict(Order.Status.choices):
            order.update_status(new_status, user=request.user)
            messages.success(request, f"Order status updated to {order.get_status_display()}.")

            # Redirect waiter back to tables after sending to kitchen
            if new_status == Order.Status.CONFIRMED:
                return redirect("dashboard:tables")
        else:
            messages.error(request, "Invalid status.")
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")

    return redirect("dashboard:order_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def order_add_item(request, pk):
    """Add item to an order."""
    try:
        order = Order.objects.get(pk=pk)

        if order.status not in [Order.Status.PENDING, Order.Status.CONFIRMED]:
            messages.error(request, "Cannot modify this order.")
            return redirect("dashboard:order_detail", pk=pk)

        menu_item_id = request.POST.get("menu_item")
        quantity = int(request.POST.get("quantity", 1))
        special_instructions = request.POST.get("special_instructions", "")
        seat_number = request.POST.get("seat_number")

        # Convert seat_number to int or None
        if seat_number and seat_number.strip() and seat_number != "null":
            try:
                seat_number = int(seat_number)
            except ValueError:
                seat_number = None
        else:
            seat_number = None

        try:
            menu_item = MenuItem.objects.get(pk=menu_item_id, is_available=True)

            # Create order item
            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                item_name=menu_item.name,
                unit_price=menu_item.base_price,
                quantity=quantity,
                total_price=menu_item.base_price * quantity,
                special_instructions=special_instructions,
                seat_number=seat_number,
            )

            # Recalculate totals
            order.calculate_totals()
            order.save()

            seat_info = f" (Seat {seat_number})" if seat_number else ""
            messages.success(request, f"Added {quantity}x {menu_item.name}{seat_info} to order.")
        except MenuItem.DoesNotExist:
            messages.error(request, "Menu item not found or unavailable.")
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")

    return redirect("dashboard:order_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def order_remove_item(request, pk, item_pk):
    """Remove item from an order."""
    try:
        order = Order.objects.get(pk=pk)

        if order.status not in [Order.Status.PENDING, Order.Status.CONFIRMED]:
            messages.error(request, "Cannot modify this order.")
            return redirect("dashboard:order_detail", pk=pk)

        try:
            item = order.items.get(pk=item_pk)
            item_name = item.item_name
            item.delete()

            # Recalculate totals
            order.calculate_totals()
            order.save()

            messages.success(request, f"Removed {item_name} from order.")
        except OrderItem.DoesNotExist:
            messages.error(request, "Item not found in order.")
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")

    return redirect("dashboard:order_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def order_update_item_qty(request, pk, item_pk):
    """Update quantity of an item in an order (+/-)."""
    try:
        order = Order.objects.get(pk=pk)

        if order.status not in [Order.Status.PENDING, Order.Status.CONFIRMED]:
            messages.error(request, "Cannot modify this order.")
            return redirect("dashboard:order_detail", pk=pk)

        try:
            item = order.items.get(pk=item_pk)
            action = request.POST.get("action")

            if action == "increase":
                item.quantity += 1
                item.save()
            elif action == "decrease":
                if item.quantity > 1:
                    item.quantity -= 1
                    item.save()
                else:
                    # Remove item if quantity would be 0
                    item.delete()

            # Recalculate totals
            order.calculate_totals()
            order.save()

        except OrderItem.DoesNotExist:
            messages.error(request, "Item not found in order.")
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")

    return redirect("dashboard:order_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def order_payment(request, pk):
    """Process payment for an order."""
    from decimal import Decimal

    try:
        order = Order.objects.get(pk=pk)

        amount = request.POST.get("amount")
        method = request.POST.get("method", Payment.Method.CASH)
        amount_tendered = request.POST.get("amount_tendered")
        transaction_id = request.POST.get("transaction_id", "")
        seat_number = request.POST.get("seat_number")

        # Handle split bill by seat
        if seat_number and seat_number not in ["", "None", "null"]:
            try:
                seat_number = int(seat_number)
                # Calculate amount for this seat's items
                seat_items = order.items.filter(seat_number=seat_number)
                amount = sum(item.total_price for item in seat_items)
                notes = f"Split bill - Seat {seat_number}"
            except (ValueError, TypeError):
                seat_number = None
                notes = ""
        elif seat_number in ["None", "null", ""]:
            # Items with no seat assigned
            seat_items = order.items.filter(seat_number__isnull=True)
            amount = sum(item.total_price for item in seat_items)
            notes = "Split bill - No seat assigned"
        else:
            notes = ""

        if not amount:
            try:
                amount = float(request.POST.get("amount", 0))
            except (TypeError, ValueError):
                amount = float(order.balance_due)

        if amount <= 0:
            messages.error(request, "Invalid payment amount.")
            return redirect("dashboard:order_detail", pk=pk)

        payment = Payment.objects.create(
            order=order,
            amount=amount,
            method=method,
            status=Payment.Status.COMPLETED,
            amount_tendered=float(amount_tendered) if amount_tendered else None,
            transaction_id=transaction_id,
            processed_by=request.user,
            notes=notes,
        )

        # Check if fully paid
        if order.is_paid:
            from django.db.models import Q

            if order.status in [Order.Status.SERVED, Order.Status.READY]:
                order.update_status(Order.Status.COMPLETED)

            # Auto-release tables when bill is fully paid
            if order.order_type == Order.OrderType.DINE_IN:
                all_tables = order.all_tables

                for tbl in all_tables:
                    # Check if there are other active orders for this table
                    other_orders = Order.objects.filter(
                        Q(table=tbl) | Q(combined_tables=tbl),
                        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
                    ).exclude(pk=pk).exists()

                    if not other_orders:
                        tbl.status = Table.Status.VACANT
                        tbl.save(update_fields=["status", "updated_at"])

            messages.success(request, f"Payment of ₹{amount} processed. Order fully paid!")
        else:
            messages.success(request, f"Payment of ₹{amount} processed. Balance: ₹{order.balance_due}")

    except Order.DoesNotExist:
        messages.error(request, "Order not found.")

    return redirect("dashboard:order_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def order_cancel(request, pk):
    """Cancel an order."""
    from django.db.models import Q

    try:
        order = Order.objects.prefetch_related("combined_tables").get(pk=pk)

        if order.status == Order.Status.COMPLETED:
            messages.error(request, "Cannot cancel a completed order.")
        elif order.is_paid:
            messages.error(request, "Cannot cancel a paid order. Process refund first.")
        else:
            order.update_status(Order.Status.CANCELLED)

            # Free up all tables if dine-in
            if order.order_type == Order.OrderType.DINE_IN:
                all_tables = order.all_tables

                for tbl in all_tables:
                    # Check if there are other active orders for this table
                    other_orders = Order.objects.filter(
                        Q(table=tbl) | Q(combined_tables=tbl),
                        status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY]
                    ).exclude(pk=pk).exists()

                    if not other_orders:
                        tbl.status = Table.Status.VACANT
                        tbl.save(update_fields=["status", "updated_at"])

            messages.success(request, f"Order #{order.order_number} cancelled.")
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")

    return redirect("dashboard:orders")


@login_required
def order_back_to_tables(request, pk):
    """Go back to tables, auto-delete empty pending orders."""
    from django.db.models import Q

    try:
        order = Order.objects.prefetch_related("combined_tables").get(pk=pk)

        # If order is pending/confirmed with no items, delete it
        if order.status in [Order.Status.PENDING, Order.Status.CONFIRMED] and order.items.count() == 0:
            table = order.table
            combined_tables = list(order.combined_tables.all())

            # Delete the empty order
            order.delete()

            # Free up primary table if no other active orders
            if table:
                other_orders = Order.objects.filter(
                    Q(table=table) | Q(combined_tables=table),
                    status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
                ).exists()

                if not other_orders:
                    table.status = Table.Status.VACANT
                    table.save(update_fields=["status", "updated_at"])

            # Free up combined tables
            for ct in combined_tables:
                other_orders = Order.objects.filter(
                    Q(table=ct) | Q(combined_tables=ct),
                    status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
                ).exists()

                if not other_orders:
                    ct.status = Table.Status.VACANT
                    ct.save(update_fields=["status", "updated_at"])

    except Order.DoesNotExist:
        pass

    return redirect("dashboard:tables")


@login_required
def order_print(request, pk):
    """Print order receipt/bill."""
    try:
        order = Order.objects.select_related(
            "table", "created_by"
        ).prefetch_related(
            "items", "payments"
        ).get(pk=pk)
    except Order.DoesNotExist:
        messages.error(request, "Order not found.")
        return redirect("dashboard:orders")

    from apps.core.models import BusinessSettings
    business = BusinessSettings.load()

    context = {
        "order": order,
        "business": business,
    }
    return render(request, "dashboard/orders/print.html", context)


# ============================================================================
# Inventory Management (Super Admin only)
# ============================================================================


from apps.inventory.models import (
    InventoryCategory, InventoryItem, Supplier,
    StockMovement, PurchaseOrder, PurchaseOrderItem, StockAlert
)


@login_required
def inventory_dashboard(request):
    """Inventory management dashboard."""
    from apps.core.models import Outlet

    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    # Get all outlets for filter
    outlets = Outlet.objects.filter(is_active=True).order_by("name")
    selected_outlet = request.GET.get("outlet", "")

    # Get stats - filter by outlet if selected
    items = InventoryItem.objects.filter(is_active=True)
    categories_qs = InventoryCategory.objects.filter(is_active=True)
    suppliers_qs = Supplier.objects.filter(is_active=True)
    alerts_qs = StockAlert.objects.filter(is_resolved=False).select_related("item")
    movements_qs = StockMovement.objects.select_related("item", "created_by")

    if selected_outlet:
        items = items.filter(category__outlet_id=selected_outlet)
        categories_qs = categories_qs.filter(outlet_id=selected_outlet)
        suppliers_qs = suppliers_qs.filter(outlet_id=selected_outlet)
        alerts_qs = alerts_qs.filter(item__category__outlet_id=selected_outlet)
        movements_qs = movements_qs.filter(item__category__outlet_id=selected_outlet)

    low_stock_items = [item for item in items if item.is_low_stock]
    out_of_stock = [item for item in items if item.current_stock <= 0]

    # Get recent alerts
    recent_alerts = alerts_qs[:10]

    # Get recent movements
    recent_movements = movements_qs[:10]

    # Calculate total stock value
    total_stock_value = sum(item.stock_value for item in items)

    context = {
        "page_title": "Inventory",
        "stats": {
            "total_items": items.count(),
            "low_stock": len(low_stock_items),
            "out_of_stock": len(out_of_stock),
            "total_value": total_stock_value,
            "categories": categories_qs.count(),
            "suppliers": suppliers_qs.count(),
        },
        "low_stock_items": low_stock_items[:5],
        "recent_alerts": recent_alerts,
        "recent_movements": recent_movements,
        "outlets": outlets,
        "selected_outlet": selected_outlet,
    }
    return render(request, "dashboard/inventory/dashboard.html", context)


@login_required
def inventory_items(request):
    """List all inventory items."""
    from apps.core.models import Outlet

    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    # Get all outlets for filter
    outlets = Outlet.objects.filter(is_active=True).order_by("name")
    selected_outlet = request.GET.get("outlet", "")

    category_filter = request.GET.get("category", "")
    status_filter = request.GET.get("status", "")
    search = request.GET.get("search", "")

    items = InventoryItem.objects.select_related("category", "supplier").filter(is_active=True)
    categories = InventoryCategory.objects.filter(is_active=True).order_by("display_order")
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")

    # Apply outlet filter first
    if selected_outlet:
        items = items.filter(category__outlet_id=selected_outlet)
        categories = categories.filter(outlet_id=selected_outlet)
        suppliers = suppliers.filter(outlet_id=selected_outlet)

    # Apply other filters
    if category_filter:
        items = items.filter(category_id=category_filter)
    if status_filter == "low":
        items = [item for item in items if item.is_low_stock and item.current_stock > 0]
    elif status_filter == "out":
        items = items.filter(current_stock__lte=0)
    if search:
        items = items.filter(name__icontains=search)

    context = {
        "page_title": "Inventory Items",
        "items": items,
        "categories": categories,
        "suppliers": suppliers,
        "units": InventoryItem.Unit.choices,
        "current_category": category_filter,
        "current_status": status_filter,
        "search": search,
        "outlets": outlets,
        "selected_outlet": selected_outlet,
    }
    return render(request, "dashboard/inventory/items.html", context)


@login_required
def inventory_item_detail(request, pk):
    """View inventory item details."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    try:
        item = InventoryItem.objects.select_related("category", "supplier").get(pk=pk)
    except InventoryItem.DoesNotExist:
        messages.error(request, "Inventory item not found.")
        return redirect("dashboard:inventory_items")

    # Get recent movements
    movements = item.movements.select_related("created_by", "purchase_order").order_by("-created_at")[:20]

    # Get alerts
    alerts = item.alerts.order_by("-created_at")[:10]

    categories = InventoryCategory.objects.filter(is_active=True).order_by("display_order")
    suppliers = Supplier.objects.filter(is_active=True).order_by("name")

    context = {
        "page_title": item.name,
        "item": item,
        "movements": movements,
        "alerts": alerts,
        "categories": categories,
        "suppliers": suppliers,
        "units": InventoryItem.Unit.choices,
        "movement_types": StockMovement.MovementType.choices,
    }
    return render(request, "dashboard/inventory/item_detail.html", context)


@login_required
def inventory_item_create(request):
    """Create new inventory item."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:inventory_items")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category_id = request.POST.get("category")
        supplier_id = request.POST.get("supplier")
        unit = request.POST.get("unit", InventoryItem.Unit.PIECE)
        current_stock = request.POST.get("current_stock", 0)
        minimum_stock = request.POST.get("minimum_stock", 0)
        maximum_stock = request.POST.get("maximum_stock", 0)
        cost_price = request.POST.get("cost_price", 0)
        description = request.POST.get("description", "")
        is_perishable = request.POST.get("is_perishable") == "on"

        if not name:
            messages.error(request, "Item name is required.")
        else:
            item = InventoryItem.objects.create(
                name=name,
                category_id=category_id if category_id else None,
                supplier_id=supplier_id if supplier_id else None,
                unit=unit,
                current_stock=float(current_stock) if current_stock else 0,
                minimum_stock=float(minimum_stock) if minimum_stock else 0,
                maximum_stock=float(maximum_stock) if maximum_stock else 0,
                cost_price=float(cost_price) if cost_price else 0,
                description=description,
                is_perishable=is_perishable,
            )
            messages.success(request, f"Inventory item '{name}' created successfully.")
            return redirect("dashboard:inventory_item_detail", pk=item.pk)

    return redirect("dashboard:inventory_items")


@login_required
def inventory_item_edit(request, pk):
    """Edit inventory item."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:inventory_items")

    try:
        item = InventoryItem.objects.get(pk=pk)
    except InventoryItem.DoesNotExist:
        messages.error(request, "Inventory item not found.")
        return redirect("dashboard:inventory_items")

    if request.method == "POST":
        item.name = request.POST.get("name", item.name).strip()
        item.category_id = request.POST.get("category") or None
        item.supplier_id = request.POST.get("supplier") or None
        item.unit = request.POST.get("unit", item.unit)
        item.minimum_stock = float(request.POST.get("minimum_stock", 0) or 0)
        item.maximum_stock = float(request.POST.get("maximum_stock", 0) or 0)
        item.cost_price = float(request.POST.get("cost_price", 0) or 0)
        item.description = request.POST.get("description", "")
        item.is_perishable = request.POST.get("is_perishable") == "on"
        item.is_active = request.POST.get("is_active") == "on"
        item.save()
        messages.success(request, f"Item '{item.name}' updated successfully.")

    return redirect("dashboard:inventory_item_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def inventory_item_delete(request, pk):
    """Delete inventory item."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:inventory_items")

    try:
        item = InventoryItem.objects.get(pk=pk)
        name = item.name
        item.delete()
        messages.success(request, f"Item '{name}' deleted successfully.")
    except InventoryItem.DoesNotExist:
        messages.error(request, "Inventory item not found.")

    return redirect("dashboard:inventory_items")


@login_required
@require_http_methods(["POST"])
def inventory_stock_adjustment(request, pk):
    """Adjust stock for an inventory item."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:inventory_items")

    try:
        item = InventoryItem.objects.get(pk=pk)

        movement_type = request.POST.get("movement_type", StockMovement.MovementType.ADJUSTMENT)
        quantity = float(request.POST.get("quantity", 0))
        reason = request.POST.get("reason", "")
        notes = request.POST.get("notes", "")

        if quantity == 0:
            messages.error(request, "Quantity cannot be zero.")
            return redirect("dashboard:inventory_item_detail", pk=pk)

        # Calculate new stock
        stock_before = item.current_stock
        if movement_type in [StockMovement.MovementType.SALE, StockMovement.MovementType.WASTAGE]:
            # Deduct stock
            stock_after = stock_before - abs(quantity)
            quantity = -abs(quantity)
        else:
            # Add stock
            stock_after = stock_before + abs(quantity)
            quantity = abs(quantity)

        # Create movement record
        StockMovement.objects.create(
            item=item,
            movement_type=movement_type,
            quantity=quantity,
            stock_before=stock_before,
            stock_after=stock_after,
            reason=reason,
            notes=notes,
            created_by=request.user,
        )

        # Update item stock
        item.current_stock = stock_after
        item.save(update_fields=["current_stock", "updated_at"])

        # Check for alerts
        if item.is_low_stock and item.current_stock > 0:
            StockAlert.objects.get_or_create(
                item=item,
                alert_type=StockAlert.AlertType.LOW_STOCK,
                is_resolved=False,
                defaults={
                    "priority": StockAlert.Priority.HIGH,
                    "message": f"{item.name} is running low. Current stock: {item.current_stock} {item.unit}",
                }
            )
        elif item.current_stock <= 0:
            StockAlert.objects.get_or_create(
                item=item,
                alert_type=StockAlert.AlertType.OUT_OF_STOCK,
                is_resolved=False,
                defaults={
                    "priority": StockAlert.Priority.CRITICAL,
                    "message": f"{item.name} is out of stock!",
                }
            )

        messages.success(request, f"Stock adjusted. New stock: {item.current_stock} {item.unit}")

    except InventoryItem.DoesNotExist:
        messages.error(request, "Inventory item not found.")

    return redirect("dashboard:inventory_item_detail", pk=pk)


# ============================================================================
# Inventory Categories
# ============================================================================


@login_required
def inventory_categories(request):
    """List and manage inventory categories."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    categories = InventoryCategory.objects.annotate(
        item_count=Count("items")
    ).order_by("display_order", "name")

    context = {
        "page_title": "Inventory Categories",
        "categories": categories,
    }
    return render(request, "dashboard/inventory/categories.html", context)


@login_required
def inventory_category_create(request):
    """Create new inventory category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:inventory_categories")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "")
        display_order = request.POST.get("display_order", 0)

        if not name:
            messages.error(request, "Category name is required.")
        elif InventoryCategory.objects.filter(name=name).exists():
            messages.error(request, "Category with this name already exists.")
        else:
            InventoryCategory.objects.create(
                name=name,
                description=description,
                display_order=int(display_order) if display_order else 0,
            )
            messages.success(request, f"Category '{name}' created successfully.")

    return redirect("dashboard:inventory_categories")


@login_required
def inventory_category_edit(request, pk):
    """Edit inventory category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:inventory_categories")

    try:
        category = InventoryCategory.objects.get(pk=pk)
    except InventoryCategory.DoesNotExist:
        messages.error(request, "Category not found.")
        return redirect("dashboard:inventory_categories")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "")
        display_order = request.POST.get("display_order", 0)
        is_active = request.POST.get("is_active") == "on"

        if not name:
            messages.error(request, "Category name is required.")
        elif InventoryCategory.objects.filter(name=name).exclude(pk=pk).exists():
            messages.error(request, "Category with this name already exists.")
        else:
            category.name = name
            category.description = description
            category.display_order = int(display_order) if display_order else 0
            category.is_active = is_active
            category.save()
            messages.success(request, f"Category '{name}' updated successfully.")

    return redirect("dashboard:inventory_categories")


@login_required
@require_http_methods(["POST"])
def inventory_category_delete(request, pk):
    """Delete inventory category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:inventory_categories")

    try:
        category = InventoryCategory.objects.get(pk=pk)
        if category.items.exists():
            messages.error(request, f"Cannot delete category '{category.name}' - it has items. Move or delete the items first.")
        else:
            name = category.name
            category.delete()
            messages.success(request, f"Category '{name}' deleted successfully.")
    except InventoryCategory.DoesNotExist:
        messages.error(request, "Category not found.")

    return redirect("dashboard:inventory_categories")


# ============================================================================
# Suppliers
# ============================================================================


@login_required
def suppliers(request):
    """List and manage suppliers."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    supplier_list = Supplier.objects.annotate(
        item_count=Count("items"),
        order_count=Count("purchase_orders"),
    ).order_by("name")

    context = {
        "page_title": "Suppliers",
        "suppliers": supplier_list,
    }
    return render(request, "dashboard/inventory/suppliers.html", context)


@login_required
def supplier_detail(request, pk):
    """View supplier details."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    try:
        supplier = Supplier.objects.get(pk=pk)
    except Supplier.DoesNotExist:
        messages.error(request, "Supplier not found.")
        return redirect("dashboard:suppliers")

    items = supplier.items.filter(is_active=True)
    orders = supplier.purchase_orders.order_by("-created_at")[:10]

    context = {
        "page_title": supplier.name,
        "supplier": supplier,
        "items": items,
        "orders": orders,
    }
    return render(request, "dashboard/inventory/supplier_detail.html", context)


@login_required
def supplier_create(request):
    """Create new supplier."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:suppliers")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        contact_person = request.POST.get("contact_person", "")
        email = request.POST.get("email", "")
        phone = request.POST.get("phone", "")
        address = request.POST.get("address", "")
        gst_number = request.POST.get("gst_number", "")
        payment_terms = request.POST.get("payment_terms", "")
        notes = request.POST.get("notes", "")

        if not name:
            messages.error(request, "Supplier name is required.")
        else:
            supplier = Supplier.objects.create(
                name=name,
                contact_person=contact_person,
                email=email,
                phone=phone,
                address=address,
                gst_number=gst_number,
                payment_terms=payment_terms,
                notes=notes,
            )
            messages.success(request, f"Supplier '{name}' created successfully.")
            return redirect("dashboard:supplier_detail", pk=supplier.pk)

    return redirect("dashboard:suppliers")


@login_required
def supplier_edit(request, pk):
    """Edit supplier."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:suppliers")

    try:
        supplier = Supplier.objects.get(pk=pk)
    except Supplier.DoesNotExist:
        messages.error(request, "Supplier not found.")
        return redirect("dashboard:suppliers")

    if request.method == "POST":
        supplier.name = request.POST.get("name", supplier.name).strip()
        supplier.contact_person = request.POST.get("contact_person", "")
        supplier.email = request.POST.get("email", "")
        supplier.phone = request.POST.get("phone", "")
        supplier.address = request.POST.get("address", "")
        supplier.gst_number = request.POST.get("gst_number", "")
        supplier.payment_terms = request.POST.get("payment_terms", "")
        supplier.notes = request.POST.get("notes", "")
        supplier.is_active = request.POST.get("is_active") == "on"
        supplier.save()
        messages.success(request, f"Supplier '{supplier.name}' updated successfully.")

    return redirect("dashboard:supplier_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def supplier_delete(request, pk):
    """Delete supplier."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:suppliers")

    try:
        supplier = Supplier.objects.get(pk=pk)
        if supplier.items.exists():
            messages.error(request, f"Cannot delete supplier '{supplier.name}' - it has linked items.")
        elif supplier.purchase_orders.exists():
            messages.error(request, f"Cannot delete supplier '{supplier.name}' - it has purchase orders.")
        else:
            name = supplier.name
            supplier.delete()
            messages.success(request, f"Supplier '{name}' deleted successfully.")
    except Supplier.DoesNotExist:
        messages.error(request, "Supplier not found.")

    return redirect("dashboard:suppliers")


# ============================================================================
# Purchase Orders
# ============================================================================


@login_required
def purchase_orders(request):
    """List purchase orders."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    status_filter = request.GET.get("status", "")
    orders = PurchaseOrder.objects.select_related("supplier", "created_by").order_by("-created_at")

    if status_filter:
        orders = orders.filter(status=status_filter)

    context = {
        "page_title": "Purchase Orders",
        "orders": orders[:50],
        "status_choices": PurchaseOrder.Status.choices,
        "current_status": status_filter,
    }
    return render(request, "dashboard/inventory/purchase_orders.html", context)


@login_required
def purchase_order_detail(request, pk):
    """View purchase order details."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    try:
        order = PurchaseOrder.objects.select_related(
            "supplier", "created_by", "approved_by"
        ).prefetch_related("items__inventory_item").get(pk=pk)
    except PurchaseOrder.DoesNotExist:
        messages.error(request, "Purchase order not found.")
        return redirect("dashboard:purchase_orders")

    items = InventoryItem.objects.filter(is_active=True).order_by("name")

    context = {
        "page_title": f"PO #{order.order_number}",
        "order": order,
        "items": items,
        "status_choices": PurchaseOrder.Status.choices,
    }
    return render(request, "dashboard/inventory/purchase_order_detail.html", context)


@login_required
def purchase_order_create(request):
    """Create new purchase order."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:purchase_orders")

    if request.method == "POST":
        supplier_id = request.POST.get("supplier")
        expected_date = request.POST.get("expected_date")
        notes = request.POST.get("notes", "")

        if not supplier_id:
            messages.error(request, "Please select a supplier.")
        else:
            try:
                supplier = Supplier.objects.get(pk=supplier_id)
                order = PurchaseOrder.objects.create(
                    supplier=supplier,
                    expected_date=expected_date if expected_date else None,
                    notes=notes,
                    created_by=request.user,
                )
                messages.success(request, f"Purchase order #{order.order_number} created.")
                return redirect("dashboard:purchase_order_detail", pk=order.pk)
            except Supplier.DoesNotExist:
                messages.error(request, "Supplier not found.")

    suppliers_list = Supplier.objects.filter(is_active=True).order_by("name")

    context = {
        "page_title": "Create Purchase Order",
        "suppliers": suppliers_list,
    }
    return render(request, "dashboard/inventory/purchase_order_create.html", context)


@login_required
@require_http_methods(["POST"])
def purchase_order_add_item(request, pk):
    """Add item to purchase order."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:purchase_orders")

    try:
        order = PurchaseOrder.objects.get(pk=pk)

        if order.status not in [PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.PENDING]:
            messages.error(request, "Cannot modify this purchase order.")
            return redirect("dashboard:purchase_order_detail", pk=pk)

        item_id = request.POST.get("inventory_item")
        quantity = float(request.POST.get("quantity", 1))
        unit_price = float(request.POST.get("unit_price", 0))

        try:
            item = InventoryItem.objects.get(pk=item_id)

            PurchaseOrderItem.objects.create(
                purchase_order=order,
                inventory_item=item,
                quantity_ordered=quantity,
                unit_price=unit_price,
                total_price=quantity * unit_price,
            )

            # Recalculate totals
            order.calculate_totals()
            order.save()

            messages.success(request, f"Added {quantity} x {item.name} to order.")
        except InventoryItem.DoesNotExist:
            messages.error(request, "Inventory item not found.")
    except PurchaseOrder.DoesNotExist:
        messages.error(request, "Purchase order not found.")

    return redirect("dashboard:purchase_order_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def purchase_order_remove_item(request, pk, item_pk):
    """Remove item from purchase order."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:purchase_orders")

    try:
        order = PurchaseOrder.objects.get(pk=pk)

        if order.status not in [PurchaseOrder.Status.DRAFT, PurchaseOrder.Status.PENDING]:
            messages.error(request, "Cannot modify this purchase order.")
            return redirect("dashboard:purchase_order_detail", pk=pk)

        try:
            item = order.items.get(pk=item_pk)
            item.delete()
            order.calculate_totals()
            order.save()
            messages.success(request, "Item removed from order.")
        except PurchaseOrderItem.DoesNotExist:
            messages.error(request, "Item not found in order.")
    except PurchaseOrder.DoesNotExist:
        messages.error(request, "Purchase order not found.")

    return redirect("dashboard:purchase_order_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def purchase_order_update_status(request, pk):
    """Update purchase order status."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:purchase_orders")

    try:
        order = PurchaseOrder.objects.get(pk=pk)
        new_status = request.POST.get("status")

        if new_status in dict(PurchaseOrder.Status.choices):
            old_status = order.status
            order.status = new_status

            # Set dates based on status
            if new_status == PurchaseOrder.Status.APPROVED:
                order.approved_by = request.user
            elif new_status == PurchaseOrder.Status.ORDERED:
                order.order_date = timezone.now().date()
            elif new_status == PurchaseOrder.Status.RECEIVED:
                order.received_date = timezone.now().date()

            order.save()
            messages.success(request, f"Order status updated to {order.get_status_display()}.")
        else:
            messages.error(request, "Invalid status.")
    except PurchaseOrder.DoesNotExist:
        messages.error(request, "Purchase order not found.")

    return redirect("dashboard:purchase_order_detail", pk=pk)


@login_required
@require_http_methods(["POST"])
def purchase_order_receive(request, pk):
    """Receive items from purchase order and update inventory."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:purchase_orders")

    try:
        order = PurchaseOrder.objects.prefetch_related("items__inventory_item").get(pk=pk)

        if order.status not in [PurchaseOrder.Status.ORDERED, PurchaseOrder.Status.PARTIAL]:
            messages.error(request, "Cannot receive items for this order.")
            return redirect("dashboard:purchase_order_detail", pk=pk)

        # Process received quantities
        all_received = True
        for po_item in order.items.all():
            received_key = f"received_{po_item.pk}"
            received_qty = float(request.POST.get(received_key, 0))

            if received_qty > 0:
                # Update PO item
                po_item.quantity_received += received_qty
                po_item.save()

                # Update inventory
                inv_item = po_item.inventory_item
                stock_before = inv_item.current_stock
                inv_item.current_stock += received_qty
                inv_item.last_purchase_price = po_item.unit_price
                inv_item.save()

                # Create stock movement
                StockMovement.objects.create(
                    item=inv_item,
                    movement_type=StockMovement.MovementType.PURCHASE,
                    quantity=received_qty,
                    unit_cost=po_item.unit_price,
                    stock_before=stock_before,
                    stock_after=inv_item.current_stock,
                    purchase_order=order,
                    reference_number=order.order_number,
                    created_by=request.user,
                )

                # Resolve any low stock alerts
                StockAlert.objects.filter(
                    item=inv_item,
                    is_resolved=False,
                    alert_type__in=[StockAlert.AlertType.LOW_STOCK, StockAlert.AlertType.OUT_OF_STOCK]
                ).update(is_resolved=True, resolved_at=timezone.now(), resolved_by=request.user)

            if po_item.quantity_received < po_item.quantity_ordered:
                all_received = False

        # Update order status
        if all_received:
            order.status = PurchaseOrder.Status.RECEIVED
            order.received_date = timezone.now().date()
        else:
            order.status = PurchaseOrder.Status.PARTIAL

        order.save()
        messages.success(request, "Items received and inventory updated.")

    except PurchaseOrder.DoesNotExist:
        messages.error(request, "Purchase order not found.")

    return redirect("dashboard:purchase_order_detail", pk=pk)


# ============================================================================
# Stock Alerts
# ============================================================================


@login_required
def stock_alerts(request):
    """View stock alerts."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    status_filter = request.GET.get("status", "active")
    alerts = StockAlert.objects.select_related("item", "resolved_by").order_by("-created_at")

    if status_filter == "active":
        alerts = alerts.filter(is_resolved=False)
    elif status_filter == "resolved":
        alerts = alerts.filter(is_resolved=True)

    context = {
        "page_title": "Stock Alerts",
        "alerts": alerts[:100],
        "current_status": status_filter,
    }
    return render(request, "dashboard/inventory/alerts.html", context)


@login_required
@require_http_methods(["POST"])
def stock_alert_resolve(request, pk):
    """Resolve a stock alert."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:stock_alerts")

    try:
        alert = StockAlert.objects.get(pk=pk)
        alert.resolve(user=request.user)
        messages.success(request, "Alert resolved.")
    except StockAlert.DoesNotExist:
        messages.error(request, "Alert not found.")

    return redirect("dashboard:stock_alerts")


# ============================================================================
# Stock Movements History
# ============================================================================


@login_required
def stock_movements(request):
    """View stock movement history."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    type_filter = request.GET.get("type", "")
    item_filter = request.GET.get("item", "")

    movements = StockMovement.objects.select_related(
        "item", "created_by", "purchase_order"
    ).order_by("-created_at")

    if type_filter:
        movements = movements.filter(movement_type=type_filter)
    if item_filter:
        movements = movements.filter(item_id=item_filter)

    items = InventoryItem.objects.filter(is_active=True).order_by("name")

    context = {
        "page_title": "Stock Movements",
        "movements": movements[:200],
        "movement_types": StockMovement.MovementType.choices,
        "items": items,
        "current_type": type_filter,
        "current_item": item_filter,
    }
    return render(request, "dashboard/inventory/movements.html", context)


# ============================================================================
# Payment Gateway Integration (Razorpay)
# ============================================================================


@login_required
@require_http_methods(["POST"])
def create_razorpay_order(request, pk):
    """Create a Razorpay order for QR payment."""
    import json
    from django.http import JsonResponse
    from apps.payments.models import PaymentSettings, RazorpayOrder

    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    amount = order.balance_due
    if amount <= 0:
        return JsonResponse({"error": "No balance due"}, status=400)

    # Get payment settings
    settings = PaymentSettings.load()
    client = settings.get_razorpay_client()

    if not client:
        return JsonResponse({
            "error": "Payment gateway not configured. Please add Razorpay API keys in settings."
        }, status=400)

    try:
        # Create Razorpay order
        amount_paise = int(float(amount) * 100)

        razorpay_order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"order_{order.order_number}",
            "notes": {
                "order_id": str(order.pk),
                "order_number": order.order_number,
            }
        })

        # Save to our database
        rzp_order = RazorpayOrder.objects.create(
            order=order,
            razorpay_order_id=razorpay_order["id"],
            amount=amount_paise,
            currency="INR",
        )

        # Generate UPI QR code URL
        # Razorpay provides QR code via their API
        qr_code_url = f"https://api.razorpay.com/v1/payments/qr_codes/{razorpay_order['id']}"

        return JsonResponse({
            "success": True,
            "razorpay_order_id": razorpay_order["id"],
            "razorpay_key_id": settings.razorpay_key_id,
            "amount": amount_paise,
            "amount_display": str(amount),
            "currency": "INR",
            "order_number": order.order_number,
            "customer_name": order.customer_name or "Customer",
        })

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def verify_razorpay_payment(request, pk):
    """Verify Razorpay payment and record it."""
    import json
    import hmac
    import hashlib
    from django.http import JsonResponse
    from apps.payments.models import PaymentSettings, RazorpayOrder

    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    data = json.loads(request.body)
    razorpay_order_id = data.get("razorpay_order_id")
    razorpay_payment_id = data.get("razorpay_payment_id")
    razorpay_signature = data.get("razorpay_signature")

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return JsonResponse({"error": "Missing payment details"}, status=400)

    settings = PaymentSettings.load()

    # Verify signature
    message = f"{razorpay_order_id}|{razorpay_payment_id}"
    expected_signature = hmac.new(
        settings.razorpay_key_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()

    if expected_signature != razorpay_signature:
        return JsonResponse({"error": "Invalid payment signature"}, status=400)

    # Update Razorpay order
    try:
        rzp_order = RazorpayOrder.objects.get(razorpay_order_id=razorpay_order_id)
        rzp_order.razorpay_payment_id = razorpay_payment_id
        rzp_order.razorpay_signature = razorpay_signature
        rzp_order.status = RazorpayOrder.Status.PAID
        rzp_order.save()

        # Record payment in our system
        amount = rzp_order.amount / 100  # Convert paise to rupees

        payment = Payment.objects.create(
            order=order,
            amount=amount,
            method=Payment.Method.UPI,
            status=Payment.Status.COMPLETED,
            transaction_id=razorpay_payment_id,
            reference_number=razorpay_order_id,
            processed_by=request.user,
        )

        # Check if fully paid and update order
        if order.is_paid:
            if order.status in [Order.Status.SERVED, Order.Status.READY]:
                order.update_status(Order.Status.COMPLETED)

            # Auto-release table
            if order.table and order.order_type == Order.OrderType.DINE_IN:
                other_orders = Order.objects.filter(
                    table=order.table,
                    status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
                ).exclude(pk=pk).exists()

                if not other_orders:
                    order.table.status = Table.Status.VACANT
                    order.table.save(update_fields=["status", "updated_at"])

        return JsonResponse({
            "success": True,
            "message": "Payment recorded successfully",
            "is_paid": order.is_paid,
            "balance_due": str(order.balance_due),
        })

    except RazorpayOrder.DoesNotExist:
        return JsonResponse({"error": "Razorpay order not found"}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def check_payment_status(request, pk):
    """Check payment status for an order."""
    from django.http import JsonResponse
    from apps.payments.models import PaymentSettings, RazorpayOrder

    try:
        order = Order.objects.get(pk=pk)
    except Order.DoesNotExist:
        return JsonResponse({"error": "Order not found"}, status=404)

    razorpay_order_id = request.GET.get("razorpay_order_id")

    if razorpay_order_id:
        settings = PaymentSettings.load()
        client = settings.get_razorpay_client()

        if client:
            try:
                # Fetch payment status from Razorpay
                payments = client.order.payments(razorpay_order_id)

                for payment in payments.get("items", []):
                    if payment.get("status") == "captured":
                        # Payment successful - record it
                        try:
                            rzp_order = RazorpayOrder.objects.get(razorpay_order_id=razorpay_order_id)
                            if rzp_order.status != RazorpayOrder.Status.PAID:
                                rzp_order.razorpay_payment_id = payment["id"]
                                rzp_order.status = RazorpayOrder.Status.PAID
                                rzp_order.save()

                                # Record payment
                                amount = rzp_order.amount / 100
                                Payment.objects.create(
                                    order=order,
                                    amount=amount,
                                    method=Payment.Method.UPI,
                                    status=Payment.Status.COMPLETED,
                                    transaction_id=payment["id"],
                                    reference_number=razorpay_order_id,
                                    processed_by=request.user,
                                )

                                # Update order status
                                if order.is_paid:
                                    if order.status in [Order.Status.SERVED, Order.Status.READY]:
                                        order.update_status(Order.Status.COMPLETED)

                                    if order.table and order.order_type == Order.OrderType.DINE_IN:
                                        other_orders = Order.objects.filter(
                                            table=order.table,
                                            status__in=[Order.Status.PENDING, Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY, Order.Status.SERVED]
                                        ).exclude(pk=pk).exists()

                                        if not other_orders:
                                            order.table.status = Table.Status.VACANT
                                            order.table.save(update_fields=["status", "updated_at"])

                                return JsonResponse({
                                    "status": "paid",
                                    "is_paid": order.is_paid,
                                    "balance_due": str(order.balance_due),
                                })
                        except RazorpayOrder.DoesNotExist:
                            pass

                return JsonResponse({
                    "status": "pending",
                    "is_paid": order.is_paid,
                    "balance_due": str(order.balance_due),
                })

            except Exception as e:
                return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({
        "status": "unknown",
        "is_paid": order.is_paid,
        "balance_due": str(order.balance_due),
    })


@login_required
def payment_settings_view(request):
    """Payment gateway settings (Super Admin only)."""
    from apps.payments.models import PaymentSettings

    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "Access denied.")
        return redirect("dashboard:home")

    settings = PaymentSettings.load()

    if request.method == "POST":
        settings.gateway = request.POST.get("gateway", "razorpay")
        settings.razorpay_key_id = request.POST.get("razorpay_key_id", "")
        settings.razorpay_key_secret = request.POST.get("razorpay_key_secret", "")
        settings.razorpay_webhook_secret = request.POST.get("razorpay_webhook_secret", "")
        settings.upi_id = request.POST.get("upi_id", "")
        settings.upi_merchant_name = request.POST.get("upi_merchant_name", "")
        settings.is_live_mode = request.POST.get("is_live_mode") == "on"
        settings.save()

        messages.success(request, "Payment settings saved successfully!")
        return redirect("dashboard:payment_settings")

    context = {
        "page_title": "Payment Settings",
        "settings": settings,
    }
    return render(request, "dashboard/settings/payment.html", context)


# ============================================================================
# Expense Management (Super Admin only)
# ============================================================================


from apps.finance.models import (
    ExpenseCategory, Expense, CashDrawer, CashierShift, CashDrawerTransaction
)


@login_required
def expense_dashboard(request):
    """Expense management dashboard."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    today = timezone.now().date()
    month_start = today.replace(day=1)

    # Get stats
    expenses = Expense.objects.filter(status=Expense.Status.PAID)
    today_expenses = expenses.filter(date=today)
    month_expenses = expenses.filter(date__gte=month_start)

    # Category breakdown for this month
    category_breakdown = month_expenses.values(
        "category__name"
    ).annotate(
        total=Sum("amount")
    ).order_by("-total")[:5]

    # Recent expenses
    recent_expenses = Expense.objects.select_related("category", "created_by").order_by("-date", "-created_at")[:10]

    context = {
        "page_title": "Expenses",
        "stats": {
            "today_total": today_expenses.aggregate(total=Sum("amount"))["total"] or 0,
            "today_count": today_expenses.count(),
            "month_total": month_expenses.aggregate(total=Sum("amount"))["total"] or 0,
            "month_count": month_expenses.count(),
        },
        "category_breakdown": category_breakdown,
        "recent_expenses": recent_expenses,
        "categories": ExpenseCategory.objects.filter(is_active=True),
    }
    return render(request, "dashboard/expenses/dashboard.html", context)


@login_required
def expense_list(request):
    """List all expenses with filters."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    category_filter = request.GET.get("category", "")
    status_filter = request.GET.get("status", "")
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    expenses = Expense.objects.select_related("category", "created_by").order_by("-date", "-created_at")

    if category_filter:
        expenses = expenses.filter(category_id=category_filter)
    if status_filter:
        expenses = expenses.filter(status=status_filter)
    if date_from:
        expenses = expenses.filter(date__gte=date_from)
    if date_to:
        expenses = expenses.filter(date__lte=date_to)

    context = {
        "page_title": "Expenses",
        "expenses": expenses[:100],
        "categories": ExpenseCategory.objects.filter(is_active=True),
        "status_choices": Expense.Status.choices,
        "payment_methods": Expense.PaymentMethod.choices,
        "current_category": category_filter,
        "current_status": status_filter,
        "date_from": date_from,
        "date_to": date_to,
    }
    return render(request, "dashboard/expenses/list.html", context)


@login_required
def expense_create(request):
    """Create a new expense."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:expenses")

    if request.method == "POST":
        category_id = request.POST.get("category")
        date = request.POST.get("date")
        amount = request.POST.get("amount")
        description = request.POST.get("description", "")
        payment_method = request.POST.get("payment_method", Expense.PaymentMethod.CASH)
        vendor_name = request.POST.get("vendor_name", "")
        reference_number = request.POST.get("reference_number", "")
        notes = request.POST.get("notes", "")

        if not all([category_id, date, amount]):
            messages.error(request, "Category, date, and amount are required.")
        else:
            try:
                expense = Expense.objects.create(
                    category_id=category_id,
                    date=date,
                    amount=float(amount),
                    description=description,
                    payment_method=payment_method,
                    vendor_name=vendor_name,
                    reference_number=reference_number,
                    notes=notes,
                    status=Expense.Status.PAID,
                    created_by=request.user,
                )

                # If cash expense, create cash drawer transaction
                if payment_method == Expense.PaymentMethod.CASH:
                    today = timezone.now().date()
                    cash_drawer, _ = CashDrawer.objects.get_or_create(
                        date=today,
                        defaults={"opening_balance": 0, "opened_at": timezone.now()}
                    )
                    transaction = CashDrawerTransaction.objects.create(
                        cash_drawer=cash_drawer,
                        transaction_type=CashDrawerTransaction.TransactionType.EXPENSE,
                        amount=-abs(float(amount)),
                        description=f"Expense: {expense.expense_number} - {description[:50]}",
                        reference=expense.expense_number,
                        created_by=request.user,
                    )
                    expense.cash_drawer_transaction = transaction
                    expense.save()

                # Handle receipt upload
                if "receipt" in request.FILES:
                    expense.receipt = request.FILES["receipt"]
                    expense.save()

                messages.success(request, f"Expense {expense.expense_number} created successfully.")
                return redirect("dashboard:expense_list")
            except Exception as e:
                messages.error(request, f"Error creating expense: {str(e)}")

    categories = ExpenseCategory.objects.filter(is_active=True)
    context = {
        "page_title": "Add Expense",
        "categories": categories,
        "today": timezone.now().date(),
    }
    return render(request, "dashboard/expenses/form.html", context)


@login_required
def expense_detail(request, pk):
    """View expense details."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:expenses")

    try:
        expense = Expense.objects.select_related("category", "created_by", "approved_by").get(pk=pk)
    except Expense.DoesNotExist:
        messages.error(request, "Expense not found.")
        return redirect("dashboard:expense_list")

    context = {
        "page_title": f"Expense {expense.expense_number}",
        "expense": expense,
        "categories": ExpenseCategory.objects.filter(is_active=True),
        "payment_methods": Expense.PaymentMethod.choices,
    }
    return render(request, "dashboard/expenses/detail.html", context)


@login_required
def expense_edit(request, pk):
    """Edit an expense."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:expenses")

    try:
        expense = Expense.objects.get(pk=pk)
    except Expense.DoesNotExist:
        messages.error(request, "Expense not found.")
        return redirect("dashboard:expense_list")

    if request.method == "POST":
        expense.category_id = request.POST.get("category", expense.category_id)
        expense.date = request.POST.get("date", expense.date)
        expense.amount = float(request.POST.get("amount", expense.amount))
        expense.description = request.POST.get("description", expense.description)
        expense.payment_method = request.POST.get("payment_method", expense.payment_method)
        expense.vendor_name = request.POST.get("vendor_name", expense.vendor_name)
        expense.reference_number = request.POST.get("reference_number", expense.reference_number)
        expense.notes = request.POST.get("notes", expense.notes)

        # Handle status update
        new_status = request.POST.get("status")
        if new_status:
            expense.status = new_status
            if new_status == Expense.Status.APPROVED:
                expense.approved_by = request.user

        if "receipt" in request.FILES:
            expense.receipt = request.FILES["receipt"]

        expense.save()
        messages.success(request, f"Expense {expense.expense_number} updated.")
        return redirect("dashboard:expense_detail", pk=pk)

    categories = ExpenseCategory.objects.filter(is_active=True)
    context = {
        "page_title": f"Edit Expense {expense.expense_number}",
        "expense": expense,
        "categories": categories,
    }
    return render(request, "dashboard/expenses/form.html", context)


@login_required
@require_http_methods(["POST"])
def expense_delete(request, pk):
    """Delete an expense."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:expenses")

    try:
        expense = Expense.objects.get(pk=pk)
        expense_number = expense.expense_number
        expense.delete()
        messages.success(request, f"Expense {expense_number} deleted.")
    except Expense.DoesNotExist:
        messages.error(request, "Expense not found.")

    return redirect("dashboard:expense_list")


@login_required
def expense_categories(request):
    """Manage expense categories."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:expenses")

    categories = ExpenseCategory.objects.annotate(
        expense_count=Count("expenses"),
        total_amount=Sum("expenses__amount")
    ).order_by("display_order", "name")

    context = {
        "page_title": "Expense Categories",
        "categories": categories,
    }
    return render(request, "dashboard/expenses/categories.html", context)


@login_required
def expense_category_create(request):
    """Create expense category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:expense_categories")

    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "")

        if not name:
            messages.error(request, "Category name is required.")
        else:
            ExpenseCategory.objects.create(
                name=name,
                description=description,
                category_type=ExpenseCategory.CategoryType.CUSTOM,
                is_default=False,
            )
            messages.success(request, f"Category '{name}' created.")

    return redirect("dashboard:expense_categories")


@login_required
def expense_category_edit(request, pk):
    """Edit expense category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:expense_categories")

    try:
        category = ExpenseCategory.objects.get(pk=pk)
    except ExpenseCategory.DoesNotExist:
        messages.error(request, "Category not found.")
        return redirect("dashboard:expense_categories")

    if request.method == "POST":
        category.name = request.POST.get("name", category.name).strip()
        category.description = request.POST.get("description", category.description)
        category.is_active = request.POST.get("is_active") == "on"
        category.save()
        messages.success(request, f"Category '{category.name}' updated.")

    return redirect("dashboard:expense_categories")


@login_required
@require_http_methods(["POST"])
def expense_category_delete(request, pk):
    """Delete expense category."""
    if request.user.role != User.Role.SUPER_ADMIN:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:expense_categories")

    try:
        category = ExpenseCategory.objects.get(pk=pk)
        if category.is_default:
            messages.error(request, "Cannot delete default category.")
        elif category.expenses.exists():
            messages.error(request, f"Cannot delete category with expenses. Move expenses first.")
        else:
            name = category.name
            category.delete()
            messages.success(request, f"Category '{name}' deleted.")
    except ExpenseCategory.DoesNotExist:
        messages.error(request, "Category not found.")

    return redirect("dashboard:expense_categories")


# ============================================================================
# Cash Drawer Management (Admin + Cashier)
# ============================================================================


@login_required
def cash_drawer_dashboard(request):
    """Cash drawer dashboard - current status."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    today = timezone.now().date()

    # Get or display today's cash drawer
    cash_drawer = CashDrawer.objects.filter(date=today).first()

    # Get current user's active shift
    active_shift = None
    if request.user.role == User.Role.STAFF_CASHIER and cash_drawer:
        active_shift = CashierShift.objects.filter(
            cashier=request.user,
            cash_drawer=cash_drawer,
            is_closed=False,
        ).first()

    # Recent transactions
    recent_transactions = []
    if cash_drawer:
        recent_transactions = cash_drawer.transactions.select_related("created_by").order_by("-created_at")[:20]

    context = {
        "page_title": "Cash Drawer",
        "cash_drawer": cash_drawer,
        "active_shift": active_shift,
        "recent_transactions": recent_transactions,
        "today": today,
    }
    return render(request, "dashboard/cash_drawer/dashboard.html", context)


@login_required
def cash_drawer_open(request):
    """Open daily cash drawer."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:cash_drawer")

    today = timezone.now().date()

    # Check if already open
    if CashDrawer.objects.filter(date=today).exists():
        messages.warning(request, "Cash drawer for today is already open.")
        return redirect("dashboard:cash_drawer")

    if request.method == "POST":
        opening_balance = float(request.POST.get("opening_balance", 0))

        cash_drawer = CashDrawer.objects.create(
            date=today,
            opening_balance=opening_balance,
            opened_by=request.user,
            opened_at=timezone.now(),
        )
        cash_drawer.calculate_expected()
        cash_drawer.save()

        messages.success(request, f"Cash drawer opened with ₹{opening_balance} opening balance.")
        return redirect("dashboard:cash_drawer")

    # Get previous day's closing balance as suggestion
    previous_drawer = CashDrawer.objects.filter(is_closed=True).order_by("-date").first()
    suggested_balance = previous_drawer.actual_balance if previous_drawer else 0

    context = {
        "page_title": "Open Cash Drawer",
        "suggested_balance": suggested_balance,
        "today": today,
    }
    return render(request, "dashboard/cash_drawer/open.html", context)


@login_required
def cash_drawer_close(request):
    """Close daily cash drawer."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:cash_drawer")

    today = timezone.now().date()

    try:
        cash_drawer = CashDrawer.objects.get(date=today)
    except CashDrawer.DoesNotExist:
        messages.error(request, "No cash drawer open for today.")
        return redirect("dashboard:cash_drawer")

    if cash_drawer.is_closed:
        messages.warning(request, "Cash drawer is already closed.")
        return redirect("dashboard:cash_drawer")

    # Check for unclosed shifts
    unclosed_shifts = cash_drawer.shifts.filter(is_closed=False)
    if unclosed_shifts.exists():
        messages.warning(request, f"There are {unclosed_shifts.count()} unclosed shifts. Close all shifts first.")

    if request.method == "POST":
        actual_balance = float(request.POST.get("actual_balance", 0))
        notes = request.POST.get("notes", "")

        cash_drawer.actual_balance = actual_balance
        cash_drawer.calculate_variance()
        cash_drawer.notes = notes
        cash_drawer.closed_by = request.user
        cash_drawer.closed_at = timezone.now()
        cash_drawer.is_closed = True
        cash_drawer.save()

        variance = cash_drawer.variance
        if variance < 0:
            messages.warning(request, f"Cash drawer closed. Shortage of ₹{abs(variance)}")
        elif variance > 0:
            messages.info(request, f"Cash drawer closed. Overage of ₹{variance}")
        else:
            messages.success(request, "Cash drawer closed. Cash matches exactly!")

        return redirect("dashboard:cash_drawer")

    context = {
        "page_title": "Close Cash Drawer",
        "cash_drawer": cash_drawer,
    }
    return render(request, "dashboard/cash_drawer/close.html", context)


@login_required
def cash_drawer_history(request):
    """View cash drawer history."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    drawers = CashDrawer.objects.order_by("-date")[:30]

    context = {
        "page_title": "Cash Drawer History",
        "drawers": drawers,
    }
    return render(request, "dashboard/cash_drawer/history.html", context)


@login_required
def cash_drawer_detail(request, pk):
    """View cash drawer details for a specific day."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    try:
        cash_drawer = CashDrawer.objects.prefetch_related("transactions", "shifts").get(pk=pk)
    except CashDrawer.DoesNotExist:
        messages.error(request, "Cash drawer not found.")
        return redirect("dashboard:cash_drawer_history")

    transactions = cash_drawer.transactions.select_related("created_by", "cashier_shift").order_by("-created_at")
    shifts = cash_drawer.shifts.select_related("cashier").order_by("-shift_start")

    context = {
        "page_title": f"Cash Drawer - {cash_drawer.date}",
        "cash_drawer": cash_drawer,
        "transactions": transactions,
        "shifts": shifts,
    }
    return render(request, "dashboard/cash_drawer/detail.html", context)


@login_required
def cash_in_out(request):
    """Record cash in or out."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:cash_drawer")

    today = timezone.now().date()

    try:
        cash_drawer = CashDrawer.objects.get(date=today, is_closed=False)
    except CashDrawer.DoesNotExist:
        messages.error(request, "No open cash drawer for today.")
        return redirect("dashboard:cash_drawer")

    if request.method == "POST":
        transaction_type = request.POST.get("transaction_type")
        amount = float(request.POST.get("amount", 0))
        description = request.POST.get("description", "")
        reference = request.POST.get("reference", "")

        if amount <= 0:
            messages.error(request, "Amount must be positive.")
        elif transaction_type not in ["cash_in", "cash_out"]:
            messages.error(request, "Invalid transaction type.")
        else:
            # Find active shift
            active_shift = CashierShift.objects.filter(
                cashier=request.user,
                cash_drawer=cash_drawer,
                is_closed=False,
            ).first()

            # Adjust amount based on type
            if transaction_type == "cash_out":
                amount = -abs(amount)
                trans_type = CashDrawerTransaction.TransactionType.CASH_OUT
            else:
                amount = abs(amount)
                trans_type = CashDrawerTransaction.TransactionType.CASH_IN

            CashDrawerTransaction.objects.create(
                cash_drawer=cash_drawer,
                cashier_shift=active_shift,
                transaction_type=trans_type,
                amount=amount,
                description=description,
                reference=reference,
                created_by=request.user,
            )

            messages.success(request, f"Cash {'in' if amount > 0 else 'out'} of ₹{abs(amount)} recorded.")

    return redirect("dashboard:cash_drawer")


# ============================================================================
# Cashier Shifts
# ============================================================================


@login_required
def shift_start(request):
    """Start a cashier shift."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    today = timezone.now().date()

    # Get or create today's cash drawer
    cash_drawer = CashDrawer.objects.filter(date=today).first()
    if not cash_drawer:
        messages.error(request, "Please open the cash drawer first.")
        return redirect("dashboard:cash_drawer_open")

    # Check for existing active shift
    existing_shift = CashierShift.objects.filter(
        cashier=request.user,
        cash_drawer=cash_drawer,
        is_closed=False,
    ).first()

    if existing_shift:
        messages.warning(request, "You already have an active shift.")
        return redirect("dashboard:cash_drawer")

    if request.method == "POST":
        opening_balance = float(request.POST.get("opening_balance", 0))

        shift = CashierShift.objects.create(
            cash_drawer=cash_drawer,
            cashier=request.user,
            shift_start=timezone.now(),
            opening_balance=opening_balance,
        )
        shift.calculate_expected()
        shift.save()

        messages.success(request, f"Shift started with ₹{opening_balance} opening balance.")
        return redirect("dashboard:cash_drawer")

    context = {
        "page_title": "Start Shift",
        "cash_drawer": cash_drawer,
    }
    return render(request, "dashboard/shifts/start.html", context)


@login_required
def shift_end(request):
    """End current shift."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    today = timezone.now().date()
    cash_drawer = CashDrawer.objects.filter(date=today).first()

    if not cash_drawer:
        messages.error(request, "No cash drawer for today.")
        return redirect("dashboard:cash_drawer")

    # Find active shift
    shift = CashierShift.objects.filter(
        cashier=request.user,
        cash_drawer=cash_drawer,
        is_closed=False,
    ).first()

    if not shift:
        messages.error(request, "No active shift found.")
        return redirect("dashboard:cash_drawer")

    if request.method == "POST":
        actual_balance = float(request.POST.get("actual_balance", 0))
        notes = request.POST.get("notes", "")

        shift.actual_balance = actual_balance
        shift.shift_end = timezone.now()
        shift.calculate_variance()
        shift.notes = notes
        shift.is_closed = True
        shift.save()

        variance = shift.variance
        if variance < 0:
            messages.warning(request, f"Shift ended. Shortage of ₹{abs(variance)}")
        elif variance > 0:
            messages.info(request, f"Shift ended. Overage of ₹{variance}")
        else:
            messages.success(request, "Shift ended. Cash matches exactly!")

        return redirect("dashboard:cash_drawer")

    context = {
        "page_title": "End Shift",
        "shift": shift,
    }
    return render(request, "dashboard/shifts/end.html", context)


@login_required
def shift_history(request):
    """View shift history."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission.")
        return redirect("dashboard:home")

    if request.user.role == User.Role.SUPER_ADMIN:
        shifts = CashierShift.objects.select_related("cashier", "cash_drawer").order_by("-shift_start")[:50]
    else:
        shifts = CashierShift.objects.filter(cashier=request.user).select_related("cash_drawer").order_by("-shift_start")[:50]

    context = {
        "page_title": "Shift History",
        "shifts": shifts,
    }
    return render(request, "dashboard/shifts/history.html", context)


# ============================================================================
# Cashier Reports (Sales Only - for Cashiers)
# ============================================================================


@login_required
def cashier_reports(request):
    """Sales-only reports for cashiers."""
    if request.user.role not in [User.Role.SUPER_ADMIN, User.Role.OUTLET_MANAGER, User.Role.STAFF_CASHIER]:
        messages.error(request, "You do not have permission to access this page.")
        return redirect("dashboard:home")

    today = timezone.now().date()
    month_start = today.replace(day=1)

    # Filter orders (completed and served)
    completed_statuses = [Order.Status.COMPLETED, Order.Status.SERVED]

    # Today's stats
    today_orders = Order.objects.filter(
        created_at__date=today,
        status__in=completed_statuses,
    )
    today_revenue = today_orders.aggregate(total=Sum("total_amount"))["total"] or 0
    today_count = today_orders.count()

    # Month's stats
    month_orders = Order.objects.filter(
        created_at__date__gte=month_start,
        status__in=completed_statuses,
    )
    month_revenue = month_orders.aggregate(total=Sum("total_amount"))["total"] or 0
    month_count = month_orders.count()

    # Payment method breakdown for today
    payment_stats = Payment.objects.filter(
        created_at__date=today,
        status=Payment.Status.COMPLETED,
    ).values("method").annotate(
        count=Count("id"),
        total=Sum("amount"),
    )

    # Order type breakdown for today
    order_types = today_orders.values("order_type").annotate(
        count=Count("id"),
        total=Sum("total_amount"),
    )

    context = {
        "page_title": "Sales Report",
        "today": today,
        "stats": {
            "today_revenue": today_revenue,
            "today_count": today_count,
            "month_revenue": month_revenue,
            "month_count": month_count,
            "avg_order": today_revenue / today_count if today_count > 0 else 0,
        },
        "payment_stats": payment_stats,
        "order_types": order_types,
    }
    return render(request, "dashboard/cashier_reports/index.html", context)


# ============================================================================
# Outlet Management (Super Admin only)
# ============================================================================


@login_required
def outlet_list(request):
    """List all outlets with usage stats."""
    from django.conf import settings as django_settings
    from apps.core.models import Outlet

    if request.user.role != "super_admin":
        messages.error(request, "You don't have permission to manage outlets.")
        return redirect("dashboard:home")

    outlets = Outlet.objects.all().order_by("name")
    max_outlets = getattr(django_settings, "MAX_OUTLETS", 1)

    context = {
        "page_title": "Outlets",
        "outlets": outlets,
        "plan_info": {
            "name": getattr(django_settings, "PLAN_NAME", "Basic"),
            "max_outlets": max_outlets,
            "max_outlets_display": "Unlimited" if max_outlets == 0 else max_outlets,
            "outlets_used": outlets.count(),
            "can_create": Outlet.can_create_outlet(),
        },
    }
    return render(request, "dashboard/outlets/list.html", context)


@login_required
def outlet_create(request):
    """Create a new outlet."""
    from django.conf import settings as django_settings
    from apps.core.models import Outlet

    if request.user.role != "super_admin":
        messages.error(request, "You don't have permission to create outlets.")
        return redirect("dashboard:home")

    # Check if can create more outlets
    if not Outlet.can_create_outlet():
        max_outlets = getattr(django_settings, "MAX_OUTLETS", 1)
        messages.error(
            request,
            f"Cannot create more outlets. Your {getattr(django_settings, 'PLAN_NAME', 'Basic')} plan "
            f"allows maximum {max_outlets} outlet(s). Contact your vendor to upgrade."
        )
        return redirect("dashboard:outlets")

    if request.method == "POST":
        try:
            from decimal import Decimal
            outlet = Outlet(
                # Basic Info
                name=request.POST.get("name"),
                code=request.POST.get("code", "").upper(),
                # Location
                address=request.POST.get("address", ""),
                city=request.POST.get("city", ""),
                state=request.POST.get("state", ""),
                country=request.POST.get("country", "India"),
                postal_code=request.POST.get("postal_code", ""),
                # Contact
                phone=request.POST.get("phone", ""),
                email=request.POST.get("email", ""),
                # Currency
                currency_code=request.POST.get("currency_code", "INR"),
                currency_symbol=request.POST.get("currency_symbol", "₹"),
                currency_position=request.POST.get("currency_position", "before"),
                # Tax Settings
                tax_enabled=request.POST.get("tax_enabled") == "on",
                cgst_rate=Decimal(request.POST.get("cgst_rate", "2.50") or "0"),
                sgst_rate=Decimal(request.POST.get("sgst_rate", "2.50") or "0"),
                service_charge_enabled=request.POST.get("service_charge_enabled") == "on",
                service_charge_rate=Decimal(request.POST.get("service_charge_rate", "0") or "0"),
                tax_inclusive_pricing=request.POST.get("tax_inclusive_pricing") == "on",
                # Order Settings
                order_prefix=request.POST.get("order_prefix", "ORD"),
                default_prep_time=int(request.POST.get("default_prep_time", "10") or "10"),
                auto_accept_orders=request.POST.get("auto_accept_orders") == "on",
                allow_qr_ordering=request.POST.get("allow_qr_ordering") == "on",
                # Receipt Branding
                receipt_header=request.POST.get("receipt_header", ""),
                receipt_footer=request.POST.get("receipt_footer", ""),
            )
            outlet.save()
            messages.success(request, f"Outlet '{outlet.name}' created successfully!")
            return redirect("dashboard:outlets")
        except Exception as e:
            messages.error(request, str(e))

    context = {
        "page_title": "Create Outlet",
    }
    return render(request, "dashboard/outlets/form.html", context)


@login_required
def outlet_edit(request, pk):
    """Edit an existing outlet."""
    from apps.core.models import Outlet

    if request.user.role != "super_admin":
        messages.error(request, "You don't have permission to edit outlets.")
        return redirect("dashboard:home")

    try:
        outlet = Outlet.objects.get(pk=pk)
    except Outlet.DoesNotExist:
        messages.error(request, "Outlet not found.")
        return redirect("dashboard:outlets")

    if request.method == "POST":
        from decimal import Decimal

        # Basic Info
        outlet.name = request.POST.get("name", outlet.name)
        outlet.code = request.POST.get("code", outlet.code).upper()
        # Location
        outlet.address = request.POST.get("address", outlet.address)
        outlet.city = request.POST.get("city", outlet.city)
        outlet.state = request.POST.get("state", outlet.state)
        outlet.country = request.POST.get("country", outlet.country)
        outlet.postal_code = request.POST.get("postal_code", outlet.postal_code)
        # Contact
        outlet.phone = request.POST.get("phone", outlet.phone)
        outlet.email = request.POST.get("email", outlet.email)
        # Currency
        outlet.currency_code = request.POST.get("currency_code", outlet.currency_code)
        outlet.currency_symbol = request.POST.get("currency_symbol", outlet.currency_symbol)
        outlet.currency_position = request.POST.get("currency_position", outlet.currency_position)
        # Tax Settings
        outlet.tax_enabled = request.POST.get("tax_enabled") == "on"
        outlet.cgst_rate = Decimal(request.POST.get("cgst_rate", "2.50") or "0")
        outlet.sgst_rate = Decimal(request.POST.get("sgst_rate", "2.50") or "0")
        outlet.service_charge_enabled = request.POST.get("service_charge_enabled") == "on"
        outlet.service_charge_rate = Decimal(request.POST.get("service_charge_rate", "0") or "0")
        outlet.tax_inclusive_pricing = request.POST.get("tax_inclusive_pricing") == "on"
        # Order Settings
        outlet.order_prefix = request.POST.get("order_prefix", outlet.order_prefix)
        outlet.default_prep_time = int(request.POST.get("default_prep_time", "10") or "10")
        outlet.auto_accept_orders = request.POST.get("auto_accept_orders") == "on"
        outlet.allow_qr_ordering = request.POST.get("allow_qr_ordering") == "on"
        # Receipt Branding
        outlet.receipt_header = request.POST.get("receipt_header", "")
        outlet.receipt_footer = request.POST.get("receipt_footer", "")
        # Status
        outlet.is_active = request.POST.get("is_active") == "on"

        try:
            outlet.save()
            messages.success(request, f"Outlet '{outlet.name}' updated successfully!")
            return redirect("dashboard:outlets")
        except Exception as e:
            messages.error(request, str(e))

    context = {
        "page_title": f"Edit Outlet: {outlet.name}",
        "outlet": outlet,
    }
    return render(request, "dashboard/outlets/form.html", context)


@login_required
def outlet_delete(request, pk):
    """Delete an outlet."""
    from apps.core.models import Outlet

    if request.user.role != "super_admin":
        messages.error(request, "You don't have permission to delete outlets.")
        return redirect("dashboard:home")

    try:
        outlet = Outlet.objects.get(pk=pk)
        name = outlet.name
        outlet.delete()
        messages.success(request, f"Outlet '{name}' deleted successfully!")
    except Outlet.DoesNotExist:
        messages.error(request, "Outlet not found.")

    return redirect("dashboard:outlets")
