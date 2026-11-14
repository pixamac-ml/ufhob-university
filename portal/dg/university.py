"""Institutional supervision using existing schools, offerings and histories."""

from django.core.paginator import Paginator
from django.db.models import Count, Exists, OuterRef, Prefetch, Q

from academics.models import AcademicClass
from branches.models import Branch
from core.models import School, SchoolBranch
from formations.models import Programme

from .scoping import scoped
from .selectors import get_dg_base_querysets


def admissions_context(request, navigation):
    queryset = get_dg_base_querysets(navigation.scoped_branch_ids, academic_year=navigation.academic_year)["candidatures"]
    query = (request.GET.get("q") or "").strip()[:120]
    if query:
        queryset = queryset.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(programme__title__icontains=query))
    return {
        "admission_page": Paginator(queryset.select_related("programme__school", "branch").order_by("-submitted_at", "-pk"), 25).get_page(request.GET.get("page")),
        "admission_query": query,
    }


def university_indicators(navigation, *, summaries=None):
    base = get_dg_base_querysets(navigation.scoped_branch_ids, academic_year=navigation.academic_year)
    staff = base["staff"].aggregate(total=Count("pk", distinct=True), teachers=Count("pk", filter=Q(position="teacher"), distinct=True))
    return {
        "schools": 1 if navigation.selected_school else len(navigation.available_schools),
        "campuses": len(navigation.scoped_branches),
        "implantations": sum(1 for school, branch in navigation.school_branch_pairs if branch in navigation.scoped_branch_ids and (not navigation.selected_school or school == navigation.selected_school.pk)),
        "programmes": scoped(Programme).filter(is_active=True, is_archived=False).count(),
        "candidatures": sum(item["candidature_count"] for item in summaries) if summaries is not None else base["candidatures"].count(),
        "enrollments": sum(item["enrollment_count"] for item in summaries) if summaries is not None else base["enrollments"].count(),
        "staff": staff["total"],
        "teachers": staff["teachers"],
    }


def structure_context(request, navigation):
    links = SchoolBranch.objects.select_related("branch").order_by("branch__name")
    if navigation.selected_branch:
        links = links.filter(branch=navigation.selected_branch)
    schools = scoped(School).annotate(programme_count=Count("programmes", distinct=True)).prefetch_related(
        Prefetch("school_branches", queryset=links, to_attr="dg_implantations"),
        Prefetch("programmes", queryset=Programme.objects.order_by("title"), to_attr="dg_programmes"),
    )
    campuses = scoped(Branch).prefetch_related(
        Prefetch("school_branches", queryset=SchoolBranch.objects.select_related("school").order_by("school__code"), to_attr="dg_schools")
    ).order_by("name")
    programmes = scoped(Programme).select_related("school", "cycle").prefetch_related(
        Prefetch("school__school_branches", queryset=links.filter(is_active=True, branch__is_active=True), to_attr="dg_offerings")
    ).order_by("school__code", "title")
    query = (request.GET.get("q") or "").strip()[:120]
    if query:
        programmes = programmes.filter(Q(title__icontains=query) | Q(school__code__icontains=query))
    classes = scoped(AcademicClass).filter(branch_id__in=navigation.scoped_branch_ids)
    if navigation.academic_year:
        classes = classes.filter(academic_year=navigation.academic_year)
    valid_pair = SchoolBranch.objects.filter(
        school_id=OuterRef("programme__school_id"), branch_id=OuterRef("branch_id"),
        is_active=True, school__is_active=True,
    )
    inconsistent_classes = classes.filter(programme__school__isnull=False).annotate(valid_offering=Exists(valid_pair)).filter(valid_offering=False)
    page = Paginator(programmes, 25).get_page(request.GET.get("page"))
    return {
        "university_indicators": university_indicators(navigation),
        "structure_schools": schools,
        "structure_campuses": campuses,
        "structure_implantations": scoped(SchoolBranch).select_related("school", "branch").order_by("school__code", "branch__name"),
        "structure_view": request.GET.get("structure_view") if request.GET.get("structure_view") in {"schools", "campuses", "implantations", "programmes"} else "schools",
        "structure_programmes": page,
        "structure_query": query,
        "unassigned_programmes": Programme.objects.filter(school__isnull=True).count() if not navigation.selected_school else None,
        "inconsistent_classes": inconsistent_classes.count(),
    }
