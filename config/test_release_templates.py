"""Regression checks for template failures discovered by release validation."""
from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase


class ReleaseTemplateTests(SimpleTestCase):
    def test_inscription_names_remain_inside_the_javascript_string(self):
        name = "O'Neil </script>"
        inscription = SimpleNamespace(
            id=1, balance=100,
            candidature=SimpleNamespace(full_name=name, first_name="O", last_name="Neil", programme=SimpleNamespace(title="Test")),
        )
        html = render_to_string("accounts/dashboard/partials/inscription_search_results.html", {"inscriptions": [inscription]})
        self.assertIn(r"O\u0027Neil \u003C/script\u003E", html)
        self.assertNotIn("'O'Neil", html)
        self.assertEqual(render_to_string("accounts/dashboard/partials/inscription_search_results.html", {"inscriptions": []}).strip(), "<!-- Résultats recherche inscriptions -->")

    def test_closure_modal_compiles_its_own_humanize_filters(self):
        html = render_to_string("portal/dg/modals/closure_detail.html", {"closure": None})
        self.assertIn("introuvable", html)

    def test_moderation_badge_displays_only_pending_reports(self):
        request = RequestFactory().get("/")
        request.user = SimpleNamespace(is_staff=True)
        topic = SimpleNamespace(slug="test-topic", is_locked=False, pending_report_count=2)
        html = render_to_string("community/partials/moderation_actions.html", {"request": request, "topic": topic})
        self.assertIn("2 signalement(s)", html)
        topic.pending_report_count = 0
        html = render_to_string("community/partials/moderation_actions.html", {"request": request, "topic": topic})
        self.assertNotIn("signalement(s)", html)
