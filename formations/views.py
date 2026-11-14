from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch, Count, Q
from django.core.paginator import Paginator
from django_htmx.middleware import HtmxDetails
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
    schools = School.objects.filter(is_active=True).order_by("order", "code")

    school_token = (request.GET.get("school") or "").strip()
    active_school = None
    if school_token:
        active_school = get_object_or_404(School.objects.filter(
            is_active=True, code__iexact=school_token
        ))
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
        "schools": schools,
        "active_school": active_school,
        "programmes": programmes,
        "programme_count": programme_count,
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
def formation_detail(request, slug):
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
        == set(range(1, programme.duration_years + 1))
        and all(item["fees"] for item in years_with_totals)
    )
    if not complete_pricing:
        total_programme_cost = None
    average_year_cost = (
        total_programme_cost // programme.duration_years
        if total_programme_cost and programme.duration_years else None
    )

    # Déterminer le type de cycle pour affichage conditionnel
    cycle_name = programme.cycle.name.lower()
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
        .order_by("-is_featured", "title")[:3]
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

    context = {
        "programme": programme,
        "page_title": f"{programme.title} | UFHOB",
        "meta_description": programme.effective_meta_description,
        "meta_og_title": programme.effective_meta_title,
        "meta_og_description": programme.effective_meta_description,
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
    return render(
        request,
        "formations/detail.html",
        context
    )
