"""Opt-in real-browser consent recipe: ESFE_COOKIE_BROWSER_TESTS=1."""
import json
import asyncio
import os
import secrets
import sys
import tempfile
import time
from datetime import timedelta
from http.cookies import SimpleCookie
from unittest import skipUnless
from unittest.mock import patch
from urllib.parse import unquote

from django.contrib.auth import get_user_model
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.test import override_settings
from django.utils import timezone

from core import views


@skipUnless(os.environ.get("ESFE_COOKIE_BROWSER_TESTS") == "1", "Opt-in Playwright recipe")
@override_settings(
    DEBUG=True,
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    SECURE_SSL_REDIRECT=False,
)
class CookieConsentBrowserTests(StaticLiveServerTestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright

        self.password = secrets.token_urlsafe(24)
        self.user = get_user_model().objects.create_superuser(
            username="cookie-recipe", email="cookie-recipe@example.invalid", password=self.password,
        )
        profile = self.user.profile
        profile.position = "super_admin"
        profile.user_type = "staff"
        profile.role = "superadmin"
        profile.save()
        if sys.platform == "win32":
            # Playwright needs subprocess support; the application's Windows
            # selector loop is deliberately not changed outside this recipe.
            with patch("asyncio.new_event_loop", asyncio.ProactorEventLoop):
                self.playwright = sync_playwright().start()
        else:
            self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.profile_path = tempfile.mkdtemp(prefix="esfe-cookie-browser-")
        self.context = self.playwright.chromium.launch_persistent_context(self.profile_path, headless=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)

    def consent(self):
        cookie = next(cookie for cookie in self.context.cookies() if cookie["name"] == views.COOKIE_CONSENT_NAME)
        self.assertGreater(cookie["expires"], time.time() + 179 * 86400)
        return json.loads(unquote(cookie["value"]))

    def banner_hidden(self):
        self.page.wait_for_function("!document.querySelector('#cookie-banner') || document.querySelector('#cookie-banner').classList.contains('hidden')")

    def login(self):
        self.page.goto(self.live_server_url + "/accounts/login/")
        self.banner_hidden()
        self.page.locator('input[name="username"]').fill(self.user.username)
        self.page.locator('input[name="password"]').fill(self.password)
        with self.page.expect_navigation(wait_until="domcontentloaded"):
            self.page.locator('form button[type="submit"]').click()
        self.page.locator('[data-certified-dashboard-shell="true"]').wait_for()
        self.banner_hidden()

    def logout(self):
        # Submit the real CSRF-protected logout endpoint in the browser.
        self.page.evaluate("""() => {
            const token = document.cookie.split('; ').find(c => c.startsWith('csrftoken=')).split('=').slice(1).join('=');
            const form = document.createElement('form'); form.method = 'POST'; form.action = '/accounts/logout/';
            const input = document.createElement('input'); input.name = 'csrfmiddlewaretoken'; input.value = decodeURIComponent(token);
            form.append(input); document.body.append(form); form.submit();
        }""")
        self.page.wait_for_load_state("domcontentloaded")
        self.page.goto(self.live_server_url + "/accounts/login/")
        self.page.locator('input[name="username"]').wait_for()
        self.banner_hidden()

    def choose(self, status):
        selector = "#cookie-accept-all" if status == "accepted" else "#cookie-reject-all"
        with self.page.expect_response(lambda response: response.url.endswith("/cookies/consent/")) as saved:
            self.page.locator(selector).click()
        self.assertEqual(saved.value.status, 200)
        self.banner_hidden()
        self.assertEqual(self.consent()["status"], status)

    def test_accept_refuse_login_logout_reload_and_htmx(self):
        from playwright.sync_api import expect

        self.page.goto(self.live_server_url + "/accounts/login/")
        expect(self.page.locator("#cookie-banner")).to_be_visible()  # A
        self.choose("accepted")
        self.page.reload()
        self.banner_hidden()  # B
        self.login()  # D: actual authentication and certified dashboard
        self.logout()  # C
        self.assertEqual(self.consent()["status"], "accepted")
        self.context.clear_cookies(name=views.COOKIE_CONSENT_NAME)
        self.page.reload()
        expect(self.page.locator("#cookie-banner")).to_be_visible()  # E
        self.choose("rejected")
        self.page.reload()
        self.banner_hidden()
        self.login()
        self.logout()
        self.assertEqual(self.consent()["status"], "rejected")  # F

        # G: a real HTMX response reinjecting the component, followed by a
        # replacement of the canonical node and browser-history reconciliation.
        self.page.evaluate("""() => {
            const target = document.createElement('div'); target.id = 'cookie-qa-swap';
            const button = document.createElement('button'); button.id = 'cookie-qa-navigation';
            button.textContent = 'Navigation QA';
            button.setAttribute('hx-get', '/accounts/login/');
            button.setAttribute('hx-select', '#cookie-consent-root');
            button.setAttribute('hx-target', '#cookie-qa-swap');
            button.setAttribute('hx-swap', 'innerHTML');
            document.body.append(target, button); htmx.process(button);
        }""")
        with self.page.expect_response(lambda response: "/accounts/login/" in response.url):
            self.page.locator("#cookie-qa-navigation").click()
        expect(self.page.locator("#cookie-consent-root")).to_have_count(1)
        self.banner_hidden()
        self.page.evaluate("""async () => {
            await htmx.ajax('GET', '/accounts/login/', {target:'#cookie-consent-root', swap:'outerHTML', select:'#cookie-consent-root'});
            document.body.dispatchEvent(new CustomEvent('htmx:historyRestore', {bubbles:true}));
        }""")
        expect(self.page.locator("#cookie-consent-root")).to_have_count(1)
        self.banner_hidden()

        self.context.clear_cookies(name=views.COOKIE_CONSENT_NAME)
        self.page.evaluate("""() => {
            const root = document.querySelector('#cookie-consent-root');
            root.outerHTML = root.outerHTML;
            document.body.dispatchEvent(new CustomEvent('htmx:historyRestore', {bubbles:true}));
        }""")
        expect(self.page.locator("#cookie-banner")).to_be_visible()
        self.choose("rejected")

        # Really close and reopen the same browser profile, without injecting
        # cookies or reconstructing storage state in the new browser.
        self.context.close()
        self.context = self.playwright.chromium.launch_persistent_context(self.profile_path, headless=True)
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.goto(self.live_server_url + "/accounts/login/")
        self.banner_hidden()
        self.assertEqual(self.consent()["status"], "rejected")

    def test_legacy_cookie_expiry_policy_change_and_failed_acknowledgement(self):
        from playwright.sync_api import expect

        payload = {"version": views.COOKIE_CONSENT_VERSION, "necessary": True,
                   "status": "rejected", "timestamp": timezone.now().isoformat()}
        cookie = SimpleCookie()
        cookie[views.COOKIE_CONSENT_NAME] = json.dumps(payload, separators=(",", ":"))
        self.context.add_cookies([{"name": views.COOKIE_CONSENT_NAME,
                                  "value": cookie[views.COOKIE_CONSENT_NAME].coded_value,
                                  "url": self.live_server_url, "expires": time.time() + 180 * 86400}])
        self.page.goto(self.live_server_url + "/accounts/login/")
        self.banner_hidden()
        self.context.clear_cookies(name=views.COOKIE_CONSENT_NAME)
        self.page.reload()
        for failure in ("http", "network"):
            with self.subTest(failure=failure):
                self.context.clear_cookies(name=views.COOKIE_CONSENT_NAME)
                self.page.reload()
                def fail(route):
                    if failure == "http":
                        route.fulfill(status=403, body="CSRF verification failed")
                    else:
                        route.abort()
                self.page.route("**/cookies/consent/", fail)
                self.page.locator("#cookie-reject-all").click()
                self.banner_hidden()
                self.page.reload()
                self.banner_hidden()
                self.assertEqual(self.consent()["status"], "rejected")
                self.page.unroute("**/cookies/consent/", fail)

        payload["timestamp"] = (timezone.now() - timedelta(days=181)).isoformat()
        self.page.evaluate("p => document.cookie = 'esfe_cookie_consent=' + encodeURIComponent(JSON.stringify(p)) + '; Path=/'", payload)
        self.page.reload()
        expect(self.page.locator("#cookie-banner")).to_be_visible()
        self.choose("accepted")
        with patch.object(views, "COOKIE_CONSENT_VERSION", 73):
            self.page.reload()
            expect(self.page.locator("#cookie-banner")).to_be_visible()
            self.choose("rejected")
            self.page.reload()
            self.banner_hidden()
            self.assertEqual(self.consent()["version"], 73)
