import json
from html.parser import HTMLParser

from django.test import TestCase, override_settings

from core.models import Infrastructure, Institution, School, Staff
from formations.models import Cycle, Filiere, Programme
from ui.components.layout.footer.footer import Footer
from ui.components.layout.navbar.navbar import Navbar


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.h1 = 0
        self.meta = {}
        self.canonical = []
        self.title = ""
        self.in_title = False
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "h1":
            self.h1 += 1
        if tag == "meta":
            self.meta[attrs.get("name", attrs.get("property"))] = attrs.get("content")
        if tag == "link" and attrs.get("rel") == "canonical":
            self.canonical.append(attrs["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"], SECURE_SSL_REDIRECT=False,
                   META_PIXEL_ID="", STORAGES={
                       "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                       "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
                   })
class PublicDeliveryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.institution = Institution.objects.create(name="UFHOB-Mali", short_name="UFHOB", phone="+223 76 88 24 79")
        cls.cycle = Cycle.objects.create(name="Licence", min_duration_years=3, max_duration_years=3)
        cls.filiere = Filiere.objects.create(name="Filière de test")
        cls.programmes = []
        for code in ("FATEC", "ESGA", "ESMED", "ESFÉ", "HIDDEN"):
            school = School.objects.create(institution=cls.institution, code=code, short_name=code,
                                          is_public=code != "HIDDEN")
            cls.programmes.append(Programme.objects.create(
                title=f"Licence {code}", school=school, cycle=cls.cycle, filiere=cls.filiere,
                description="Formation de test", short_description="Présentation de test", duration_years=3,
            ))

    def test_about_handles_missing_optional_media(self):
        Staff.objects.create(full_name="Équipe de test", position="Direction", category="direction", photo="")
        Infrastructure.objects.create(name="Espace de test", description="Présentation", image="")
        response = self.client.get("/apropos/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Équipe de test")

    def test_unique_metadata_single_heading_canonical_and_social(self):
        descriptions = []
        urls = ["/", "/formations/", "/ecoles/fatec/", "/ecoles/esga/", "/apropos/",
                "/admissions/", "/contact/", "/plan-du-site/", "/blog/"]
        urls += [p.get_absolute_url() for p in self.programmes[:2]]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                html = response.content.decode()
                page = Page(html)
                self.assertEqual(page.h1, 1)
                self.assertEqual(page.canonical, ["https://www.ufhob-mali.ml" + url])
                descriptions.append(page.meta["description"])
                self.assertIn("UFHOB-Mali", page.meta["og:title"])
                self.assertEqual(page.title.strip(), page.meta["og:title"])
                self.assertEqual(page.meta["og:title"], page.meta["twitter:title"])
                self.assertIn("ufhob-share.png", page.meta["og:image"])
                self.assertNotIn("chart.umd", html)
                self.assertNotIn("fbevents.js", html)
                self.assertNotIn("fbq(", html)
                self.assertNotIn("communautes", html)
                self.assertNotIn("Diplôme reconnu par l'État", html)
                for hidden in ("ESMED", "ESMed", "ESFé Sup", "Licence HIDDEN"):
                    self.assertNotIn(hidden, html)
        self.assertEqual(len(descriptions), len(set(descriptions)))

    def test_hidden_objects_do_not_escape_public_querysets_or_sitemap(self):
        self.assertEqual(Programme.objects.public().count(), 2)
        self.assertEqual(School.objects.public().count(), 2)
        navbar = Navbar().get_context_data()
        self.assertEqual(sum(len(c.programmes.all()) for c in navbar["cycles"]), 2)
        self.assertEqual(Footer._default_stats()[0]["value"], 2)
        xml = self.client.get("/sitemap.xml")
        self.assertEqual(xml.status_code, 200)
        for p in self.programmes[2:]:
            self.assertNotContains(xml, p.get_absolute_url())
            self.assertRedirects(self.client.get(p.get_absolute_url()), "/formations/", fetch_redirect_response=False)
        self.assertContains(xml, "https://www.ufhob-mali.ml/ecoles/fatec/")
        self.assertNotContains(xml, "testserver")
        self.assertContains(self.client.get("/robots.txt"), "Sitemap: https://www.ufhob-mali.ml/sitemap.xml")

    @override_settings(META_PIXEL_ID="123456789")
    def test_pixel_pageview_viewcontent_and_checkout(self):
        self.assertContains(self.client.get("/"), "fbq('track', 'PageView')")
        detail = self.client.get(self.programmes[0].get_absolute_url())
        self.assertContains(detail, "fbq('track', 'ViewContent'")
        self.assertContains(detail, "content_name: 'Licence FATEC'")
        self.assertContains(self.client.get("/admissions/"), "fbq('track', 'InitiateCheckout')")
        self.assertNotContains(detail, "fbq('track', 'Lead')")

    def test_structured_data_and_script_escaping(self):
        home = self.client.get("/").content.decode()
        self.assertIn('"@type": "CollegeOrUniversity"', home)
        self.assertIn('"telephone": "+223 76 88 24 79"', home)
        self.assertIn("Campus de Moribabougou", home)
        from core.seo import programme_schema
        p = self.programmes[0]
        p.title = "</script><script>alert(1)</script>"
        serialized = programme_schema(p)
        self.assertNotIn("</script>", serialized)
        self.assertEqual(json.loads(serialized)["name"], p.title)
        self.assertContains(self.client.get(p.get_absolute_url()), '"@type": "EducationalOccupationalProgram"')
