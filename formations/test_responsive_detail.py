from unittest.mock import patch

from django.test import TestCase

from core.models import School
from formations.models import Cycle, Programme


class ResponsiveProgrammeContextTests(TestCase):
    def setUp(self):
        from admissions.tests import AdmissionTunnelValidationTests
        AdmissionTunnelValidationTests.setUp(self)

    def test_sibling_levels_are_public_and_from_same_school_and_filiere(self):
        master = Cycle.objects.create(name="Master", min_duration_years=2, max_duration_years=2)
        other = School.objects.create(institution=self.school.institution, code="ESGA", short_name="ESGA")
        def sibling(school, slug, public=True):
            return Programme.objects.create(
                school=school, cycle=master, filiere=self.filiere, diploma_awarded=self.diploma,
                title="Parcours de test " + slug, slug=slug, duration_years=2, is_public=public,
            )
        expected = sibling(self.school, "same-school")
        sibling(other, "other-school")
        sibling(self.school, "hidden-level", public=False)
        response = self.client.get(self.programme.get_absolute_url())
        self.assertEqual([p.pk for p in response.context["sibling_levels"]], [self.programme.pk, expected.pk])
        self.assertEqual(response.context["filiere_title"], self.filiere.name)

    @patch("django.contrib.staticfiles.finders.find", return_value=None)
    def test_missing_photo_uses_plain_background_and_keeps_tracked_apply_link(self, _find):
        self.filiere.name = "Génie logiciel"
        self.filiere.save(update_fields=["name"])
        response = self.client.get(self.programme.get_absolute_url(), {"utm_source": "responsive-test"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["formation_hero_url"], "")
        self.assertNotContains(response, "background-image:url")
        self.assertIn("formation=" + self.programme.slug, response.context["apply_url"])
        self.assertIn("utm_source=responsive-test", response.context["apply_url"])
        self.assertEqual(response.context["admission_academic_year"].start_date.month, 10)

    def test_responsive_hero_is_shared_across_levels_and_used_for_social_image(self):
        self.filiere.name = "Génie logiciel"
        self.filiere.save(update_fields=["name"])
        programmes = [self.programme]
        for name, years in (("DUT", 2), ("Master", 2)):
            cycle = Cycle.objects.create(name=name, min_duration_years=years, max_duration_years=years)
            programmes.append(Programme.objects.create(
                school=self.school, cycle=cycle, filiere=self.filiere,
                diploma_awarded=self.diploma, title="Parcours de test " + name,
                slug="test-photo-" + name.lower(), duration_years=years,
            ))
        for programme in programmes:
            response = self.client.get(programme.get_absolute_url())
            self.assertEqual(response.context["formation_hero_url"], "/static/images/formations/genie-logiciel.webp")
            self.assertContains(response, "genie-logiciel-800.webp 800w")
            self.assertContains(response, "genie-logiciel.webp 1600w")
            self.assertContains(response, "genie-logiciel-1920.webp 1920w")
            self.assertContains(response, 'sizes="100vw"')
            self.assertContains(response, 'width="1600" height="900"')
            self.assertContains(response, 'fetchpriority="high"')
            self.assertEqual(response.context["og_image_url"], "https://www.ufhob-mali.ml/static/images/formations/genie-logiciel.webp")

    def test_school_pages_use_responsive_hero_and_social_image(self):
        School.objects.create(institution=self.school.institution, code="ESGA", short_name="ESGA")
        for code in ("fatec", "esga"):
            response = self.client.get("/ecoles/" + code + "/")
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, code + "-hero-800.webp 800w")
            self.assertContains(response, code + "-hero.webp 1600w")
            self.assertContains(response, code + "-hero-1920.webp 1920w")
            self.assertEqual(response.context["og_image_url"], "https://www.ufhob-mali.ml/static/images/ecoles/" + code + "-hero.webp")
