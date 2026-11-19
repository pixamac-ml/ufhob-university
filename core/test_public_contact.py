from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings
from django.template.loader import render_to_string

from core.public_contact import get_public_contact, get_public_social_links


VALID_CONTACTS = dict(
    PUBLIC_CAMPAIGN_PHONE="+223 76 88 24 79",
    PUBLIC_WEBSITE_URL="https://www.ufhob-mali.ml",
    PUBLIC_SOCIAL_HANDLE="@ufhob_officiel",
    PUBLIC_CONTACT_EMAIL="",
)


@override_settings(**VALID_CONTACTS)
class PublicContactTests(SimpleTestCase):
    def institution(self, **changes):
        values = dict(email="universite@univ-fhb-mali.org", phone="76 37 88 66 / 00223 66.37.88.66",
                      address="Moribabougou", city="Bamako", country="Mali")
        return SimpleNamespace(**(values | changes))

    def test_only_validated_campaign_contacts_are_published(self):
        contact = get_public_contact(self.institution())
        self.assertEqual([p["href"] for p in contact["phones"]], ["tel:+22376882479"])
        self.assertEqual(contact["phones"][0]["label"], "+223 76 88 24 79")
        self.assertEqual(contact["website"], "https://www.ufhob-mali.ml")
        self.assertEqual(contact["website_label"], "www.ufhob-mali.ml")
        self.assertEqual(contact["social_handle"], "@ufhob_officiel")
        # Ancien domaine et anciens numéros stockés dans Institution : jamais publiés.
        self.assertEqual(contact["email"], "")
        self.assertEqual(contact["address"], "Moribabougou, Bamako, Mali")

    def test_postal_box_is_never_published(self):
        contact = get_public_contact(self.institution(address="BP 1234 Moribabougou"))
        self.assertEqual(contact["address"], "")

    def test_footer_renders_single_source_without_obsolete_contacts(self):
        contact = get_public_contact(self.institution())
        html = render_to_string("cotton/public/footer.html", {"public_contact": contact})
        self.assertIn('href="tel:+22376882479"', html)
        self.assertIn("www.ufhob-mali.ml", html)
        self.assertIn("@ufhob_officiel", html)
        for obsolete in ("univ-fhb-mali.org", "76 37 88 66", "66.37.88.66", "provisoire"):
            self.assertNotIn(obsolete, html)

    def test_empty_and_placeholder_social_links_are_hidden(self):
        self.assertEqual(get_public_social_links(None), [])
        config = SimpleNamespace(facebook_url="#", instagram_url="https://example.com/account", youtube_url="javascript:alert(1)")
        self.assertEqual(get_public_social_links(config), [])

    def test_configured_social_link_exposes_existing_icon(self):
        config = SimpleNamespace(facebook_url="https://www.facebook.com/ufhob", instagram_url="", tiktok_url="", youtube_url="", linkedin_url="")
        links = get_public_social_links(config)
        self.assertEqual([link["key"] for link in links], ["facebook"])
        self.assertEqual(links[0]["icon"], "fa-brands fa-facebook-f")
