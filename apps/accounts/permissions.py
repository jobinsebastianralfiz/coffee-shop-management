"""
Custom permissions for role-based access control.
"""

from rest_framework.permissions import BasePermission

from .models import User


class IsSuperAdmin(BasePermission):
    """
    Allows access only to super admin users.
    """

    message = "Only super admins can perform this action."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.SUPER_ADMIN
        )


class IsCashier(BasePermission):
    """
    Allows access to cashier users.
    """

    message = "Only cashiers can perform this action."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.STAFF_CASHIER
        )


class IsKitchenStaff(BasePermission):
    """
    Allows access to kitchen staff users.
    """

    message = "Only kitchen staff can perform this action."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.STAFF_KITCHEN
        )


class IsWaiter(BasePermission):
    """
    Allows access to waiter users.
    """

    message = "Only waiters can perform this action."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.WAITER
        )


class IsAdminOrCashier(BasePermission):
    """
    Allows access to super admin or cashier users.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in [User.Role.SUPER_ADMIN, User.Role.STAFF_CASHIER]
        )


class IsAdminOrWaiter(BasePermission):
    """
    Allows access to super admin or waiter users.
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in [User.Role.SUPER_ADMIN, User.Role.WAITER]
        )


class IsStaff(BasePermission):
    """
    Allows access to any staff member (admin, cashier, kitchen, waiter).
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role
            in [
                User.Role.SUPER_ADMIN,
                User.Role.STAFF_CASHIER,
                User.Role.STAFF_KITCHEN,
                User.Role.WAITER,
            ]
        )


class CanManageOrders(BasePermission):
    """
    Allows access to users who can create/manage orders (admin, cashier, waiter).
    """

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role
            in [
                User.Role.SUPER_ADMIN,
                User.Role.STAFF_CASHIER,
                User.Role.WAITER,
            ]
        )


class CanProcessPayments(BasePermission):
    """
    Allows access to users who can process payments (admin, cashier).
    """

    message = "Only admins and cashiers can process payments."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in [User.Role.SUPER_ADMIN, User.Role.STAFF_CASHIER]
        )


class CanViewReports(BasePermission):
    """
    Allows access to users who can view reports (admin only).
    """

    message = "Only admins can view reports."

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == User.Role.SUPER_ADMIN
        )


class CanUpdateOrderStatus(BasePermission):
    """
    Allows access to users who can update order status (all staff).
    """

    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role in [
            User.Role.SUPER_ADMIN,
            User.Role.STAFF_CASHIER,
            User.Role.STAFF_KITCHEN,
            User.Role.WAITER,
        ]
