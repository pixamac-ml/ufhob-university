import json
from html.parser import HTMLParser

from django.test import TestCase, override_settings
from django.urls import reverse

from core.public_brand import BRAND_NAME
from core.test_public_delivery import PublicDeliveryTests
from formations.models import Programme, RequiredDocument, ProgrammeRequiredDocument


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.schemas, self.images, self.links = [], [], []
        self.json_text = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script" and attrs.get("type") == "application/ld+json":
            self.json_text = ""
        if tag == "img":
            self.images.append(attrs)
        if tag == "a":
            self.links.append(attrs.get("href"))

    def handle_data(self, data):
        if self.json_text is not None:
            self.json_text += data

    def handle_endtag(self, tag):
        if tag == "script" and self.json_text is not None:
            self.schemas.append(json.loads(self.json_text))
            self.json_text = None


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False, DEBUG=False,
                   META_PIXEL_ID="", GOOGLE_SITE_VERIFICATION="", STORAGES={
                       "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                       "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                   })
class BrandSeoTests(TestCase):
    setUpTestData = classmethod(PublicDeliveryTests.setUpTestData.__func__)

    def test_brand_schemas_and_complete_home_links(self):
        response = self.client.get("/")
        html = response.content.decode()
        self.assertContains(response, BRAND_NAME, count=None)
        self.assertEqual(response.context["home_hero_title"], BRAND_NAME)
        document = Document(html)
        university = next(s for s in document.schemas if s["@type"] == "CollegeOrUniversity")
        self.assertEqual(university["alternateName"], ["UFHOB", "UFHOB-Mali", "Université Félix Houphouët Boigny Mali"])
        self.assertEqual(university["address"]["addressRegion"], "Koulikoro")
        self.assertEqual(university["telephone"], "+223 76 88 24 79")
        self.assertEqual(university["sameAs"], ["https://www.instagram.com/ufhob_mali/"])
        for p in Programme.objects.public():
            self.assertIn(p.get_absolute_url(), document.links)
        self.assertIn("/ecoles/fatec/", document.links)
        self.assertIn("/ecoles/esga/", document.links)
        self.assertIn("/faq/", document.links)
        self.assertNotIn("google-site-verification", html)

    @override_settings(GOOGLE_SITE_VERIFICATION='token"test', SOCIAL_INSTAGRAM_URL="", SOCIAL_FACEBOOK_URL="https://www.facebook.com/ufhob")
    def test_search_console_escaping_and_optional_socials(self):
        html = self.client.get("/").content.decode()
        self.assertIn('content="token&quot;test"', html)
        university = next(s for s in Document(html).schemas if s["@type"] == "CollegeOrUniversity")
        self.assertEqual(university["sameAs"], ["https://www.facebook.com/ufhob"])

    def test_faq_schema_matches_eight_visible_answers_and_public_documents(self):
        doc = RequiredDocument.objects.create(name="Pièce de test publiée")
        ProgrammeRequiredDocument.objects.create(programme=self.programmes[0], document=doc)
        response = self.client.get("/faq/")
        self.assertEqual(response.status_code, 200)
        schema = next(s for s in Document(response.content.decode()).schemas if s["@type"] == "FAQPage")
        self.assertEqual(len(schema["mainEntity"]), 8)
        for item in schema["mainEntity"]:
            self.assertContains(response, item["name"])
            self.assertContains(response, item["acceptedAnswer"]["text"])
        self.assertContains(response, doc.name)
        self.assertContains(response, "5 octobre 2026")
        self.assertNotContains(response, "ESMED")
        self.assertContains(self.client.get("/sitemap.xml"), "https://www.ufhob-mali.ml/faq/")

    def test_filiere_intros_breadcrumbs_and_related_links(self):
        from core.seo import programme_introduction
        intros = []
        for programme in Programme.objects.public().select_related("school", "cycle"):
            intro = programme_introduction(programme)
            intros.append(intro)
            response = self.client.get(programme.get_absolute_url())
            self.assertContains(response, intro)
            for word in (programme.title, programme.cycle.name, "UFHOB-Mali", "Bamako"):
                self.assertIn(word, intro)
            schema = next(s for s in Document(response.content.decode()).schemas if s["@type"] == "BreadcrumbList")
            self.assertEqual(schema["itemListElement"][-1]["item"], "https://www.ufhob-mali.ml" + programme.get_absolute_url())
            self.assertEqual([item["position"] for item in schema["itemListElement"]], list(range(1, len(schema["itemListElement"]) + 1)))
        self.assertEqual(len(intros), len(set(intros)))
        for path in ("/ecoles/fatec/", "/ecoles/esga/"):
            self.assertIn("BreadcrumbList", [s["@type"] for s in Document(self.client.get(path).content.decode()).schemas])

    def test_images_and_real_404(self):
        for path in ("/", "/apropos/", "/ecoles/fatec/", "/faq/", self.programmes[0].get_absolute_url()):
            for img in Document(self.client.get(path).content.decode()).images:
                self.assertTrue(img.get("alt", "").strip(), (path, img))
                self.assertTrue(img.get("width"), (path, img))
                self.assertTrue(img.get("height"), (path, img))
                self.assertTrue(img.get("loading") or img.get("fetchpriority") == "high", (path, img))
        response = self.client.get("/page-inexistante-test/")
        self.assertEqual(response.status_code, 404)
        links = Document(response.content.decode()).links
        for path in ("/", "/formations/", "/admissions/"):
            self.assertIn(path, links)
        self.assertNotContains(response, "ESMED", status_code=404)

    def test_images_in_editable_programme_content_have_attributes(self):
        programme = self.programmes[0]
        programme.description = '<p>Présentation <img src="/static/photo-test.jpg" alt="" title="Test &gt; image"></p>'
        programme.save(update_fields=["description"])
        response = self.client.get(programme.get_absolute_url())
        images = Document(response.content.decode()).images
        image = next(img for img in images if img.get("src") == "/static/photo-test.jpg")
        self.assertEqual(image["alt"], programme.title)
        self.assertEqual(image["loading"], "lazy")
        self.assertEqual((image["width"], image["height"]), ("1200", "800"))
