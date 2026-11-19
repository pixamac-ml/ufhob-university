from collections import defaultdict
from urllib.parse import urlencode

from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch
from formations.models import Programme
from memoires.models import Memoire
from news.models import Event

from .models import (
    Infrastructure,
    Institution,
    InstitutionPresentation,
    InstitutionStat,
    DirectorGeneralMessage,
    Partner,
    School,
    SchoolBranch,
    SiteConfiguration,
    Staff,
    UniversityLifeItem,
    Value,
)


def _hidden_school_code(code):
    from .public_visibility import school_code_is_hidden
    return school_code_is_hidden(code)


def school_detail(request, code):
    from .seo import breadcrumb_schema
    def school_breadcrumbs(school):
        return breadcrumb_schema([("Accueil", reverse("core:home")), (school.display_name, reverse("core:school_detail", kwargs={"code": school.code.lower()}))])
    if _hidden_school_code(code):
        return redirect("formations:list")
    if code.upper() in ('FATEC','ESGA'):
        from formations.fatec_esga import grouped_programmes, public_catalogue_context
        school=get_object_or_404(School.objects.public(),code__iexact=code)
        programmes=Programme.objects.public().filter(school=school).select_related('school','cycle','filiere','diploma_awarded')
        return render(request, 'formations/scoped_catalogue.html', {
            'page_title': f'{school.display_name} | UFHOB-Mali | Bamako, Moribabougou',
            'breadcrumb_schema_json': school_breadcrumbs(school),
            'meta_description': f'Découvrez les formations de {school.display_name} à UFHOB-Mali, campus de Moribabougou près de Bamako. Consultez les filières et candidatez en ligne.',
            'catalogue_schools': [{'school': school, 'domains': grouped_programmes(programmes)}],
            **public_catalogue_context(),
        })
    public_programmes = (
        Programme.objects.public()
        .select_related("school", "cycle", "diploma_awarded", "filiere")
        .order_by("cycle__min_duration_years", "cycle__name", "title")
    )
    school = get_object_or_404(
        School.objects.public()
        .select_related("institution")
        .prefetch_related(
            Prefetch("programmes", queryset=public_programmes, to_attr="public_programmes"),
            Prefetch(
                "school_branches",
                queryset=SchoolBranch.objects.filter(is_active=True, branch__is_active=True)
                .select_related("branch")
                .order_by("branch__name"),
                to_attr="public_school_branches",
            ),
        ),
        code__iexact=code,
    )

    programmes = list(school.public_programmes)
    school_branches = list(school.public_school_branches)

    # Cycles réellement proposés par l'école, groupés dynamiquement.
    grouped = {}
    for programme in programmes:
        bucket = grouped.setdefault(
            programme.cycle_id, {"cycle": programme.cycle, "programmes": []}
        )
        bucket["programmes"].append(programme)
    programmes_by_cycle = sorted(
        grouped.values(),
        key=lambda bucket: (bucket["cycle"].min_duration_years, bucket["cycle"].name) if bucket["cycle"] else (0, ""),
    )
    cycles = [bucket["cycle"] for bucket in programmes_by_cycle if bucket["cycle"]]

    # Domaines enseignés, dérivés des filières réelles des programmes.
    domain_names = []
    for programme in programmes:
        name = programme.filiere.name if programme.filiere_id else ""
        if name and name not in domain_names:
            domain_names.append(name)
    domain_label = " · ".join(domain_names[:3])

    # Débouchés/perspectives : affichés uniquement lorsque les données existent.
    outcome_programmes = [
        programme
        for programme in programmes
        if programme.career_opportunities or programme.learning_outcomes
    ]

    admission_base = reverse("admissions:admission_tunnel")
    default_cta_url = f"{admission_base}?{urlencode({'school': school.code})}"
    campus_names = ", ".join(presence.branch.name for presence in school_branches)
    for presence in school_branches:
        presence.programme_count = len(programmes)
        presence.apply_url = (
            f"{admission_base}?"
            f"{urlencode({'school': school.code, 'branch': presence.branch.slug})}"
        )

    hero_image_url = school.hero_image.url if school.hero_image else ""

    return render(
        request,
        "public/school_detail.html",
        {
            "school": school,
            "breadcrumb_schema_json": school_breadcrumbs(school),
            "programmes": programmes,
            "programmes_by_cycle": programmes_by_cycle,
            "cycles": cycles,
            "domain_label": domain_label,
            "outcome_programmes": outcome_programmes,
            "school_branches": school_branches,
            "campus_names": campus_names,
            "hero_image_url": hero_image_url,
            "school_apply_url": default_cta_url,
            "school_can_apply": any(programme.admissions_open for programme in programmes),
            "school_cta_title": school.cta_title or f"Construisez votre parcours au sein de {school.display_name}",
            "school_cta_text": school.cta_text or "Choisissez un programme et un campus compatible dans le parcours de candidature UFHOB.",
            "school_cta_button_text": school.cta_button_text or "Candidater",
            "school_cta_button_url": school.cta_button_url or default_cta_url,
            "page_title": f"{school.display_name} | UFHOB-Mali | Bamako, Moribabougou",
            "meta_description": school.description or f"Découvrez {school.display_name}, ses formations et ses campus à UFHOB-Mali, Bamako et Moribabougou.",
        },
    )


def campus_life(request):
    site_configuration = SiteConfiguration.objects.first()
    infrastructures = Infrastructure.objects.filter(is_active=True).order_by("order", "name")[:8]
    life_items = UniversityLifeItem.objects.filter(is_active=True).order_by("order", "title")
    return render(
        request,
        "public/campus_life.html",
        {
            "infrastructures": infrastructures,
            "life_items": life_items,
            "site_configuration": site_configuration,
            "page_title": "Vie universitaire | UFHOB",
            "meta_description": "Découvrez les activités, services, ressources et équipements de la vie universitaire à l’UFHOB.",
        },
    )


def campus_detail(request, slug):
    """Fiche publique d'un campus, dérivée exclusivement de Branch/SchoolBranch."""
    campus = get_object_or_404(
        Branch.objects.filter(is_active=True).prefetch_related(
            Prefetch(
                "school_branches",
                queryset=SchoolBranch.objects.filter(is_active=True, school__in=School.objects.public())
                .select_related("school")
                .order_by("school__order", "school__code"),
                to_attr="active_school_branches",
            )
        ),
        slug=slug,
    )
    school_ids = [presence.school_id for presence in campus.active_school_branches]
    campus.public_programmes = list(
        Programme.objects.public().filter(school_id__in=school_ids)
        .select_related("school", "cycle", "diploma_awarded")
        .order_by("school__order", "title")
    )
    map_query = ", ".join(part for part in (campus.address, campus.city) if part)
    return render(request, "public/campus_detail.html", {
        "campus": campus,
        "map_query": urlencode({"q": map_query}) if map_query else "",
        "page_title": f"{campus.name} | Campus UFHOB",
        "meta_description": f"Informations pratiques et composantes du campus {campus.name} de l’UFHOB.",
    })


def university(request):
    institution = Institution.objects.filter(is_active=True).first()
    presentation = InstitutionPresentation.objects.first()
    site_configuration = SiteConfiguration.objects.first()

    infrastructures = Infrastructure.objects.filter(is_active=True).order_by("order")[:8]
    values = Value.objects.filter(is_active=True).order_by("order")
    partners = Partner.objects.filter(is_active=True).order_by("order", "name")
    stats = InstitutionStat.objects.filter(is_active=True).order_by("order")
    director_message = DirectorGeneralMessage.objects.filter(is_active=True).first()

    leader = (
        Staff.objects.filter(
            is_active=True, category="direction", position__icontains="recteur"
        )
        .order_by("-is_featured", "order")
        .first()
    )
    if not leader:
        leader = (
            Staff.objects.filter(
                is_active=True, category="direction", is_featured=True
            )
            .order_by("order")
            .first()
        )
    if not leader:
        leader = Staff.objects.filter(is_active=True, category="direction").order_by("order").first()

    team = Staff.objects.filter(
        is_active=True, is_featured=True
    ).order_by("order", "full_name")[:12]

    administration_members = Staff.objects.filter(
        is_active=True,
        category__in=("direction", "admin"),
    ).order_by("order", "full_name")[:8]

    schools = (
        School.objects.public()
        .select_related("institution")
        .prefetch_related(
            Prefetch(
                "school_branches",
                queryset=SchoolBranch.objects.filter(is_active=True).select_related("branch").order_by("branch__name"),
                to_attr="active_branches",
            )
        )
        .order_by("order", "code")
    )

    branches = Branch.objects.filter(is_active=True).order_by("name")

    programme_count = Programme.objects.public().count()
    school_count = schools.count()
    branch_count = branches.count()
    infrastructure_count = infrastructures.count()

    about_image = ""
    if presentation and presentation.about_image:
        about_image = presentation.about_image.url
    elif site_configuration and site_configuration.about_main_image:
        about_image = site_configuration.about_main_image.url

    hero_image = ""
    if site_configuration and site_configuration.about_hero_background_image:
        hero_image = site_configuration.about_hero_background_image.url
    elif site_configuration and site_configuration.home_hero_image:
        hero_image = site_configuration.home_hero_image.url
    elif about_image:
        hero_image = about_image

    intro_title = (
        presentation.about_title
        if presentation and presentation.about_title
        else "L’UFHOB en quelques mots"
    )
    intro_text = (
        presentation.about_text
        if presentation and presentation.about_text
        else ""
    )

    cta_title = (
        presentation.cta_title
        if presentation and presentation.cta_title
        else "Construisez votre parcours à l’UFHOB"
    )
    cta_text = (
        presentation.cta_subtitle
        if presentation and presentation.cta_subtitle
        else "Rejoignez une université plurielle engagée par l’excellence et l’innovation."
    )
    cta_button_text = (
        presentation.cta_button_text
        if presentation and presentation.cta_button_text
        else "Candidater"
    )
    cta_button_url = (
        presentation.cta_button_url
        if presentation and presentation.cta_button_url
        else reverse("admissions:admission_tunnel")
    )

    leader_label = (
        institution.director_title
        if institution and institution.director_title
        else "Rectorat"
    )

    return render(
        request,
        "public/university.html",
        {
            "institution": institution,
            "presentation": presentation,
            "site_configuration": site_configuration,
            "infrastructures": infrastructures,
            "values": values,
            "stats": stats,
            "partners": partners,
            "leader": leader,
            "director_message": director_message,
            "leader_label": leader_label,
            "team": team,
            "administration_members": administration_members,
            "schools": schools,
            "branches": branches,
            "programme_count": programme_count,
            "school_count": school_count,
            "branch_count": branch_count,
            "infrastructure_count": infrastructure_count,
            "about_image": about_image,
            "hero_image": hero_image,
            "intro_title": intro_title,
            "intro_text": intro_text,
            "cta_title": cta_title,
            "cta_text": cta_text,
            "cta_button_text": cta_button_text,
            "cta_button_url": cta_button_url,
            "page_title": "L’université | UFHOB",
            "meta_description": (
                institution.name if institution else "UFHOB"
            ) + " — Découvrir l’institution, son dirigeant, ses équipes et ses infrastructures.",
        },
    )


def research_innovation(request):
    site_configuration = SiteConfiguration.objects.first()
    research_terms = (
        Q(title__icontains="recherche")
        | Q(title__icontains="scientifique")
        | Q(title__icontains="innovation")
        | Q(description__icontains="recherche")
        | Q(description__icontains="scientifique")
        | Q(description__icontains="innovation")
        | Q(event_type__name__icontains="recherche")
        | Q(event_type__name__icontains="scientifique")
        | Q(event_type__name__icontains="innovation")
        | Q(event_type__name__icontains="conférence")
        | Q(event_type__name__icontains="conference")
    )
    scientific_events = (
        Event.objects.filter(is_published=True, is_archived=False)
        .filter(research_terms, event_date__gte=timezone.localdate())
        .select_related("event_type")
        .order_by("event_date", "start_time")[:4]
    )
    scientific_works = (
        Memoire.objects.filter(statut=Memoire.Statut.PUBLIE)
        .select_related("filiere")
        .order_by("-est_mis_en_avant", "-date_publication", "-date_depot")[:6]
    )
    research_infrastructures = Infrastructure.objects.filter(
        is_active=True, category__in=("laboratory", "equipment", "library")
    ).order_by("order", "name")[:6]
    return render(
        request,
        "public/research_innovation.html",
        {
            "scientific_events": scientific_events,
            "scientific_works": scientific_works,
            "research_infrastructures": research_infrastructures,
            "site_configuration": site_configuration,
            "page_title": "Recherche & Innovation | UFHOB",
            "meta_description": "Recherche, innovation, travaux academiques et diffusion des savoirs a l'UFHOB.",
        },
    )
