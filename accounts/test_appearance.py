"""Appearance persistence and HTMX response contracts for authenticated users."""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.models import UserPreference


class AppearancePreferenceTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="appearance-user", password="Example-pass-123!"
        )
        self.other = get_user_model().objects.create_user(
            username="appearance-other", password="Example-pass-123!"
        )
        self.url = reverse("accounts:appearance_update")
        self.client.force_login(self.user)

    def test_authenticated_htmx_change_persists_without_full_page(self):
        preference = UserPreference.objects.create(user=self.user, notify_email=False)
        response = self.client.post(
            self.url, {"theme": "DARK", "font_scale": "XL"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        preference.refresh_from_db()
        self.assertEqual((preference.theme, preference.font_scale), ("DARK", "XL"))
        self.assertFalse(preference.notify_email)
        event = json.loads(response.headers["HX-Trigger"])
        self.assertEqual(event["account:preferences-updated"], {"theme": "DARK", "font_scale": "XL"})
        self.assertEqual(event["ui:toast"]["tone"], "success")
        self.assertFalse(UserPreference.objects.filter(user=self.other).exists())

    def test_all_modes_and_scales_are_accepted(self):
        for theme, scale in (("LIGHT", "SM"), ("SYSTEM", "MD"), ("DARK", "LG")):
            with self.subTest(theme=theme, scale=scale):
                response = self.client.post(
                    self.url, {"theme": theme, "font_scale": scale}, HTTP_HX_REQUEST="true"
                )
                self.assertEqual(response.status_code, 204)
                preference = UserPreference.objects.get(user=self.user)
                self.assertEqual((preference.theme, preference.font_scale), (theme, scale))

    def test_invalid_value_does_not_change_saved_preference(self):
        preference = UserPreference.objects.create(user=self.user, theme="LIGHT", font_scale="MD")
        response = self.client.post(
            self.url, {"theme": "INVALID", "font_scale": "XL"}, HTTP_HX_REQUEST="true"
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn(b"<html", response.content.lower())
        preference.refresh_from_db()
        self.assertEqual((preference.theme, preference.font_scale), ("LIGHT", "MD"))

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.post(self.url, {"theme": "DARK", "font_scale": "XL"})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(UserPreference.objects.filter(user=self.user).exists())
