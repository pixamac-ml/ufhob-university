"""Opt-in local browser coverage; always uses Django's isolated test database."""
import os
import subprocess
from unittest import skipUnless

from django.conf import settings
from django.contrib.staticfiles.testing import StaticLiveServerTestCase

from core.models import School, SchoolBranch
from formations.models import Programme, ProgrammeRequiredDocument


@skipUnless(os.environ.get("UFHOB_TUNNEL_BROWSER_TESTS") == "1", "Opt-in mobile browser test")
class TunnelMobileBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        from admissions.tests import AdmissionTunnelValidationTests

        AdmissionTunnelValidationTests.setUp(self)
        self.programme.slug = "tunnel-fatec"
        self.programme.title = "Programme de recette FATEC"
        self.programme.save()
        school = School.objects.create(institution=self.school.institution, code="ESGA", short_name="ESGA")
        SchoolBranch.objects.create(school=school, branch=self.branch)
        programme = Programme.objects.create(
            school=school, title="Programme de recette ESGA", slug="tunnel-esga",
            filiere=self.filiere, cycle=self.cycle, diploma_awarded=self.diploma,
            duration_years=3, description="Recette locale uniquement", short_description="Recette locale",
        )
        for link in self.programme.required_documents.all():
            ProgrammeRequiredDocument.objects.create(programme=programme, document=link.document)

    def test_mobile_fatec_esga_submission_old_draft_and_unique_lead(self):
        environment = dict(os.environ, UFHOB_TEST_ORIGIN=self.live_server_url)
        result = subprocess.run(
            ["node", "admissions/check_funnel_browser.cjs"], cwd=settings.BASE_DIR,
            env=environment, capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout)
