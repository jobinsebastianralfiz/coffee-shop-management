"""
Template tags for currency formatting based on outlet settings.
"""
from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def format_currency(value, outlet=None):
    """
    Format a value as currency using outlet settings.

    Usage:
        {{ amount|format_currency:outlet }}
        {{ amount|format_currency }}  # Uses default ₹ symbol
    """
    if value is None:
        return ""

    try:
        amount = Decimal(str(value))
    except (ValueError, TypeError):
        return str(value)

    # Format the number with commas
    formatted_amount = f"{amount:,.2f}"

    # Get currency settings from outlet or use defaults
    if outlet:
        symbol = outlet.currency_symbol or "₹"
        position = outlet.currency_position or "before"
    else:
        symbol = "₹"
        position = "before"

    # Apply symbol based on position
    if position == "after":
        return f"{formatted_amount}{symbol}"
    return f"{symbol}{formatted_amount}"


@register.simple_tag
def currency_symbol(outlet=None):
    """
    Get the currency symbol for an outlet.

    Usage:
        {% currency_symbol outlet %}
        {% currency_symbol %}  # Returns default ₹
    """
    if outlet and hasattr(outlet, 'currency_symbol'):
        return outlet.currency_symbol or "₹"
    return "₹"


@register.simple_tag(takes_context=True)
def outlet_currency(context, amount):
    """
    Format amount using the outlet from context (if available).

    Usage:
        {% outlet_currency amount %}
    """
    if amount is None:
        return ""

    try:
        amount = Decimal(str(amount))
    except (ValueError, TypeError):
        return str(amount)

    # Try to get outlet from context
    outlet = context.get('outlet') or context.get('order', {})
    if hasattr(outlet, 'outlet'):
        outlet = outlet.outlet

    formatted_amount = f"{amount:,.2f}"

    if outlet and hasattr(outlet, 'currency_symbol'):
        symbol = outlet.currency_symbol or "₹"
        position = getattr(outlet, 'currency_position', 'before') or 'before'
    else:
        symbol = "₹"
        position = "before"

    if position == "after":
        return f"{formatted_amount}{symbol}"
    return f"{symbol}{formatted_amount}"
