"""Coordonnées publiques UFHOB : source unique pour tout le site vitrine.

Seules les coordonnées validées pour la campagne 2026-2027 sont exposées :
téléphone ``PUBLIC_CAMPAIGN_PHONE``, site ``PUBLIC_WEBSITE_URL`` et compte
``PUBLIC_SOCIAL_HANDLE``. Les anciens numéros, l'ancien domaine et la boîte
postale éventuellement stockés dans ``Institution`` ne sont jamais publiés.
"""

import re
from urllib.parse import urlsplit

from django.conf import settings


def _phone_entry(value):
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 8:
        digits = "223" + digits
    if not digits:
        return None
    return {"label": value.strip(), "href": "tel:+" + digits}


def get_public_contact(institution):
    contact = {
        "email": (getattr(settings, "PUBLIC_CONTACT_EMAIL", "") or "").strip(),
        "address": "",
        "phones": [],
        "website": "",
        "website_label": "",
        "social_handle": (getattr(settings, "PUBLIC_SOCIAL_HANDLE", "") or "").strip(),
    }
    phone = _phone_entry(getattr(settings, "PUBLIC_CAMPAIGN_PHONE", ""))
    if phone:
        contact["phones"].append(phone)
    if institution:
        # Localisation uniquement (ville / pays) : aucune boîte postale.
        address = ", ".join(filter(None, (institution.address, institution.city, institution.country)))
        if not re.search(r"\b(B\.?\s?P\.?|bo[iî]te postale)\b", address, re.IGNORECASE):
            contact["address"] = address
    website = (getattr(settings, "PUBLIC_WEBSITE_URL", "") or "").strip()
    netloc = urlsplit(website).netloc
    if netloc:
        contact["website"] = website
        contact["website_label"] = netloc
    return contact


SOCIAL_NETWORKS = (
    ("facebook", "Facebook", "fa-brands fa-facebook-f"),
    ("instagram", "Instagram", "fa-brands fa-instagram"),
    ("tiktok", "TikTok", "fa-brands fa-tiktok"),
    ("youtube", "YouTube", "fa-brands fa-youtube"),
    ("linkedin", "LinkedIn", "fa-brands fa-linkedin-in"),
)


def get_public_social_links(configuration):
    """URL issues de SiteConfiguration ; une URL vide ou fictive masque l'icône."""
    links = []
    for key, label, icon in SOCIAL_NETWORKS:
        configured = getattr(settings, f"SOCIAL_{key.upper()}_URL", None)
        value = (configured if configured is not None else getattr(configuration, f"{key}_url", "")) or ""
        value = value.strip()
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname and parsed.hostname not in {
            "example.com", "www.example.com", "example.org", "localhost",
        }:
            links.append({"key": key, "label": label, "url": value, "icon": icon})
    return links
