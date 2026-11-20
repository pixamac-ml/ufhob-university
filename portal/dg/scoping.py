"""DG navigation narrows reads without changing the executive's authorization."""

from contextvars import ContextVar
from dataclasses import replace
from functools import wraps

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.db.models.functions import Coalesce
from django.http import HttpResponseBadRequest, Http404

from accounts.access_context import get_request_access_context
from accounts.scoping import access_scope, scope_queryset, scoped as shared_scoped, SCOPE_PATHS

_navigation = ContextVar("dg_navigation", default=None)


def current_navigation():
    return _navigation.get()


def staff_branch_filter(branch_ids):
    from portal.models import DirectorTeacherAssignment

    assignments = scoped(DirectorTeacherAssignment).filter(branch_id__in=branch_ids)
    navigation = current_navigation()
    return Q(branch_id__in=branch_ids) | Q(branch__isnull=True) | Q(user_id__in=assignments.values("teacher_id"))


def dg_navigation_scope(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        authorization = get_request_access_context(request)
        if authorization.position in {"secretary", "branch_manager", "annex_manager"}:
            raise Http404("Espace de direction indisponible.")
        if authorization.position not in {"executive_director", "deputy_executive_director", "super_admin"}:
            raise PermissionDenied("Accès réservé à la Direction générale.")
        if not authorization.is_valid or authorization.scope != "GLOBAL":
            raise PermissionDenied("Le pilotage universitaire exige une affectation exécutive globale valide.")
        from .context import resolve_dg_context

        try:
            navigation = resolve_dg_context(request, accept_legacy_branch_param=view.__name__ in {"dg_portal", "dg_section", "dg_export"})
        except ValidationError as exc:
            return HttpResponseBadRequest(" ".join(exc.messages))
        reading = replace(authorization, school=navigation.selected_school, branch=navigation.selected_branch, scope=navigation.mode.upper())
        token = _navigation.set(navigation)
        try:
            with access_scope(reading):
                if view.__name__ == "dg_export" and request.GET.get("kind") in {"school_summary", "school_bulletins"}:
                    from .school_reports import export_school_summary
                    if request.GET.get("kind") == "school_bulletins":
                        from .school_reports import export_school_bulletins
                        return export_school_bulletins(request, navigation)
                    return export_school_summary(request, navigation)
                return view(request, *args, **kwargs)
        finally:
            _navigation.reset(token)
    return wrapped


def scoped(model, *, user=None, context=None):
    """Adapt shared scope for DG history and explicitly attributable records."""
    navigation = current_navigation()
    if navigation is None:
        return shared_scoped(model, user=user, context=context)
    label = model._meta.label_lower
    queryset = model.objects.all()
    school = navigation.selected_school
    year = navigation.academic_year
    if label == "portal.directorteacherassignment":
        # A teaching assignment can target Class, Semester, UE or EC directly.
        paths = ("academic_class", "semester__academic_class", "ue__semester__academic_class", "ec__ue__semester__academic_class")
        queryset = queryset.annotate(
            _dg_school=Coalesce(*(f"{path}__programme__school_id" for path in paths)),
            _dg_year=Coalesce(*(f"{path}__academic_year_id" for path in paths)),
        ).filter(branch_id__in=navigation.scoped_branch_ids)
        if school:
            queryset = queryset.filter(_dg_school=school.pk)
        if year:
            queryset = queryset.filter(_dg_year=year.pk)
        return queryset
    if label == "students.student":
        from academics.models import AcademicEnrollment

        enrollments = scoped(AcademicEnrollment).filter(branch_id__in=navigation.scoped_branch_ids)
        if year:
            enrollments = enrollments.filter(academic_year=year)
        return queryset.filter(user_id__in=enrollments.values("student_id"))
    if label == "accounts.profile":
        from portal.models import DirectorTeacherAssignment

        assignments = scoped(DirectorTeacherAssignment).filter(branch_id__in=navigation.scoped_branch_ids)
        membership = Q(branch_id__in=navigation.scoped_branch_ids) | Q(branch__isnull=True)
        if school:
            membership = Q(user__institutional_profile__school=school)
            if navigation.selected_branch:
                membership &= Q(user__institutional_profile__branch=navigation.selected_branch) | Q(user__institutional_profile__branch__isnull=True)
        return queryset.filter(membership | Q(user_id__in=assignments.values("teacher_id"))).distinct()
    if label in SCOPE_PATHS:
        return scope_queryset(queryset, user=user, context=context)
    paths = {
        "academics.academicdiplomaaward": "programme__school_id",
        "students.teacherattendance": "schedule_event__academic_class__programme__school_id",
        "students.attendancerollsheet": "academic_class__programme__school_id",
    }
    if school and label in paths:
        return queryset.filter(**{paths[label]: school.pk})
    if school and label == "students.attendancealert":
        from students.models import Student

        return queryset.filter(student_id__in=scoped(Student).values("pk"))
    # A selected campus does not make its ledger attributable to one school.
    # Empty means non-attributable, never a fake zero.
    if school and label in {
        "accounts.branchexpense", "accounts.branchmonthlyclosure",
        "accounts.branchcashmovement", "accounts.branchbanktransfer",
        "portal.administrativedocument", "secretary.administrativedocument",
    }:
        if any(field.name == "school" for field in model._meta.fields):
            return queryset.filter(school=school, branch_id__in=navigation.scoped_branch_ids)
        return queryset.none()
    return queryset
