"""T3 — « Directeur d'école » (code director_of_studies) : libellés et cloisonnement ESGA / FATEC."""

from django.test import TestCase, override_settings
from django.urls import reverse

from academics.models import AcademicClass
from accounts.access_context import build_access_context
from accounts.models import Profile
from accounts.position_registry import get_position_definition
from accounts.scoping import access_scope, scoped
from core import test_ufhob_phase2 as fixtures


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class DirecteurEcoleTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        _esmed, cls.esga, cls.fatec = cls.schools
        cls.class_esga, cls.class_fatec = cls.classes[1], cls.classes[2]
        cls.dir_esga = cls.make_user("dir-ecole-esga", "director_of_studies", cls.a, cls.esga, "SCHOOL_BRANCH")
        cls.dir_fatec = cls.make_user("dir-ecole-fatec", "director_of_studies", cls.a, cls.fatec, "SCHOOL_BRANCH")

    def test_libelles_directeur_ecole(self):
        self.assertEqual(get_position_definition("director_of_studies").label, "Directeur d’école")
        self.assertEqual(dict(Profile.POSITION_CHOICES)["director_of_studies"], "Directeur d’école")

    def test_perimetre_normal_ecole_et_campus(self):
        context = build_access_context(self.dir_esga)
        self.assertTrue(context.is_valid)
        self.assertEqual(context.scope, "SCHOOL_BRANCH")
        self.assertEqual(context.school, self.esga)

    def test_chaque_directeur_ne_voit_que_les_classes_de_son_ecole(self):
        for user, own, foreign in (
            (self.dir_esga, self.class_esga, self.class_fatec),
            (self.dir_fatec, self.class_fatec, self.class_esga),
        ):
            with self.subTest(user.username), access_scope(build_access_context(user)):
                visible = scoped(AcademicClass)
                self.assertTrue(visible.filter(pk=own.pk).exists())
                self.assertFalse(visible.filter(pk=foreign.pk).exists())

    def test_tableau_de_bord_et_classe_d_une_autre_ecole(self):
        self.client.force_login(self.dir_esga)
        response = self.client.get(reverse("accounts_portal:portal_dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Direction de l’école")
        self.assertNotContains(response, "Directeur des etudes")
        foreign = self.client.get(
            reverse("accounts_portal:director_weekly_slots_workspace", args=[self.class_fatec.pk]),
            HTTP_HX_REQUEST="true",
        )
        # La vue HTMX répond par un message « Classe introuvable » sans rien
        # révéler de la classe FATEC.
        self.assertIn(foreign.status_code, {200, 403, 404})
        self.assertNotContains(foreign, self.class_fatec.programme.title, status_code=foreign.status_code)
        if foreign.status_code == 200:
            self.assertContains(foreign, "Classe introuvable")
        own = self.client.get(
            reverse("accounts_portal:director_weekly_slots_workspace", args=[self.class_esga.pk]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(own.status_code, 200)
