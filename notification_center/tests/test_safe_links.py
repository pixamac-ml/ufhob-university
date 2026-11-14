from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase

from notification_center.presentation import get_safe_action_url


class LegacyNotificationLinkSafetyTests(SimpleTestCase):
    def test_backslash_network_path_cannot_escape_the_application(self):
        request = RequestFactory().get("/notifications/")
        message = SimpleNamespace(metadata={"action_url": "/\\evil.example/phishing"}, event=None, event_type="legacy")
        self.assertEqual(get_safe_action_url(message, request), "")

    def test_internal_path_is_preserved(self):
        request = RequestFactory().get("/notifications/")
        message = SimpleNamespace(metadata={"action_url": "/payments/receipt/RC-1/"}, event=None, event_type="legacy")
        self.assertEqual(get_safe_action_url(message, request), "/payments/receipt/RC-1/")
