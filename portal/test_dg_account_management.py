"""Focused DG account policy checks for UFHOB."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from accounts.access_context import build_access_context
from accounts.models import InstitutionalProfile
from branches.models import Branch
from core.models import Institution, School, SchoolBranch
from portal.dg.forms import DgRecruitmentForm, DgStaffLifecycleForm
from portal.dg.rh_service import apply_staff_lifecycle_action, can_physically_delete_staff
from portal.models import SupportAuditLog


class DgAccountManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        institution = Institution.objects.create(
            name="UFHOB test", short_name="UFHOB", address="Test", city="Test",
            phone="000", email="test@example.invalid",
        )
        cls.school = School.objects.create(institution=institution, code="TEST", short_name="École test")
        cls.other_school = School.objects.create(institution=institution, code="OTHER", short_name="Autre école")
        cls.campus = Branch.objects.create(name="Campus test", slug="dg-account-test", code="DAT")
        SchoolBranch.objects.create(school=cls.school, branch=cls.campus)
        cls.dg = cls._staff("dg-account-test", "executive_director")

    @staticmethod
    def _staff(username, position, *, branch=None, school=None, email=""):
        user = get_user_model().objects.create_user(username=username, password=None, email=email)
        profile = user.profile
        profile.user_type = "staff"
        profile.position = position
        profile.branch = branch
        profile.save()
        institutional = user.institutional_profile
        institutional.school = school
        institutional.save()
        return get_user_model().objects.get(pk=user.pk)

    def _action_form(self, user, action, **extra):
        data = {"profile_id": user.profile.pk, "action": action, "reason": "Décision test", **extra}
        form = DgStaffLifecycleForm(data)
        self.assertTrue(form.is_valid(), form.errors)
        return form

    def test_dg_creation_allows_business_position_and_rejects_technical_post(self):
        self.client.force_login(self.dg)
        url = reverse("accounts_portal:dg_recruit_staff")
        data = {"first_name": "Compte", "last_name": "Test", "position": "secretary",
                "branch": self.campus.pk, "access_scope": "BRANCH"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(get_user_model().objects.filter(first_name="Compte", institutional_profile__position="secretary").exists())
        response = self.client.post(url, {**data, "position": "super_admin", "first_name": "Interdit"})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(get_user_model().objects.filter(first_name="Interdit").exists())

    def test_four_scopes_and_school_branch_validation(self):
        global_form = DgRecruitmentForm({"first_name": "A", "last_name": "B", "position": "marketing_manager", "access_scope": "GLOBAL"})
        self.assertTrue(global_form.is_valid(), global_form.errors)
        school_data = {"first_name": "A", "last_name": "B", "position": "secretary", "access_scope": "SCHOOL", "school": self.school.pk}
        self.assertTrue(DgRecruitmentForm(school_data).is_valid())
        self.assertFalse(DgRecruitmentForm({**school_data, "school": ""}).is_valid())
        campus_data = {"first_name": "A", "last_name": "B", "position": "secretary", "access_scope": "BRANCH", "branch": self.campus.pk}
        self.assertTrue(DgRecruitmentForm(campus_data).is_valid())
        self.assertFalse(DgRecruitmentForm({**campus_data, "branch": ""}).is_valid())
        pair = {**school_data, "access_scope": "SCHOOL_BRANCH", "branch": self.campus.pk}
        self.assertTrue(DgRecruitmentForm(pair).is_valid())
        self.assertFalse(DgRecruitmentForm({**pair, "school": self.other_school.pk}).is_valid())
        SchoolBranch.objects.filter(school=self.school, branch=self.campus).update(is_active=False)
        self.assertFalse(DgRecruitmentForm(pair).is_valid())

    def test_position_and_scope_edit_revalidate_and_revoke_sessions(self):
        user = self._staff("dg-edit-test", "secretary", branch=self.campus)
        session_client = Client()
        session_client.force_login(user)
        key = session_client.session.session_key
        form = self._action_form(user, "update_assignment", position="director_of_studies",
                                 school=self.school.pk, access_scope="SCHOOL")
        apply_staff_lifecycle_action(actor=self.dg, form=form)
        user.refresh_from_db()
        self.assertEqual(user.institutional_profile.position, "director_of_studies")
        self.assertEqual(build_access_context(user).scope, "SCHOOL")
        self.assertIsNone(build_access_context(user).branch)
        self.assertFalse(Session.objects.filter(session_key=key).exists())
        bad = DgStaffLifecycleForm({"profile_id": user.profile.pk, "action": "update_assignment",
                                    "reason": "test", "position": "secretary", "access_scope": "SCHOOL_BRANCH",
                                    "school": self.other_school.pk, "branch": self.campus.pk})
        self.assertFalse(bad.is_valid())

    def test_suspend_reactivate_and_revoke_close_sessions(self):
        user = self._staff("dg-lifecycle-test", "secretary", branch=self.campus)
        session_client = Client()
        session_client.force_login(user)
        key = session_client.session.session_key
        apply_staff_lifecycle_action(actor=self.dg, form=self._action_form(user, "suspend"))
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(Session.objects.filter(session_key=key).exists())
        apply_staff_lifecycle_action(actor=self.dg, form=self._action_form(user, "reactivate"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        session_client.force_login(user)
        key = session_client.session.session_key
        apply_staff_lifecycle_action(actor=self.dg, form=self._action_form(user, "revoke"))
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertFalse(Session.objects.filter(session_key=key).exists())

    @patch("portal.dg.rh_service.send_mail")
    def test_resend_invitation_retains_account_and_rotates_token(self, send_mail):
        user = self._staff("dg-invite-test", "secretary", branch=self.campus, email="invite@example.invalid")
        old_password = user.password
        old_token = default_token_generator.make_token(user)
        count = get_user_model().objects.count()
        request = RequestFactory().post("/portal/dg/staff/action/")
        result = apply_staff_lifecycle_action(actor=self.dg, form=self._action_form(user, "resend_invitation"), request=request)
        user.refresh_from_db()
        self.assertTrue(result["ok"])
        self.assertEqual(get_user_model().objects.count(), count)
        self.assertNotEqual(user.password, old_password)
        self.assertFalse(default_token_generator.check_token(user, old_token))
        send_mail.assert_called_once()

    def test_delete_clean_account_keeps_audit(self):
        user = self._staff("dg-delete-test", "secretary", branch=self.campus)
        self.assertTrue(can_physically_delete_staff(actor=self.dg, profile=user.profile))
        result = apply_staff_lifecycle_action(actor=self.dg, form=self._action_form(user, "delete", confirm_delete="on"))
        self.assertTrue(result["ok"])
        self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())
        self.assertTrue(SupportAuditLog.objects.filter(actor=self.dg, details__contains="Suppression physique").exists())

    def test_delete_historical_and_technical_accounts_refused(self):
        user = self._staff("dg-history-test", "secretary", branch=self.campus)
        SupportAuditLog.objects.create(actor=user, action_type=SupportAuditLog.ACTION_STAFF_ASSIGNED, target_label="Historique")
        self.assertFalse(can_physically_delete_staff(actor=self.dg, profile=user.profile))
        with self.assertRaisesMessage(ValidationError, "historique institutionnel"):
            apply_staff_lifecycle_action(actor=self.dg, form=self._action_form(user, "delete", confirm_delete="on"))
        self.assertTrue(get_user_model().objects.filter(pk=user.pk).exists())
        technical = self._staff("dg-technical-test", "super_admin")
        self.client.force_login(self.dg)
        response = self.client.post(reverse("accounts_portal:dg_staff_action"),
                                    {"profile_id": technical.profile.pk, "action": "delete", "reason": "test", "confirm_delete": "on"})
        self.assertEqual(response.status_code, 403)
        edit_response = self.client.post(reverse("accounts_portal:dg_staff_edit"),
                                         {"profile_id": technical.profile.pk})
        self.assertEqual(edit_response.status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=technical.pk).exists())

    def test_dg_cannot_delete_self_or_skip_confirmation(self):
        user = self._staff("dg-no-confirm-test", "secretary", branch=self.campus)
        form = DgStaffLifecycleForm({"profile_id": user.profile.pk, "action": "delete", "reason": "test"})
        self.assertFalse(form.is_valid())
        self.assertIn("confirm_delete", form.errors)
        self.assertFalse(can_physically_delete_staff(actor=self.dg, profile=self.dg.profile))
        self.client.force_login(self.dg)
        response = self.client.post(reverse("accounts_portal:dg_staff_action"),
                                    {"profile_id": self.dg.profile.pk, "action": "delete",
                                     "reason": "test", "confirm_delete": "on"})
        self.assertEqual(response.status_code, 403)
