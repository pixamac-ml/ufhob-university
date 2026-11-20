"""T2 — plus aucune suppression définitive de candidature par l'ancienne interface (R-C3)."""

from datetime import date

from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from admissions.models import Candidature
from core import test_ufhob_phase2 as fixtures


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class SuppressionCandidatureTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        cls.candidature = Candidature.objects.create(
            programme=cls.programmes[1], branch=cls.a, academic_year=cls.year.name,
            birth_date=date(2000, 1, 1), first_name="A", last_name="Supprimer", email="sup@example.invalid",
            gender="female", phone="70000001", birth_place="Bamako", status="rejected",
        )
        cls.secretary = cls.make_user("secretaire-t2", "secretary", cls.a, cls.schools[1], "SCHOOL_BRANCH")

    def test_route_definitive_n_existe_plus(self):
        with self.assertRaises(NoReverseMatch):
            reverse("accounts:delete_candidature_htmx", args=[self.candidature.pk])

    def test_ancienne_url_ne_supprime_rien(self):
        for user in (self.secretary, self.global_user):
            self.client.force_login(user)
            response = self.client.post(
                f"/accounts/htmx/candidature/{self.candidature.pk}/delete/", HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, 404)
        self.assertTrue(Candidature.objects.filter(pk=self.candidature.pk).exists())

    def test_aucun_gabarit_n_appelle_l_ancienne_route(self):
        from pathlib import Path
        from django.conf import settings

        hits = [
            str(path) for path in Path(settings.BASE_DIR).rglob("*.html")
            if "node_modules" not in path.parts and "_archive" not in path.parts
            and "delete_candidature_htmx" in path.read_text(encoding="utf-8", errors="ignore")
        ]
        self.assertEqual(hits, [])
