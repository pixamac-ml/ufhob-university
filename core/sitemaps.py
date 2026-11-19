from django.contrib.sitemaps import Sitemap
from django.urls import NoReverseMatch, reverse

from blog.models import Article
from formations.models import Programme
from news.models import News
from core.models import LegalPage, School
from django.conf import settings


class CanonicalSitemap(Sitemap):
    protocol = "https"

    def get_urls(self, page=1, site=None, protocol=None):
        from types import SimpleNamespace
        from urllib.parse import urlsplit
        return super().get_urls(page, SimpleNamespace(domain=urlsplit(settings.PUBLIC_WEBSITE_URL).netloc), "https")


class StaticViewSitemap(CanonicalSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        items = [
            "core:home",
            "core:about",
            "core:faq",
            "core:contact",
            "core:sitemap",
            "formations:list",
            "admissions:admission_tunnel",
            "core:university",
            "news:list",
            "news:result_list",
            "blog:article_list",
        ]
        legal_urls = {
            "legal": "core:legal_notice",
            "privacy": "core:privacy_policy",
            "terms": "core:terms_of_service",
        }
        published_types = set(
            LegalPage.objects.filter(status="published").values_list("page_type", flat=True)
        )
        return items + [
            url_name for page_type, url_name in legal_urls.items() if page_type in published_types
        ]

    def location(self, item):
        try:
            return reverse(item)
        except NoReverseMatch:
            return "/"


class ProgrammeSitemap(CanonicalSitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Programme.objects.public().select_related("school").order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


class SchoolSitemap(CanonicalSitemap):
    def items(self):
        return School.objects.public()

    def location(self, obj):
        return reverse("core:school_detail", kwargs={"code": obj.code.lower()})


class NewsSitemap(CanonicalSitemap):
    changefreq = "daily"
    priority = 0.8

    def items(self):
        return News.objects.filter(status=News.STATUS_PUBLISHED).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


class BlogArticleSitemap(CanonicalSitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self):
        return Article.objects.filter(status="published", is_deleted=False).order_by("-updated_at")

    def lastmod(self, obj):
        return obj.updated_at


def build_sitemaps():
    return {
        "static": StaticViewSitemap,
        "formations": ProgrammeSitemap,
        "schools": SchoolSitemap,
        "news": NewsSitemap,
        "blog": BlogArticleSitemap,
    }
