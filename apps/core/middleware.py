"""
Custom middleware for the Coffee Shop Management System.
"""


class OutletContextMiddleware:
    """
    Middleware to inject the current outlet context into the request.

    The outlet is determined from:
    1. The authenticated user's assigned outlet
    2. A session-stored outlet selection (for admins with multi-outlet access)
    3. An X-Outlet-ID header (for API requests)

    Usage in views:
        outlet = request.outlet  # Get current outlet
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Initialize outlet to None
        request.outlet = None

        if request.user.is_authenticated:
            # Check for outlet override in header (for API requests)
            outlet_header = request.headers.get("X-Outlet-ID")
            if outlet_header:
                from apps.core.models import Outlet
                try:
                    # For super admins, allow switching outlets
                    if request.user.role == "super_admin":
                        request.outlet = Outlet.objects.get(
                            id=outlet_header, is_active=True
                        )
                    else:
                        # Regular staff can only access their assigned outlet
                        request.outlet = request.user.outlet
                except Outlet.DoesNotExist:
                    request.outlet = request.user.outlet
            # Check for outlet in session (for admin switching)
            elif "current_outlet_id" in request.session and request.user.role == "super_admin":
                from apps.core.models import Outlet
                try:
                    request.outlet = Outlet.objects.get(
                        id=request.session["current_outlet_id"], is_active=True
                    )
                except Outlet.DoesNotExist:
                    request.outlet = request.user.outlet
            else:
                # Default: use user's assigned outlet
                request.outlet = request.user.outlet

        response = self.get_response(request)
        return response


class NoCacheMiddleware:
    """
    Middleware to prevent browser caching of authenticated pages.

    This prevents the browser from showing cached dashboard pages
    after the user has logged out (back button issue).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Add no-cache headers for authenticated users
        # This prevents the browser from caching pages that require login
        if request.user.is_authenticated:
            response["Cache-Control"] = "no-cache, no-store, must-revalidate, private"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"

        return response
