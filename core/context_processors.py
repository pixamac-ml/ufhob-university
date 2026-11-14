import json

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

from branches.models import Branch
from formations.models import Programme
from core.models import Institution, LegalPage, School, SiteConfiguration
from core.branding import get_branding_assets
from core.public_contact import get_public_contact, get_public_social_links


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
    site_name = "UFHOB"
    default_description = (
        "UFHOB - Universite privee engagee dans la formation, la recherche, "
        "l'innovation et l'accompagnement des etudiants."
    )
    default_image = ""
    public_schools = []

    try:
        institution = Institution.objects.filter(is_active=True).first()
        site_config = SiteConfiguration.objects.first()
        public_schools = list(
            School.objects.filter(is_active=True)
            .only("id", "code", "short_name", "official_name", "order")
            .order_by("order", "code")
        )
    except (ProgrammingError, OperationalError):
        institution = None
        site_config = None

    if institution:
        site_name = institution.short_name or institution.name or site_name
        default_description = (
            f"{institution.name} - Formation universitaire, recherche, innovation "
            "et engagement au service des communautes."
        )

    if site_config and site_config.site_logo:
        default_image = _absolute_media_url(site_config.site_logo.url)

    canonical_url = f"{settings.BASE_URL}{request.path}"
    robots_value = "noindex, nofollow" if settings.DEBUG else "index, follow, max-image-preview:large"

    organization_schema = {
        "@context": "https://schema.org",
        "@type": "EducationalOrganization",
        "name": site_name,
        "url": settings.BASE_URL,
    }

    if institution:
        organization_schema["email"] = institution.email
        phones = get_public_contact(institution)["phones"]
        if phones:
            organization_schema["telephone"] = [phone["href"][4:] for phone in phones]
        organization_schema["address"] = {
            "@type": "PostalAddress",
            "streetAddress": institution.address,
            "addressLocality": institution.city,
            "addressCountry": institution.country,
        }

    if default_image:
        organization_schema["logo"] = default_image

    website_schema = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": site_name,
        "url": settings.BASE_URL,
    }

    social_links = get_public_social_links(site_config)
    return {
        "seo_site_name": site_name,
        "seo_default_description": default_description,
        "seo_default_image": default_image,
        "canonical_url": canonical_url,
        "meta_robots": robots_value,
        "organization_schema_json": json.dumps(organization_schema, ensure_ascii=True),
        "website_schema_json": json.dumps(website_schema, ensure_ascii=True),
        "public_institution": institution,
        "public_contact": get_public_contact(institution),
        "public_social_links": social_links,
        "public_whatsapp_url": next((link["url"] for link in social_links if link["label"] == "WhatsApp"), ""),
        "public_site_logo_url": site_config.site_logo.url if site_config and site_config.site_logo else "",
        "public_site_configuration": site_config,
        "public_schools": public_schools,
        "public_footer": {
            "schools": public_schools,
            "campuses": list(Branch.objects.filter(is_active=True).only("name", "slug").order_by("name")),
            "school_count": len(public_schools),
            "programme_count": Programme.objects.public().count(),
            "campus_count": Branch.objects.filter(is_active=True).count(),
        },
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

