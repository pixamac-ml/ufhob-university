"""Public metadata and safely serialized structured data."""
import json

from django.conf import settings
from django.templatetags.static import static
from django.utils.html import strip_tags
from django.urls import reverse

from .public_brand import BRAND_NAME, BRAND_INTRO


def schema_json(value):
    # JSON-LD lives inside a script element, including when text is editable.
    return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c")


def public_metadata(request):
    route = request.resolver_match.view_name if request.resolver_match else ""
    pages = {
        "core:home": (f"{BRAND_NAME} | Moribabougou, Bamako", BRAND_INTRO),
        "core:about": (f"À propos | {BRAND_NAME}", "Découvrez l’UFHOB-Mali, son projet universitaire, ses valeurs et son équipe au campus de Moribabougou, près de Bamako au Mali."),
        "core:faq": ("FAQ : formations, admissions et campus | UFHOB-Mali", "Les réponses aux questions sur UFHOB-Mali : Moribabougou, filières, DUT, Licence, Master, candidature, documents, rentrée et frais."),
        "admissions:admission_tunnel": ("Admissions et candidature en ligne | UFHOB-Mali", "Candidatez à UFHOB-Mali : choisissez votre formation et votre campus, renseignez votre dossier et transmettez votre candidature en ligne."),
        "core:contact": ("Contact | UFHOB-Mali", "Contactez UFHOB-Mali au +223 76 88 24 79, campus de Moribabougou près de Bamako. Posez vos questions sur les formations et les admissions."),
        "blog:article_list": ("Blog et articles | UFHOB-Mali", "Retrouvez les articles, conseils et perspectives de la communauté universitaire UFHOB-Mali à Moribabougou, près de Bamako."),
    }
    title, description = pages.get(route, ("UFHOB-Mali", "Découvrez les formations, les campus et la vie universitaire de l’UFHOB-Mali à Bamako et Moribabougou."))
    base = settings.PUBLIC_WEBSITE_URL.rstrip("/")
    return {
        "public_brand_name": BRAND_NAME,
        "public_brand_intro": BRAND_INTRO,
        "google_site_verification": settings.GOOGLE_SITE_VERIFICATION,
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
        "description": programme_introduction(programme),
        "url": base + programme.get_absolute_url(),
        "educationalCredentialAwarded": cycle,
        "provider": {"@type": "CollegeOrUniversity", "name": "UFHOB-Mali", "url": base},
    })


def programme_introduction(programme):
    """Texte distinct dérivé des seules données du programme ; aucune écriture."""
    degree = programme.cycle.name if programme.cycle_id else ""
    label = programme.title if degree.casefold() in programme.title.casefold() else f"{degree} — {programme.title}"
    school = f", au sein de {programme.school.display_name}," if programme.school_id else ""
    intro = f"La formation {label}{school} est présentée par UFHOB-Mali à Bamako et Moribabougou."
    detail = " ".join(strip_tags(programme.short_description or programme.description or "").split())
    outcomes_text = programme.career_opportunities or programme.learning_outcomes or ""
    try:
        learning = json.loads(outcomes_text)
    except (ValueError, TypeError):
        learning = None
    if isinstance(learning, list):
        outcomes_text = "; ".join(
            " — ".join(str(item[key]) for key in ("title", "desc") if item.get(key))
            if isinstance(item, dict) else str(item)
            for item in learning
        )
    outcomes = " ".join(strip_tags(outcomes_text).split()).rstrip(".")
    if detail:
        intro += " " + detail
    if outcomes:
        intro += " Compétences ou débouchés présentés pour ce parcours : " + outcomes + "."
    return intro


def breadcrumb_schema(items):
    base = settings.PUBLIC_WEBSITE_URL.rstrip("/")
    return schema_json({
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": base + path}
            for i, (name, path) in enumerate(items, 1)
        ],
    })


def programme_breadcrumbs(programme):
    items = [("Accueil", reverse("core:home")), ("Formations", reverse("formations:list"))]
    if programme.school_id:
        items.append((programme.school.display_name, reverse("core:school_detail", kwargs={"code": programme.school.code.lower()})))
    items.append((programme.title, programme.get_absolute_url()))
    return breadcrumb_schema(items)
