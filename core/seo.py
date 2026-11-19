"""Public metadata and safely serialized structured data."""
import json

from django.conf import settings
from django.templatetags.static import static
from django.utils.html import strip_tags


def schema_json(value):
    # JSON-LD lives inside a script element, including when text is editable.
    return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c")


def public_metadata(request):
    route = request.resolver_match.view_name if request.resolver_match else ""
    pages = {
        "core:home": ("UFHOB-Mali | Université privée à Moribabougou, Bamako", "Étudiez à l’Université Privée Félix Houphouët Boigny Mali : formations FATEC et ESGA, campus de Moribabougou près de Bamako. Candidatez en ligne."),
        "core:about": ("À propos | UFHOB-Mali | Moribabougou, Bamako", "Découvrez l’UFHOB-Mali, son projet universitaire, ses valeurs et son équipe au campus de Moribabougou, près de Bamako au Mali."),
        "admissions:admission_tunnel": ("Admissions et candidature en ligne | UFHOB-Mali", "Candidatez à UFHOB-Mali : choisissez votre formation et votre campus, renseignez votre dossier et transmettez votre candidature en ligne."),
        "core:contact": ("Contact | UFHOB-Mali", "Contactez UFHOB-Mali au +223 76 88 24 79, campus de Moribabougou près de Bamako. Posez vos questions sur les formations et les admissions."),
        "blog:article_list": ("Blog et articles | UFHOB-Mali", "Retrouvez les articles, conseils et perspectives de la communauté universitaire UFHOB-Mali à Moribabougou, près de Bamako."),
    }
    title, description = pages.get(route, ("UFHOB-Mali", "Découvrez les formations, les campus et la vie universitaire de l’UFHOB-Mali à Bamako et Moribabougou."))
    base = settings.PUBLIC_WEBSITE_URL.rstrip("/")
    return {
        "page_title": title,
        "meta_description": description,
        "seo_default_image": base + static("images/institution/ufhob-share.png"),
        "canonical_url": base + request.path,
        "meta_pixel_id": settings.META_PIXEL_ID if settings.META_PIXEL_ID.isascii() and settings.META_PIXEL_ID.isdecimal() else "",
        "pixel_initiate_checkout": route == "admissions:admission_tunnel",
    }


def programme_schema(programme):
    cycle = programme.cycle.name if programme.cycle_id else ""
    base = settings.PUBLIC_WEBSITE_URL.rstrip("/")
    return schema_json({
        "@context": "https://schema.org",
        "@type": "EducationalOccupationalProgram",
        "name": programme.title,
        "description": strip_tags(programme.effective_meta_description),
        "url": base + programme.get_absolute_url(),
        "educationalCredentialAwarded": cycle,
        "provider": {"@type": "CollegeOrUniversity", "name": "UFHOB-Mali", "url": base},
    })
