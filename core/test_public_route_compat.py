from django.test import SimpleTestCase
from django.urls import reverse


class PublicRouteCompatibilityTests(SimpleTestCase):
    def test_recherche_route_redirects_to_canonical_landing_page(self):
        response = self.client.get(reverse("core:research_alias"))

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], reverse("core:research_innovation"))
