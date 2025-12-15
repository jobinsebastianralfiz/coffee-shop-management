"""
Utility functions for the Coffee Shop Management System.
"""

from decimal import Decimal


def format_currency(amount, outlet=None, symbol=None, position=None):
    """
    Format an amount with currency symbol.

    Args:
        amount: The amount to format (Decimal, float, or int)
        outlet: Outlet instance to get currency settings from
        symbol: Override currency symbol (defaults to outlet's or '₹')
        position: Override position ('before' or 'after')

    Returns:
        Formatted string like "₹1,234.56" or "1,234.56€"

    Examples:
        >>> format_currency(1234.56)
        '₹1,234.56'
        >>> format_currency(1234.56, symbol='$')
        '$1,234.56'
        >>> format_currency(1234.56, symbol='€', position='after')
        '1,234.56€'
    """
    # Convert to Decimal for consistent formatting
    if not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    # Get currency settings from outlet or use defaults
    if outlet:
        currency_symbol = symbol or outlet.currency_symbol
        currency_position = position or outlet.currency_position
    else:
        currency_symbol = symbol or "₹"
        currency_position = position or "before"

    # Format the amount with thousand separators
    formatted_amount = f"{amount:,.2f}"

    # Apply currency symbol based on position
    if currency_position == "before":
        return f"{currency_symbol}{formatted_amount}"
    else:
        return f"{formatted_amount}{currency_symbol}"


def get_outlet_currency_symbol(outlet):
    """
    Get the currency symbol for an outlet.

    Args:
        outlet: Outlet instance

    Returns:
        Currency symbol string (e.g., '₹', '$', '€')
    """
    if outlet:
        return outlet.currency_symbol
    return "₹"


def get_outlet_currency_code(outlet):
    """
    Get the ISO 4217 currency code for an outlet.

    Args:
        outlet: Outlet instance

    Returns:
        Currency code string (e.g., 'INR', 'USD', 'EUR')
    """
    if outlet:
        return outlet.currency_code
    return "INR"


# Common currency configurations for easy setup
CURRENCY_PRESETS = {
    "INR": {"code": "INR", "symbol": "₹", "position": "before", "name": "Indian Rupee"},
    "USD": {"code": "USD", "symbol": "$", "position": "before", "name": "US Dollar"},
    "EUR": {"code": "EUR", "symbol": "€", "position": "after", "name": "Euro"},
    "GBP": {"code": "GBP", "symbol": "£", "position": "before", "name": "British Pound"},
    "AED": {"code": "AED", "symbol": "د.إ", "position": "before", "name": "UAE Dirham"},
    "SAR": {"code": "SAR", "symbol": "﷼", "position": "before", "name": "Saudi Riyal"},
    "SGD": {"code": "SGD", "symbol": "S$", "position": "before", "name": "Singapore Dollar"},
    "MYR": {"code": "MYR", "symbol": "RM", "position": "before", "name": "Malaysian Ringgit"},
    "THB": {"code": "THB", "symbol": "฿", "position": "before", "name": "Thai Baht"},
    "JPY": {"code": "JPY", "symbol": "¥", "position": "before", "name": "Japanese Yen"},
    "CNY": {"code": "CNY", "symbol": "¥", "position": "before", "name": "Chinese Yuan"},
    "AUD": {"code": "AUD", "symbol": "A$", "position": "before", "name": "Australian Dollar"},
    "CAD": {"code": "CAD", "symbol": "C$", "position": "before", "name": "Canadian Dollar"},
}


def get_currency_choices():
    """
    Get currency choices for form fields.

    Returns:
        List of tuples [(code, display_name), ...]
    """
    return [(code, f"{data['symbol']} - {data['name']}") for code, data in CURRENCY_PRESETS.items()]


def get_currency_preset(code):
    """
    Get currency preset configuration by code.

    Args:
        code: ISO 4217 currency code (e.g., 'INR', 'USD')

    Returns:
        Dict with currency configuration or None if not found
    """
    return CURRENCY_PRESETS.get(code.upper())
