"""Dernière ligne droite : frais ESMed (tableau annuel) et masquage public d'ESFé Sup."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings

from core.models import Institution, School
from formations.models import Cycle, Fee, Filiere, Programme, ProgrammeYear


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class LancementFinalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name="UFHOB-Mali", short_name="UFHOB", phone="+223 76 88 24 79")
        cls.esmed = School.objects.create(institution=cls.institution, code="ESMED", short_name="ESMed", order=1)
        cls.esfe = School.objects.create(institution=cls.institution, code="ESFÉ", short_name="ESFé Sup", order=4)
        cls.cycle = Cycle.objects.create(name="Doctorat", min_duration_years=5, max_duration_years=7)
        cls.master = Cycle.objects.create(name="Master", min_duration_years=2, max_duration_years=2)
        cls.filiere = Filiere.objects.create(name="Sciences de la Santé")
        # Situation locale avant décision : Pharmacie 6 ans, avec un frais historique à conserver.
        cls.pharmacie = Programme.objects.create(
            title="Pharmacie", school=cls.esmed, filiere=cls.filiere, cycle=cls.cycle, duration_years=6,
            short_description="Doctorat en Pharmacie", description="<p>Pharmacie</p>",
        )
        year = ProgrammeYear.objects.create(programme=cls.pharmacie, year_number=1)
        Fee.objects.create(programme_year=year, label="Inscription", amount=900_000, due_month="Octobre")
        cls.master_esfe = Programme.objects.create(
            title="Master — Épidémiologie", slug="master-epidemiologie", school=cls.esfe, filiere=cls.filiere,
            cycle=cls.master, duration_years=2, short_description="Master", description="<p>Master</p>",
        )

    def test_charger_frais_esmed_is_idempotent_and_creates_missing_programmes(self):
        out = StringIO()
        call_command("charger_frais_esmed", "--dry-run", stdout=out)
        self.pharmacie.refresh_from_db()
        self.assertEqual(self.pharmacie.duration_years, 6, "--dry-run ne doit rien enregistrer")

        call_command("charger_frais_esmed", stdout=StringIO())
        durations = dict(Programme.objects.filter(school=self.esmed).values_list("title", "duration_years"))
        self.assertEqual(durations, {"Médecine": 7, "Pharmacie": 7, "Chirurgie dentaire": 6})
        for programme in Programme.objects.filter(school=self.esmed):
            years = list(programme.years.order_by("year_number"))
            self.assertEqual([y.year_number for y in years], list(range(1, programme.duration_years + 1)))
            for year in years:
                self.assertEqual(sum(f.amount for f in year.fees.all()), 2_100_000)

        out = StringIO()
        call_command("charger_frais_esmed", stdout=out)
        self.assertIn("aucun changement", out.getvalue())

    def test_esmed_page_shows_annual_fee_table(self):
        call_command("charger_frais_esmed", stdout=StringIO())
        dentaire = Programme.objects.get(school=self.esmed, title="Chirurgie dentaire")
        response = self.client.get(dentaire.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-annual-fees")
        self.assertContains(response, "data-cursus-year=", count=6)
        self.assertContains(response, "1 100 000")
        self.assertContains(response, "1 000 000")
        self.assertContains(response, "2 100 000")

    def test_masquer_esfe_public_hides_and_redirects_without_deleting(self):
        self.assertContains(self.client.get("/formations/"), "ESFé Sup")
        call_command("masquer_esfe_public", stdout=StringIO())
        self.esfe.refresh_from_db(); self.master_esfe.refresh_from_db()
        self.assertFalse(self.esfe.is_public)
        self.assertTrue(self.esfe.is_active, "l'école reste active en interne")
        self.assertFalse(self.master_esfe.is_public)
        self.assertTrue(School.objects.filter(pk=self.esfe.pk).exists())

        for url in ("/", "/formations/", "/plan-du-site/", "/admissions/"):
            self.assertNotContains(self.client.get(url), "ESFé Sup", msg_prefix=url)
        for url in ("/ecoles/esfe/", "/ecoles/esf%C3%A9/", "/formations/master-epidemiologie/", "/formations/?school=esf%C3%A9"):
            self.assertRedirects(self.client.get(url), "/formations/", fetch_redirect_response=False, msg_prefix=url)

        out = StringIO()
        call_command("masquer_esfe_public", stdout=out)
        self.assertIn("écoles modifiées : 0, programmes modifiés : 0", out.getvalue())

        call_command("masquer_esfe_public", "--reactiver", stdout=StringIO())
        self.esfe.refresh_from_db(); self.master_esfe.refresh_from_db()
        self.assertTrue(self.esfe.is_public and self.master_esfe.is_public)
