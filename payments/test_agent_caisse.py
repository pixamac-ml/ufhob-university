"""T5 — l'agent de caisse est la gestionnaire de l'école du dossier (R-I3, R-M1)."""

import json
from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from admissions.models import Candidature
from core import test_ufhob_phase2 as fixtures
from inscriptions.models import Inscription
from payments.models import CashPaymentSession, PaymentAgent
from payments.services.cash import (
    NO_AGENT_MESSAGE,
    eligible_agents_for_inscription,
    verify_agent_and_create_session,
)


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class AgentCaisseTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        cls.esmed, cls.esga, cls.fatec = cls.schools
        # Même personne, même nom, deux comptes (un par école) sur le même campus.
        cls.gest_esga = cls.make_user("gest-esga-t5", "annex_manager", cls.a, cls.esga, "SCHOOL_BRANCH")
        cls.gest_fatec = cls.make_user("gest-fatec-t5", "annex_manager", cls.a, cls.fatec, "SCHOOL_BRANCH")
        for user in (cls.gest_esga, cls.gest_fatec):
            user.first_name, user.last_name = "Awa", "Traoré"
            user.save(update_fields=["first_name", "last_name"])
        cls.agent_esga = PaymentAgent.objects.get(user=cls.gest_esga)
        cls.agent_fatec = PaymentAgent.objects.get(user=cls.gest_fatec)
        cls.ins_esga = cls._inscription(cls.programmes[1], "esga")
        cls.ins_fatec = cls._inscription(cls.programmes[2], "fatec")
        cls.ins_esmed = cls._inscription(cls.programmes[0], "esmed")

    @classmethod
    def _inscription(cls, programme, key):
        candidature = Candidature.objects.create(
            programme=programme, branch=cls.a, academic_year=cls.year.name, birth_date=date(2000, 1, 1),
            first_name="Payeur", last_name=key, email=f"payeur.{key}@example.invalid", gender="female",
            phone=f"7{programme.pk:07d}", birth_place="Bamako", status="accepted",
        )
        return Inscription.objects.create(candidature=candidature, amount_due=100000, amount_paid=0)

    def test_chaque_dossier_va_a_la_gestionnaire_de_son_ecole(self):
        self.assertEqual(list(eligible_agents_for_inscription(self.ins_esga)), [self.agent_esga])
        self.assertEqual(list(eligible_agents_for_inscription(self.ins_fatec)), [self.agent_fatec])
        agent, error = verify_agent_and_create_session(self.ins_fatec)
        self.assertIsNone(error)
        self.assertEqual(agent, self.agent_fatec)
        session = CashPaymentSession.objects.get(inscription=self.ins_fatec)
        self.assertEqual(session.agent, self.agent_fatec)

    def test_code_d_une_autre_ecole_refuse(self):
        agent, error = verify_agent_and_create_session(self.ins_esga, self.agent_fatec.agent_code)
        self.assertIsNone(agent)
        self.assertIn("ne correspond", error)
        self.assertFalse(CashPaymentSession.objects.filter(inscription=self.ins_esga).exists())

    def test_ecole_sans_gestionnaire(self):
        agent, error = verify_agent_and_create_session(self.ins_esmed)
        self.assertIsNone(agent)
        self.assertEqual(error, NO_AGENT_MESSAGE)

    def test_plusieurs_gestionnaires_choix_par_code(self):
        second = self.make_user("gest-esga-bis", "annex_manager", self.a, self.esga, "SCHOOL_BRANCH")
        second_agent = PaymentAgent.objects.get(user=second)
        agent, error = verify_agent_and_create_session(self.ins_esga)
        self.assertIsNone(agent)
        self.assertIn("Choisissez", error)
        agent, error = verify_agent_and_create_session(self.ins_esga, second_agent.agent_code.lower())
        self.assertEqual(agent, second_agent)

    def _open_dossier(self, inscription):
        session = self.client.session
        session[f"inscription_access_{inscription.id}"] = True
        session.save()

    def test_vue_publique_sans_nom_et_json_valide(self):
        self._open_dossier(self.ins_esga)
        response = self.client.post(
            reverse("payments:verify_agent", args=[self.ins_esga.public_token]),
            {"agent_code": self.agent_fatec.agent_code}, HTTP_HX_REQUEST="true",
        )
        trigger = json.loads(response["HX-Trigger"])
        self.assertEqual(trigger["toast"]["type"], "error")
        ok = self.client.post(
            reverse("payments:verify_agent", args=[self.ins_esga.public_token]), {}, HTTP_HX_REQUEST="true",
        )
        self.assertEqual(json.loads(ok["HX-Trigger"])["toast"]["type"], "success")
        self.assertEqual(CashPaymentSession.objects.get(inscription=self.ins_esga).agent, self.agent_esga)
