"""Isolated, reusable SQLite database for public campaign validation."""
from .settings_test_ufhob import *

DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": BASE_DIR / ".tmp-campaign-tests.sqlite3",
    "TEST": {"NAME": BASE_DIR / ".tmp-campaign-tests.sqlite3"},
}}
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
