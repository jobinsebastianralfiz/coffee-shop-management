# Coffee Shop Management System - Implementation Plan

## Project Overview

**Project Name:** Coffee Shop Management System
**Client:** Ralfiz Technologies
**Stack:** Django 5.x + DRF + Django Channels + Flutter + PostgreSQL + Redis

---

## 1. Technology Stack

### Backend
| Component | Technology | Version |
|-----------|------------|---------|
| Framework | Django | 5.x |
| API | Django REST Framework | 3.14+ |
| WebSocket | Django Channels | 4.x |
| Database | PostgreSQL | 16 |
| Cache/Broker | Redis | 7.x |
| Task Queue | Celery | 5.x |
| Auth | JWT (SimpleJWT) | 5.x |

### Frontend
| Component | Technology |
|-----------|------------|
| Admin/Staff Panel | Django Templates + HTMX + Alpine.js + Tailwind CSS |
| Waiter App | Flutter (Android/iOS/Tablet) |
| Customer QR Ordering | PWA (Django + Service Worker) |
| Kitchen Display (KDS) | Web (Full-screen responsive) |

### Infrastructure
| Component | Technology |
|-----------|------------|
| Web Server | Nginx |
| WSGI | Gunicorn |
| ASGI | Daphne/Uvicorn |
| Storage | AWS S3 / Cloudinary |
| Deployment | Docker + Docker Compose |

---

## 2. Project Structure

```
coffee_shop/
├── manage.py
├── requirements/
│   ├── base.txt
│   ├── development.txt
│   └── production.txt
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── config/
│   ├── __init__.py
│   ├── settings/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── development.py
│   │   └── production.py
│   ├── urls.py
│   ├── asgi.py
│   ├── wsgi.py
│   └── celery.py
├── apps/
│   ├── __init__.py
│   ├── accounts/              # User Management
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── permissions.py
│   │   ├── signals.py
│   │   └── admin.py
│   ├── menu/                  # Menu Management
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── admin.py
│   ├── tables/                # Table Management
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── utils.py           # QR generation
│   │   └── admin.py
│   ├── orders/                # Order Management
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── signals.py
│   │   └── admin.py
│   ├── payments/              # Payment System
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── gateways/
│   │   │   ├── razorpay.py
│   │   │   └── base.py
│   │   └── admin.py
│   ├── kitchen/               # Kitchen Display System
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── consumers.py
│   ├── inventory/             # Inventory Management
│   │   ├── models.py
│   │   ├── serializers.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   └── admin.py
│   ├── reports/               # Reports & Analytics
│   │   ├── models.py
│   │   ├── views.py
│   │   ├── urls.py
│   │   ├── services.py
│   │   └── exports.py
│   ├── notifications/         # Notifications
│   │   ├── models.py
│   │   ├── services.py
│   │   ├── tasks.py
│   │   └── consumers.py
│   └── core/                  # Shared utilities
│       ├── models.py          # Base models
│       ├── permissions.py
│       ├── pagination.py
│       ├── exceptions.py
│       └── utils.py
├── realtime/                  # WebSocket Consumers
│   ├── __init__.py
│   ├── routing.py
│   ├── consumers.py
│   └── middleware.py
├── templates/
│   ├── base.html
│   ├── admin/
│   ├── staff/
│   ├── kitchen/
│   └── customer/
├── static/
│   ├── css/
│   ├── js/
│   └── images/
└── media/
    ├── menu_items/
    ├── categories/
    └── qr_codes/
```

---

## 3. Database Models

### 3.1 Accounts App

```python
# apps/accounts/models.py

class User(AbstractUser):
    """Custom user model with role-based access"""

    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', 'Super Admin'
        STAFF_CASHIER = 'staff_cashier', 'Cashier'
        STAFF_KITCHEN = 'staff_kitchen', 'Kitchen Staff'
        WAITER = 'waiter', 'Waiter'

    role = models.CharField(max_length=20, choices=Role.choices)
    phone = models.CharField(max_length=15, unique=True, null=True)
    pin = models.CharField(max_length=6, null=True)  # Quick login PIN
    employee_id = models.CharField(max_length=20, unique=True, null=True)
    profile_photo = models.ImageField(upload_to='profiles/', null=True)
    is_on_duty = models.BooleanField(default=False)
    current_shift = models.CharField(max_length=20, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class StaffAttendance(models.Model):
    """Track staff clock in/out"""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    clock_in = models.DateTimeField()
    clock_out = models.DateTimeField(null=True)
    shift = models.CharField(max_length=20)
    notes = models.TextField(blank=True)


class AuditLog(models.Model):
    """Track user actions for security"""

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100)
    object_id = models.PositiveIntegerField(null=True)
    changes = models.JSONField(default=dict)
    ip_address = models.GenericIPAddressField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
```

### 3.2 Menu App

```python
# apps/menu/models.py

class Category(models.Model):
    """Menu categories"""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='categories/', null=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    available_from = models.TimeField(null=True)  # Time-based availability
    available_until = models.TimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']
        verbose_name_plural = 'Categories'


class MenuItem(models.Model):
    """Individual menu items"""

    class FoodType(models.TextChoices):
        VEG = 'veg', 'Vegetarian'
        NON_VEG = 'non_veg', 'Non-Vegetarian'
        VEGAN = 'vegan', 'Vegan'

    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='items')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='menu_items/', null=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    food_type = models.CharField(max_length=10, choices=FoodType.choices, default=FoodType.VEG)
    preparation_time = models.PositiveIntegerField(help_text='Minutes')
    calories = models.PositiveIntegerField(null=True)
    is_available = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_popular = models.BooleanField(default=False)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']


class MenuItemVariant(models.Model):
    """Size variants (S/M/L)"""

    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=50)  # Small, Medium, Large
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_default = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True)

    class Meta:
        unique_together = ['menu_item', 'name']


class AddOnGroup(models.Model):
    """Group of add-ons (e.g., 'Milk Options', 'Toppings')"""

    name = models.CharField(max_length=100)
    is_required = models.BooleanField(default=False)
    is_multi_select = models.BooleanField(default=True)
    max_selections = models.PositiveIntegerField(null=True)
    menu_items = models.ManyToManyField(MenuItem, related_name='addon_groups')


class AddOn(models.Model):
    """Individual add-on items"""

    group = models.ForeignKey(AddOnGroup, on_delete=models.CASCADE, related_name='addons')
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)


class ComboMeal(models.Model):
    """Combo/bundle meals"""

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='combos/', null=True)
    original_price = models.DecimalField(max_digits=10, decimal_places=2)
    combo_price = models.DecimalField(max_digits=10, decimal_places=2)
    items = models.ManyToManyField(MenuItem, through='ComboItem')
    is_active = models.BooleanField(default=True)
    available_from = models.TimeField(null=True)
    available_until = models.TimeField(null=True)


class ComboItem(models.Model):
    """Items in a combo"""

    combo = models.ForeignKey(ComboMeal, on_delete=models.CASCADE)
    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE)
    variant = models.ForeignKey(MenuItemVariant, on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)
```

### 3.3 Tables App

```python
# apps/tables/models.py

class Floor(models.Model):
    """Floor/section of the restaurant"""

    name = models.CharField(max_length=100)  # Main Floor, Outdoor, Rooftop
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)


class Table(models.Model):
    """Restaurant tables"""

    class Status(models.TextChoices):
        VACANT = 'vacant', 'Vacant'
        OCCUPIED = 'occupied', 'Occupied'
        BILLED = 'billed', 'Billed'
        CLEANING = 'cleaning', 'Cleaning'
        RESERVED = 'reserved', 'Reserved'

    class TableType(models.TextChoices):
        TWO_SEATER = '2_seater', '2 Seater'
        FOUR_SEATER = '4_seater', '4 Seater'
        SIX_SEATER = '6_seater', '6 Seater'
        BOOTH = 'booth', 'Booth'
        ROUND = 'round', 'Round'

    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, related_name='tables')
    number = models.CharField(max_length=10)  # T1, T2, etc.
    name = models.CharField(max_length=50, blank=True)  # Optional custom name
    capacity = models.PositiveIntegerField()
    table_type = models.CharField(max_length=20, choices=TableType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.VACANT)
    qr_code = models.ImageField(upload_to='qr_codes/', null=True)
    qr_code_url = models.URLField(blank=True)
    position_x = models.PositiveIntegerField(default=0)  # For floor map
    position_y = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['floor', 'number']


class TableSession(models.Model):
    """Track customer sessions at tables"""

    table = models.ForeignKey(Table, on_delete=models.CASCADE, related_name='sessions')
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True)
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=15, blank=True)
    guest_count = models.PositiveIntegerField(default=1)
    waiter = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
```

### 3.4 Orders App

```python
# apps/orders/models.py

class Order(models.Model):
    """Main order model"""

    class OrderType(models.TextChoices):
        DINE_IN = 'dine_in', 'Dine In'
        TAKEAWAY = 'takeaway', 'Takeaway'
        DELIVERY = 'delivery', 'Delivery'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        ACCEPTED = 'accepted', 'Accepted'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        SERVED = 'served', 'Served'
        COMPLETED = 'completed', 'Completed'
        CANCELLED = 'cancelled', 'Cancelled'

    order_number = models.CharField(max_length=20, unique=True)
    order_type = models.CharField(max_length=20, choices=OrderType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)

    # For dine-in
    table = models.ForeignKey('tables.Table', on_delete=models.SET_NULL, null=True, blank=True)
    table_session = models.ForeignKey('tables.TableSession', on_delete=models.SET_NULL, null=True, blank=True)

    # For takeaway
    token_number = models.CharField(max_length=10, blank=True)
    customer_name = models.CharField(max_length=100, blank=True)
    customer_phone = models.CharField(max_length=15, blank=True)
    expected_pickup_time = models.DateTimeField(null=True)

    # Staff
    waiter = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='waiter_orders')
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='created_orders')

    # Source
    is_qr_order = models.BooleanField(default=False)

    # Pricing
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Meta
    notes = models.TextField(blank=True)  # Special instructions
    priority = models.BooleanField(default=False)  # Rush order
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True)
    ready_at = models.DateTimeField(null=True)
    served_at = models.DateTimeField(null=True)
    completed_at = models.DateTimeField(null=True)

    class Meta:
        ordering = ['-created_at']


class OrderItem(models.Model):
    """Individual items in an order"""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        SERVED = 'served', 'Served'
        CANCELLED = 'cancelled', 'Cancelled'

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey('menu.MenuItem', on_delete=models.PROTECT)
    variant = models.ForeignKey('menu.MenuItemVariant', on_delete=models.SET_NULL, null=True)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    special_instructions = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class OrderItemAddOn(models.Model):
    """Add-ons for order items"""

    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name='addons')
    addon = models.ForeignKey('menu.AddOn', on_delete=models.PROTECT)
    price = models.DecimalField(max_digits=10, decimal_places=2)


class OrderStatusHistory(models.Model):
    """Track order status changes"""

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_history')
    from_status = models.CharField(max_length=20)
    to_status = models.CharField(max_length=20)
    changed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
```

### 3.5 Payments App

```python
# apps/payments/models.py

class Payment(models.Model):
    """Payment transactions"""

    class Method(models.TextChoices):
        CASH = 'cash', 'Cash'
        CARD = 'card', 'Card'
        UPI = 'upi', 'UPI'
        WALLET = 'wallet', 'Wallet'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        COMPLETED = 'completed', 'Completed'
        FAILED = 'failed', 'Failed'
        REFUNDED = 'refunded', 'Refunded'
        PARTIAL_REFUND = 'partial_refund', 'Partial Refund'

    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT, related_name='payments')
    payment_number = models.CharField(max_length=50, unique=True)
    method = models.CharField(max_length=20, choices=Method.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    # Cash specific
    amount_received = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    change_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True)

    # Digital payment specific
    transaction_id = models.CharField(max_length=100, blank=True)
    gateway_response = models.JSONField(default=dict)

    # Meta
    processed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True)


class Bill(models.Model):
    """Generated bills/invoices"""

    order = models.OneToOneField('orders.Order', on_delete=models.PROTECT, related_name='bill')
    bill_number = models.CharField(max_length=50, unique=True)

    # Amounts
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    cgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    sgst = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount_reason = models.CharField(max_length=200, blank=True)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    # Meta
    generated_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_printed = models.BooleanField(default=False)
    printed_at = models.DateTimeField(null=True)


class Refund(models.Model):
    """Track refunds"""

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    approved_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='approved_refunds')
    processed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='processed_refunds')
    created_at = models.DateTimeField(auto_now_add=True)


class CashDrawer(models.Model):
    """Daily cash drawer tracking"""

    date = models.DateField()
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    cash_in = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cash_out = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    opened_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='opened_drawers')
    closed_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True, related_name='closed_drawers')
    notes = models.TextField(blank=True)
    discrepancy = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    is_closed = models.BooleanField(default=False)
```

### 3.6 Inventory App

```python
# apps/inventory/models.py

class InventoryCategory(models.Model):
    """Categories for inventory items"""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)


class InventoryItem(models.Model):
    """Stock items"""

    class Unit(models.TextChoices):
        KG = 'kg', 'Kilogram'
        G = 'g', 'Gram'
        L = 'l', 'Liter'
        ML = 'ml', 'Milliliter'
        PCS = 'pcs', 'Pieces'
        PKT = 'pkt', 'Packet'

    category = models.ForeignKey(InventoryCategory, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=200)
    sku = models.CharField(max_length=50, unique=True)
    unit = models.CharField(max_length=10, choices=Unit.choices)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    minimum_stock = models.DecimalField(max_digits=10, decimal_places=2)  # Alert threshold
    cost_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    supplier = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    last_restocked = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class StockMovement(models.Model):
    """Track all stock movements"""

    class MovementType(models.TextChoices):
        PURCHASE = 'purchase', 'Purchase'
        SALE = 'sale', 'Sale'
        WASTAGE = 'wastage', 'Wastage'
        DAMAGE = 'damage', 'Damage'
        ADJUSTMENT = 'adjustment', 'Manual Adjustment'
        TRANSFER = 'transfer', 'Transfer'

    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=MovementType.choices)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)  # Positive or negative
    previous_stock = models.DecimalField(max_digits=10, decimal_places=2)
    new_stock = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=100, blank=True)  # PO number, order number, etc.
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey('accounts.User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Recipe(models.Model):
    """Link menu items to inventory (ingredient mapping)"""

    menu_item = models.ForeignKey('menu.MenuItem', on_delete=models.CASCADE, related_name='recipes')
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=3)  # Amount used per unit
```

### 3.7 Core/Settings App

```python
# apps/core/models.py

class BusinessSettings(models.Model):
    """Global business configuration - Singleton"""

    business_name = models.CharField(max_length=200)
    logo = models.ImageField(upload_to='branding/', null=True)
    address = models.TextField()
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    gst_number = models.CharField(max_length=50, blank=True)
    currency = models.CharField(max_length=10, default='INR')
    currency_symbol = models.CharField(max_length=5, default='₹')
    opening_time = models.TimeField()
    closing_time = models.TimeField()
    receipt_header = models.TextField(blank=True)
    receipt_footer = models.TextField(blank=True)

    # Tax settings
    cgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.5)
    sgst_rate = models.DecimalField(max_digits=5, decimal_places=2, default=2.5)
    service_charge_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_inclusive_pricing = models.BooleanField(default=False)

    # Order settings
    auto_accept_orders = models.BooleanField(default=False)
    default_prep_time = models.PositiveIntegerField(default=10)  # Minutes
    allow_qr_ordering = models.BooleanField(default=True)
    require_phone_takeaway = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Business Settings'
        verbose_name_plural = 'Business Settings'

    def save(self, *args, **kwargs):
        self.pk = 1  # Ensure singleton
        super().save(*args, **kwargs)
```

---

## 4. API Endpoints

### 4.1 Authentication APIs

```
POST   /api/v1/auth/login/                 # Email/Phone + Password login
POST   /api/v1/auth/login/pin/             # PIN-based quick login
POST   /api/v1/auth/logout/                # Logout
POST   /api/v1/auth/token/refresh/         # Refresh JWT token
POST   /api/v1/auth/password/reset/        # Request password reset
POST   /api/v1/auth/password/reset/confirm/ # Confirm password reset
GET    /api/v1/auth/me/                    # Current user profile
PUT    /api/v1/auth/me/                    # Update profile
```

### 4.2 User Management APIs (Admin)

```
GET    /api/v1/users/                      # List all users
POST   /api/v1/users/                      # Create user
GET    /api/v1/users/{id}/                 # Get user details
PUT    /api/v1/users/{id}/                 # Update user
DELETE /api/v1/users/{id}/                 # Deactivate user
POST   /api/v1/users/{id}/activate/        # Reactivate user
GET    /api/v1/users/staff/on-duty/        # List staff on duty

GET    /api/v1/attendance/                 # Attendance records
POST   /api/v1/attendance/clock-in/        # Clock in
POST   /api/v1/attendance/clock-out/       # Clock out
```

### 4.3 Menu APIs

```
# Categories
GET    /api/v1/menu/categories/            # List categories
POST   /api/v1/menu/categories/            # Create category
GET    /api/v1/menu/categories/{id}/       # Get category
PUT    /api/v1/menu/categories/{id}/       # Update category
DELETE /api/v1/menu/categories/{id}/       # Delete category
POST   /api/v1/menu/categories/reorder/    # Reorder categories

# Menu Items
GET    /api/v1/menu/items/                 # List items (filterable)
POST   /api/v1/menu/items/                 # Create item
GET    /api/v1/menu/items/{id}/            # Get item with variants/addons
PUT    /api/v1/menu/items/{id}/            # Update item
DELETE /api/v1/menu/items/{id}/            # Delete item
POST   /api/v1/menu/items/{id}/toggle/     # Toggle availability

# Variants
POST   /api/v1/menu/items/{id}/variants/   # Add variant
PUT    /api/v1/menu/variants/{id}/         # Update variant
DELETE /api/v1/menu/variants/{id}/         # Delete variant

# Add-ons
GET    /api/v1/menu/addon-groups/          # List addon groups
POST   /api/v1/menu/addon-groups/          # Create addon group
PUT    /api/v1/menu/addon-groups/{id}/     # Update addon group
DELETE /api/v1/menu/addon-groups/{id}/     # Delete addon group
POST   /api/v1/menu/addons/                # Add addon to group
PUT    /api/v1/menu/addons/{id}/           # Update addon
DELETE /api/v1/menu/addons/{id}/           # Delete addon

# Customer Menu (Public)
GET    /api/v1/menu/public/                # Full menu for customer QR ordering
GET    /api/v1/menu/public/categories/     # Categories only
GET    /api/v1/menu/public/items/{id}/     # Single item details
```

### 4.4 Table APIs

```
# Floors
GET    /api/v1/tables/floors/              # List floors
POST   /api/v1/tables/floors/              # Create floor
PUT    /api/v1/tables/floors/{id}/         # Update floor
DELETE /api/v1/tables/floors/{id}/         # Delete floor

# Tables
GET    /api/v1/tables/                     # List all tables
POST   /api/v1/tables/                     # Create table
GET    /api/v1/tables/{id}/                # Get table details
PUT    /api/v1/tables/{id}/                # Update table
DELETE /api/v1/tables/{id}/                # Delete table
POST   /api/v1/tables/{id}/status/         # Update table status
GET    /api/v1/tables/{id}/qr/             # Get/Generate QR code
POST   /api/v1/tables/{id}/qr/regenerate/  # Regenerate QR code
GET    /api/v1/tables/floor-map/           # Get floor map data

# Table Sessions
GET    /api/v1/tables/{id}/session/        # Get current session
POST   /api/v1/tables/{id}/session/start/  # Start new session
POST   /api/v1/tables/{id}/session/end/    # End session
GET    /api/v1/tables/sessions/            # List all active sessions

# QR Landing (Public)
GET    /api/v1/tables/qr/{table_uuid}/     # Validate QR and get table info
```

### 4.5 Order APIs

```
# Orders
GET    /api/v1/orders/                     # List orders (filterable by status, date, type)
POST   /api/v1/orders/                     # Create order
GET    /api/v1/orders/{id}/                # Get order details
PUT    /api/v1/orders/{id}/                # Update order
DELETE /api/v1/orders/{id}/                # Cancel order

# Order Status
POST   /api/v1/orders/{id}/accept/         # Accept order
POST   /api/v1/orders/{id}/preparing/      # Mark preparing
POST   /api/v1/orders/{id}/ready/          # Mark ready
POST   /api/v1/orders/{id}/served/         # Mark served
POST   /api/v1/orders/{id}/complete/       # Mark completed
POST   /api/v1/orders/{id}/cancel/         # Cancel with reason

# Order Items
POST   /api/v1/orders/{id}/items/          # Add items to order
PUT    /api/v1/orders/items/{id}/          # Update item
DELETE /api/v1/orders/items/{id}/          # Remove item
POST   /api/v1/orders/items/{id}/status/   # Update item status (KDS)

# Customer Orders (QR)
POST   /api/v1/orders/qr/                  # Create order via QR (public)
GET    /api/v1/orders/qr/{order_number}/   # Track order status (public)

# Takeaway
GET    /api/v1/orders/takeaway/            # List takeaway orders
GET    /api/v1/orders/takeaway/ready/      # Ready for pickup
POST   /api/v1/orders/takeaway/{id}/pickup/ # Mark as picked up

# Kitchen (KDS)
GET    /api/v1/orders/kitchen/             # Orders for kitchen display
GET    /api/v1/orders/kitchen/station/{station}/ # Orders by station
POST   /api/v1/orders/kitchen/{id}/bump/   # Bump order (complete)
```

### 4.6 Payment APIs

```
# Payments
GET    /api/v1/payments/                   # List payments
POST   /api/v1/payments/                   # Create payment
GET    /api/v1/payments/{id}/              # Get payment details

# Payment Processing
POST   /api/v1/payments/cash/              # Process cash payment
POST   /api/v1/payments/card/              # Initiate card payment
POST   /api/v1/payments/upi/generate/      # Generate UPI QR
POST   /api/v1/payments/upi/verify/        # Verify UPI payment
POST   /api/v1/payments/webhook/           # Payment gateway webhook

# Bill
POST   /api/v1/orders/{id}/bill/           # Generate bill
GET    /api/v1/orders/{id}/bill/           # Get bill
POST   /api/v1/orders/{id}/bill/print/     # Print bill
POST   /api/v1/orders/{id}/bill/send/      # Send digital bill (WhatsApp/Email)

# Refunds
POST   /api/v1/payments/{id}/refund/       # Initiate refund
GET    /api/v1/refunds/                    # List refunds

# Cash Drawer
GET    /api/v1/cash-drawer/today/          # Today's drawer
POST   /api/v1/cash-drawer/open/           # Open drawer
POST   /api/v1/cash-drawer/close/          # Close drawer
```

### 4.7 Inventory APIs

```
GET    /api/v1/inventory/                  # List inventory items
POST   /api/v1/inventory/                  # Create item
GET    /api/v1/inventory/{id}/             # Get item details
PUT    /api/v1/inventory/{id}/             # Update item
DELETE /api/v1/inventory/{id}/             # Delete item

GET    /api/v1/inventory/low-stock/        # Items below minimum
POST   /api/v1/inventory/{id}/add-stock/   # Add stock
POST   /api/v1/inventory/{id}/adjust/      # Manual adjustment
POST   /api/v1/inventory/{id}/wastage/     # Record wastage

GET    /api/v1/inventory/movements/        # Stock movement history
GET    /api/v1/inventory/categories/       # Inventory categories
```

### 4.8 Reports APIs

```
# Dashboard
GET    /api/v1/reports/dashboard/          # Dashboard summary

# Sales Reports
GET    /api/v1/reports/sales/daily/        # Daily sales
GET    /api/v1/reports/sales/weekly/       # Weekly sales
GET    /api/v1/reports/sales/monthly/      # Monthly sales
GET    /api/v1/reports/sales/by-category/  # Sales by category
GET    /api/v1/reports/sales/by-item/      # Sales by item
GET    /api/v1/reports/sales/by-payment/   # Sales by payment method
GET    /api/v1/reports/sales/by-time/      # Sales by hour/time

# Order Reports
GET    /api/v1/reports/orders/summary/     # Order summary
GET    /api/v1/reports/orders/cancelled/   # Cancelled orders

# Staff Reports
GET    /api/v1/reports/staff/performance/  # Staff performance
GET    /api/v1/reports/staff/attendance/   # Attendance report

# Inventory Reports
GET    /api/v1/reports/inventory/stock/    # Current stock levels
GET    /api/v1/reports/inventory/movement/ # Stock movements
GET    /api/v1/reports/inventory/wastage/  # Wastage report

# Financial
GET    /api/v1/reports/financial/eod/      # End of day report
GET    /api/v1/reports/financial/tax/      # Tax collection

# Export
POST   /api/v1/reports/export/pdf/         # Export as PDF
POST   /api/v1/reports/export/excel/       # Export as Excel
```

### 4.9 Settings APIs

```
GET    /api/v1/settings/business/          # Get business settings
PUT    /api/v1/settings/business/          # Update business settings
GET    /api/v1/settings/tax/               # Tax configuration
PUT    /api/v1/settings/tax/               # Update tax config
GET    /api/v1/settings/notifications/     # Notification settings
PUT    /api/v1/settings/notifications/     # Update notification settings
GET    /api/v1/settings/printers/          # Printer configuration
PUT    /api/v1/settings/printers/          # Update printer config
```

---

## 5. WebSocket Events

### 5.1 Channel Groups

```python
# Channel naming convention
cafe_orders           # All order events
cafe_tables           # Table status events
cafe_kitchen          # Kitchen-specific events
cafe_payments         # Payment events
waiter_{user_id}      # Personal waiter notifications
table_{table_id}      # Customer order tracking
```

### 5.2 Event Types

```python
# Order Events
{
    "type": "order.created",
    "order_id": 123,
    "table": "T5",
    "items_count": 3,
    "total": "766.50"
}

{
    "type": "order.status_changed",
    "order_id": 123,
    "old_status": "pending",
    "new_status": "preparing"
}

# Table Events
{
    "type": "table.status_changed",
    "table_id": 5,
    "old_status": "vacant",
    "new_status": "occupied"
}

# Kitchen Events
{
    "type": "kitchen.new_order",
    "order_id": 123,
    "priority": false
}

# Payment Events
{
    "type": "payment.received",
    "order_id": 123,
    "amount": "766.50",
    "method": "upi"
}
```

---

## 6. Development Phases

### Phase 1: Foundation (Tasks: 35)

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 1.1 | Project setup with Django 5.x | P0 | - |
| 1.2 | Configure PostgreSQL database | P0 | 1.1 |
| 1.3 | Setup Redis for caching | P0 | 1.1 |
| 1.4 | Configure Django REST Framework | P0 | 1.1 |
| 1.5 | Setup Django Channels (WebSocket) | P0 | 1.3 |
| 1.6 | Configure Celery for background tasks | P1 | 1.3 |
| 1.7 | Setup Docker development environment | P1 | 1.1-1.6 |
| 1.8 | Create custom User model | P0 | 1.1 |
| 1.9 | Implement JWT authentication | P0 | 1.8 |
| 1.10 | Implement PIN-based quick login | P0 | 1.9 |
| 1.11 | Create role-based permissions | P0 | 1.8 |
| 1.12 | User CRUD API endpoints | P0 | 1.11 |
| 1.13 | Staff attendance model & API | P1 | 1.8 |
| 1.14 | Audit logging system | P1 | 1.8 |
| 1.15 | Category model & API | P0 | 1.4 |
| 1.16 | MenuItem model with variants | P0 | 1.15 |
| 1.17 | MenuItem CRUD API | P0 | 1.16 |
| 1.18 | AddOn groups & items | P0 | 1.16 |
| 1.19 | Combo meals (model only) | P2 | 1.16 |
| 1.20 | Public menu API (for QR) | P0 | 1.17 |
| 1.21 | Floor model | P0 | 1.4 |
| 1.22 | Table model with status | P0 | 1.21 |
| 1.23 | Table CRUD API | P0 | 1.22 |
| 1.24 | QR code generation utility | P0 | 1.22 |
| 1.25 | Table session model | P0 | 1.22 |
| 1.26 | Session management API | P0 | 1.25 |
| 1.27 | Floor map data API | P1 | 1.23 |
| 1.28 | Business settings model | P0 | 1.4 |
| 1.29 | Settings API | P1 | 1.28 |
| 1.30 | Admin dashboard template (base) | P1 | 1.4 |
| 1.31 | HTMX integration setup | P1 | 1.30 |
| 1.32 | Alpine.js integration | P1 | 1.30 |
| 1.33 | Tailwind CSS setup | P1 | 1.30 |
| 1.34 | Admin login page | P0 | 1.9, 1.30 |
| 1.35 | API documentation (Swagger/ReDoc) | P1 | 1.4 |

### Phase 2: Core Operations (Tasks: 30)

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 2.1 | Order model | P0 | Phase 1 |
| 2.2 | OrderItem model | P0 | 2.1 |
| 2.3 | OrderItemAddOn model | P0 | 2.2 |
| 2.4 | Order status flow logic | P0 | 2.1 |
| 2.5 | Order creation API (dine-in) | P0 | 2.4 |
| 2.6 | Order creation API (takeaway) | P0 | 2.4 |
| 2.7 | Order modification API | P0 | 2.5 |
| 2.8 | Order cancellation API | P0 | 2.5 |
| 2.9 | Order status update API | P0 | 2.4 |
| 2.10 | Order list/filter API | P0 | 2.1 |
| 2.11 | Order number generation | P0 | 2.1 |
| 2.12 | Token number generation (takeaway) | P0 | 2.6 |
| 2.13 | WebSocket consumer setup | P0 | 1.5 |
| 2.14 | Order events broadcasting | P0 | 2.13 |
| 2.15 | Table status events | P0 | 2.13 |
| 2.16 | Kitchen Display System view | P0 | 2.14 |
| 2.17 | KDS order cards component | P0 | 2.16 |
| 2.18 | KDS status update (bump) | P0 | 2.17 |
| 2.19 | KDS sound alerts | P1 | 2.16 |
| 2.20 | KDS timer display | P0 | 2.17 |
| 2.21 | Bill model | P0 | 2.1 |
| 2.22 | Bill generation logic | P0 | 2.21 |
| 2.23 | Tax calculation service | P0 | 1.28, 2.22 |
| 2.24 | Payment model | P0 | 2.21 |
| 2.25 | Cash payment processing | P0 | 2.24 |
| 2.26 | Bill API endpoints | P0 | 2.22 |
| 2.27 | Admin orders view | P0 | 2.10, 1.31 |
| 2.28 | Admin order details view | P0 | 2.27 |
| 2.29 | Auto table status update on order | P0 | 2.5, 1.25 |
| 2.30 | Order status history tracking | P1 | 2.9 |

### Phase 3: Mobile & QR (Tasks: 35)

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 3.1 | Flutter project setup | P0 | - |
| 3.2 | Flutter authentication service | P0 | 3.1, 1.9 |
| 3.3 | Flutter API client | P0 | 3.1 |
| 3.4 | Flutter WebSocket service | P0 | 3.1, 2.13 |
| 3.5 | Waiter app - Login screen | P0 | 3.2 |
| 3.6 | Waiter app - PIN login | P0 | 3.5 |
| 3.7 | Waiter app - Dashboard | P0 | 3.5 |
| 3.8 | Waiter app - Floor map view | P0 | 3.7 |
| 3.9 | Waiter app - Table selection | P0 | 3.8 |
| 3.10 | Waiter app - Menu grid | P0 | 3.7 |
| 3.11 | Waiter app - Item detail modal | P0 | 3.10 |
| 3.12 | Waiter app - Cart sidebar | P0 | 3.10 |
| 3.13 | Waiter app - Order creation | P0 | 3.12 |
| 3.14 | Waiter app - Active orders list | P0 | 3.7 |
| 3.15 | Waiter app - Order status updates | P0 | 3.4, 3.14 |
| 3.16 | Waiter app - Ready notifications | P0 | 3.15 |
| 3.17 | Waiter app - Bill request | P0 | 3.14 |
| 3.18 | Waiter app - Offline capability | P1 | 3.3 |
| 3.19 | QR ordering - Landing page | P0 | 1.24 |
| 3.20 | QR ordering - Menu display | P0 | 3.19, 1.20 |
| 3.21 | QR ordering - Category filter | P0 | 3.20 |
| 3.22 | QR ordering - Veg/Non-veg filter | P0 | 3.20 |
| 3.23 | QR ordering - Add to cart | P0 | 3.20 |
| 3.24 | QR ordering - Cart view | P0 | 3.23 |
| 3.25 | QR ordering - Order submission | P0 | 3.24, 2.5 |
| 3.26 | QR ordering - Order confirmation | P0 | 3.25 |
| 3.27 | QR ordering - Order tracking | P0 | 3.26, 2.14 |
| 3.28 | QR ordering - PWA configuration | P1 | 3.19 |
| 3.29 | Takeaway dashboard view | P0 | 2.6, 1.31 |
| 3.30 | Takeaway token display | P0 | 3.29 |
| 3.31 | Razorpay integration setup | P0 | 2.24 |
| 3.32 | UPI QR payment generation | P0 | 3.31 |
| 3.33 | Payment webhook handler | P0 | 3.31 |
| 3.34 | Card payment flow | P1 | 3.31 |
| 3.35 | Payment status display | P0 | 3.33, 2.14 |

### Phase 4: Advanced Features (Tasks: 30)

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 4.1 | Inventory item model | P0 | Phase 3 |
| 4.2 | Inventory category model | P0 | 4.1 |
| 4.3 | Stock movement model | P0 | 4.1 |
| 4.4 | Inventory CRUD API | P0 | 4.1 |
| 4.5 | Stock add/adjust API | P0 | 4.3 |
| 4.6 | Low stock calculation | P0 | 4.1 |
| 4.7 | Low stock alerts | P1 | 4.6 |
| 4.8 | Recipe/ingredient mapping | P2 | 4.1, 1.16 |
| 4.9 | Auto stock deduction | P2 | 4.8 |
| 4.10 | Inventory admin view | P0 | 4.4, 1.31 |
| 4.11 | Dashboard metrics service | P0 | 2.1, 2.24 |
| 4.12 | Dashboard API | P0 | 4.11 |
| 4.13 | Daily sales report | P0 | 4.11 |
| 4.14 | Weekly/Monthly sales report | P0 | 4.13 |
| 4.15 | Sales by category report | P0 | 4.11 |
| 4.16 | Sales by item report | P0 | 4.11 |
| 4.17 | Sales by payment method | P0 | 4.11 |
| 4.18 | Peak hours analysis | P1 | 4.11 |
| 4.19 | Staff performance report | P1 | 1.13, 2.1 |
| 4.20 | EOD report generation | P0 | 4.11 |
| 4.21 | Report export (PDF) | P0 | 4.20 |
| 4.22 | Report export (Excel) | P0 | 4.20 |
| 4.23 | Admin dashboard view | P0 | 4.12, 1.31 |
| 4.24 | SMS notification service | P1 | 1.6 |
| 4.25 | Order ready SMS | P1 | 4.24, 2.9 |
| 4.26 | WhatsApp notification (optional) | P2 | 4.24 |
| 4.27 | Thermal printer service | P1 | - |
| 4.28 | Receipt printing | P1 | 4.27, 2.22 |
| 4.29 | KOT printing | P1 | 4.27, 2.5 |
| 4.30 | Comprehensive testing | P0 | All |

### Phase 5: Polish & Launch (Tasks: 15)

| # | Task | Priority | Dependencies |
|---|------|----------|--------------|
| 5.1 | Performance optimization | P0 | Phase 4 |
| 5.2 | Database query optimization | P0 | 5.1 |
| 5.3 | Caching implementation | P0 | 5.1 |
| 5.4 | API rate limiting | P0 | 5.1 |
| 5.5 | Security audit | P0 | 5.1 |
| 5.6 | Input validation review | P0 | 5.5 |
| 5.7 | Permission testing | P0 | 5.5 |
| 5.8 | XSS/CSRF protection verify | P0 | 5.5 |
| 5.9 | User acceptance testing | P0 | 5.5 |
| 5.10 | Bug fixes from testing | P0 | 5.9 |
| 5.11 | Production Docker setup | P0 | 5.10 |
| 5.12 | CI/CD pipeline | P1 | 5.11 |
| 5.13 | Production deployment | P0 | 5.11 |
| 5.14 | SSL/Domain configuration | P0 | 5.13 |
| 5.15 | Monitoring setup (Sentry) | P1 | 5.13 |

---

## 7. Key Implementation Notes

### 7.1 Order Number Format
```
Format: ORD-YYYYMMDD-XXXX
Example: ORD-20240115-0042
```

### 7.2 Bill Number Format
```
Format: INV-YYYYMMDD-XXXX
Example: INV-20240115-0042
```

### 7.3 Takeaway Token Format
```
Format: T-XXX (resets daily)
Example: T-045
```

### 7.4 Table QR URL Format
```
Format: https://domain.com/order/t/{table_uuid}
```

### 7.5 Status Color Codes
```
Vacant:     #22C55E (Green)
Occupied:   #F97316 (Orange)
Billed:     #3B82F6 (Blue)
Cleaning:   #9CA3AF (Gray)
Reserved:   #8B5CF6 (Purple)

Order Status:
Pending:    #9CA3AF (Gray)
Accepted:   #3B82F6 (Blue)
Preparing:  #F59E0B (Amber)
Ready:      #22C55E (Green)
Served:     #6B7280 (Muted Gray)
```

### 7.6 Permission Matrix

| Action | Super Admin | Cashier | Kitchen | Waiter |
|--------|-------------|---------|---------|--------|
| Manage Users | ✅ | ❌ | ❌ | ❌ |
| Manage Menu | ✅ | ❌ | ❌ | ❌ |
| Manage Tables | ✅ | ❌ | ❌ | ❌ |
| Create Orders | ✅ | ✅ | ❌ | ✅ |
| View All Orders | ✅ | ✅ | ✅ | ❌ |
| Update Order Status | ✅ | ✅ | ✅ | ✅ |
| Process Payments | ✅ | ✅ | ❌ | ❌ |
| Issue Refunds | ✅ | ❌ | ❌ | ❌ |
| View Reports | ✅ | ❌ | ❌ | ❌ |
| Manage Inventory | ✅ | ❌ | ❌ | ❌ |
| System Settings | ✅ | ❌ | ❌ | ❌ |

---

## 8. Dependencies (requirements/base.txt)

```
# Django
Django>=5.0,<6.0
djangorestframework>=3.14.0
django-cors-headers>=4.3.0
django-filter>=23.5

# Authentication
djangorestframework-simplejwt>=5.3.0

# Database
psycopg2-binary>=2.9.9

# Redis & Channels
redis>=5.0.0
channels>=4.0.0
channels-redis>=4.1.0

# Celery
celery>=5.3.0
django-celery-beat>=2.5.0

# Utils
Pillow>=10.0.0
qrcode>=7.4.0
python-decouple>=3.8
whitenoise>=6.6.0

# API Documentation
drf-spectacular>=0.27.0

# Payments
razorpay>=1.4.0

# Exports
reportlab>=4.0.0
openpyxl>=3.1.0

# Notifications
twilio>=8.10.0  # SMS
```

---

## 9. Environment Variables

```env
# Django
SECRET_KEY=your-secret-key
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database
DATABASE_URL=postgres://user:pass@localhost:5432/coffeeshop

# Redis
REDIS_URL=redis://localhost:6379/0

# JWT
JWT_ACCESS_TOKEN_LIFETIME=60  # minutes
JWT_REFRESH_TOKEN_LIFETIME=1440  # minutes (1 day)

# Storage
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_REGION_NAME=

# Payments
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=

# Notifications
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_PHONE_NUMBER=

# Business
DEFAULT_CURRENCY=INR
DEFAULT_CURRENCY_SYMBOL=₹
```

---

## 10. Summary

**Total Tasks:** 145 tasks across 5 phases

| Phase | Focus | Task Count |
|-------|-------|------------|
| Phase 1 | Foundation | 35 |
| Phase 2 | Core Operations | 30 |
| Phase 3 | Mobile & QR | 35 |
| Phase 4 | Advanced Features | 30 |
| Phase 5 | Polish & Launch | 15 |

**Key Deliverables:**
- Django REST API backend
- Real-time WebSocket updates
- Admin web panel (Django + HTMX + Alpine.js)
- Kitchen Display System (Web)
- Waiter tablet app (Flutter)
- Customer QR ordering (PWA)
- Payment integration (Razorpay)
- Reports & Analytics
- Inventory management

---

*Document Version: 1.0*
*Created: December 2024*
