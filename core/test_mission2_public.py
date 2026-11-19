"""Mission 2 : plan du site, bannière d'accueil, identité FATEC/ESGA, contacts, sections vides."""
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils.html import escape

from core.models import Institution, School
from core.school_identity import SCHOOL_IDENTITY, school_logo_url


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False)
class Mission2PublicTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(
            name="Université Félix Houphouët Boigny - Mali", short_name="UFHOB",
            email="universite@univ-fhb-mali.org", phone="76 37 88 66", address="Moribabougou", city="Bamako", country="Mali",
        )
        cls.fatec = School.objects.create(institution=cls.institution, code="FATEC", short_name="FATEC", order=2,
                                          official_name="Faculté des Technologies Appliquées Cheick Modibo Diarra")
        cls.esga = School.objects.create(institution=cls.institution, code="ESGA", short_name="ESGA", order=1,
                                         official_name="École Supérieure de Gestion Alassane Dramane Ouattara")

    def test_sitemap_returns_200_and_lists_schools_by_order(self):
        response = self.client.get("/plan-du-site/")
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertLess(content.index("/ecoles/esga/"), content.index("/ecoles/fatec/"))

    def test_empty_news_and_placeholder_blocks_are_hidden(self):
        response = self.client.get("/")
        self.assertContains(response, "cinematic-hero")
        for placeholder in ("Aucune actualité", "Informations à venir", 'id="actualites"', "en cours de préparation"):
            self.assertNotContains(response, placeholder)

    def test_valid_contacts_only(self):
        response = self.client.get("/")
        self.assertContains(response, "+223 76 88 24 79")
        self.assertContains(response, "www.ufhob-mali.ml")
        self.assertContains(response, "@ufhob_officiel")
        for obsolete in ("univ-fhb-mali.org", "76 37 88 66", "provisoire", "esfe_officiel", "esfe_tv"):
            self.assertNotContains(response, obsolete)

    def test_school_logos_resolve_by_code_without_ufhob_fallback(self):
        self.assertTrue(school_logo_url(self.fatec).endswith("images/institution/fatec-logo.svg"))
        self.assertTrue(school_logo_url(self.esga, "white").endswith("images/institution/esga-logo-blanc.svg"))
        other = School(institution=self.institution, code="ESMED", short_name="ESMed")
        self.assertEqual(school_logo_url(other), "")

    def test_identity_command_is_idempotent_and_respects_existing_text(self):
        self.esga.description = "Texte validé par la direction"
        self.esga.save()
        call_command("charger_identite_ecoles", stdout=StringIO())
        self.fatec.refresh_from_db(); self.esga.refresh_from_db()
        self.assertEqual(self.fatec.description, SCHOOL_IDENTITY["FATEC"]["description"])
        self.assertEqual(self.esga.description, "Texte validé par la direction")
        out = StringIO()
        call_command("charger_identite_ecoles", stdout=out)
        self.assertIn("Mises à jour : 0", out.getvalue())
        call_command("charger_identite_ecoles", force=True, stdout=StringIO())
        self.esga.refresh_from_db()
        self.assertEqual(self.esga.description, SCHOOL_IDENTITY["ESGA"]["description"])

    def test_school_page_shows_logo_and_description_without_banner(self):
        call_command("charger_identite_ecoles", stdout=StringIO())
        for code in ("fatec", "esga"):
            response = self.client.get(f"/ecoles/{code}/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f"images/institution/{code}-logo.svg")
            self.assertContains(response, escape(SCHOOL_IDENTITY[code.upper()]["description"][:60]))
            for absent in ("banniere-", "school-theme--", "campaign-hero"):
                self.assertNotContains(response, absent)
