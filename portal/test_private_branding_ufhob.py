from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.test import TestCase
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from accounts.access_context import build_access_context
from branches.models import Branch
from core.models import Institution, School, SchoolBranch


class UFHOBPrivateBrandingTests(TestCase):
    def setUp(self):
        institution = Institution.objects.create(
            name="UFHOB", short_name="UFHOB", address="Campus", city="Bamako",
            phone="000", email="test@example.invalid",
        )
        self.school = School.objects.create(institution=institution, code="FATEC", short_name="FATEC")
        self.branch = Branch.objects.create(name="Moribabougou", code="MBG", slug="moribabougou")
        SchoolBranch.objects.create(school=self.school, branch=self.branch)
        self.user = get_user_model().objects.create_user(
            username="de-fatec", email="de-fatec@example.invalid", password=None, is_staff=True, is_active=True,
        )
        profile = self.user.profile
        profile.position = "director_of_studies"
        profile.branch = self.branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        institutional = self.user.institutional_profile
        institutional.position = "director_of_studies"
        institutional.school = self.school
        institutional.branch = self.branch
        institutional.access_scope = "SCHOOL_BRANCH"
        institutional.save()

    def test_fatec_activation_uses_private_ufhob_shell(self):
        url = reverse(
            "accounts_portal:dg_staff_activation",
            args=[urlsafe_base64_encode(force_bytes(self.user.pk)), default_token_generator.make_token(self.user)],
        )
        response = self.client.get(url)
        body = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "UFHOB")
        self.assertContains(response, "FATEC")
        self.assertContains(response, "Directeur des études")
        self.assertNotIn("ESFE", body)
        self.assertNotIn("cookie-banner", body)
        self.assertNotIn("footer", body.lower())

    def test_login_and_password_reset_use_the_ufhob_auth_shell(self):
        for url_name in ("login", "password_reset"):
            response = self.client.get(reverse(url_name))
            body = response.content.decode()

            self.assertEqual(response.status_code, 200)
            self.assertIn("UFHOB", body)
            self.assertNotIn("ESFE", body)
            self.assertNotIn("cookie-banner", body)

    def test_payment_receipt_uses_the_school_and_campus_context(self):
        receipt = render_to_string(
            "documents/payment_receipt/payment_receipt.html",
            {
                "school": "FATEC",
                "branch_name": "Moribabougou",
                "student_name": "Étudiant FATEC",
                "academic_year": "2026-2027",
            },
        )

        self.assertIn("UFHOB", receipt)
        self.assertIn("FATEC", receipt)
        self.assertIn("Moribabougou", receipt)
        self.assertNotIn("ESFE", receipt)

    def test_an_esga_staff_context_never_falls_back_to_fatec(self):
        esga = School.objects.create(
            institution=self.school.institution,
            code="ESGA",
            short_name="ESGA",
        )
        SchoolBranch.objects.create(school=esga, branch=self.branch)
        user = get_user_model().objects.create_user(
            username="de-esga", email="de-esga@example.invalid", password="test-password", is_staff=True,
        )
        profile = user.profile
        profile.position = "director_of_studies"
        profile.branch = self.branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        institutional = user.institutional_profile
        institutional.position = "director_of_studies"
        institutional.school = esga
        institutional.branch = self.branch
        institutional.access_scope = "SCHOOL_BRANCH"
        institutional.save()

        context = build_access_context(user)

        self.assertEqual(context.school.code, "ESGA")
        self.assertNotEqual(context.school.code, "FATEC")
