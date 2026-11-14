import json
import os
from pathlib import Path
import subprocess
import tempfile
from unittest import skipUnless

from django.conf import settings
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.test_manager_workflows import (
    _create_academic_class, _create_branch, _create_candidature,
    _create_positioning_fee, _create_programme, _create_user,
)
from inscriptions.models import Inscription


@override_settings(AUTH_POLICY_V2_ENABLED=False)
class RegistrationStabilityTests(TestCase):
    def setUp(self):
        self.branch = _create_branch()
        self.programme = _create_programme()
        self.manager = _create_user("registration_manager", branch=self.branch)
        self.candidate = _create_candidature(self.programme, self.branch, status="accepted")
        self.academic_class = _create_academic_class(self.programme, self.branch)
        _create_positioning_fee(self.programme, level="L1", amount=100000)
        self.client.force_login(self.manager)

    def test_invalid_class_selection_returns_form_instead_of_server_error(self):
        url = reverse("accounts:htmx_inscription_create", args=[self.candidate.pk])
        for value in ("", "not-a-class", "-1", "999999999999999999999999999999999"):
            with self.subTest(value=value):
                response = self.client.post(url, {"academic_class": value})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "Selectionnez une classe existante")
        self.assertFalse(Inscription.objects.exists())

    def test_incompatible_programme_class_cannot_create_enrollment(self):
        self.academic_class.is_active = False
        self.academic_class.save()
        response = self.client.post(
            reverse("accounts:htmx_inscription_create", args=[self.candidate.pk]),
            {"academic_class": self.academic_class.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Inscription.objects.exists())

    @skipUnless(os.environ.get("UFHOB_REGISTRATION_BROWSER_TESTS") == "1", "Opt-in browser test")
    def test_acceptance_modal_remains_open_and_positioning_script_runs(self):
        _create_academic_class(self.programme, self.branch, level="L2")
        _create_positioning_fee(self.programme, level="L2", amount=150000)
        self.candidate.status = "to_complete"
        self.candidate.save()
        detail_url = reverse("accounts:htmx_candidature_detail", args=[self.candidate.pk])
        accept_url = reverse("accounts:htmx_candidature_accept", args=[self.candidate.pk])
        positioning_url = reverse("accounts:htmx_inscription_positioning", args=[self.candidate.pk])
        detail = self.client.get(detail_url)
        accepted = self.client.post(accept_url)
        positioning = self.client.get(positioning_url)
        type(self.academic_class).objects.filter(programme=self.programme).update(is_active=False)
        blocked_positioning = self.client.get(positioning_url)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(positioning.status_code, 200)
        payload = {
            "candidateId": self.candidate.pk,
            "detail": detail.content.decode(),
            "acceptUrl": accept_url,
            "positioningUrl": positioning_url,
            "accepted": accepted.content.decode(),
            "headers": dict(accepted.headers),
            "positioning": positioning.content.decode(),
            "blockedPositioning": blocked_positioning.content.decode(),
        }
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR) as directory:
            fixture = Path(directory) / "responses.json"
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                ["node", "accounts/check_registration_stability.cjs", str(fixture)],
                cwd=settings.BASE_DIR, capture_output=True, text=True, timeout=90,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
