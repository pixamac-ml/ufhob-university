import json
from urllib.parse import unquote
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings

from core import context_processors, views


class CookieConsentPersistenceTests(SimpleTestCase):
    def test_both_choices_produce_javascript_readable_persistent_cookies(self):
        for status in ("accepted", "rejected"):
            with self.subTest(status=status):
                request = RequestFactory().post(
                    "/cookies/consent/", json.dumps({"status": status}),
                    content_type="application/json",
                )
                response = views.set_cookie_preferences(request)
                cookie = response.cookies[views.COOKIE_CONSENT_NAME]
                # coded_value is the actual on-the-wire cookie, not Django's
                # already-unescaped value (which hid the original regression).
                consent = json.loads(unquote(cookie.coded_value))
                self.assertEqual(consent["status"], status)
                self.assertEqual(consent["version"], views.COOKIE_CONSENT_VERSION)
                self.assertTrue(consent["necessary"])
                self.assertIn("timestamp", consent)
                self.assertEqual(cookie["max-age"], 180 * 24 * 60 * 60)
                self.assertTrue(cookie["expires"])
                self.assertEqual(cookie["path"], "/")
                self.assertEqual(cookie["samesite"], "Lax")

    @override_settings(DEBUG=False)
    def test_cookie_secure_attribute_follows_the_actual_connection(self):
        for secure in (True, False):
            with self.subTest(secure=secure):
                request = RequestFactory().post(
                    "/cookies/consent/", '{"status":"rejected"}',
                    content_type="application/json", secure=secure,
                )
                response = views.set_cookie_preferences(request)
                self.assertEqual(bool(response.cookies[views.COOKIE_CONSENT_NAME]["secure"]), secure)

    def test_invalid_payloads_do_not_create_consent(self):
        for payload in ("[]", "null", "true", "{}", '{"status":"closed"}', '{"status":[]}', "invalid"):
            with self.subTest(payload=payload):
                response = views.set_cookie_preferences(RequestFactory().post(
                    "/cookies/consent/", payload, content_type="application/json",
                ))
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(views.COOKIE_CONSENT_NAME, response.cookies)

    @patch("core.context_processors.get_published_legal_links", return_value=[])
    def test_template_policy_version_is_the_endpoint_version(self, _links):
        with patch.object(views, "COOKIE_CONSENT_VERSION", 73):
            context = context_processors.public_legal_links(RequestFactory().get("/"))
        self.assertEqual(context["cookie_consent_version"], 73)
        self.assertEqual(context["cookie_consent_max_age"], views.COOKIE_CONSENT_MAX_AGE)
