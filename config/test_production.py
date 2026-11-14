"""Production guards run without connecting to any database or Redis server."""

import os
import runpy
import json
import subprocess
import sys
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config import settings as base


class ProductionSettingsTests(SimpleTestCase):
    def load_profile(self, **overrides):
        values = {
            "DEBUG": False,
            "SECRET_KEY": "test-production-secret-" * 4,
            "CARD_SIGNING_KEY": "test-independent-card-key-" * 4,
            "DATABASES": {"default": {
                "ENGINE": "django.db.backends.postgresql", "NAME": "ufhob_db", "USER": "ufhob_app",
            }},
            "ALLOWED_HOSTS": ["ufhob.example.com"],
            "BASE_URL": "https://ufhob.example.com",
            "CSRF_TRUSTED_ORIGINS": ["https://ufhob.example.com"],
            "SECURE_SSL_REDIRECT": True,
            "SESSION_COOKIE_SECURE": True,
            "CSRF_COOKIE_SECURE": True,
            "SYSTEM_SESSION_MANUAL_TEST_MODE": False,
            "ONLINE_CLASSROOM_TIME_BYPASS": False,
            "LOGGING": {"loggers": {}},
            "REDIS_URL": "redis://127.0.0.1:6379/2",
            "ENABLE_WEBSOCKETS": True,
            "CHANNEL_LAYERS": {"default": {
                "BACKEND": "channels_redis.core.RedisChannelLayer", "CONFIG": {},
            }},
            "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "EMAIL_HOST": "smtp.example.test",
            "EMAIL_HOST_USER": "smtp-test-account",
            "EMAIL_HOST_PASSWORD": "test-only-smtp-password",
            "EMAIL_USE_TLS": True,
            "EMAIL_USE_SSL": False,
        }
        values.update(overrides)
        with patch.multiple(base, **values), patch.dict(os.environ, {
            "SECURE_HSTS_SECONDS": "3600",
            "SECURE_HSTS_INCLUDE_SUBDOMAINS": "False",
            "SECURE_HSTS_PRELOAD": "False",
            "UFHOB_ENVIRONMENT": "production",
        }):
            return runpy.run_module("config.settings_production")

    def test_valid_profile_disables_persistent_asgi_connections(self):
        profile = self.load_profile()
        self.assertEqual(profile["DATABASES"]["default"]["CONN_MAX_AGE"], 0)
        self.assertFalse(profile["USE_X_FORWARDED_HOST"])
        self.assertFalse(profile["SECURE_HSTS_INCLUDE_SUBDOMAINS"])
        self.assertFalse(profile["SECURE_HSTS_PRELOAD"])

    def test_debug_is_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "DEBUG=False"):
            self.load_profile(DEBUG=True)

    def test_shared_database_role_is_rejected(self):
        with self.assertRaisesMessage(ImproperlyConfigured, "ufhob_app"):
            self.load_profile(DATABASES={"default": {
                "ENGINE": "django.db.backends.postgresql", "NAME": "ufhob_db", "USER": "another_app",
            }})

    def test_redis_and_secure_smtp_are_required(self):
        for values in [
            {"REDIS_URL": ""}, {"EMAIL_HOST_PASSWORD": ""},
            {"EMAIL_USE_TLS": False, "EMAIL_USE_SSL": False},
            {"EMAIL_USE_TLS": True, "EMAIL_USE_SSL": True},
        ]:
            with self.subTest(fields=list(values)), self.assertRaises(ImproperlyConfigured):
                self.load_profile(**values)

    def test_redis_namespaces_are_specific_to_ufhob(self):
        profile = self.load_profile()
        self.assertEqual(profile["CACHES"]["default"]["KEY_PREFIX"], "ufhob:production")
        self.assertEqual(profile["CHANNEL_LAYERS"]["default"]["CONFIG"]["prefix"], "ufhob:production:channels")

    def test_server_profile_does_not_read_developer_dotenv(self):
        for module in ["config.settings_production", "config.settings_staging"]:
            with self.subTest(module=module):
                env = {key: os.environ[key] for key in ["PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP"] if key in os.environ}
                env.update({
                    "DJANGO_SETTINGS_MODULE": module,
                    "SECRET_KEY": "test-only-configuration-key-" * 3,
                    "ENABLE_WEBSOCKETS": "False",
                })
                result = subprocess.run([
                    sys.executable, "-c",
                    "import json; from config import settings as s; "
                    "print(json.dumps([s.DEBUG, bool(s.EMAIL_HOST_PASSWORD), bool(s.BBB_SECRET)]))",
                ], cwd=base.BASE_DIR, env=env, text=True, capture_output=True, check=True)
                self.assertEqual(json.loads(result.stdout), [False, False, False])

    def test_other_databases_are_rejected(self):
        for name in ["esfe_db", "postgres", ""]:
            with self.subTest(name=name), self.assertRaisesMessage(
                ImproperlyConfigured, "ufhob_db"
            ):
                self.load_profile(DATABASES={"default": {
                    "ENGINE": "django.db.backends.postgresql", "NAME": name,
                }})

    def test_weak_or_shared_signing_keys_are_rejected(self):
        for values in [
            {"SECRET_KEY": "short"},
            {"CARD_SIGNING_KEY": ""},
            {"CARD_SIGNING_KEY": "generate-another-independent-secret-with-at-least-50-characters"},
            {"CARD_SIGNING_KEY": "test-production-secret-" * 4},
        ]:
            with self.subTest(values=list(values)), self.assertRaises(ImproperlyConfigured):
                self.load_profile(**values)

    def test_wildcard_or_local_hosts_are_rejected(self):
        for hosts in [["*"], ["localhost"], []]:
            with self.subTest(hosts=hosts), self.assertRaises(ImproperlyConfigured):
                self.load_profile(ALLOWED_HOSTS=hosts)

    def test_wrong_public_url_is_rejected(self):
        for url in ["http://ufhob.example.com", "https://other.example.com", "https://ufhob.example.com/path"]:
            with self.subTest(url=url), self.assertRaises(ImproperlyConfigured):
                self.load_profile(BASE_URL=url)

    def test_insecure_cookies_and_test_modes_are_rejected(self):
        for values in [
            {"CSRF_COOKIE_SECURE": False},
            {"SESSION_COOKIE_SECURE": False},
            {"SECURE_SSL_REDIRECT": False},
            {"SYSTEM_SESSION_MANUAL_TEST_MODE": True},
            {"ONLINE_CLASSROOM_TIME_BYPASS": True},
            {"CSRF_TRUSTED_ORIGINS": ["http://ufhob.example.com"]},
        ]:
            with self.subTest(values=values), self.assertRaises(ImproperlyConfigured):
                self.load_profile(**values)

    def test_asgi_routes_websockets_through_origin_validation(self):
        from channels.security.websocket import OriginValidator
        from config.asgi import application

        self.assertIsInstance(application.application_mapping["websocket"], OriginValidator)

    async def test_websocket_rejects_foreign_origin_before_authentication(self):
        from channels.security.websocket import AllowedHostsOriginValidator

        called = []
        sent = []
        events = iter([
            {"type": "websocket.connect"},
            {"type": "websocket.disconnect", "code": 1000},
        ])

        async def application(scope, receive, send):
            called.append(scope)

        async def receive():
            return next(events)

        async def send(message):
            sent.append(message)

        with self.settings(ALLOWED_HOSTS=["ufhob.example.com"], DEBUG=False):
            validator = AllowedHostsOriginValidator(application)
            await validator({
                "type": "websocket", "headers": [(b"origin", b"https://attacker.example")],
            }, receive, send)
        self.assertEqual(called, [])
        self.assertEqual(sent, [{"type": "websocket.close"}])
