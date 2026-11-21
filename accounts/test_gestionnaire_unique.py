"""T4 — décisions D2 (gestionnaire unique) et D3 (agent de caisse automatique)."""

import importlib

from django.apps import apps as django_apps
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.access import get_user_position
from accounts.models import InstitutionalProfile, LegacyPositionConversion, Profile
from accounts.position_registry import (
    POSITION_REGISTRY,
    RETIRED_MANAGER_POSITIONS,
    dg_assignable_positions,
    get_position_definition,
)
from core import test_ufhob_phase2 as fixtures
from payments.models import PaymentAgent

conversion_migration = importlib.import_module("accounts.migrations.0048_convertir_postes_gestionnaire")


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class GestionnaireUniqueTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        _esmed, cls.esga, cls.fatec = cls.schools

    def test_postes_retires_absents_des_listes(self):
        for code in RETIRED_MANAGER_POSITIONS:
            with self.subTest(code):
                self.assertNotIn(code, POSITION_REGISTRY)
                self.assertNotIn(code, dg_assignable_positions())
                self.assertNotIn(code, dict(Profile.POSITION_CHOICES))
                # alias historique : le code désigne la gestionnaire
                self.assertEqual(get_position_definition(code).code, "annex_manager")
        self.assertEqual(get_position_definition("annex_manager").label, "Gestionnaire")

    def test_formulaire_super_admin_ne_propose_plus_les_postes_retires(self):
        from superadmin.views import _institutional_position_choices

        codes = {code for code, _label in _institutional_position_choices()}
        self.assertIn("annex_manager", codes)
        self.assertFalse(codes & RETIRED_MANAGER_POSITIONS)

    def test_ancien_code_est_traite_comme_gestionnaire(self):
        user = self.make_user("ancien-finance", "finance_manager", self.a, self.esga, "SCHOOL_BRANCH")
        self.assertEqual(get_user_position(user), "annex_manager")

    def test_anciens_liens_finance_et_admissions_menent_au_cockpit(self):
        user = self.make_user("gest-liens", "annex_manager", self.a, self.esga, "SCHOOL_BRANCH")
        self.client.force_login(user)
        cockpit = reverse("accounts_portal:portal_annex_manager")
        for route, section in (("accounts_portal:portal_finance", "paiements"), ("accounts_portal:portal_admissions", "candidatures")):
            with self.subTest(route):
                response = self.client.get(reverse(route))
                self.assertRedirects(response, f"{cockpit}?section={section}", fetch_redirect_response=False)
        for route in ("accounts:finance_dashboard", "accounts:admissions_dashboard"):
            with self.subTest(route):
                response = self.client.get(reverse(route), follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.request["PATH_INFO"], cockpit)

    def test_gestionnaire_recoit_automatiquement_son_agent_de_caisse(self):
        user = self.make_user("gest-agent", "annex_manager", self.a, self.fatec, "SCHOOL_BRANCH")
        agent = PaymentAgent.objects.get(user=user)
        self.assertTrue(agent.is_active)
        self.assertEqual(agent.branch, self.a)
        self.assertTrue(agent.agent_code)

    def test_creation_par_super_admin_cree_l_agent(self):
        admin = self.make_user("super-t4", "super_admin")
        admin.is_superuser = True
        admin.is_staff = True
        admin.save()
        self.client.force_login(admin)
        response = self.client.post(reverse("superadmin:user_create"), {
            "username": "gest.fatec.t4", "email": "gest.fatec.t4@example.invalid", "first_name": "Awa",
            "last_name": "Diarra", "password": "Mot-de-passe-1234", "position": "annex_manager",
            "school": self.fatec.pk, "branch": self.a.pk, "access_scope": "SCHOOL_BRANCH",
            "is_staff": "on", "is_active": "on",
        })
        self.assertEqual(response.status_code, 302)
        created = InstitutionalProfile.objects.get(user__username="gest.fatec.t4")
        self.assertEqual((created.position, created.school, created.branch), ("annex_manager", self.fatec, self.a))
        self.assertTrue(PaymentAgent.objects.filter(user=created.user, branch=self.a, is_active=True).exists())

    def test_migration_de_donnees_aller_retour(self):
        user = self.make_user("ancien-admissions", "secretary", self.a)
        # État « avant D2 » écrit directement, sans les signaux d'aujourd'hui.
        Profile.objects.filter(user=user).update(position="admissions", role="admissions")
        InstitutionalProfile.objects.filter(user=user).update(position="admissions")
        Group.objects.get_or_create(name="admissions")[0].user_set.add(user)
        PaymentAgent.objects.filter(user=user).delete()

        conversion_migration.convertir(django_apps, None)
        self.assertEqual(Profile.objects.get(user=user).position, "annex_manager")
        self.assertEqual(InstitutionalProfile.objects.get(user=user).position, "annex_manager")
        self.assertTrue(user.groups.filter(name="annex_manager").exists())
        self.assertFalse(user.groups.filter(name="admissions").exists())
        self.assertTrue(PaymentAgent.objects.filter(user=user, branch=self.a).exists())
        self.assertEqual(LegacyPositionConversion.objects.filter(user=user).count(), 2)

        conversion_migration.restaurer(django_apps, None)
        profile = Profile.objects.get(user=user)
        self.assertEqual((profile.position, profile.role), ("admissions", "admissions"))
        self.assertEqual(InstitutionalProfile.objects.get(user=user).position, "admissions")
        self.assertFalse(PaymentAgent.objects.filter(user=user).exists())
        self.assertFalse(LegacyPositionConversion.objects.exists())
