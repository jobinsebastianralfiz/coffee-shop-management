"""
URL configuration for the dashboard app.
"""

from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    # Authentication
    path("login/", views.login_view, name="login"),
    path("pin-login/", views.pin_login_view, name="pin_login"),
    path("logout/", views.logout_view, name="logout"),

    # Dashboard Home
    path("", views.dashboard_home, name="home"),

    # Profile
    path("profile/", views.profile_view, name="profile"),
    path("profile/change-password/", views.change_password_view, name="change_password"),

    # Menu Management
    path("menu/", views.menu_list, name="menu"),
    path("menu/category/<int:pk>/", views.category_detail, name="category_detail"),
    path("menu/category/create/", views.category_create, name="category_create"),
    path("menu/category/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("menu/category/<int:pk>/delete/", views.category_delete, name="category_delete"),
    path("menu/item/<int:pk>/", views.menu_item_detail, name="menu_item_detail"),
    path("menu/item/create/", views.menu_item_create, name="menu_item_create"),
    path("menu/item/<int:pk>/edit/", views.menu_item_edit, name="menu_item_edit"),
    path("menu/item/<int:pk>/delete/", views.menu_item_delete, name="menu_item_delete"),
    path("menu/item/<int:pk>/toggle-availability/", views.menu_item_toggle_availability, name="menu_item_toggle_availability"),

    # Table Management
    path("tables/", views.table_list, name="tables"),
    path("tables/<int:pk>/", views.table_detail, name="table_detail"),
    path("tables/<int:pk>/order/", views.table_take_order, name="table_take_order"),
    path("tables/create/", views.table_create, name="table_create"),
    path("tables/<int:pk>/edit/", views.table_edit, name="table_edit"),
    path("tables/<int:pk>/delete/", views.table_delete, name="table_delete"),
    path("tables/<int:pk>/status/", views.table_update_status, name="table_update_status"),
    path("tables/<int:pk>/regenerate-qr/", views.table_regenerate_qr, name="table_regenerate_qr"),

    # Floor Management
    path("floors/create/", views.floor_create, name="floor_create"),
    path("floors/<int:pk>/edit/", views.floor_edit, name="floor_edit"),
    path("floors/<int:pk>/delete/", views.floor_delete, name="floor_delete"),

    # User Management
    path("users/", views.user_list, name="users"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/toggle-status/", views.user_toggle_status, name="user_toggle_status"),
    path("users/<int:pk>/reset-pin/", views.user_reset_pin, name="user_reset_pin"),
    path("users/<int:pk>/reset-password/", views.user_reset_password, name="user_reset_password"),
    path("users/<int:pk>/delete/", views.user_delete, name="user_delete"),

    # Kitchen Display
    path("kitchen/", views.kitchen_display, name="kitchen"),

    # Orders / POS
    path("orders/", views.order_list, name="orders"),
    path("orders/pos/", views.pos_view, name="pos"),
    path("orders/pos/table/<int:table_pk>/", views.pos_view, name="pos_table"),
    path("orders/<int:pk>/", views.order_detail, name="order_detail"),
    path("orders/<int:pk>/update-status/", views.order_update_status, name="order_update_status"),
    path("orders/<int:pk>/add-item/", views.order_add_item, name="order_add_item"),
    path("orders/<int:pk>/remove-item/<int:item_pk>/", views.order_remove_item, name="order_remove_item"),
    path("orders/<int:pk>/update-qty/<int:item_pk>/", views.order_update_item_qty, name="order_update_item_qty"),
    path("orders/<int:pk>/payment/", views.order_payment, name="order_payment"),
    path("orders/<int:pk>/cancel/", views.order_cancel, name="order_cancel"),
    path("orders/<int:pk>/back/", views.order_back_to_tables, name="order_back"),
    path("orders/<int:pk>/print/", views.order_print, name="order_print"),

    # Reports
    path("reports/", views.reports_view, name="reports"),

    # Settings
    path("settings/", views.settings_view, name="settings"),
    path("settings/payment/", views.payment_settings_view, name="payment_settings"),

    # Payment Gateway
    path("orders/<int:pk>/razorpay/create/", views.create_razorpay_order, name="create_razorpay_order"),
    path("orders/<int:pk>/razorpay/verify/", views.verify_razorpay_payment, name="verify_razorpay_payment"),
    path("orders/<int:pk>/razorpay/status/", views.check_payment_status, name="check_payment_status"),

    # Inventory Management
    path("inventory/", views.inventory_dashboard, name="inventory"),
    path("inventory/items/", views.inventory_items, name="inventory_items"),
    path("inventory/items/create/", views.inventory_item_create, name="inventory_item_create"),
    path("inventory/items/<int:pk>/", views.inventory_item_detail, name="inventory_item_detail"),
    path("inventory/items/<int:pk>/edit/", views.inventory_item_edit, name="inventory_item_edit"),
    path("inventory/items/<int:pk>/delete/", views.inventory_item_delete, name="inventory_item_delete"),
    path("inventory/items/<int:pk>/adjust/", views.inventory_stock_adjustment, name="inventory_stock_adjustment"),

    # Inventory Categories
    path("inventory/categories/", views.inventory_categories, name="inventory_categories"),
    path("inventory/categories/create/", views.inventory_category_create, name="inventory_category_create"),
    path("inventory/categories/<int:pk>/edit/", views.inventory_category_edit, name="inventory_category_edit"),
    path("inventory/categories/<int:pk>/delete/", views.inventory_category_delete, name="inventory_category_delete"),

    # Suppliers
    path("inventory/suppliers/", views.suppliers, name="suppliers"),
    path("inventory/suppliers/create/", views.supplier_create, name="supplier_create"),
    path("inventory/suppliers/<int:pk>/", views.supplier_detail, name="supplier_detail"),
    path("inventory/suppliers/<int:pk>/edit/", views.supplier_edit, name="supplier_edit"),
    path("inventory/suppliers/<int:pk>/delete/", views.supplier_delete, name="supplier_delete"),

    # Purchase Orders
    path("inventory/purchase-orders/", views.purchase_orders, name="purchase_orders"),
    path("inventory/purchase-orders/create/", views.purchase_order_create, name="purchase_order_create"),
    path("inventory/purchase-orders/<int:pk>/", views.purchase_order_detail, name="purchase_order_detail"),
    path("inventory/purchase-orders/<int:pk>/add-item/", views.purchase_order_add_item, name="purchase_order_add_item"),
    path("inventory/purchase-orders/<int:pk>/remove-item/<int:item_pk>/", views.purchase_order_remove_item, name="purchase_order_remove_item"),
    path("inventory/purchase-orders/<int:pk>/update-status/", views.purchase_order_update_status, name="purchase_order_update_status"),
    path("inventory/purchase-orders/<int:pk>/receive/", views.purchase_order_receive, name="purchase_order_receive"),

    # Stock Alerts
    path("inventory/alerts/", views.stock_alerts, name="stock_alerts"),
    path("inventory/alerts/<int:pk>/resolve/", views.stock_alert_resolve, name="stock_alert_resolve"),

    # Stock Movements
    path("inventory/movements/", views.stock_movements, name="stock_movements"),

    # Expense Management (Admin only)
    path("expenses/", views.expense_dashboard, name="expenses"),
    path("expenses/list/", views.expense_list, name="expense_list"),
    path("expenses/create/", views.expense_create, name="expense_create"),
    path("expenses/<int:pk>/", views.expense_detail, name="expense_detail"),
    path("expenses/<int:pk>/edit/", views.expense_edit, name="expense_edit"),
    path("expenses/<int:pk>/delete/", views.expense_delete, name="expense_delete"),
    path("expenses/categories/", views.expense_categories, name="expense_categories"),
    path("expenses/categories/create/", views.expense_category_create, name="expense_category_create"),
    path("expenses/categories/<int:pk>/edit/", views.expense_category_edit, name="expense_category_edit"),
    path("expenses/categories/<int:pk>/delete/", views.expense_category_delete, name="expense_category_delete"),

    # Cash Drawer Management (Admin + Cashier)
    path("cash-drawer/", views.cash_drawer_dashboard, name="cash_drawer"),
    path("cash-drawer/open/", views.cash_drawer_open, name="cash_drawer_open"),
    path("cash-drawer/close/", views.cash_drawer_close, name="cash_drawer_close"),
    path("cash-drawer/history/", views.cash_drawer_history, name="cash_drawer_history"),
    path("cash-drawer/<int:pk>/", views.cash_drawer_detail, name="cash_drawer_detail"),
    path("cash-drawer/cash-in-out/", views.cash_in_out, name="cash_in_out"),

    # Cashier Shifts
    path("shift/start/", views.shift_start, name="shift_start"),
    path("shift/end/", views.shift_end, name="shift_end"),
    path("shift/history/", views.shift_history, name="shift_history"),

    # Cashier Reports (Sales Only)
    path("cashier-reports/", views.cashier_reports, name="cashier_reports"),

    # Outlet Management (Super Admin only)
    path("outlets/", views.outlet_list, name="outlets"),
    path("outlets/create/", views.outlet_create, name="outlet_create"),
    path("outlets/<int:pk>/edit/", views.outlet_edit, name="outlet_edit"),
    path("outlets/<int:pk>/delete/", views.outlet_delete, name="outlet_delete"),
]
