from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from accounts.access_context import build_access_context
from branches.models import Branch
from core.models import Institution, School, SchoolBranch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from admissions.models import Candidature
from portal.permissions import get_post_login_portal_url, user_requires_branch_assignment
from portal.student.widgets.academics import get_student_academic_snapshot
from students.models import Student


class UFHOBStudentContextTests(TestCase):
    def setUp(self):
        institution = Institution.objects.create(
            name="UFHOB", short_name="UFHOB", address="Campus", city="Bamako",
            phone="000", email="test@example.invalid",
        )
        self.school = School.objects.create(institution=institution, code="FATEC", short_name="FATEC")
        self.other_school = School.objects.create(institution=institution, code="ESMED", short_name="ESMED")
        self.branch = Branch.objects.create(name="Moribabougou", code="MBG", slug="mbg")
        SchoolBranch.objects.create(school=self.school, branch=self.branch)
        SchoolBranch.objects.create(school=self.other_school, branch=self.branch)
        cycle = Cycle.objects.create(name="Licence", min_duration_years=1, max_duration_years=1)
        diploma = Diploma.objects.create(name="Diplôme", level="superieur")
        filiere = Filiere.objects.create(name="Informatique")
        self.programme = Programme.objects.create(
            title="Génie logiciel", school=self.school, cycle=cycle, filiere=filiere,
            diploma_awarded=diploma, duration_years=1, short_description="Test", description="Test",
        )
        self.year = AcademicYear.objects.create(name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 8, 31))

    def _student(self):
        user = get_user_model().objects.create_user(username="student-fatec", password="pass")
        user.profile.role = "student"
        user.profile.save(update_fields=["role", "updated_at"])
        candidature = Candidature.objects.create(
            programme=self.programme, branch=self.branch, academic_year=self.year.name,
            birth_date=date(2000, 1, 1), first_name="Test", last_name="FATEC",
            email="student-fatec@example.invalid", gender="female", phone="000",
            birth_place="Bamako", status="accepted",
        )
        inscription = Inscription.objects.create(candidature=candidature, amount_due=100, status="active")
        return user, inscription

    def test_context_is_derived_from_enrollment_without_institutional_profile(self):
        user, inscription = self._student()
        student = Student.objects.create(user=user, inscription=inscription, matricule="UFHOB-TEST-1")
        academic_class = AcademicClass.objects.create(
            programme=self.programme, branch=self.branch, academic_year=self.year, level="Première année"
        )
        enrollment = AcademicEnrollment.objects.create(
            inscription=inscription, student=user, programme=self.programme, branch=self.branch,
            academic_year=self.year, academic_class=academic_class,
        )
        context = build_access_context(user)
        snapshot = get_student_academic_snapshot(user)
        self.assertEqual(context.position, "student")
        self.assertEqual(context.school, self.school)
        self.assertEqual(context.branch, self.branch)
        self.assertTrue(context.is_valid)
        self.assertEqual(snapshot["academic_programme"], self.programme)
        self.assertFalse(user_requires_branch_assignment(user))
        self.assertEqual(get_post_login_portal_url(user), "/portal/student-dashboard/")

    def test_missing_class_keeps_programme_and_campus_context(self):
        user, inscription = self._student()
        student = Student.objects.create(user=user, inscription=inscription, matricule="UFHOB-TEST-2")
        snapshot = get_student_academic_snapshot(user)
        self.assertEqual(snapshot["academic_programme"], self.programme)
        self.assertEqual(student.inscription.candidature.branch, self.branch)
        self.assertEqual(snapshot["academic_status"], "pending")
        self.assertNotIn("Aucune annexe", snapshot["academic_status_message"])
