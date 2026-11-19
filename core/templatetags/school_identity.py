from django import template

from core.school_identity import school_logo_url as _school_logo_url

register = template.Library()


@register.filter
def school_logo_url(school, variant="color"):
    return _school_logo_url(school, variant)
