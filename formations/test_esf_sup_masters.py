from copy import deepcopy
from datetime import date

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import AcademicClass, AcademicYear, EC, Semester, UE
from branches.models import Branch
from core.models import Institution, School, SchoolBranch
from formations.esf_sup_masters import EXPECTED, find_school, install_masters, load_manifest
from formations.models import Cycle, Diploma, Filiere, Programme


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"])
class ESFSupMasterInstallationTests(TestCase):
    def setUp(self):
        self.institution = Institution.objects.create(
            name="Université test", short_name="UFHOB", address="Adresse test",
            city="Ville test", phone="000", email="university@example.test",
        )
        self.school = School.objects.create(
            institution=self.institution, code="ESFÉ", short_name="ESFé Sup", order=99,
        )
        self.other = School.objects.create(institution=self.institution, code="ESGA", short_name="ESGA")
        self.cycle = Cycle.objects.create(name="Master", min_duration_years=2, max_duration_years=2)
        self.diploma = Diploma.objects.create(name="Master", level="superieur")
        self.filiere = Filiere.objects.create(name="Sciences de la Santé")
        self.campus = Branch.objects.create(name="Campus test", code="TST", slug="campus-test")

    def configure_academic_context(self):
        SchoolBranch.objects.create(school=self.school, branch=self.campus)
        return AcademicYear.objects.create(
            name="2040-2041", start_date=date(2040, 10, 1),
            end_date=date(2041, 7, 31), is_active=True,
        )

    def test_dry_run_missing_context_and_apply_catalogue_do_not_invent_classes(self):
        plan = install_masters()
        self.assertEqual(plan["created"]["programmes"], 7)
        self.assertEqual(Programme.objects.count(), 0)
        self.assertEqual(self.school.short_name, "ESFé Sup")
        result = install_masters(apply=True)
        self.assertEqual(result["created"]["programmes"], 7)
        self.assertEqual(result["created"]["programme_years"], 14)
        self.assertEqual(len(result["blockers"]), 2)
        self.assertFalse(AcademicClass.objects.exists())
        self.assertFalse(AcademicYear.objects.exists())
        self.assertFalse(SchoolBranch.objects.exists())
        self.assertEqual(find_school().pk, self.school.pk)
        self.assertEqual(School.objects.count(), 2)

    def test_master_licence_distinction_and_configured_campus(self):
        year = self.configure_academic_context()
        licence = Cycle.objects.create(name="Licence", min_duration_years=3, max_duration_years=3)
        original = Programme.objects.create(
            title="Nutrition", cycle=licence, diploma_awarded=self.diploma,
            filiere=self.filiere, school=self.school, duration_years=3,
            description="Test licence", short_description="Test licence",
        )
        result = install_masters(apply=True)
        original.refresh_from_db()
        self.assertEqual(original.cycle_id, licence.pk)
        masters = Programme.objects.filter(school=self.school, cycle=self.cycle)
        self.assertEqual(masters.count(), 7)
        self.assertEqual(masters.available_on(self.campus).count(), 7)
        self.assertEqual(AcademicClass.objects.filter(academic_year=year).count(), 14)
        self.assertEqual(set(AcademicClass.objects.values_list("level", flat=True)), {"M1", "M2"})
        self.assertEqual(result["created"]["semesters"], 14)
        self.assertEqual(result["created"]["ues"], 58)
        self.assertEqual(EC.objects.count(), 0)  # Source coefficients are absent.
        self.assertFalse(Semester.objects.filter(academic_class__programme__title__contains="Manager").exists())
        self.assertFalse(Semester.objects.filter(academic_class__programme__title__contains="Nutrition", number=4).exists())
        self.assertFalse(Semester.objects.filter(academic_class__programme__title__contains="Épidémiologie", number=4).exists())
        repeat = install_masters(apply=True)
        self.assertTrue(all(value == 0 for value in repeat["created"].values()))
        self.assertTrue(all(value == 0 for value in repeat["updated"].values()))

    def test_semester_source_credit_conflict_stops_and_rolls_back(self):
        manifest = deepcopy(load_manifest())
        manifest["programmes"][0]["semesters"][0]["credits"] = 29
        with self.assertRaisesMessage(ValidationError, "SOURCE_CONFLICT"):
            install_masters(apply=True, manifest=manifest)
        self.assertFalse(Programme.objects.exists())
        self.school.refresh_from_db()
        self.assertEqual(self.school.short_name, "ESFé Sup")

    def test_duplicate_school_and_cycle_stop_transaction(self):
        School.objects.create(institution=self.institution, code="ESF2", short_name="ESF-Sup")
        with self.assertRaises(ValidationError):
            install_masters(apply=True)
        self.assertEqual(Programme.objects.count(), 0)

    def test_multiple_master_cycles_are_not_chosen_arbitrarily(self):
        Cycle.objects.create(name="Cycle Master", min_duration_years=2, max_duration_years=2)
        with self.assertRaises(ValidationError):
            install_masters(apply=True)
        self.assertEqual(Programme.objects.count(), 0)

    def test_only_documented_ec_values_are_imported_and_conflicts_rollback(self):
        self.configure_academic_context()
        manifest = deepcopy(load_manifest())
        for programme in manifest["programmes"]:
            programme["semesters"] = []
        manifest["programmes"][0]["semesters"] = [{
            "year": 1, "number": 1, "credits": 3, "confidence": "HIGH",
            "sources": [{"path": "test-fixture"}], "ues": [{
                "code": "TEST", "title": "UE de test", "credits": 3, "coefficient": 2,
                "ecs": [{"title": "EC de test", "credits": 3, "coefficient": 2}],
            }],
        }]
        result = install_masters(apply=True, manifest=manifest)
        self.assertEqual(result["created"]["ecs"], 1)
        repeat = install_masters(apply=True, manifest=manifest)
        self.assertEqual(repeat["created"]["ecs"], 0)
        manifest["programmes"][0]["semesters"][0]["ues"][0]["credits"] = 4
        with self.assertRaisesMessage(ValidationError, "SOURCE_CONFLICT"):
            install_masters(apply=True, manifest=manifest)
        self.assertEqual(EC.objects.get().credit_required, 3)

    def test_public_school_programme_filter_details_and_other_school_isolation(self):
        self.configure_academic_context()
        install_masters(apply=True)
        other = Programme.objects.create(
            title="Autre programme test", school=self.other, cycle=self.cycle,
            filiere=self.filiere, diploma_awarded=self.diploma,
            duration_years=2, short_description="Test", description="Test",
        )
        for code in ("ESMED", "FATEC"):
            School.objects.create(institution=self.institution, code=code, short_name=code)
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ESFé Sup")
        # SQLite NOCASE is ASCII-only; PostgreSQL live checks also exercise
        # the lowercase accented route produced by the public navigation.
        response = self.client.get(reverse("core:school_detail", kwargs={"code": self.school.code}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["programmes"]), 7)
        self.assertNotIn(other.pk, [p.pk for p in response.context["programmes"]])
        listing = self.client.get(reverse("formations:list"), {"school": self.school.code})
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.context["programme_count"], 7)
        self.assertTrue(all(p.school_id == self.school.pk for p in listing.context["programmes"]))
        for programme in listing.context["programmes"]:
            self.assertContains(listing, programme.title)
            detail = self.client.get(programme.get_absolute_url())
            self.assertEqual(detail.status_code, 200)
            self.assertContains(detail, f">\n      {programme.title}\n", html=False)
            self.assertEqual(detail.context["programme"].school_id, self.school.pk)
            self.assertFalse(detail.context["can_apply"])
        other_listing = self.client.get(reverse("formations:list"), {"school": self.other.code})
        self.assertEqual(list(other_listing.context["programmes"]), [other])
        self.assertEqual(self.client.get(reverse("formations:list"), {"school": "unknown"}).status_code, 404)
        self.assertTrue(all(p.school_id == self.other.pk for p in self.client.get(other.get_absolute_url()).context["related_programmes"]))
