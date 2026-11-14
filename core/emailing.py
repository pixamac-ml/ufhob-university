from urllib.parse import urljoin
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string
from django.utils import timezone

from core.models import Institution, SiteConfiguration
from core.branding import get_branding_assets
from core.pdf_documents import OFFICIAL_SLOGAN, OFFICIAL_UNIVERSITY_NAME


logger = logging.getLogger(__name__)


def get_formatted_from_email():
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@localhost")
    from_name = getattr(settings, "EMAIL_FROM_NAME", "").strip()
    if from_name:
        return f"{from_name} <{from_email}>"
    return from_email


def get_email_branding_context():
    """Construit l'identité UFHOB sans URL ni réseau social supposé."""
    institution = Institution.objects.first()
    site_configuration = SiteConfiguration.objects.first()
    base_url = getattr(settings, "BASE_URL", "").rstrip("/")
    branding_assets = get_branding_assets(site_configuration)

    if institution:
        institution_name = institution.name or OFFICIAL_UNIVERSITY_NAME
        institution_short_name = institution.short_name or "UFHOB"
        institution_email = institution.email or getattr(settings, "DEFAULT_FROM_EMAIL", "")
        institution_phone = institution.phone or ""
        institution_address = ", ".join(filter(None, [institution.address, institution.city, institution.country]))
    else:
        institution_name = OFFICIAL_UNIVERSITY_NAME
        institution_short_name = "UFHOB"
        institution_email = getattr(settings, "DEFAULT_FROM_EMAIL", "")
        institution_phone = ""
        institution_address = ""

    return {
        "institution": institution,
        "institution_name": institution_name,
        "institution_short_name": institution_short_name,
        "institution_email": institution_email,
        "institution_phone": institution_phone,
        "institution_address": institution_address,
        "institution_website": base_url,
        "institution_slogan": OFFICIAL_SLOGAN,
        "logo_url": urljoin(base_url + "/", branding_assets.email_logo) if base_url else branding_assets.email_logo,
        "social_links": [
            ("Facebook", getattr(site_configuration, "facebook_url", "")),
            ("Instagram", getattr(site_configuration, "instagram_url", "")),
            ("LinkedIn", getattr(site_configuration, "linkedin_url", "")),
            ("YouTube", getattr(site_configuration, "youtube_url", "")),
            ("TikTok", getattr(site_configuration, "tiktok_url", "")),
            ("WhatsApp", getattr(site_configuration, "whatsapp_url", "")),
        ],
        "year": timezone.now().year,
    }


def send_templated_email(
    *,
    subject,
    recipient,
    text_template=None,
    html_template=None,
    context=None,
    attachments=None,
    fallback_text="",
    fail_silently=False,
):
    """Envoi standardise texte + HTML avec contexte institutionnel."""
    if not recipient:
        return False

    merged_context = {}
    merged_context.update(get_email_branding_context())
    if context:
        merged_context.update(context)

    text_body = ""
    html_body = ""

    if text_template:
        try:
            text_body = render_to_string(text_template, merged_context)
        except TemplateDoesNotExist:
            logger.warning("Template texte introuvable: %s", text_template)
        except Exception:
            logger.exception("Echec rendu template texte: %s", text_template)
    if html_template:
        try:
            html_body = render_to_string(html_template, merged_context)
        except TemplateDoesNotExist:
            logger.warning("Template HTML introuvable: %s", html_template)
        except Exception:
            logger.exception("Echec rendu template HTML: %s", html_template)

    if not text_body and html_body:
        text_body = fallback_text or "Veuillez consulter la version HTML de cet email."
    elif not text_body:
        text_body = fallback_text or ""

    message = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=get_formatted_from_email(),
        to=[recipient],
    )

    if html_body:
        message.attach_alternative(html_body, "text/html")

    for attachment in attachments or []:
        path = attachment.get("path")
        if not path:
            continue
        try:
            with open(path, "rb") as file_obj:
                message.attach(
                    attachment.get("name") or path.split("/")[-1].split("\\")[-1],
                    file_obj.read(),
                    attachment.get("mimetype") or "application/octet-stream",
                )
        except FileNotFoundError:
            logger.warning("Piece jointe email introuvable: %s", path)
        except Exception:
            logger.exception("Echec attachement email: %s", path)

    message.send(fail_silently=fail_silently)
    return True

