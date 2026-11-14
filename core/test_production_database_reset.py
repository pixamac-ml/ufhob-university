from django.contrib.auth import get_user_model
from django.test import TestCase

from branches.models import Branch
from core.models import Institution, School
from core.services.production_database_reset import (
    build_production_reset_plan,
    execute_production_reset,
    validate_execute_plan,
)


class ProductionDatabaseResetTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="Université UFHOB de test",
            short_name="UFHOB",
            address="Bamako",
            city="Bamako",
            phone="00000000",
            email="contact@example.test",
        )
        self.school = School.objects.create(
            institution=self.institution,
            code="ESMED",
            short_name="ESMed",
        )
        self.legacy_school = School.objects.create(
            institution=self.institution,
            code="ESFÉ",
            short_name="ESFé Sup",
        )
        self.branch = Branch.objects.create(name="Campus test", code="TST", slug="campus-test")
        user_model = get_user_model()
        self.bootstrap = user_model.objects.create_superuser(
            username="bootstrap-admin",
            email="bootstrap@example.test",
            password="bootstrap-password",
        )
        self.demo_user = user_model.objects.create_user(
            username="demo-user",
            password="demo-password",
        )

    def test_preserves_ufhob_structure_and_removes_only_operational_data(self):
        plan = build_production_reset_plan(preserve_usernames=[self.bootstrap.username])

        self.assertEqual(plan.structural_keep["Écoles"][0]["code"], "ESMED")
        self.assertEqual(plan.structural_remove, {})
        self.assertIn("auth.User", plan.delete_counts)
        self.assertEqual(validate_execute_plan(plan), [self.bootstrap.pk])

        execute_production_reset(plan)

        user_model = get_user_model()
        self.assertEqual(list(user_model.objects.values_list("username", flat=True)), [self.bootstrap.username])
        self.assertTrue(Institution.objects.filter(pk=self.institution.pk).exists())
        self.assertTrue(School.objects.filter(pk=self.school.pk).exists())
        self.assertTrue(School.objects.filter(pk=self.legacy_school.pk).exists())
        self.assertTrue(Branch.objects.filter(pk=self.branch.pk).exists())

        # A second execution is safe once the database is already clean.
        second_plan = build_production_reset_plan(preserve_usernames=[self.bootstrap.username])
        self.assertEqual(execute_production_reset(second_plan), {})
