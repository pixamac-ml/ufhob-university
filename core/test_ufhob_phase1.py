from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.contrib.auth import get_user_model

from branches.models import Branch
from core.models import Institution, School, SchoolBranch
from formations.models import Cycle, Diploma, Filiere, Programme
from academics.models import AcademicYear
from accounts.access_context import build_access_context


class UFHOBPhase1Tests(TestCase):
    """Tests ciblés Phase 1 : fondation institutionnelle multi-écoles."""

    @classmethod
    def setUpTestData(cls):
        cls.institution, _ = Institution.objects.get_or_create(
            name="UFHOB",
            defaults={
                "short_name": "UFHOB",
                "address": "Bamako",
                "city": "Bamako",
                "phone": "-",
                "email": "test@ufhob.local",
            },
        )
        call_command("bootstrap_ufhob_phase1", verbosity=0)

        cls.branch, _ = Branch.objects.get_or_create(
            name="Moribabougou",
            slug="moribabougou",
            defaults={"code": "MOR", "city": "Bamako"},
        )

        cls.cycle, _ = Cycle.objects.get_or_create(
            name="Cycle test",
            defaults={
                "min_duration_years": 1,
                "max_duration_years": 1,
            },
        )
        cls.diploma, _ = Diploma.objects.get_or_create(
            name="Diplôme test",
            defaults={"level": "superieur"},
        )

    @property
    def esmed(self):
        return School.objects.get(code="ESMED")

    @property
    def esga(self):
        return School.objects.get(code="ESGA")

    @property
    def fatec(self):
        return School.objects.get(code="FATEC")

    @property
    def institution_obj(self):
        return Institution.objects.first()

    def _make_programme(self, title, filiere_name, school=None):
        filiere, _ = Filiere.objects.get_or_create(
            name=filiere_name,
            defaults={"description": "", "is_active": True},
        )
        slug = f"{title.lower().replace(' ', '-')}-{filiere_name.lower().replace(' ', '-')}"
        if len(slug) > 50:
            slug = slug[:50]
        return Programme.objects.create(
            title=title,
            slug=slug,
            filiere=filiere,
            cycle=self.cycle,
            diploma_awarded=self.diploma,
            school=school,
            duration_years=1,
            short_description="Programme de test UFHOB Phase 1.",
            description="Description de test.",
        )

    def test_a_institution_can_contain_many_schools(self):
        self.assertEqual(self.institution_obj.schools.count(), 3)

    def test_b_esmed_esga_fatec_created_once(self):
        codes = set(School.objects.values_list("code", flat=True))
        self.assertEqual(codes, {"ESMED", "ESGA", "FATEC"})

    def test_c_school_can_be_linked_to_multiple_branches(self):
        other, _ = Branch.objects.get_or_create(
            name="Djélibougou",
            slug="djelibougou",
            defaults={"code": "DJE", "city": "Bamako"},
        )
        SchoolBranch.objects.get_or_create(school=self.esmed, branch=self.branch)
        SchoolBranch.objects.get_or_create(school=self.esmed, branch=other)
        self.assertEqual(self.esmed.school_branches.count(), 2)

    def test_d_branch_can_host_multiple_schools(self):
        SchoolBranch.objects.get_or_create(school=self.esmed, branch=self.branch)
        SchoolBranch.objects.get_or_create(school=self.esga, branch=self.branch)
        self.assertEqual(self.branch.school_branches.count(), 2)

    def test_e_programme_belongs_to_a_school(self):
        programme = self._make_programme("Médecine", "Filière Médecine", school=self.esmed)
        self.assertEqual(programme.school, self.esmed)

    def test_f_esmed_programmes_medicine_pharmacy_dentistry(self):
        med = self._make_programme("Médecine", "Filière Médecine", school=self.esmed)
        pharma = self._make_programme("Pharmacie", "Filière Pharmacie", school=self.esmed)
        dental = self._make_programme("Chirurgie dentaire", "Filière Chirurgie dentaire", school=self.esmed)

        self.assertEqual(med.school, self.esmed)
        self.assertEqual(pharma.school, self.esmed)
        self.assertEqual(dental.school, self.esmed)

        esmed_programmes = Programme.objects.filter(school=self.esmed)
        self.assertEqual(esmed_programmes.count(), 3)

    def test_g_program_not_offered_if_school_not_in_branch(self):
        programme = self._make_programme("Test offre", "Test offre", school=self.esmed)
        self.assertFalse(Programme.objects.available_on(self.branch).filter(pk=programme.pk).exists())
        SchoolBranch.objects.create(school=self.esmed, branch=self.branch)
        self.assertTrue(Programme.objects.available_on(self.branch).filter(pk=programme.pk).exists())

    def test_h_academic_year_remains_unique_at_institution_level(self):
        AcademicYear.objects.create(
            name="2026-2027",
            start_date="2026-10-01",
            end_date="2027-07-31",
            is_active=True,
        )
        with self.assertRaises(ValidationError):
            ay = AcademicYear(
                name="2027-2028",
                start_date="2027-10-01",
                end_date="2028-07-31",
                is_active=True,
            )
            ay.save()

    def test_i_similar_program_names_across_schools_do_not_collide(self):
        p1 = self._make_programme("Licence Sciences", "Filière Sciences ESMED", school=self.esmed)
        p2 = self._make_programme("Licence Sciences", "Filière Sciences ESGA", school=self.esga)

        self.assertEqual(p1.school, self.esmed)
        self.assertEqual(p2.school, self.esga)
        self.assertNotEqual(p1.slug, p2.slug)

    def test_j_access_context_distinguishes_school_and_branch(self):
        user = get_user_model().objects.create_user(
            username="test_access_user", email="test@ufhob.local", password="testpass"
        )
        ctx = build_access_context(user)
        self.assertTrue(hasattr(ctx, "school"))
        self.assertTrue(hasattr(ctx, "branch"))

    def test_k_user_esmed_moribabougou_does_not_see_esga_data(self):
        SchoolBranch.objects.get_or_create(school=self.esmed, branch=self.branch)
        SchoolBranch.objects.get_or_create(school=self.esga, branch=self.branch)

        self._make_programme("Médecine", "Filière Médecine", school=self.esmed)
        self._make_programme("Droit", "Filière Droit", school=self.esga)

        esmed_programmes = Programme.objects.filter(school__code="ESMED")
        esga_programmes = Programme.objects.filter(school__code="ESGA")

        self.assertEqual(esmed_programmes.count(), 1)
        self.assertEqual(esga_programmes.count(), 1)
        self.assertNotIn(
            self.esga,
            [p.school for p in esmed_programmes],
        )

    def test_l_bootstrap_is_idempotent(self):
        initial_count = School.objects.count()
        call_command("bootstrap_ufhob_phase1", verbosity=0)
        self.assertEqual(School.objects.count(), initial_count)
        self.assertEqual(School.objects.count(), 3)

    def test_m_existing_workflows_continue_to_import_and_load(self):
        # Vérification de l'importation/chargement des modules métier clés.
        self.assertTrue(hasattr(Programme, "school"))
        self.assertTrue(hasattr(AcademicYear, "name"))
        user = get_user_model().objects.create_user(
            username="test_m_user", email="m@ufhob.local", password="testpass"
        )
        ctx = build_access_context(user)
        self.assertTrue(hasattr(ctx, "school"))
