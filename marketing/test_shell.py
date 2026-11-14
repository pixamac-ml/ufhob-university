"""Regression checks for marketing pages on the certified application shell."""

from types import SimpleNamespace
from unittest.mock import patch

from django import forms
from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase

from marketing.views import _render_marketing_form
from portal.services.certified_dashboard_shell import build_certified_dashboard_shell


class MarketingShellTests(SimpleTestCase):
    def setUp(self):
        self.request = RequestFactory().get("/marketing/prospects/create/")
        self.request.user = SimpleNamespace(is_authenticated=True, username="marketing", pk=1)

    @patch("marketing.views.render")
    @patch("marketing.views._marketing_shell", return_value={"dashboard_shell": {"key": "marketing"}})
    def test_form_view_supplies_the_same_shell_as_dashboard(self, shell, render_view):
        _render_marketing_form(self.request, {
            "form": forms.Form(),
            "form_kind": "generic",
            "title": "Nouveau prospect",
            "submit_label": "Ajouter",
        }, active_section="prospects")
        self.assertEqual(shell.call_args.kwargs["active_section"], "prospects")
        self.assertEqual(render_view.call_args.args[1], "marketing/form.html")
        self.assertEqual(render_view.call_args.args[2]["dashboard_shell"]["key"], "marketing")

    def test_form_renders_inside_certified_shell_without_legacy_navigation(self):
        context = build_certified_dashboard_shell(
            role="marketing_manager",
            key="marketing",
            page_title="Nouveau prospect",
            title="Nouveau prospect",
            subtitle="Communication et campagnes",
            context_label="UFHOB",
            user_name="Marketing",
            navigation=[],
            active_section="prospects",
            workspace_template="portal/staff/shared/empty_workspace.html",
            topbar_template="portal/staff/shared/empty_workspace.html",
            script_path="",
        )
        context.update({
            "form": forms.Form(),
            "form_kind": "generic",
            "title": "Nouveau prospect",
            "submit_label": "Ajouter",
        })
        html = render_to_string("marketing/form.html", context)
        self.assertIn('data-certified-dashboard-shell="true"', html)
        self.assertIn('id="marketing-workspace"', html)
        self.assertIn("certified_dashboard_shell.js", html)
        self.assertNotIn('class="mk-shell"', html)
        self.assertEqual(html.count("<html"), 1)
