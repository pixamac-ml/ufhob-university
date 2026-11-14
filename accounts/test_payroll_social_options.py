from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from decimal import Decimal

from django.test import TestCase

from accounts.forms import PayrollEntryForm
from accounts.models import Profile, PayrollEntry, TeacherHonorariumEntry
from branches.models import Branch


class PayrollSocialOptionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.branch = Branch.objects.create(name="Campus RH", code="CRH", slug="campus-rh")
        cls.user = get_user_model().objects.create_user(
            username="salarie-rh", first_name="Awa", last_name="Traore"
        )
        cls.profile = Profile.objects.get(user=cls.user)
        cls.profile.user_type = "staff"
        cls.profile.position = "secretary"
        cls.profile.branch = cls.branch
        cls.profile.salary_base = 100_000
        cls.profile.amo_applicable = True
        cls.profile.inps_applicable = True
        cls.profile.amo_rate = Decimal("10.00")
        cls.profile.inps_rate = Decimal("5.00")
        cls.profile.save()

    def test_net_salary_covers_all_social_combinations(self):
        cases = (
            (True, True, Decimal("10.00"), Decimal("5.00"), 15_000, 85_000),
            (True, False, Decimal("10.00"), Decimal("5.00"), 10_000, 90_000),
            (False, True, Decimal("10.00"), Decimal("5.00"), 5_000, 95_000),
            (False, False, Decimal("10.00"), Decimal("5.00"), 0, 100_000),
        )
        for amo, inps, amo_rate, inps_rate, expected_social, expected in cases:
            with self.subTest(amo=amo, inps=inps):
                entry = PayrollEntry.objects.create(
                    branch=self.branch,
                    employee=self.user,
                    period_month="2045-01-01",
                    base_salary=100_000,
                    amo_applicable=amo,
                    inps_applicable=inps,
                    amo_rate=amo_rate,
                    inps_rate=inps_rate,
                )
                self.assertEqual(entry.social_deductions, expected_social)
                self.assertEqual(entry.net_salary, expected)
                entry.delete()

    def test_payroll_form_exposes_monthly_social_override(self):
        form = PayrollEntryForm(
            data={
                "base_salary": "100000",
                "allowances": "0",
                "amo_applicable": "on",
                "amo_rate": "10",
                "inps_applicable": "",
                "inps_rate": "5",
                "advances": "0",
                "notes": "Override janvier",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)
        entry = form.save(commit=False)
        entry.branch = self.branch
        entry.employee = self.user
        entry.period_month = "2045-02-01"
        entry.save()
        self.assertTrue(entry.amo_applicable)
        self.assertFalse(entry.inps_applicable)
        self.assertEqual(entry.net_salary, 90_000)
        self.assertEqual(entry.amo_amount, 10_000)
        self.assertEqual(entry.inps_amount, 0)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.amo_applicable)
        self.assertTrue(self.profile.inps_applicable)

    def test_payroll_form_never_exposes_social_amount_inputs(self):
        form = PayrollEntryForm()
        self.assertNotIn("amo_amount", form.fields)
        self.assertNotIn("inps_amount", form.fields)
        self.assertNotIn("deductions", form.fields)
        self.assertEqual(form.fields["amo_rate"].label, "Taux AMO (%)")
        self.assertEqual(form.fields["inps_rate"].label, "Taux INPS (%)")
        self.assertIn("pourcentage", form.fields["amo_rate"].help_text)

    def test_disabled_social_rate_can_be_left_blank(self):
        form = PayrollEntryForm(
            data={
                "base_salary": "100000",
                "allowances": "0",
                "amo_applicable": "",
                "amo_rate": "",
                "inps_applicable": "",
                "inps_rate": "",
                "advances": "0",
                "notes": "",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_moniteur_cannot_receive_pedagogical_honorarium(self):
        self.profile.position = "moniteur"
        self.profile.save(update_fields=["position", "updated_at"])
        with self.assertRaises(ValidationError):
            TeacherHonorariumEntry.objects.create(
                branch=self.branch,
                teacher=self.user,
                period_month="2045-03-01",
                hourly_rate=5_000,
                validated_hours=1,
            )
