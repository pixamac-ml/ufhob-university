"""HTMX avatar regression checks for the shared certified staff account panel."""

import json
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image


def valid_png():
    image_bytes = BytesIO()
    Image.new("RGB", (1, 1), "#ffffff").save(image_bytes, format="PNG")
    return image_bytes.getvalue()


class StaffAvatarShellTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="avatar-shell-admin",
            email="avatar-shell@example.test",
            password="Example-pass-123!",
        )
        self.client.force_login(self.user)
        self.url = reverse("accounts_portal:staff_account_panel") + "?dash=superadmin&view=edit"

    def test_first_avatar_upload_returns_fresh_partial_and_refresh_event(self):
        with TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=Path(media_root)):
            response = self.client.post(
                self.url,
                {
                    "first_name": "Awa",
                    "last_name": "Traore",
                    "avatar": SimpleUploadedFile("portrait.png", valid_png(), content_type="image/png"),
                },
                HTTP_HX_REQUEST="true",
            )
            self.assertEqual(response.status_code, 200)
            self.user.profile.refresh_from_db()
            self.assertTrue(self.user.profile.avatar)
            self.assertNotIn(b"<html", response.content.lower())
            self.assertContains(response, 'data-user-avatar')
            self.assertContains(response, self.user.profile.avatar.url)
            event = json.loads(response.headers["HX-Trigger"])
            self.assertEqual(
                event["account:profile-updated"]["avatar_url"],
                self.user.profile.avatar.url,
            )

    def test_invalid_avatar_keeps_edit_partial_and_returns_errors(self):
        response = self.client.post(
            self.url,
            {
                "first_name": "Awa",
                "avatar": SimpleUploadedFile("portrait.exe", b"invalid", content_type="application/octet-stream"),
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b"<html", response.content.lower())
        self.assertContains(response, "avatar", status_code=400)
