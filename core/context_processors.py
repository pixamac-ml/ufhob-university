import json

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

from branches.models import Branch
from formations.models import Programme
from core.models import Institution, LegalPage, School, SiteConfiguration
from core.branding import get_branding_assets
from core.public_contact import get_public_contact, get_public_social_links
from news.models import News


PUBLISHED_LEGAL_LINKS = (
    ("legal", "Mentions légales", "core:legal_notice"),
    ("privacy", "Politique de confidentialité", "core:privacy_policy"),
    ("terms", "Conditions d'utilisation", "core:terms_of_service"),
)


def get_published_legal_links():
    """Expose uniquement les pages légales effectivement publiées."""
    from django.urls import reverse

    try:
        published_types = set(
            LegalPage.objects.filter(status="published").values_list("page_type", flat=True)
        )
    except (ProgrammingError, OperationalError):
        return []

    return [
        {"label": label, "url": reverse(url_name)}
        for page_type, label, url_name in PUBLISHED_LEGAL_LINKS
        if page_type in published_types
    ]


def _absolute_media_url(path: str) -> str:
    if not path:
        return ""
    return f"{settings.BASE_URL}{path}"


def seo_defaults(request):
    from admissions.tracking import capture_tracking
    # Requêtes sans session (RequestFactory, rendus hors middleware) : pas d'attribution.
    campaign_tracking = capture_tracking(request) if hasattr(request, "session") else {}
    site_name = "UFHOB-Mali"
    default_description = (
        "UFHOB-Mali — Université privée engagée dans la formation, la recherche, "
        "l'innovation et l'accompagnement des étudiants."
    )
    default_image = ""
    public_schools = []

    try:
        institution = Institution.objects.filter(is_active=True).first()
        site_config = SiteConfiguration.objects.first()
        public_schools = list(
            School.objects.public()
            .only("id", "code", "short_name", "official_name", "order")
            .order_by("order", "code")
        )
    except (ProgrammingError, OperationalError):
        institution = None
        site_config = None

    if institution:
        site_name = "UFHOB-Mali"
        default_description = (
            f"{institution.name} - Formation universitaire, recherche, innovation "
            "et engagement au service des communautés."
        )

    if site_config and site_config.site_logo:
        default_image = _absolute_media_url(site_config.site_logo.url)

    canonical_url = f"{settings.BASE_URL}{request.path}"
    robots_value = "noindex, nofollow" if settings.DEBUG else "index, follow, max-image-preview:large"

    organization_schema = {
        "@context": "https://schema.org",
        "@type": "CollegeOrUniversity",
        "name": "Université Privée Félix Houphouët Boigny – Mali (UFHOB-Mali)",
        "alternateName": ["UFHOB", "UFHOB-Mali", "Université Félix Houphouët Boigny Mali"],
        "url": settings.PUBLIC_WEBSITE_URL,
    }

    public_contact = get_public_contact(institution)
    if public_contact["website"]:
        organization_schema["url"] = public_contact["website"]
    if public_contact["email"]:
        organization_schema["email"] = public_contact["email"]
    if public_contact["phones"]:
        organization_schema["telephone"] = [phone["href"][4:] for phone in public_contact["phones"]]
    if institution:
        organization_schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": institution.address,
            "addressLocality": institution.city,
            "addressCountry": institution.country,
        }

    from django.templatetags.static import static
    organization_schema["logo"] = settings.PUBLIC_WEBSITE_URL + static("images/institution/ufhob-logo.webp")
    organization_schema["telephone"] = "+223 76 88 24 79"
    organization_schema["address"] = {"@type": "PostalAddress", "streetAddress": "Campus de Moribabougou", "addressLocality": "Moribabougou", "addressRegion": "Koulikoro", "addressCountry": "ML"}
    organization_schema["areaServed"] = {"@type": "Country", "name": "Mali"}
    organization_schema["sameAs"] = [link["url"] for link in get_public_social_links(None) if link["key"] != "linkedin"]

    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site_name,
        "url": settings.PUBLIC_WEBSITE_URL,
    }

    social_links = get_public_social_links(site_config)
    try:
        has_published_news = News.objects.filter(status="published").exists()
    except (ProgrammingError, OperationalError):
        has_published_news = False
    from core.seo import public_metadata, schema_json
    return {
        "public_has_news": has_published_news,
        "seo_site_name": site_name,
        "seo_default_description": default_description,
        "seo_default_image": default_image,
        "canonical_url": canonical_url,
        "meta_robots": robots_value,
        "organization_schema_json": schema_json(organization_schema) if request.path == "/" else "",
        "website_schema_json": schema_json(website_schema),
        "public_institution": institution,
        "public_contact": public_contact,
        "public_social_links": social_links,
        "public_whatsapp_url": settings.PUBLIC_WHATSAPP_URL,
        "campaign_tracking": campaign_tracking,
        "public_fees_enabled": settings.PUBLIC_FEES_ENABLED,
        "public_site_logo_url": static("images/institution/ufhob-logo.webp"),
        "public_site_configuration": site_config,
        "public_schools": public_schools,
        "public_footer": {
            "schools": public_schools,
            "campuses": list(Branch.objects.filter(is_active=True).only("name", "slug").order_by("name")),
            "school_count": len(public_schools),
            "programme_count": Programme.objects.public().count(),
            "campus_count": Branch.objects.filter(is_active=True).count(),
        },
        **public_metadata(request),
    }


def public_legal_links(request):
    """Rend les liens légaux publiés disponibles à tous les templates publics."""
    from core.views import COOKIE_CONSENT_MAX_AGE, COOKIE_CONSENT_VERSION

    return {
        "public_legal_links": get_published_legal_links(),
        "cookie_consent_version": COOKIE_CONSENT_VERSION,
        "cookie_consent_max_age": COOKIE_CONSENT_MAX_AGE,
    }


def branding(request):
    """Provide the same safe logo fallback to public, email and PDF templates."""

    try:
        site_configuration = SiteConfiguration.objects.first()
    except (ProgrammingError, OperationalError):
        site_configuration = None
    return {"branding": get_branding_assets(site_configuration)}

