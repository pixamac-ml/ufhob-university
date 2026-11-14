from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from notification_center.presentation import NotificationTargetResolver


class PaymentTargetTests(SimpleTestCase):
    @patch("accounts.access_context.build_access_context")
    @patch("payments.models.Payment.objects.select_related")
    def test_payment_receipt_is_built_from_payment_id_and_revalidates_school(self, related, access):
        school = SimpleNamespace(pk=3)
        branch = SimpleNamespace(pk=8)
        candidature = SimpleNamespace(programme=SimpleNamespace(school_id=3), branch_id=8)
        payment = SimpleNamespace(receipt_number="UFHOB-TEST", inscription=SimpleNamespace(candidature=candidature))
        related.return_value.filter.return_value.first.return_value = payment
        access.return_value = SimpleNamespace(is_valid=True, scope="SCHOOL_BRANCH", school=school, branch=branch)
        notification = SimpleNamespace(event_type="payment_validated", metadata={"payment_id": 17, "receipt_url": "/wrong-path/"})
        request = RequestFactory().get("/notifications/")
        request.user = SimpleNamespace(is_staff=True)

        target = NotificationTargetResolver.resolve(notification, request)
        self.assertEqual(target, reverse("payments:receipt_detail", args=["UFHOB-TEST"]))
        access.return_value = SimpleNamespace(is_valid=True, scope="SCHOOL_BRANCH", school=SimpleNamespace(pk=4), branch=branch)
        self.assertEqual(NotificationTargetResolver.resolve(notification, request), "")
