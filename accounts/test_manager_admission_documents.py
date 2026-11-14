import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.test_manager_workflows import _create_branch, _create_programme, _create_user, _create_candidature
from admissions.models import CandidatureDocument
from formations.models import RequiredDocument, ProgrammeRequiredDocument
from inscriptions.models import Inscription


@override_settings(AUTH_POLICY_V2_ENABLED=False)
class ManagerAdmissionDocumentsTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory(dir=".")
        self.addCleanup(media.cleanup)
        override = override_settings(MEDIA_ROOT=media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.branch = _create_branch()
        self.programme = _create_programme()
        self.user = _create_user("document_manager", branch=self.branch)
        self.candidate = _create_candidature(self.programme, self.branch, status="to_complete")
        self.kind = RequiredDocument.objects.create(name="Document de test")
        ProgrammeRequiredDocument.objects.create(programme=self.programme, document=self.kind)
        self.client.force_login(self.user)

    def upload(self, candidate=None, kind=None, filename="piece.pdf"):
        return self.client.post(reverse("accounts:htmx_candidature_document_add", args=[(candidate or self.candidate).pk]), {
            "document_type": (kind or self.kind).pk,
            "file": SimpleUploadedFile(filename, b"%PDF-1.4 test", content_type="application/pdf"),
        }, HTTP_HX_REQUEST="true")

    def test_incomplete_candidate_has_decisions_and_can_be_accepted_without_documents(self):
        response = self.client.get(reverse("accounts:htmx_candidature_detail", args=[self.candidate.pk]))
        self.assertContains(response, "Compléter les documents")
        self.assertContains(response, reverse("accounts:htmx_candidature_accept", args=[self.candidate.pk]))
        response = self.client.post(reverse("accounts:htmx_candidature_accept", args=[self.candidate.pk]))
        self.assertEqual(response.status_code, 200)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, "accepted")
        self.assertEqual(self.candidate.reviewed_by, self.user)
        self.assertFalse(self.candidate.documents.exists())

    def test_upload_and_validate_after_enrollment_preserves_status(self):
        self.candidate.status = "accepted"
        self.candidate.save()
        enrollment = Inscription.objects.create(candidature=self.candidate, amount_due=100000)
        self.assertEqual(self.upload().status_code, 200)
        document = self.candidate.documents.get()
        self.assertFalse(document.is_valid)
        response = self.client.post(reverse("accounts:htmx_candidature_document_validate", args=[document.pk]))
        self.assertEqual(response.status_code, 200)
        document.refresh_from_db()
        self.assertTrue(document.is_valid)
        self.assertTrue(document.is_validated)
        self.assertEqual(document.validated_by, self.user)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.status, "accepted")
        self.assertEqual(self.candidate.inscription.pk, enrollment.pk)

    def test_invalid_and_duplicate_uploads_are_rejected(self):
        other_kind = RequiredDocument.objects.create(name="Autre document")
        self.assertContains(self.upload(kind=other_kind), "errorlist")
        self.assertContains(self.upload(filename="piece.exe"), "Format non autorisé")
        self.assertFalse(CandidatureDocument.objects.exists())
        self.upload()
        self.upload()
        self.assertEqual(CandidatureDocument.objects.count(), 1)

    def test_other_branch_and_deleted_candidates_are_protected(self):
        other = _create_candidature(self.programme, _create_branch(code="OTHER", name="Autre annexe de test"), email="other@test.com")
        self.assertEqual(self.upload(candidate=other).status_code, 404)
        foreign_doc = CandidatureDocument.objects.create(candidature=other, document_type=self.kind, file="foreign.pdf")
        self.assertEqual(self.client.post(reverse("accounts:htmx_candidature_document_validate", args=[foreign_doc.pk])).status_code, 404)
        self.candidate.is_deleted = True
        self.candidate.save()
        self.assertEqual(self.upload().status_code, 404)

    def test_user_without_admissions_capability_cannot_upload_or_validate(self):
        user = _create_user("finance_document_user", branch=self.branch, position="finance")
        self.client.force_login(user)
        self.assertEqual(self.upload().status_code, 403)
        document = CandidatureDocument.objects.create(candidature=self.candidate, document_type=self.kind, file="test.pdf")
        self.assertEqual(self.client.post(reverse("accounts:htmx_candidature_document_validate", args=[document.pk])).status_code, 403)
