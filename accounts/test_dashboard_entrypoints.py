"""Routing contracts that do not require a business-data test database."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.template.loader import get_template
from django.urls import resolve, reverse

from accounts.dashboards.admissions_dashboard import admissions_dashboard
from accounts.dashboards.finance_dashboard import finance_dashboard
from accounts.services.redirects import legacy_executive_dashboard, resolve_user_dashboard
from portal.permissions import get_post_login_portal_url
from portal.views.annex_manager import legacy_manager_entry
from portal.views.views import staff_portal, student_portal
from portal.views.reenrollment import reenrollment_workspace


class DashboardEntryPointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, is_superuser=False, support_state=None)

    @override_settings(AUTH_PORTAL_ROUTING_V2_ENABLED=False)
    @patch("portal.permissions.get_user_groups", return_value=[])
    @patch("portal.permissions.user_requires_branch_assignment", return_value=False)
    def test_known_positions_resolve_directly_to_certified_entries(self, _assignment, _groups):
        destinations = {
            "student": "portal_student:dashboard",
            "teacher": "accounts_portal:portal_teacher",
            "director_of_studies": "accounts_portal:portal_director",
            "executive_director": "accounts_portal:portal_dg",
            "it_support": "accounts_portal:portal_dashboard",
            "academic_supervisor": "accounts_portal:portal_dashboard",
            "secretary": "accounts_portal:portal_secretary",
            "annex_manager": "accounts_portal:portal_annex_manager",
            # D2 : les anciens postes finance / admissions mènent à la gestionnaire.
            "finance_manager": "accounts_portal:portal_annex_manager",
            "admissions": "accounts_portal:portal_annex_manager",
            "marketing_manager": "marketing:dashboard",
            "super_admin": "superadmin:dashboard",
        }
        for position, url_name in destinations.items():
            with self.subTest(position=position):
                with patch("portal.permissions.get_user_position", return_value=position):
                    self.assertEqual(resolve_user_dashboard(self.user), reverse(url_name))

    @override_settings(AUTH_PORTAL_ROUTING_V2_ENABLED=True)
    @patch("portal.permissions.user_requires_branch_assignment", return_value=False)
    @patch("accounts.access_context.build_access_context")
    def test_incomplete_account_keeps_regularization(self, context_builder, _assignment):
        context_builder.return_value = SimpleNamespace(context_type="SYSTEM", is_valid=False)
        self.assertEqual(
            get_post_login_portal_url(self.user),
            reverse("accounts_portal:access_regularization"),
        )

    @patch("accounts.services.redirects.resolve_user_dashboard", return_value="/portal/dg/")
    def test_old_executive_url_redirects_without_serving_legacy_template(self, _resolver):
        request = self.factory.get("/accounts/dashboard/executive/?section=finance")
        request.user = self.user
        self.assertEqual(legacy_executive_dashboard(request).url, "/portal/dg/?section=finance")
        self.assertEqual(resolve(reverse("accounts:executive_dashboard")).func, legacy_executive_dashboard)

    def test_old_manager_finance_and_admissions_urls_preserve_filters(self):
        cases = (
            (legacy_manager_entry, "accounts_portal:portal_annex_manager", None),
            (finance_dashboard, "accounts_portal:portal_finance", "accounts"),
            (admissions_dashboard, "accounts_portal:portal_admissions", "accounts"),
        )
        for view, destination, namespace in cases:
            with self.subTest(destination=destination):
                request = self.factory.get("/legacy/?section=paiements&page=2")
                request.user = self.user
                request.resolver_match = SimpleNamespace(namespace=namespace)
                self.assertEqual(
                    view(request).url,
                    reverse(destination) + "?section=paiements&page=2",
                )

    @patch("portal.views.views.can_access", return_value=True)
    def test_old_student_and_staff_pages_do_not_render_legacy_shell(self, _access):
        student = self.factory.get(reverse("accounts_portal:portal_student"))
        student.user = self.user
        self.assertEqual(student_portal(student).url, reverse("portal_student:dashboard"))

        staff = self.factory.get(reverse("accounts_portal:portal_staff"))
        staff.user = self.user
        with patch("portal.views.views.get_post_login_portal_url", return_value=reverse("accounts_portal:portal_dashboard")):
            self.assertEqual(staff_portal(staff).url, reverse("accounts_portal:access_regularization"))

    @patch("portal.views.reenrollment.render")
    @patch("portal.views.reenrollment.build_role_dashboard_shell", return_value={"dashboard_shell": {"key": "reenrollment"}})
    @patch("portal.views.reenrollment.resolve_user_dashboard", return_value="/portal/manager/")
    @patch("portal.views.reenrollment.get_reenrollment_dashboard_context", return_value={})
    @patch("portal.views.reenrollment._resolve_reenrollment_filters", return_value=(None, None, None, None, None, None))
    @patch("portal.views.reenrollment._require_reenrollment_access", return_value=True)
    def test_full_reenrollment_page_uses_certified_shell_and_htmx_keeps_partial(
        self, _access, _filters, _context, _dashboard, shell, render_view
    ):
        self.assertEqual(
            get_template("portal/reenrollment/page.html").template.nodelist[0].parent_name.var,
            "portal/staff/director_dashboard.html",
        )
        request = self.factory.get(reverse("accounts_portal:reenrollment_workspace"))
        request.user = self.user
        reenrollment_workspace(request)
        self.assertEqual(render_view.call_args.args[1], "portal/reenrollment/page.html")
        self.assertEqual(shell.call_args.kwargs["key"], "reenrollment")
        self.assertEqual(shell.call_args.kwargs["workspace_template"], "portal/reenrollment/workspace.html")

        request = self.factory.get(reverse("accounts_portal:reenrollment_workspace"), HTTP_HX_REQUEST="true")
        request.user = self.user
        reenrollment_workspace(request)
        self.assertEqual(render_view.call_args.args[1], "portal/reenrollment/manager_workspace.html")

    def test_remaining_active_grade_pages_extend_the_certified_shell(self):
        for template_name in (
            "portal/staff/it_grades_import.html",
            "portal/admin/grades/dashboard.html",
        ):
            with self.subTest(template=template_name):
                template = get_template(template_name).template
                self.assertEqual(
                    template.nodelist[0].parent_name.var,
                    "portal/staff/director_dashboard.html",
                )

    def test_migrated_dashboard_fragments_still_compile(self):
        for template_name in (
            "portal/dg/modals/detail.html",
            "portal/staff/supervisor/partials/planner_workspace.html",
            "portal/staff/supervisor/partials/planner_class_hub.html",
            "portal/staff/supervisor/partials/weekly_slots_workspace.html",
            "portal/staff/supervisor/partials/schedule_week_grid.html",
            "portal/staff/partials/it_surveillance_workspace.html",
            "accounts/dashboard/partials/payment_modal.html",
            "accounts/dashboard/partials/inscription_modal.html",
            "superadmin/dashboard.html",
        ):
            with self.subTest(template=template_name):
                self.assertIsNotNone(get_template(template_name))
