"""Focused checks for university dashboard mutations and context boundaries."""

from django.test import TestCase, override_settings
from django.urls import reverse

from branches.models import Branch
from core.models import School, SchoolBranch
from core import test_ufhob_phase2 as fixtures
from formations.models import Programme
from portal.dg.forms import DgProgrammeForm


@override_settings(AXES_ENABLED=False)
class UniversityStructureDashboardTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)

    def setUp(self):
        self.client.force_login(self.global_user)

    def test_school_create_edit_and_duplicate_validation(self):
        url = reverse("accounts_portal:dg_school_editor")
        self.assertContains(self.client.get(url), "Créer une école")
        data = {"code": "test-new", "short_name": "École de test", "order": 0, "is_active": "on"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 200)
        school = School.objects.get(code="TEST-NEW")
        self.assertEqual(response.json()["context_params"]["scope_school_id"], str(school.pk))
        self.assertEqual(self.client.post(url, data).status_code, 400)
        data.update(school_id=school.pk, official_name="Nom fourni par l’utilisateur")
        self.assertEqual(self.client.post(url, data).status_code, 200)
        school.refresh_from_db()
        self.assertEqual(school.official_name, data["official_name"])

    def test_implantation_reuses_campus_and_preserves_closed_pair(self):
        url = reverse("accounts_portal:dg_implantation_editor")
        data = {"school_id": self.schools[1].pk, "branch": self.b.pk, "is_active": "on"}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        link = SchoolBranch.objects.get(school=self.schools[1], branch=self.b)
        self.assertEqual(Branch.objects.count(), 2)
        self.assertTrue(Programme.objects.available_on(self.b).filter(pk=self.programmes[1].pk).exists())
        self.assertEqual(self.client.post(url, data).status_code, 400)
        data.update(link_id=link.pk)
        data.pop("is_active")
        scoped_url = f"{url}?scope_school_id={self.schools[1].pk}&scope_branch_id={self.b.pk}"
        response = self.client.post(scoped_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["context_params"], {"scope_branch_id": ""})
        link.refresh_from_db()
        self.assertFalse(link.is_active)
        self.assertFalse(Programme.objects.available_on(self.b).filter(pk=self.programmes[1].pk).exists())
        self.assertTrue(SchoolBranch.objects.filter(school=self.schools[0], branch=self.b, is_active=True).exists())

    def test_university_page_exposes_hierarchy_and_scoped_catalogue(self):
        url = reverse("accounts_portal:dg_section", args=["university"])
        response = self.client.get(url)
        self.assertContains(response, "Créer une école")
        self.assertContains(response, "Rattacher un campus")
        self.assertContains(response, "Campus physiques")
        response = self.client.get(url, {"scope_school_id": self.schools[0].pk, "scope_branch_id": self.b.pk})
        self.assertContains(response, self.programmes[0].title)
        self.assertNotContains(response, self.programmes[1].title)
        self.assertEqual(list(response.context["structure_campuses"]), [self.b])

    def test_non_executive_and_local_executive_cannot_mutate_structure(self):
        local_dg = self.make_user("local-executive", "executive_director", self.a, self.schools[0], "SCHOOL_BRANCH")
        for user in (self.director, local_dg):
            self.client.force_login(user)
            for route in ("dg_school_editor", "dg_implantation_editor", "dg_branch_save", "dg_programme_save", "dg_programme_reference_save", "dg_programme_archive"):
                with self.subTest(user=user.pk, route=route):
                    self.assertEqual(self.client.post(reverse(f"accounts_portal:{route}"), {}).status_code, 403)

    def test_forged_scope_or_object_is_rejected(self):
        url = reverse("accounts_portal:dg_school_editor")
        response = self.client.post(f"{url}?scope_school_id={self.schools[0].pk}", {"school_id": self.schools[1].pk})
        self.assertEqual(response.status_code, 404)
        response = self.client.post(f"{url}?scope_school_id={self.schools[1].pk}&scope_branch_id={self.b.pk}", {})
        self.assertEqual(response.status_code, 400)
        response = self.client.post(reverse("accounts_portal:dg_programme_save") + f"?scope_school_id={self.schools[0].pk}", {"programme_id": self.programmes[1].pk})
        self.assertEqual(response.status_code, 404)
        self.assertTrue(DgProgrammeForm().fields["school"].required)

    def test_school_director_selects_only_its_operational_campuses(self):
        director = self.make_user("school-director", "director_of_studies", school=self.schools[0], access_scope="SCHOOL")
        self.client.force_login(director)
        url = reverse("accounts_portal:portal_dashboard")
        response = self.client.get(url, {"context_branch_id": self.b.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.wsgi_request.access_context.branch, self.b)
        self.assertEqual(response.wsgi_request.access_context.school, self.schools[0])
        self.assertContains(response, self.schools[0].code)
        self.assertContains(response, self.b.name)
        self.assertEqual(self.client.get(url, {"context_branch_id": "999999"}).status_code, 403)
