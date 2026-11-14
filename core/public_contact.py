"""Presentation of the existing institutional contact configuration."""

import re
from urllib.parse import urlsplit

from django.conf import settings


def get_public_contact(institution):
    """Keep Institution authoritative; normalize links without changing stored data."""
    contact = {"email": "", "address": "", "phones": [], "website": "", "website_label": ""}
    if institution:
        contact["email"] = institution.email
        contact["address"] = ", ".join(filter(None, (
            institution.address, institution.city, institution.country,
        )))
        phone_value = institution.phone if settings.PUBLIC_CONTACT_PHONES_CONFIRMED else ""
        for number in re.split(r"[/;]", phone_value or ""):
            digits = re.sub(r"\D", "", number)
            if digits.startswith("00223"):
                digits = digits[2:]
            if len(digits) == 8:
                digits = "223" + digits
            if len(digits) == 11 and digits.startswith("223"):
                contact["phones"].append({"label": number.strip(), "href": "tel:+" + digits})
    # Never promote a development host or an inherited domain as the public site.
    url = urlsplit(settings.BASE_URL)
    if url.scheme == "https" and url.netloc in {"univ-fhb-mali.org", "www.univ-fhb-mali.org"}:
        contact["website"] = f"https://{url.netloc}"
        contact["website_label"] = url.netloc
    return contact


def get_public_social_links(configuration):
    """Omit empty/placeholder destinations from the public presentation."""
    links = []
    for key, label in (
        ("facebook", "Facebook"), ("instagram", "Instagram"),
        ("tiktok", "TikTok"), ("youtube", "YouTube"),
        ("linkedin", "LinkedIn"), ("whatsapp", "WhatsApp"),
    ):
        value = (getattr(configuration, f"{key}_url", "") or "").strip()
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.hostname and parsed.hostname not in {
            "example.com", "www.example.com", "example.org", "localhost",
        }:
            links.append({"label": label, "url": value})
    return links
