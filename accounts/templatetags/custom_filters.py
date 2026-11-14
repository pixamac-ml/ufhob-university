from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter
def human_decimal(value, places=2):
    """Render a business decimal without exposing stored precision in the UI."""
    if value in (None, ""):
        return ""
    try:
        places = max(int(places), 0)
        decimal_value = Decimal(str(value))
        quantum = Decimal("1").scaleb(-places)
        rendered = format(decimal_value.quantize(quantum, rounding=ROUND_HALF_UP), "f")
    except (InvalidOperation, TypeError, ValueError):
        return value
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered.replace(".", ",")

@register.filter
def str_class(obj):
    return obj.__class__.__name__


# ================= MATH FILTERS =================

@register.filter
def multiply(value, arg):
    """Multiplie la valeur par l'argument"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def divide(value, arg):
    """Divise la valeur par l'argument"""
    try:
        arg = float(arg)
        if arg == 0:
            return 0
        return float(value) / arg
    except (ValueError, TypeError):
        return 0


@register.filter
def add(value, arg):
    """Ajoute l'argument à la valeur"""
    try:
        return float(value) + float(arg)
    except (ValueError, TypeError):
        return 0


@register.filter
def subtract(value, arg):
    """Soustrait l'argument de la valeur"""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0


# ================= STRING FILTERS =================

@register.filter
@stringfilter
def replace(value, arg):
    """Remplace une chaîne par une autre. Usage: {{ value|replace:"old,new" }}"""
    try:
        old, new = arg.split(',')
        return value.replace(old, new)
    except (ValueError, AttributeError):
        return value


@register.filter
def has_group(user, group_name):
    return user.groups.filter(name=group_name).exists()


@register.simple_tag
def get_user_group(user):
    if not user or not user.is_authenticated:
        return None
    return user.groups.first()
