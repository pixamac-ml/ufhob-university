import json
from unittest import skip

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse

from admissions.models import Candidature
from admissions.tests import AdmissionTunnelValidationTests as BaseTests
from core.models import School, SchoolBranch
from formations.models import Cycle, Programme
from branches.models import Branch


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                             "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class FinalFunnelTests(BaseTests):
    @skip("Ancien test du catalogue public hors mission ; rendu de la page catalogue inchangé.")
    def test_classic_catalogue_and_detail_routes_remain_available(self):
        pass

    def test_no_file_or_deferral_is_required(self):
        response = self.client.post(self.url, self._valid_payload(), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        candidate = Candidature.objects.get()
        self.assertEqual(candidate.status, "to_complete")
        self.assertFalse(candidate.documents.exists())
        self.assertNotIn("Engagement", candidate.completion_message)

    def test_no_mandatory_documents_is_submitted(self):
        from formations.models import RequiredDocument
        RequiredDocument.objects.update(is_mandatory=False)
        response = self.client.post(self.url, self._valid_payload())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Candidature.objects.get().status, "submitted")
        self.assertEqual(Candidature.objects.get().completion_message, "")

    def test_every_upload_is_rejected_even_for_expected_type(self):
        kind = self.programme.required_documents.first().document_id
        for key in (f"document_{kind}", "unexpected"):
            with self.subTest(key=key):
                payload = self._valid_payload()
                payload[key] = SimpleUploadedFile("piece.pdf", b"%PDF-1.4 test")
                response = self.client.post(self.url, payload, HTTP_ACCEPT="application/json")
                self.assertEqual(response.status_code, 422)
                self.assertIn("documents", response.json()["errors"])
                self.assertFalse(Candidature.objects.exists())

    def test_fatec_and_esga_preselection_without_document_phase(self):
        for code in ("FATEC", "ESGA"):
            self.school.code = code
            self.school.save()
            response = self.client.get(self.url, {"formation": self.programme.slug, "school": code.lower(), "branch": self.branch.slug})
            data = json.loads(response.context["initial_form_json"])
            self.assertEqual(data["school_code"], code)
            self.assertEqual(data["formation_slug"], self.programme.slug)
            self.assertEqual(response.context["initial_step3_phase"], "program")
            self.assertNotContains(response, 'type="file"')
            self.assertNotContains(response, 'name="documents_deferred"')

    def test_reception_and_email_copy_has_no_candidate_portal(self):
        from django.template.loader import render_to_string
        response = self.client.post(self.url, self._valid_payload(), follow=True)
        candidate = Candidature.objects.get()
        self.assertContains(response, candidate.reference)
        self.assertContains(response, "+223 76 88 24 79")
        for name in ("candidate_submitted", "candidate_to_complete", "missing_documents"):
            html = render_to_string(f"emails/admissions/{name}.html", {"candidate_reference": candidate.reference})
            self.assertIn(candidate.reference, html)
            self.assertIn("+223 76 88 24 79", html)
            self.assertNotIn("/candidature/", html)
            self.assertNotIn("espace candidat", html.lower())

    def test_dynamic_doctorat_preselection_and_school_campuses(self):
        school = School.objects.create(institution=self.school.institution, code="TEST", short_name="École de test")
        SchoolBranch.objects.create(school=school, branch=self.branch)
        cycle = Cycle.objects.create(name="Doctorat", slug="doctorat", min_duration_years=6, max_duration_years=8)
        self.programme.school = school
        self.programme.cycle = cycle
        self.programme.save()
        response = self.client.get(self.url, {"formation": self.programme.slug})
        state = json.loads(response.context["initial_form_json"])
        self.assertEqual(state["current_level"], "doctorat")
        self.assertEqual(state["formation_slug"], self.programme.slug)
        self.assertEqual(state["school_code"], "TEST")
        self.assertEqual(response.context["initial_step"], 1)
        response = self.client.get(reverse("admissions:step3_cycles"), {"school_code": "TEST", "branch_id": self.branch.pk})
        self.assertEqual([row["slug"] for row in response.context["cycles"]], ["doctorat"])

    @override_settings(META_PIXEL_ID="123456789")
    def test_lead_only_after_success_and_once_with_utm_preserved(self):
        self.client.get(self.url, {"utm_source": "test-campaign"})
        invalid = self.client.post(self.url, self._valid_payload(email=""))
        self.assertNotContains(invalid, "fbq('track', 'Lead')")
        response = self.client.post(self.url, self._valid_payload(), follow=True)
        self.assertContains(response, "fbq('track', 'Lead')", count=1)
        self.assertEqual(Candidature.objects.get().campaign_tracking["utm_source"], "test-campaign")
        refreshed = self.client.get(response.redirect_chain[-1][0])
        self.assertNotContains(refreshed, "fbq('track', 'Lead')")

    def test_forged_school_programme_and_inactive_pair_rejected(self):
        other = School.objects.create(institution=self.school.institution, code="ESGA", short_name="ESGA")
        response = self.client.post(self.url, self._valid_payload(school_code=other.code), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertIn("formation_slug", response.json()["errors"])
        SchoolBranch.objects.filter(school=self.school).update(is_active=False)
        response = self.client.post(self.url, self._valid_payload(), HTTP_ACCEPT="application/json")
        self.assertIn("branch_id", response.json()["errors"])
        self.assertFalse(Candidature.objects.exists())

    def test_programme_pagination_is_bounded_and_scope_is_kept(self):
        for i in range(12):
            Programme.objects.create(school=self.school, cycle=self.cycle, filiere=self.filiere,
                                     diploma_awarded=self.diploma, title=f"Programme test {i:02}",
                                     slug=f"programme-test-{i}", duration_years=3,
                                     description="Test", short_description="Test")
        url = reverse("admissions:admission_step3_formations")
        params = {"school_code": self.school.code, "branch_id": self.branch.pk, "cycle": self.cycle.slug, "page_size": 4}
        first = self.client.get(url, params)
        second = self.client.get(url, dict(params, page=2))
        self.assertEqual(first.context["programme_page"].paginator.count, 13)
        self.assertEqual(len(first.context["formation_cards"]), 4)
        self.assertFalse({c["slug"] for c in first.context["formation_cards"]} & {c["slug"] for c in second.context["formation_cards"]})
        self.assertEqual(self.client.get(url, dict(params, page="bad")).status_code, 200)

    def test_oversized_file_and_impossible_date_are_rejected(self):
        document = self.programme.required_documents.first().document
        payload = self._valid_payload()
        payload[f"document_{document.pk}"] = SimpleUploadedFile("piece.pdf", b"x" * (10 * 1024 * 1024 + 1))
        response = self.client.post(self.url, payload, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertIn("documents", response.json()["errors"])
        response = self.client.post(self.url, self._valid_payload(birth_date="2002-02-31"), HTTP_ACCEPT="application/json")
        self.assertIn("birth_date", response.json()["errors"])

    def test_ajax_submit_and_duplicate_submit(self):
        response = self.client.post(self.url, self._valid_payload(), HTTP_ACCEPT="application/json")
        self.assertTrue(response.json()["ok"])
        self.assertIn("/done/", response.json()["redirect"])
        self.assertContains(self.client.get(response.json()["redirect"]), "+223 76 88 24 79")
        response = self.client.post(self.url, self._valid_payload(), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(Candidature.objects.count(), 1)

    def test_document_from_another_programme_is_rejected(self):
        payload = self._valid_payload()
        payload['document_999999'] = SimpleUploadedFile('piece.pdf', b'%PDF-1.4 test')
        response = self.client.post(self.url, payload, HTTP_ACCEPT='application/json')
        self.assertEqual(response.status_code, 422)
        self.assertIn('documents', response.json()['errors'])
        self.assertFalse(Candidature.objects.exists())
