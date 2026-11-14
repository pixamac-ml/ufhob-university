from types import SimpleNamespace

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from notification_center.views import _role_notification_destination


class NotificationShellRoutingTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_notification_entry_uses_role_workspace_routes(self):
        expected = {
            "student": f"{reverse('portal_student:dashboard')}?section=messages",
            "teacher": f"{reverse('accounts_portal:portal_teacher')}?section=notifications",
            "director_of_studies": f"{reverse('accounts_portal:portal_director')}?section=notifications",
            "secretary": f"{reverse('accounts_portal:portal_secretary')}?section=notifications",
            "executive_director": f"{reverse('accounts_portal:portal_dg')}?section=messaging",
            "it_support": reverse("accounts_portal:it_notifications_workspace"),
            "super_admin": reverse("superadmin:dashboard"),
        }
        for position, destination in expected.items():
            with self.subTest(position=position):
                request = self.factory.get("/notifications/")
                request.access_context = SimpleNamespace(position=position)
                self.assertEqual(_role_notification_destination(request), destination)
