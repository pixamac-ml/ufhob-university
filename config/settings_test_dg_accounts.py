"""Isolated SQLite settings for focused DG account tests."""

from .settings_test_ufhob import *
from django.apps import AppConfig

MIGRATION_MODULES = {AppConfig.create(app).label: None for app in INSTALLED_APPS}
