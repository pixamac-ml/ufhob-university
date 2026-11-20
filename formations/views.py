from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Count, Q
from django.core.paginator import Paginator
from django_htmx.middleware import HtmxDetails
from django.templatetags.static import static
from branches.models import Branch
from core.models import School, Testimonial

from .models import (
    Programme,
    ProgrammeYear,
    Cycle,
)


# ==================================================
# LISTE DES FORMATIONS (SCHOOL-DRIVEN)
# ==================================================
def formation_list(request):
    from .fatec_esga import grouped_programmes, public_catalogue_context
    schools = School.objects.public().order_by("order", "code")

    school_token = (request.GET.get("school") or "").strip()
    active_school = None
    from core.public_visibility import school_code_is_hidden
    if school_token and school_code_is_hidden(school_token):
        from django.shortcuts import redirect
        return redirect("formations:list")
    if school_token:
        active_school = get_object_or_404(School.objects.public().filter(code__iexact=school_token))
    if not active_school:
        active_school = schools.first()

    programmes = (
        Programme.objects.public()
        .select_related("school", "cycle", "filiere", "diploma_awarded")
        .filter(school=active_school)
        .order_by("cycle__name", "title")
    ) if active_school else Programme.objects.none()

    programme_count = programmes.count()

    context = {
        "page_title": "Formations DUT, Licence et Master | UFHOB-Mali | Bamako, Moribabougou",
        "meta_description": "Découvrez les formations DUT, Licence et Master de FATEC et ESGA à UFHOB-Mali, campus de Moribabougou près de Bamako. Candidatez en ligne.",
        "schools": schools,
        "active_school": active_school,
        "programmes": programmes,
        "programme_count": programme_count,
        "domain_groups": grouped_programmes(programmes) if active_school and active_school.code in ("FATEC", "ESGA") else [],
    }

    if request.htmx:
        return render(
            request,
            "formations/fragments/_programme_list.html",
            context
        )

    return render(
        request,
        "formations/list.html",
        context
    )


import json  # ← AJOUTE EN HAUT DU FICHIER

# ==================================================
# DÉTAIL D'UNE FORMATION
# ==================================================
def formation_detail(request, slug, school_code=None):
    from admissions.tracking import admission_url, capture_tracking
    from .fatec_esga import canonical_slug, public_catalogue_context
    from django.shortcuts import redirect

    resolved=canonical_slug(slug)
    if resolved != slug:
        target=get_object_or_404(Programme.objects.public().select_related('school'),slug=resolved)
        suffix='?'+request.GET.urlencode() if request.GET else ''
        return redirect(target.get_absolute_url()+suffix, permanent=True)

    # Formation d'une école masquée côté public : retour au catalogue, sans 404.
    if Programme.objects.filter(slug=slug).exclude(school__in=School.objects.public()).exclude(school__isnull=True).exists():
        return redirect("formations:list")

    capture_tracking(request)
    programme = get_object_or_404(
        Programme.objects.public()
        .select_related(
            "school",
            "cycle",
            "filiere",
            "diploma_awarded"
        )
        .prefetch_related(
            Prefetch(
                "years",
                queryset=ProgrammeYear.objects
                .order_by("year_number")
                .prefetch_related("fees")
            ),
            "required_documents__document",
            "quick_facts",
            "competence_blocks__items",
        ),
        slug=slug
    )
    if school_code and (not programme.school_id or programme.school.code.lower() != school_code.lower()):
        from django.http import Http404
        raise Http404("Cette formation n'appartient pas à cette école.")
    programme_years = programme.years.all()

    # Documents requis
    required_documents = [
        prd.document for prd in programme.required_documents.all()
    ]

    # Calcul des frais par année
    total_programme_cost = 0
    years_with_totals = []

    for year in programme_years:
        month_order = {"janvier": 1, "février": 2, "mars": 3, "avril": 4,
                       "mai": 5, "juin": 6, "juillet": 7, "août": 8,
                       "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12}
        fees = sorted(year.fees.all(), key=lambda fee: (
            0 if fee.label.casefold() == "inscription" else month_order.get(fee.due_month.casefold(), 13),
            fee.label.casefold(), fee.pk,
        ))
        year_total = sum(fee.amount for fee in fees) if fees else None
        total_programme_cost += year_total or 0

        years_with_totals.append({
            "year": year,
            "year_total": year_total,
            "fees": fees,
        })

    has_documents = bool(required_documents)
    has_fees = total_programme_cost > 0
    # Un M1 connu ne constitue pas le coût d'un Master complet : M2 peut
    # légitimement rester non tarifé dans le référentiel institutionnel.
    complete_pricing = (
        {year.year_number for year in programme_years}
        == set(range(1, (programme.duration_years or 0) + 1))
        and all(item["fees"] for item in years_with_totals)
    )
    if not complete_pricing:
        total_programme_cost = None
    average_year_cost = (
        total_programme_cost // programme.duration_years
        if total_programme_cost and programme.duration_years else None
    )

    # Déterminer le type de cycle pour affichage conditionnel
    cycle_name = programme.cycle.name.lower() if programme.cycle_id else ""
    cycle_type = next(
        (name for name in ("primaire", "secondaire", "licence", "master") if name in cycle_name),
        "autre",
    )

    # =============================================
    # OBJECTIFS DE FORMATION (JSON)
    # =============================================
    try:
        learning_objectives = json.loads(programme.learning_outcomes) if programme.learning_outcomes else []
    except (json.JSONDecodeError, TypeError):
        learning_objectives = []

    # Fallback si learning_outcomes n'est pas en JSON
    if not learning_objectives and programme.learning_outcomes:
        learning_objectives = [
            {
                "title": "Objectif",
                "desc": line.strip(),
                "icon": "lightbulb",
                "color": "primary",
            }
            for line in programme.learning_outcomes.splitlines()
            if line.strip()
        ]

    career_points = [line.strip(" -\u2022") for line in (programme.career_opportunities or "").splitlines() if line.strip()]
    structure_points = [line.strip(" -\u2022") for line in (programme.program_structure or "").splitlines() if line.strip()]

    testimonials = (
        Testimonial.objects
        .filter(is_active=True)
        .filter(Q(programme=programme) | Q(programme__isnull=True))
        .order_by("-is_featured", "order")[:3]
    )

    related_programmes = (
        Programme.objects.public()
        .exclude(pk=programme.pk)
        .filter(school=programme.school)
        .select_related("school", "cycle", "diploma_awarded")
        .order_by("-is_featured", "title")
    )

    campuses = Branch.objects.filter(is_active=True)
    if programme.school_id:
        campuses = campuses.filter(
            school_branches__school_id=programme.school_id,
            school_branches__school__is_active=True,
            school_branches__is_active=True,
        )
    campuses = campuses.distinct().order_by("name")
    main_branch = campuses.first()

    effective_og_image = programme.effective_og_image
    og_image_url = request.build_absolute_uri(effective_og_image.url) if effective_og_image else None

    from core.seo import programme_schema, programme_introduction, programme_breadcrumbs
    degree = programme.cycle.name if programme.cycle_id else ""
    programme_label = programme.title if degree.casefold() in programme.title.casefold() else f"{degree} — {programme.title}"
    context = {
        "programme_schema_json": programme_schema(programme),
        "programme_intro": programme_introduction(programme),
        "breadcrumb_schema_json": programme_breadcrumbs(programme),
        "pixel_content_name": programme.title,
        "programme": programme,
        "page_title": f"{programme_label} | UFHOB-Mali | Bamako, Moribabougou",
        "meta_description": f"{programme_label} à UFHOB-Mali, campus de Moribabougou près de Bamako : programme, conditions d’admission et candidature en ligne.",
        "og_image_url": og_image_url,
        "og_type": "article",
        "programme_years": programme_years,
        "years_with_totals": years_with_totals,
        "required_documents": required_documents,
        "has_documents": has_documents,
        "has_fees": has_fees,
        "can_apply": programme.admissions_open,
        "cycle_type": cycle_type,
        "total_cost": total_programme_cost,
        "total_programme_cost": total_programme_cost,
        "average_year_cost": average_year_cost,
        "learning_objectives": learning_objectives,
        "career_points": career_points,
        "structure_points": structure_points,
        "testimonials": testimonials,
        "related_programmes": related_programmes,
        "main_branch": main_branch,
        "campuses": campuses,
    }
    from django.conf import settings
    if programme.school_id and programme.school.code == 'ESMED' and 'ESMED' in settings.PUBLIC_FEES_SCHOOL_CODES:
        # Tableau année par année : inscription / en cours d'année / total.
        context['annual_fee_rows'] = [
            {
                'year_number': item['year'].year_number,
                'registration': sum(f.amount for f in item['fees'] if f.label.casefold() == 'inscription'),
                'during_year': sum(f.amount for f in item['fees'] if f.label.casefold() != 'inscription'),
                'total': item['year_total'],
            }
            for item in years_with_totals
            if item['fees'] and item['year'].year_number <= (programme.duration_years or 0)
        ]
    context['apply_url'] = admission_url(request, programme)
    if programme.school_id and programme.school.code in ('FATEC', 'ESGA'):
        context.update(public_catalogue_context())
        context['catalogue_scoped'] = True
        context['practical_tabs'] = programme.tabs.filter(slug='conditions-catalogue', is_active=True).prefetch_related('sections')
        if programme.cycle.name != 'Master':
            context['years_with_totals'] = [item for item in years_with_totals if item['year'].year_number == 1]
    return render(
        request,
        "formations/detail.html",
        context
    )
