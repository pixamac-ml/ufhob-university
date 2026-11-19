"""Optional real-browser checks; requires Playwright and Microsoft Edge locally."""
from datetime import date
from contextlib import ExitStack
import asyncio
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.management import call_command

from academics.models import AcademicYear
from admissions.models import Candidature
from branches.models import Branch
from formations.campaign_catalogue import OFFERS
from formations.fatec_esga import canonical_slug
from formations.models import Programme


class CampaignMobileTests(StaticLiveServerTestCase):
    def test_mobile_pages_and_four_step_application(self):
        from playwright.sync_api import sync_playwright

        branch = Branch.objects.create(name="Campus mobile test", code="MOBTEST", slug="mobile-test", city="")
        AcademicYear.objects.create(name="2026-2027", start_date=date(2026, 1, 1), end_date=date(2027, 12, 31), is_active=True)
        call_command('preparer_catalogue_fatec_esga', stdout=StringIO())
        from core.models import School, SchoolBranch
        for school in School.objects.all():
            SchoolBranch.objects.get_or_create(school=school,branch=branch)
        call_command('charger_catalogue_fatec_esga', stdout=StringIO())
        titles = dict(Programme.objects.values_list('slug','title'))
        output = Path(".tmp-campaign-browser")
        output.mkdir(exist_ok=True)
        with ExitStack() as stack:
            # Channels selects the selector loop on Windows; browser subprocesses
            # need a proactor loop, confined here to Playwright's private loop.
            if sys.platform == "win32":
                stack.enter_context(patch("asyncio.new_event_loop", asyncio.ProactorEventLoop))
            playwright = stack.enter_context(sync_playwright())
            browser = playwright.chromium.launch(channel="msedge", headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, device_scale_factor=1)
            # External fonts/animation resources are unnecessary for functional checks.
            context.route("https://**/*", lambda route: route.abort())
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for width in (320, 390):
                page.set_viewport_size({"width": width, "height": 844})
                for code, title, slug, *_ in OFFERS:
                    page.goto(f"{self.live_server_url}/formations/{code.lower()}/{slug}/?utm_source=facebook&utm_campaign=mobile-test", wait_until="domcontentloaded")
                    page.locator("h1").wait_for()
                    self.assertEqual(page.locator("h1").inner_text(), titles[canonical_slug(slug)])
                    cta = page.get_by_role("link", name="Candidater à cette formation").first
                    self.assertTrue(cta.is_visible())
                    self.assertLess(cta.bounding_box()["y"] + cta.bounding_box()["height"], 844)
                    self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
                    whatsapp = page.get_by_role("link", name="Contacter UFHOB-Mali sur WhatsApp")
                    self.assertEqual(whatsapp.get_attribute("href"), "https://wa.me/22376882479")
                    page.screenshot(path=str(output / f"{slug}-{width}.png"), full_page=True)
            page.set_viewport_size({"width": 390, "height": 844})
            page.get_by_role("link", name="Candidater à cette formation").first.click()
            page.wait_for_function("window.Alpine && document.querySelector('form[x-data]')._x_dataStack")
            reject = page.locator("#cookie-reject-all")
            if reject.is_visible():
                reject.click()
            expected_slug = canonical_slug(OFFERS[-1][2])
            def check_state(step):
                page.wait_for_function("step => Alpine.$data(document.querySelector('form[x-data]')).step === step", arg=step)
                self.assertEqual(page.locator('input[name="formation_slug"]').input_value(), expected_slug)
                self.assertEqual(page.locator('input[name="utm_source"]').input_value(), "facebook")
            check_state(1)
            page.get_by_role("button", name="Commencer ma candidature").click()
            page.locator('input[data-field="last_name"]').fill("Mobile")
            page.locator('input[data-field="first_name"]').fill("Test")
            page.locator('input[data-field="city"]').fill("Test")
            page.locator('[x-show="step === 1"] button.tunnel-btn-next:visible').last.click()
            check_state(2)
            page.locator('[x-show="step === 1"]').wait_for(state="hidden")
            page.locator('[data-field="gender"] button').first.click()
            page.locator('input[data-field="birth_date"]').fill("2000-01-01")
            page.locator('input[data-field="email"]').fill("mobile-campaign@example.invalid")
            page.locator('input[data-field="phone"]').fill("70000000")
            page.locator('[x-show="step === 2"] button.tunnel-btn-next:visible').last.click()
            check_state(3)
            page.locator('[x-show="step === 2"]').wait_for(state="hidden")
            page.locator(f'[data-branch-id="{branch.pk}"]').click()
            page.locator(f'[data-programme-slug="{expected_slug}"]').wait_for()
            page.locator("#documents-deferred").check()
            page.locator('[x-show="step === 3"] button.tunnel-btn-next:visible').last.click()
            check_state(4)
            page.locator('[x-show="step === 3"]').wait_for(state="hidden")
            page.screenshot(path=str(output / "candidature-verification-390.png"), full_page=True)
            page.get_by_role("button", name="Envoyer ma candidature").click()
            page.wait_for_url("**/admissions/done/**", timeout=30000)
            self.assertEqual(errors, [])
            browser.close()
        candidature = Candidature.objects.get(email="mobile-campaign@example.invalid")
        self.assertEqual(candidature.programme.slug, expected_slug)
        self.assertEqual(candidature.campaign_tracking["utm_source"], "facebook")
        self.assertEqual(candidature.campaign_tracking["utm_campaign"], "mobile-test")
