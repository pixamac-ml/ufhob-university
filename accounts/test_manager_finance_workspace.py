from unittest import skip
from unittest.mock import patch
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test.client import RequestFactory
from django.test import TestCase, override_settings
from django.utils import timezone
from django.urls import reverse

from accounts.models import BranchCashMovement, SensitiveActionRequest
from accounts.test_manager_workflows import (
    _create_branch,
    _create_candidature,
    _create_academic_class,
    _create_programme,
    _create_user,
)
from inscriptions.models import Inscription
from notifier.models import NotificationMessage
from payments.models import FinancialLog, Payment, PaymentAgent, PaymentCorrection
from payments.services.corrections import correct_validated_payment_amount
from accounts.services.financial_reports import build_manager_financial_report_context


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class ManagerFinanceWorkspaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = _create_branch(code="FIN", name="Annexe Finance")
        cls.other_branch = _create_branch(code="AUT", name="Autre Annexe")
        cls.programme = _create_programme()
        cls.finance_manager = _create_user(
            "finance_workspace",
            branch=cls.branch,
            position="finance_manager",
        )
        cls.payment_agent_user = _create_user(
            "payment_agent_workspace",
            branch=cls.branch,
            position="payment_agent",
        )
        cls.dg = _create_user("finance_correction_dg", branch=cls.branch, position="executive_director")
        cls.dga = _create_user("finance_correction_dga", branch=cls.branch, position="deputy_executive_director")
        # D3 : l'agent de la gestionnaire est créé automatiquement.
        PaymentAgent.objects.update_or_create(
            user=cls.finance_manager,
            defaults={"branch": cls.branch, "agent_code": "FIN001", "is_active": True},
        )
        # D3 : l'agent de la gestionnaire est créé automatiquement.
        PaymentAgent.objects.update_or_create(
            user=cls.payment_agent_user,
            defaults={"branch": cls.branch, "agent_code": "AGT001", "is_active": True},
        )

        candidature = _create_candidature(
            cls.programme,
            cls.branch,
            email="finance-student@example.com",
            status="accepted",
        )
        cls.inscription = Inscription.objects.create(
            candidature=candidature,
            amount_due=500000,
            amount_paid=0,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
        cls.payment = Payment.objects.create(
            inscription=cls.inscription,
            amount=100000,
            method=Payment.METHOD_CASH,
        )

        other_candidature = _create_candidature(
            cls.programme,
            cls.other_branch,
            email="other-student@example.com",
            status="accepted",
        )
        other_inscription = Inscription.objects.create(
            candidature=other_candidature,
            amount_due=300000,
            amount_paid=0,
            status=Inscription.STATUS_AWAITING_PAYMENT,
        )
        cls.other_payment = Payment.objects.create(
            inscription=other_inscription,
            amount=50000,
            method=Payment.METHOD_ORANGE,
        )

    @skip("D2 (20/11/2026) : postes finance / agent de paiement retirés ; la gestionnaire unique fait tout (voir accounts.test_gestionnaire_unique).")
    def test_finance_route_uses_shared_manager_workspace_and_branch_scope(self):
        self.client.force_login(self.finance_manager)

        response = self.client.get(reverse("accounts_portal:portal_finance"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "accounts/dashboard/manager_dashboard.html")
        self.assertTemplateNotUsed(response, "accounts/dashboard/finance.html")
        self.assertEqual(response.context["active_section"], "paiements")
        self.assertEqual(response.context["dashboard_shell"]["key"], "manager")
        self.assertEqual(response.context["dashboard_shell"]["role"], "finance_manager")
        navigation_keys = {
            item["nav_key"]
            for group in response.context["dashboard_shell"]["navigation"]
            for item in group["items"]
        }
        self.assertTrue({"paiements", "settings", "reenrollment"}.issubset(navigation_keys))
        self.assertFalse(
            navigation_keys & {
                "overview", "candidatures", "inscriptions", "salaires",
                "honoraires", "depenses", "caisse", "rapport", "cloture",
                "boutique", "dons",
            }
        )
        self.assertContains(response, 'data-ui-core="filter-bar"')
        self.assertContains(response, 'data-ui-core="data-table"')
        self.assertContains(response, 'data-ui-core="modal"', count=1)
        self.assertNotContains(response, 'id="modal-container"')
        self.assertContains(response, self.payment.reference)
        self.assertNotContains(response, self.other_payment.reference)

        account_response = self.client.get(
            reverse("accounts_portal:portal_finance"),
            {"section": "settings"},
        )
        self.assertEqual(account_response.status_code, 200)
        self.assertContains(account_response, "Responsable finance")
        self.assertContains(account_response, 'data-dashboard-section="settings"')

    def test_finance_manager_can_validate_only_own_branch_payment(self):
        self.client.force_login(self.finance_manager)

        response = self.client.post(
            reverse("accounts:htmx_payment_validate", args=[self.payment.pk]),
            HTTP_HX_REQUEST="true",
        )
        foreign_response = self.client.post(
            reverse("accounts:htmx_payment_validate", args=[self.other_payment.pk]),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(foreign_response.status_code, 404)
        self.payment.refresh_from_db()
        self.other_payment.refresh_from_db()
        self.assertEqual(self.payment.status, Payment.STATUS_VALIDATED)
        self.assertEqual(self.other_payment.status, Payment.STATUS_PENDING)

    @skip("D2 (20/11/2026) : postes finance / agent de paiement retirés ; la gestionnaire unique fait tout (voir accounts.test_gestionnaire_unique).")
    def test_payment_agent_can_view_but_cannot_correct(self):
        self.payment.status = Payment.STATUS_VALIDATED
        self.payment.save(update_fields=["status"])
        self.client.force_login(self.payment_agent_user)

        detail = self.client.get(
            reverse("accounts:htmx_payment_detail", args=[self.payment.pk]),
            HTTP_HX_REQUEST="true",
        )
        correction = self.client.post(
            reverse("accounts:htmx_payment_correct", args=[self.payment.pk]),
            {"new_amount": "90000", "reason": "Test", "confirmation": "CORRIGER"},
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(detail.status_code, 200)
        self.assertNotContains(detail, "Correction controlee")
        self.assertEqual(correction.status_code, 403)

    @skip("D2 (20/11/2026) : postes finance / agent de paiement retirés ; la gestionnaire unique fait tout (voir accounts.test_gestionnaire_unique).")
    def test_finance_role_cannot_call_non_finance_manager_workflow(self):
        self.client.force_login(self.finance_manager)

        response = self.client.post(reverse("accounts:htmx_manager_cash_sync"))

        self.assertEqual(response.status_code, 403)

    def test_payment_correction_authorization_does_not_require_confirmation(self):
        self.payment.amount = 150000
        self.payment.save(update_fields=["amount"])
        historical_class = _create_academic_class(self.programme, self.branch)
        self.inscription.academic_class = historical_class
        self.inscription.save(update_fields=["academic_class"])
        self.client.force_login(self.finance_manager)
        validate = self.client.post(
            reverse("accounts:htmx_payment_validate", args=[self.payment.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(validate.status_code, 200)

        modal = self.client.get(
            reverse("accounts:htmx_payment_detail", args=[self.payment.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(modal.status_code, 200)
        self.assertContains(modal, "Demander l'autorisation")
        self.assertNotContains(modal, 'name="confirmation"')

        with patch("accounts.services.sensitive_actions._generate_code", return_value="481205"):
            requested = self.client.post(
                reverse("accounts:htmx_payment_correct", args=[self.payment.pk]),
                {
                    "action": "request_authorization",
                    "new_amount": "120000",
                    "reason": "ERREUR",
                },
                HTTP_HX_REQUEST="true",
            )

        self.assertEqual(requested.status_code, 200)
        self.assertContains(requested, "Autorisation demandee")
        action = SensitiveActionRequest.objects.get(
            action_type=SensitiveActionRequest.ACTION_PAYMENT_EDIT,
            target_model="Payment",
            target_id=self.payment.pk,
        )
        self.assertEqual(action.previous_state, {"amount": 150000})
        self.assertEqual(action.requested_state, {"amount": 120000, "delta": -30000})
        self.assertEqual(action.reason, "ERREUR")
        self.assertEqual(action.branch, self.branch)
        self.assertEqual(action.otp_display_code, "481205")

        notifications = NotificationMessage.objects.filter(
            event_type="sensitive_action_otp",
            recipient__in=[self.dg, self.dga],
            legacy_object_id=str(action.pk),
        )
        self.assertEqual(notifications.values("recipient_id").distinct().count(), 2)
        for notification in notifications:
            self.assertEqual(notification.title, "Demande de correction de paiement")
            self.assertIn("ERREUR", notification.body)
            self.assertIn("120000 FCFA", notification.body)
            self.assertNotIn("481205", notification.body)
            self.assertNotIn("481205", str(notification.metadata))
            self.assertIn("section=coupons", notification.metadata["action_url"])

        self.client.force_login(self.dg)
        coupons = self.client.get(
            reverse("accounts_portal:dg_section", kwargs={"section": "coupons"}),
            {"scope_branch_id": self.branch.pk},
        )
        self.assertEqual(coupons.status_code, 200)
        self.assertContains(coupons, "Corrections financières")
        self.assertContains(coupons, "481205")
        self.assertContains(coupons, self.payment.reference)
        self.assertContains(coupons, "Test Jean")
        self.assertContains(coupons, "120")
        self.assertEqual(len(coupons.context["financial_corrections"]), 1)
        self.assertNotContains(coupons, self.other_payment.reference)

        self.client.force_login(self.finance_manager)
        confirm_url = reverse("accounts:htmx_payment_correct_confirm_otp", args=[self.payment.pk])
        wrong_code = self.client.post(
            confirm_url,
            {
                "action": "apply_correction",
                "otp_request_id": action.pk,
                "otp_code": "999999",
                "confirmation": "CORRIGER",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(wrong_code.status_code, 200)
        self.assertContains(wrong_code, "Code d&#x27;autorisation incorrect.")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, 150000)

        historical_cancelled = SensitiveActionRequest.objects.create(
            branch=action.branch,
            action_type=action.action_type,
            target_model=action.target_model,
            target_id=action.target_id,
            reason="Ancienne demande annulee",
            previous_state=action.previous_state,
            requested_state=action.requested_state,
            requested_by=action.requested_by,
            otp_code_hash=action.otp_code_hash,
            status=SensitiveActionRequest.STATUS_CANCELLED,
            expires_at=timezone.now() + timedelta(minutes=5),
        )
        cancelled = self.client.post(
            confirm_url,
            {
                "otp_request_id": historical_cancelled.pk,
                "otp_code": "481205",
                "confirmation": "CORRIGER",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertContains(cancelled, "Cette demande a ete annulee.")

        expired_request = SensitiveActionRequest.objects.create(
            branch=action.branch,
            action_type=action.action_type,
            target_model=action.target_model,
            target_id=action.target_id,
            reason="Demande expiree",
            previous_state=action.previous_state,
            requested_state=action.requested_state,
            requested_by=action.requested_by,
            otp_code_hash=action.otp_code_hash,
            status=SensitiveActionRequest.STATUS_PENDING,
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        expired = self.client.post(
            confirm_url,
            {
                "otp_request_id": expired_request.pk,
                "otp_code": "481205",
                "confirmation": "CORRIGER",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(expired.status_code, 200)
        self.assertContains(expired, "Ce code a expire. Demandez une nouvelle autorisation.")
        expired_request.refresh_from_db()
        self.assertEqual(expired_request.status, SensitiveActionRequest.STATUS_EXPIRED)

        # The class may have been closed after the original payment.  The OTP
        # correction must still update only the financial history.
        historical_class.is_active = False
        historical_class.save(update_fields=["is_active"])

        applied = self.client.post(
            confirm_url,
            {
                "action": "apply_correction",
                # The endpoint resolves the newest active request despite old
                # cancelled/expired rows for the same payment.
                "otp_code": "481205",
                "confirmation": "CORRIGER",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(applied.status_code, 200)
        self.assertContains(applied, "Correction effectuee")
        self.assertContains(applied, "Historique des corrections")
        self.assertContains(applied, "Montant initial")
        self.assertContains(applied, "Reste à payer")
        self.payment.refresh_from_db()
        self.inscription.refresh_from_db()
        action.refresh_from_db()
        self.assertEqual(self.payment.amount, 120000)
        self.assertEqual(self.inscription.amount_paid, 120000)
        self.assertEqual(action.status, SensitiveActionRequest.STATUS_APPROVED)
        self.assertEqual(action.otp_display_code, "")
        historical_class.refresh_from_db()
        self.inscription.refresh_from_db()
        self.assertFalse(historical_class.is_active)
        self.assertEqual(self.inscription.academic_class_id, historical_class.pk)
        correction = PaymentCorrection.objects.get(payment=self.payment)
        self.assertEqual(correction.old_amount, 150000)
        self.assertEqual(correction.new_amount, 120000)
        self.assertEqual(correction.delta_amount, -30000)
        original_movement = BranchCashMovement.objects.get(
            branch=self.branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=self.payment.reference,
        )
        adjustment_movement = BranchCashMovement.objects.get(
            branch=self.branch,
            source=BranchCashMovement.SOURCE_ADJUSTMENT,
            source_reference=f"{self.payment.reference}:COR:{correction.pk}",
        )
        self.assertEqual(original_movement.amount, 150000)
        self.assertEqual(adjustment_movement.movement_type, BranchCashMovement.TYPE_OUT)
        self.assertEqual(adjustment_movement.amount, 30000)
        financial_log = FinancialLog.objects.get(correction=correction)
        self.assertEqual(financial_log.metadata["original_cash_movement_id"], original_movement.pk)
        self.assertEqual(financial_log.metadata["adjustment_cash_movement_id"], adjustment_movement.pk)

        report = build_manager_financial_report_context(
            branch=self.branch,
            request=RequestFactory().get("/", {"report_period": "year"}),
        )
        self.assertEqual(report["report_summary"]["student_revenue"], 150000)
        self.assertEqual(report["report_summary"]["adjustment_negative"], 30000)
        self.assertEqual(report["report_summary"]["net_result"], 120000)

    def test_payment_correction_allows_active_class(self):
        active_class = _create_academic_class(self.programme, self.branch)
        self.inscription.academic_class = active_class
        self.inscription.save(update_fields=["academic_class"])
        self.payment.amount = 150000
        self.payment.status = Payment.STATUS_VALIDATED
        self.payment.save()

        correction = correct_validated_payment_amount(
            payment=self.payment,
            new_amount=130000,
            reason="Erreur de saisie",
            actor=self.finance_manager,
        )

        self.payment.refresh_from_db()
        self.inscription.refresh_from_db()
        self.assertEqual(self.payment.amount, 130000)
        self.assertEqual(correction.delta_amount, -20000)
        self.assertEqual(self.inscription.amount_paid, 130000)
        self.assertTrue(active_class.is_active)
        original_movement = BranchCashMovement.objects.get(
            branch=self.branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=self.payment.reference,
        )
        adjustment_movement = BranchCashMovement.objects.get(
            branch=self.branch,
            source=BranchCashMovement.SOURCE_ADJUSTMENT,
            source_reference=f"{self.payment.reference}:COR:{correction.pk}",
        )
        self.assertEqual(original_movement.amount, 150000)
        self.assertEqual(adjustment_movement.movement_type, BranchCashMovement.TYPE_OUT)
        self.assertEqual(adjustment_movement.amount, 20000)
        self.client.force_login(self.finance_manager)
        export = self.client.get(reverse("accounts:export_payments_csv"))
        self.assertEqual(export.status_code, 200)
        self.assertContains(export, "Montant initial (FCFA)")
        self.assertContains(export, "Paiement ajuste")
        self.assertContains(export, self.payment.reference)
        self.assertContains(export, "Oui")

    def test_payment_correction_positive_adjustment_credits_cash(self):
        self.payment.amount = 130000
        self.payment.status = Payment.STATUS_VALIDATED
        self.payment.save()

        correction = correct_validated_payment_amount(
            payment=self.payment,
            new_amount=150000,
            reason="Omission de saisie",
            actor=self.finance_manager,
        )

        self.payment.refresh_from_db()
        self.inscription.refresh_from_db()
        adjustment_movement = BranchCashMovement.objects.get(
            branch=self.branch,
            source=BranchCashMovement.SOURCE_ADJUSTMENT,
            source_reference=f"{self.payment.reference}:COR:{correction.pk}",
        )
        self.assertEqual(self.payment.amount, 150000)
        self.assertEqual(self.inscription.amount_paid, 150000)
        self.assertEqual(correction.delta_amount, 20000)
        self.assertEqual(adjustment_movement.movement_type, BranchCashMovement.TYPE_IN)
        self.assertEqual(adjustment_movement.amount, 20000)

    def test_new_inscription_inactive_class_is_still_refused(self):
        inactive_class = _create_academic_class(self.programme, self.branch)
        inactive_class.is_active = False
        inactive_class.save(update_fields=["is_active"])
        candidature = _create_candidature(
            self.programme,
            self.branch,
            email="inactive-class-student@example.com",
            status="accepted",
        )

        with self.assertRaises(ValidationError):
            Inscription.objects.create(
                candidature=candidature,
                academic_class=inactive_class,
                amount_due=500000,
            )

    def test_payment_correction_stays_scoped_to_manager_branch(self):
        Payment.objects.filter(pk=self.other_payment.pk).update(status=Payment.STATUS_VALIDATED)
        self.client.force_login(self.finance_manager)

        response = self.client.post(
            reverse("accounts:htmx_payment_correct", args=[self.other_payment.pk]),
            {
                "action": "request_authorization",
                "new_amount": "40000",
                "reason": "ERREUR",
            },
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 404)
