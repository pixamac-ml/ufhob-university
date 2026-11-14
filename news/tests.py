from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Category, Event, EventType, News, ResultSession


class NewsHtmxFlowTests(TestCase):
	def setUp(self):
		user_model = get_user_model()
		self.author = user_model.objects.create_user(
			username="news_tester",
			email="news_tester@example.com",
			password="secret1234",
		)
		self.category = Category.objects.create(
			nom="Institution",
			slug="institution",
			is_active=True,
		)

		self.news = News.objects.create(
			titre="Lancement officiel",
			resume="Resume test",
			contenu="Contenu test",
			categorie=self.category,
			status=News.STATUS_PUBLISHED,
			auteur=self.author,
			published_at=timezone.now() - timedelta(minutes=5),
		)

	def test_news_page_renders_with_poller(self):
		response = self.client.get(reverse("news:list"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="news-content"')
		self.assertContains(response, 'id="news-poller"')

	def test_list_fragment_endpoint_with_hx_request(self):
		response = self.client.get(
			reverse("news:list_fragment"),
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="news-list-region"')
		self.assertContains(response, self.news.titre)

	def test_sidebar_fragment_endpoint_with_hx_request(self):
		response = self.client.get(
			reverse("news:sidebar_fragment"),
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="news-right-sidebar"')

	def test_poll_returns_trigger_when_news_is_newer_than_since(self):
		since = (timezone.now() - timedelta(days=1)).isoformat()
		response = self.client.get(reverse("news:poll"), {"since": since})

		self.assertEqual(response.status_code, 204)
		self.assertIn("HX-Trigger", response.headers)
		self.assertIn("news:refresh", response.headers["HX-Trigger"])

	def test_poll_returns_no_trigger_when_since_is_in_future(self):
		since = (timezone.now() + timedelta(days=1)).isoformat()
		response = self.client.get(reverse("news:poll"), {"since": since})

		self.assertEqual(response.status_code, 204)
		self.assertNotIn("HX-Trigger", response.headers)


class PublicEventParticipationTests(TestCase):
	def setUp(self):
		self.event_type = EventType.objects.create(name="Recherche", slug="recherche")
		self.event = Event.objects.create(
			title="Journée scientifique",
			event_type=self.event_type,
			event_date=timezone.localdate() + timedelta(days=30),
			start_time="09:00",
			venue="Campus UFHOB",
			is_published=True,
			registration_enabled=True,
			registration_label="Participer",
			registration_url="/contact/",
		)

	def test_future_event_can_display_registration(self):
		self.assertTrue(self.event.can_register)
		self.assertEqual(self.event.temporal_status, "upcoming")

	def test_unsafe_or_archived_registration_is_not_available(self):
		self.event.registration_url = "javascript:alert(1)"
		self.assertFalse(self.event.can_register)
		self.event.registration_url = "/contact/"
		self.event.is_archived = True
		self.assertFalse(self.event.can_register)


class ResultHtmxFlowTests(TestCase):
	def setUp(self):
		pdf_content = b"%PDF-1.4\n%Fake PDF content\n"
		self.pdf = SimpleUploadedFile(
			"result-test.pdf",
			pdf_content,
			content_type="application/pdf",
		)

		self.result = ResultSession.objects.create(
			type="semestre",
			titre="Session principale",
			annee_academique="2025-2026",
			annexe="Douala",
			filiere="Informatique",
			classe="L3",
			fichier_pdf=self.pdf,
			is_published=True,
		)

	def test_result_page_renders_with_dynamic_region(self):
		response = self.client.get(reverse("news:result_list"))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="result-content"')
		self.assertContains(response, 'id="result-poller"')

	def test_result_list_fragment_endpoint_with_hx_request(self):
		response = self.client.get(
			reverse("news:result_list_fragment"),
			HTTP_HX_REQUEST="true",
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="result-list-region"')
		self.assertContains(response, self.result.titre)

	def test_result_poll_returns_trigger_when_data_is_newer(self):
		since = (timezone.now() - timedelta(days=1)).isoformat()
		response = self.client.get(reverse("news:result_poll"), {"since": since})

		self.assertEqual(response.status_code, 204)
		self.assertIn("HX-Trigger", response.headers)
		self.assertIn("results:refresh", response.headers["HX-Trigger"])

