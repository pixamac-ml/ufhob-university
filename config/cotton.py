from django.apps import AppConfig


class CottonCompatConfig(AppConfig):
    """Load Cotton without a second lexer patch while django-components coexists."""

    name = "django_cotton"

