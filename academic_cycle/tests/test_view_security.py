"""T1 — les actions du cycle académique sont réservées et cloisonnées (R-C2)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from academic_cycle import constants
from academic_cycle.models import AcademicCorrectionRequest, BranchAcademicCycle
from core import test_ufhob_phase2 as fixtures


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class AcademicCycleViewSecurityTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        _esmed, cls.esga, cls.fatec = cls.schools
        cls.cycle_a = BranchAcademicCycle.objects.create(branch=cls.a, academic_year=cls.year)
        cls.cycle_b = BranchAcademicCycle.objects.create(branch=cls.b, academic_year=cls.year)
        cls.student_user = cls.make_user("etudiant-cycle", "student")
        cls.teacher = cls.make_user("enseignant-cycle", "teacher", cls.a)
        cls.director_esga = cls.make_user("dir-esga", "director_of_studies", cls.a, cls.esga, "SCHOOL_BRANCH")
        cls.correction_a = AcademicCorrectionRequest.objects.create(
            academic_year=cls.year, branch=cls.a, request_type=AcademicCorrectionRequest.TYPE_OTHER,
            description="Correction campus A", submitted_by=cls.global_user,
        )
        cls.correction_b = AcademicCorrectionRequest.objects.create(
            academic_year=cls.year, branch=cls.b, request_type=AcademicCorrectionRequest.TYPE_OTHER,
            description="Correction campus B", submitted_by=cls.global_user,
        )

    def post_actions(self, cycle):
        return [
            ("academic_cycle:generate_report", {}),
            ("academic_cycle:start_deliberation", {}),
            ("academic_cycle:close_branch", {}),
            ("academic_cycle:open_registration", {"target_year": self.year.pk}),
            ("academic_cycle:activate_year", {"target_year": self.year.pk}),
        ]

    def test_etudiant_et_enseignant_recoivent_404_partout(self):
        for user in (self.student_user, self.teacher):
            self.client.force_login(user)
            for name in ("academic_cycle:branch_overview", "academic_cycle:branch_readiness"):
                with self.subTest(user=user.username, view=name):
                    self.assertEqual(self.client.get(reverse(name, args=[self.cycle_a.pk])).status_code, 404)
            for name in ("academic_cycle:dg_overview", "academic_cycle:correction_list"):
                with self.subTest(user=user.username, view=name):
                    self.assertEqual(self.client.get(reverse(name)).status_code, 404)
            for name, data in self.post_actions(self.cycle_a):
                with self.subTest(user=user.username, view=name):
                    response = self.client.post(reverse(name, args=[self.cycle_a.pk]), data)
                    self.assertEqual(response.status_code, 404)
            response = self.client.post(reverse("academic_cycle:resolve_correction", args=[self.correction_a.pk]))
            self.assertEqual(response.status_code, 404)
        self.cycle_a.refresh_from_db()
        self.assertEqual(self.cycle_a.status, constants.BRANCH_CYCLE_DRAFT)
        self.correction_a.refresh_from_db()
        self.assertEqual(self.correction_a.status, AcademicCorrectionRequest.STATUS_SUBMITTED)

    def test_directeur_ecole_voit_son_campus_mais_pas_un_autre(self):
        self.client.force_login(self.director_esga)
        self.assertEqual(self.client.get(reverse("academic_cycle:branch_overview", args=[self.cycle_a.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("academic_cycle:branch_overview", args=[self.cycle_b.pk])).status_code, 404)
        self.assertEqual(
            self.client.post(reverse("academic_cycle:generate_report", args=[self.cycle_b.pk])).status_code, 404,
        )
        listing = self.client.get(reverse("academic_cycle:correction_list"))
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(list(listing.context["corrections"]), [self.correction_a])

    def test_directeur_ecole_ne_change_pas_l_annee_du_campus(self):
        self.client.force_login(self.director_esga)
        for name in ("academic_cycle:open_registration", "academic_cycle:activate_year"):
            with self.subTest(name):
                response = self.client.post(reverse(name, args=[self.cycle_a.pk]), {"target_year": self.year.pk})
                self.assertEqual(response.status_code, 404)
        self.cycle_a.refresh_from_db()
        self.assertEqual(self.cycle_a.status, constants.BRANCH_CYCLE_DRAFT)

    def test_dg_peut_activer_l_annee_et_voit_toutes_les_corrections(self):
        self.client.force_login(self.global_user)
        response = self.client.post(
            reverse("academic_cycle:activate_year", args=[self.cycle_a.pk]), {"target_year": self.year.pk},
        )
        self.assertEqual(response.status_code, 302)
        self.cycle_a.refresh_from_db()
        self.assertEqual(self.cycle_a.status, constants.BRANCH_CYCLE_ACTIVE)
        listing = self.client.get(reverse("academic_cycle:correction_list"))
        self.assertEqual(set(listing.context["corrections"]), {self.correction_a, self.correction_b})
