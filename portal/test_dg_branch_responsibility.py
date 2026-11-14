from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from accounts.models import InstitutionalProfile
from branches.models import Branch
from portal.dg.context import DgDashboardContext
from portal.dg.selectors import get_active_branches, get_dg_base_querysets
from portal.dg.services import _build_branch_summaries, _build_dg_branch_list


class DgBranchAcademicResponsibilityTests(TestCase):
    """DG annex listings must use the official academic assignment, not Branch.manager."""

    @classmethod
    def setUpTestData(cls):
        cls.branch_a = Branch.objects.create(
            name="Annexe responsabilité A", code="RA", slug="responsabilite-a"
        )
        cls.branch_b = Branch.objects.create(
            name="Annexe responsabilité B", code="RB", slug="responsabilite-b"
        )
        cls.branch_without_director = Branch.objects.create(
            name="Annexe sans DE", code="RS", slug="responsabilite-sans-de"
        )

    def _staff(self, username, *, branch, position, employment_status="active", active=True):
        user = get_user_model().objects.create_user(
            username=username,
            password="StrongPassword!2042",
            first_name=username.title(),
            last_name="ESFE",
            is_active=active,
        )
        profile = user.profile
        profile.user_type = "staff"
        profile.position = position
        profile.branch = branch
        profile.employment_status = employment_status
        profile.save()
        return user

    def _summaries(self):
        branches = list(get_active_branches())
        base = get_dg_base_querysets([branch.id for branch in branches])
        return {
            item["branch"].id: item
            for item in _build_branch_summaries(branches, base)
        }

    def test_responsible_column_follows_active_director_assignment(self):
        director_a = self._staff(
            "director-a", branch=self.branch_a, position="director_of_studies"
        )
        director_b = self._staff(
            "director-b", branch=self.branch_b, position="director_of_studies"
        )
        inactive_director = self._staff(
            "director-inactive",
            branch=self.branch_a,
            position="director_of_studies",
            employment_status="inactive",
        )
        legacy_manager = self._staff(
            "manager-legacy", branch=self.branch_a, position="annex_manager"
        )
        self.branch_a.manager = legacy_manager
        self.branch_a.save(update_fields=["manager"])

        summaries = self._summaries()

        self.assertEqual(
            summaries[self.branch_a.id]["manager_name"],
            director_a.get_full_name(),
        )
        self.assertEqual(
            summaries[self.branch_b.id]["manager_name"],
            director_b.get_full_name(),
        )
        self.assertFalse(summaries[self.branch_without_director.id]["manager_name"])
        self.assertNotIn(
            director_b.get_full_name(),
            summaries[self.branch_a.id]["academic_responsible_names"],
        )
        self.assertNotIn(
            inactive_director.get_full_name(),
            summaries[self.branch_a.id]["academic_responsible_names"],
        )
        self.assertNotIn(
            legacy_manager.get_full_name(),
            summaries[self.branch_a.id]["academic_responsible_names"],
        )

        request = RequestFactory().get("/")
        context = DgDashboardContext(
            academic_year=None,
            academic_years=[],
            all_branches=list(get_active_branches()),
            selected_branch=None,
            mode="global",
        )
        listing = _build_dg_branch_list(request, context, section="annexes")
        rows = {row["id"]: row for row in listing["backoffice_rows"]}
        self.assertEqual(
            rows[f"dg-branch-{self.branch_a.id}"]["cells"][1]["value"],
            director_a.get_full_name(),
        )
        self.assertEqual(
            rows[f"dg-branch-{self.branch_without_director.id}"]["cells"][1]["value"],
            "Non assigné",
        )

    def test_branch_summary_uses_one_batched_academic_responsibility_query(self):
        self._staff("director-query-a", branch=self.branch_a, position="director_of_studies")
        self._staff("director-query-b", branch=self.branch_b, position="director_of_studies")
        branches = list(get_active_branches())
        base = get_dg_base_querysets([branch.id for branch in branches])

        with CaptureQueriesContext(connection) as queries:
            summaries = _build_branch_summaries(branches, base)

        self.assertEqual(len(summaries), 3)
        # Seven aggregate queries plus one batched assignment query: never one
        # lookup per annexe.
        self.assertLessEqual(len(queries), 8)

    @override_settings(AUTH_POLICY_V2_ENABLED=True)
    def test_policy_v2_uses_institutional_assignment_as_the_authority(self):
        director = self._staff(
            "director-policy-v2", branch=self.branch_a, position="director_of_studies"
        )
        institutional = InstitutionalProfile.objects.get(user=director)
        institutional.branch = self.branch_b
        institutional.save(update_fields=["branch", "updated_at"])

        summaries = self._summaries()

        self.assertFalse(summaries[self.branch_a.id]["manager_name"])
        self.assertEqual(
            summaries[self.branch_b.id]["manager_name"], director.get_full_name()
        )
