from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings
from django.template.loader import render_to_string

from core.public_contact import get_public_contact, get_public_social_links


class PublicContactTests(SimpleTestCase):
    def institution(self, **changes):
        values = dict(email="office@example.org", phone="76 37 88 66 / 00223 66.37.88.66",
                      address="Moribabougou", city="Bamako", country="Mali")
        return SimpleNamespace(**(values | changes))

    @override_settings(PUBLIC_CONTACT_PHONES_CONFIRMED=False, BASE_URL="http://localhost:8000")
    def test_unconfirmed_phones_and_development_domain_are_not_published(self):
        contact = get_public_contact(self.institution())
        self.assertEqual(contact["phones"], [])
        self.assertEqual(contact["website"], "")
        self.assertEqual(contact["email"], "office@example.org")
        self.assertEqual(contact["address"], "Moribabougou, Bamako, Mali")

    @override_settings(PUBLIC_CONTACT_PHONES_CONFIRMED=True, BASE_URL="https://www.univ-fhb-mali.org")
    def test_confirmed_contacts_have_separate_dialable_links(self):
        contact = get_public_contact(self.institution())
        self.assertEqual([p["href"] for p in contact["phones"]], ["tel:+22376378866", "tel:+22366378866"])
        self.assertEqual(contact["website"], "https://www.univ-fhb-mali.org")
        self.assertEqual(get_public_contact(self.institution(email="new@example.org"))["email"], "new@example.org")
        html = render_to_string("cotton/public/footer.html", {"public_contact": contact})
        self.assertIn('href="tel:+22376378866"', html)
        self.assertIn('href="tel:+22366378866"', html)
        self.assertIn('href="mailto:office@example.org"', html)
        self.assertNotIn("Coordonnée à renseigner", html)

    def test_empty_and_placeholder_social_links_are_hidden(self):
        self.assertEqual(get_public_social_links(None), [])
        config = SimpleNamespace(facebook_url="#", instagram_url="https://example.com/account", youtube_url="javascript:alert(1)")
        self.assertEqual(get_public_social_links(config), [])
