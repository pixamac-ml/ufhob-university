"""Single presentation-level source for the currently available logo assets.

This deliberately exposes only files that exist today.  The source-library
assets in ``brand_assets/`` are not static assets and must be integrated in a
separate, explicit release once their final files have been delivered.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.templatetags.static import static


CURRENT_LOGO_FALLBACK = "images/students/logo-ubhob.png"


@dataclass(frozen=True)
class BrandingAssets:
    logo_full: str
    logo_mark: str
    email_logo: str
    document_logo: str
    favicon: str


def get_branding_assets(site_configuration=None) -> BrandingAssets:
    """Return usable presentation assets while retaining the existing fallback.

    ``SiteConfiguration.site_logo`` remains the authoritative configurable
    override.  All variants fall back to the one existing local raster asset
    until the approved asset pack is integrated.
    """

    configured_logo = ""
    if site_configuration and getattr(site_configuration, "site_logo", None):
        configured_logo = site_configuration.site_logo.url
    fallback = static(CURRENT_LOGO_FALLBACK)
    logo = configured_logo or fallback
    return BrandingAssets(
        logo_full=logo,
        logo_mark=logo,
        email_logo=logo,
        document_logo=logo,
        favicon=fallback,
    )
