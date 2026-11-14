import json
from urllib.parse import unquote

from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from core.context_processors import get_published_legal_links
from core.models import ContactMessage, DirectorGeneralMessage, LegalPage, LegalSection
from core.views import COOKIE_CONSENT_NAME, COOKIE_CONSENT_VERSION


class LegalPagesTests(TestCase):
	def setUp(self):
		self.legal = LegalPage.objects.create(
			page_type="legal",
			title="Mentions legales",
			introduction="Intro",
			status="published",
		)
		self.privacy = LegalPage.objects.create(
			page_type="privacy",
			title="Confidentialite",
			introduction="Intro",
			status="published",
		)
		self.terms = LegalPage.objects.create(
			page_type="terms",
			title="Conditions d'utilisation",
			introduction="Intro",
			status="published",
		)

		for page in [self.legal, self.privacy, self.terms]:
			LegalSection.objects.create(
				page=page,
				title="Section 1",
				content="Contenu test",
				is_active=True,
				order=1,
			)

	def test_legal_pages_are_accessible_when_published(self):
		urls = [
			reverse("core:legal_notice"),
			reverse("core:privacy_policy"),
			reverse("core:terms_of_service"),
		]

		for url in urls:
			with self.subTest(url=url):
				response = self.client.get(url)
				self.assertEqual(response.status_code, 200)

	def test_legal_page_returns_404_when_not_published(self):
		self.terms.status = "draft"
		self.terms.save(update_fields=["status"])

		response = self.client.get(reverse("core:terms_of_service"))
		self.assertEqual(response.status_code, 404)

	def test_legal_pdf_export_works(self):
		response = self.client.get(reverse("core:legal_pdf", args=["legal"]))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response["Content-Type"], "application/pdf")


class DirectorGeneralMessagePublicTests(TestCase):
	def test_only_an_active_director_message_is_visible_on_public_pages(self):
		draft = DirectorGeneralMessage.objects.create(
			full_name="Direction test",
			position="Directeur Général",
			title="Brouillon",
			message="Ce message ne doit pas être publié.",
			is_active=False,
		)
		published = DirectorGeneralMessage.objects.create(
			full_name="Direction publiée",
			position="Directeur Général",
			title="Un message institutionnel",
			message="Contenu institutionnel publié.",
			is_active=True,
		)

		for url_name in ("core:home", "core:university"):
			with self.subTest(url_name=url_name):
				response = self.client.get(reverse(url_name))
				self.assertEqual(response.status_code, 200)
				self.assertContains(response, published.title)
				self.assertContains(response, published.full_name)
				self.assertNotContains(response, draft.title)


class SeoPlatformTests(TestCase):
	def test_home_contains_core_seo_tags(self):
		response = self.client.get(reverse("core:home"))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, '<meta name="description"', html=False)
		self.assertContains(response, '<link rel="canonical"', html=False)

	def test_robots_txt_exists(self):
		response = self.client.get(reverse("core:robots_txt"))
		self.assertEqual(response.status_code, 200)
		self.assertIn("text/plain", response["Content-Type"])
		self.assertContains(response, "Sitemap:", html=False)

	def test_sitemap_xml_exists(self):
		response = self.client.get("/sitemap.xml")
		self.assertEqual(response.status_code, 200)
		self.assertIn("xml", response["Content-Type"])
		self.assertNotContains(response, "/community/", html=False)
		self.assertNotContains(response, "/mentions-legales/", html=False)


class PublicV1NavigationTests(TestCase):
	def test_v1_routes_remain_available(self):
		for url_name in (
			"core:home",
			"core:about",
			"formations:list",
			"memoires:liste",
			"core:contact",
			"admissions:admission_tunnel",
			"login",
		):
			with self.subTest(url_name=url_name):
				self.assertTrue(reverse(url_name))

	def test_public_navigation_no_longer_promotes_community_or_registration(self):
		response = self.client.get(reverse("core:home"))
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, "community:topic_list", html=False)
		self.assertNotContains(response, "S'inscrire", html=False)
		self.assertContains(response, reverse("admissions:admission_tunnel"), html=False)
		self.assertContains(response, reverse("login"), html=False)

	def test_only_published_legal_documents_are_exposed(self):
		LegalPage.objects.create(
			page_type="legal",
			title="Mentions légales",
			introduction="Version publiée",
			status="published",
		)
		LegalPage.objects.create(
			page_type="privacy",
			title="Confidentialité",
			introduction="Brouillon interne",
			status="draft",
		)

		self.assertEqual(
			get_published_legal_links(),
			[{"label": "Mentions légales", "url": reverse("core:legal_notice")}],
		)


class CookieConsentTests(TestCase):
	def test_first_public_visit_includes_an_equal_choice_banner(self):
		response = self.client.get(reverse("core:home"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="cookie-banner"', html=False)
		self.assertContains(response, 'id="cookie-accept-all"', html=False)
		self.assertContains(response, 'id="cookie-reject-all"', html=False)
		self.assertNotContains(response, "cookie-analytics", html=False)
		self.assertNotContains(response, "cookie-marketing", html=False)

	def test_rejection_remembers_only_a_first_party_technical_preference(self):
		response = self.client.post(
			reverse("core:cookie_consent"),
			data=json.dumps({"status": "rejected"}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 200)
		self.assertIn(COOKIE_CONSENT_NAME, response.cookies)
		consent = json.loads(unquote(response.cookies[COOKIE_CONSENT_NAME].value))
		self.assertEqual(consent["version"], COOKIE_CONSENT_VERSION)
		self.assertTrue(consent["necessary"])
		self.assertEqual(consent["status"], "rejected")
		self.assertNotIn("analytics", consent)
		self.assertNotIn("marketing", consent)

	def test_invalid_consent_status_is_rejected(self):
		response = self.client.post(
			reverse("core:cookie_consent"),
			data=json.dumps({"status": "customized"}),
			content_type="application/json",
		)

		self.assertEqual(response.status_code, 400)


class ContactFormTests(TestCase):
	@patch("core.views.NotificationBus.send_email")
	def test_contact_post_creates_message_without_serialization_error(self, mock_send):
		response = self.client.post(
			reverse("core:contact"),
			data={
				"full_name": "Awa Traore",
				"email": "awa@example.com",
				"phone": "+22370000000",
				"subject": "admission",
				"message": "Je souhaite contacter l'ecole.",
				"consent": True,
			},
		)

		self.assertEqual(response.status_code, 200)
		self.assertEqual(ContactMessage.objects.count(), 1)
		self.assertContains(response, "Votre message a bien été envoyé", html=False)
		self.assertEqual(mock_send.call_count, 2)

