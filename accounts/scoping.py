"""University scope for shared selectors; role checks remain in permissions.

Views and selectors opt in with ``scoped(Model)``. Branch-only services inherit
the request context; jobs must pass ``user`` or ``context`` explicitly when they
run on behalf of a person. Model managers and historical relations are unchanged.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.core.exceptions import PermissionDenied
from django.db.models import Q


_request_context = ContextVar("ufhob_access_context", default=None)

# Paths follow business records, never a student's current profile.
SCOPE_PATHS = {
    "formations.programme": ("school_id", None),
    "core.school": ("pk", None),
    "core.schoolbranch": ("school_id", "branch_id"),
    "branches.branch": (None, "pk"),
    "admissions.candidature": ("programme__school_id", "branch_id"),
    "admissions.candidaturedocument": ("candidature__programme__school_id", "candidature__branch_id"),
    "inscriptions.inscription": ("candidature__programme__school_id", "candidature__branch_id"),
    "payments.payment": ("inscription__candidature__programme__school_id", "inscription__candidature__branch_id"),
    "payments.cashpaymentsession": ("inscription__candidature__programme__school_id", "inscription__candidature__branch_id"),
    "students.student": ("inscription__candidature__programme__school_id", "inscription__candidature__branch_id"),
    "academics.academicclass": ("programme__school_id", "branch_id"),
    "academics.academicenrollment": ("programme__school_id", "branch_id"),
    "academics.semester": ("academic_class__programme__school_id", "academic_class__branch_id"),
    "academics.ue": ("semester__academic_class__programme__school_id", "semester__academic_class__branch_id"),
    "academics.ec": ("ue__semester__academic_class__programme__school_id", "ue__semester__academic_class__branch_id"),
    "academics.ecgrade": ("enrollment__programme__school_id", "enrollment__branch_id"),
    "academics.academicbulletin": ("enrollment__programme__school_id", "enrollment__branch_id"),
    "academics.resultaccessauthorization": ("enrollment__programme__school_id", "enrollment__branch_id"),
    "academics.officialtranscriptrequest": ("enrollment__programme__school_id", "enrollment__branch_id"),
    "academics.academicdocumentauditlog": ("school_id", "branch_id"),
    "academics.academicdebt": ("enrollment__programme__school_id", "enrollment__branch_id"),
    "academics.academicscheduleevent": ("academic_class__programme__school_id", "branch_id"),
    "academics.academiccalendar": (None, "branch_id"),
    "academics.academiccalendarentry": (None, "calendar__branch_id"),
    "academics.academiccalendaradjustment": (None, "calendar__branch_id"),
    "students.studentyeardecision": ("source_enrollment__programme__school_id", "source_enrollment__branch_id"),
    "academics.evaluationrequirement": ("academic_class__programme__school_id", "academic_class__branch_id"),
    "academics.evaluationcampaign": (None, "branch_id"),
    "academics.evaluationcampaignscope": ("academic_class__programme__school_id", "academic_class__branch_id"),
    "academics.weeklyscheduleslot": ("academic_class__programme__school_id", "branch_id"),
    "academics.lessonlog": ("academic_class__programme__school_id", "branch_id"),
    "students.studentattendance": ("academic_class__programme__school_id", "academic_class__branch_id"),
    "students.studentcase": ("academic_class__programme__school_id", "branch_id"),
    "students.teachercase": ("academic_class__programme__school_id", "branch_id"),
    "portal.directorteacherassignment": ("academic_class__programme__school_id", "branch_id"),
    "accounts.institutionalprofile": ("school_id", "branch_id"),
    "accounts.profile": ("user__institutional_profile__school_id", "branch_id"),
    "auth.user": (None, None),
    "portal.transferrequest": (None, "branch_id"),
    "portal.transferdocument": (None, "transfer_request__branch_id"),
    "academics.academicdiplomaaward": ("programme__school_id", "branch_id"),
    "students.teacherattendance": ("schedule_event__academic_class__programme__school_id", "branch_id"),
    "students.attendancerollsheet": ("academic_class__programme__school_id", "branch_id"),
    "students.attendancealert": (None, "branch_id"),
    "portal.supportticket": (None, "branch_id"),
    "portal.supportauditlog": (None, "branch_id"),
    "portal.accountsupportstate": (None, None),
}


@contextmanager
def access_scope(context):
    token = _request_context.set(context)
    try:
        yield
    finally:
        _request_context.reset(token)


def resolve_context(*, user=None, context=None):
    if context is not None:
        return context
    if user is not None:
        current = _request_context.get()
        if current is not None and getattr(current.user, "pk", None) == getattr(user, "pk", None):
            return current
        from accounts.access_context import build_access_context

        return build_access_context(user)
    return _request_context.get()


def scope_queryset(queryset, *, user=None, context=None):
    context = resolve_context(user=user, context=context)
    if context is None:
        return queryset
    school = getattr(context, "school", None)
    if not context.is_valid or context.context_type != "SYSTEM":
        return queryset.none()
    label = queryset.model._meta.label_lower
    # A new model must not accidentally become visible to a locally scoped
    # member just because it has not yet been added to this explicit map.
    # University-wide users have no school/campus context and keep their
    # existing unrestricted queries through ``scoped`` below.
    if label not in SCOPE_PATHS:
        return queryset if school is None and context.branch is None else queryset.none()
    school_path, branch_path = SCOPE_PATHS[label]
    if school is not None and label == "portal.directorteacherassignment":
        from django.db.models.functions import Coalesce

        paths = ("academic_class", "semester__academic_class", "ue__semester__academic_class", "ec__ue__semester__academic_class")
        queryset = queryset.annotate(_scope_school=Coalesce(*(f"{path}__programme__school_id" for path in paths))).filter(_scope_school=school.pk)
        return queryset.filter(branch=context.branch) if context.branch else queryset
    if school is not None and label == "students.attendancealert":
        from students.models import Student

        queryset = queryset.filter(student__in=scoped(Student, context=context))
    if (school is not None or context.branch is not None) and label in {"portal.supportticket", "portal.supportauditlog", "portal.accountsupportstate"}:
        from django.contrib.auth import get_user_model
        from students.models import Student
        from inscriptions.models import Inscription

        users = scoped(get_user_model(), context=context)
        if label == "portal.supportticket":
            queryset = queryset.filter(
                Q(student__in=scoped(Student, context=context))
                | Q(student__isnull=True, inscription__in=scoped(Inscription, context=context))
                | Q(student__isnull=True, inscription__isnull=True, requester_user__in=users)
                | Q(student__isnull=True, inscription__isnull=True, requester_user__isnull=True, created_by__in=users)
            )
        elif label == "portal.supportauditlog":
            queryset = queryset.filter(Q(target_user__in=users) | Q(target_user__isnull=True, actor__in=users))
        else:
            queryset = queryset.filter(user__in=users)
    if school is not None and queryset.model._meta.label_lower == "academics.evaluationcampaign":
        from academics.models import EvaluationCampaignScope

        foreign_scopes = EvaluationCampaignScope.objects.exclude(academic_class__programme__school_id=school.pk)
        queryset = queryset.filter(
            Q(scopes__academic_class__programme__school_id=school.pk)
            | Q(calendar_entry__school_id=school.pk)
        ).exclude(pk__in=foreign_scopes.values("campaign_id")).distinct()
    if school is not None and queryset.model._meta.label_lower == "academics.academiccalendaradjustment":
        from academics.models import AcademicCalendarEntry

        queryset = queryset.filter(calendar_entry__in=scoped(AcademicCalendarEntry, context=context))
    if label == "auth.user":
        from accounts.models import Profile
        from students.models import Student

        return queryset.filter(
            Q(pk__in=scoped(Profile, context=context).values("user_id"))
            | Q(pk__in=scoped(Student, context=context).values("user_id"))
        )
    if school is not None and queryset.model._meta.label_lower == "portal.transferrequest":
        source = Q(source_class__programme__school_id=school.pk)
        incoming = Q(source_class__isnull=True, target_class__programme__school_id=school.pk)
        queryset = queryset.filter(source | incoming)
    if school is not None and queryset.model._meta.label_lower == "portal.transferdocument":
        from portal.models import TransferRequest

        queryset = queryset.filter(transfer_request__in=scoped(TransferRequest, context=context))
    if school is not None and queryset.model._meta.label_lower == "accounts.profile":
        assignments = scoped_queryset_assignments(context)
        staff = Q(user__institutional_profile__school_id=school.pk)
        if context.branch:
            staff &= Q(user__institutional_profile__branch_id=context.branch.pk)
        return queryset.filter(staff | Q(user_id__in=assignments.values("teacher_id")))
    if (school is not None or context.branch is not None) and queryset.model._meta.label_lower == "students.student":
        current = Q(current_academic_enrollment__isnull=False)
        legacy = Q(current_academic_enrollment__isnull=True)
        if school:
            current &= Q(current_academic_enrollment__programme__school_id=school.pk)
            legacy &= Q(inscription__candidature__programme__school_id=school.pk)
        if context.branch:
            current &= Q(current_academic_enrollment__branch_id=context.branch.pk)
            legacy &= Q(inscription__candidature__branch_id=context.branch.pk)
        return queryset.filter(current | legacy)
    filters = {}
    if school is not None and queryset.model._meta.label_lower in {"academics.academiccalendar", "academics.academiccalendarentry"}:
        campus = "branch" if queryset.model._meta.label_lower == "academics.academiccalendar" else "calendar__branch"
        filters[f"{campus}__school_branches__school_id"] = school.pk
        filters[f"{campus}__school_branches__is_active"] = True
    if school is not None and queryset.model._meta.label_lower == "academics.academiccalendarentry":
        queryset = queryset.filter(
            Q(target_scope="branch") | Q(school_id=school.pk)
            | Q(programme__school_id=school.pk)
            | Q(academic_class__programme__school_id=school.pk)
            | Q(semester__academic_class__programme__school_id=school.pk)
        ).exclude(target_semesters__academic_class__programme__school_id__in=
                  scoped_other_school_ids(school.pk))
    if school is not None and school_path:
        filters[school_path] = school.pk
    elif school is not None and queryset.model._meta.label_lower == "branches.branch":
        filters["school_branches__school_id"] = school.pk
        filters["school_branches__is_active"] = True
    branch = getattr(context, "branch", None)
    if branch is not None and branch_path:
        filters[branch_path] = branch.pk
    if branch is not None and queryset.model._meta.label_lower == "core.school":
        filters["school_branches__branch_id"] = branch.pk
        filters["school_branches__is_active"] = True
    if queryset.model._meta.label_lower == "formations.programme" and branch:
        queryset = queryset.available_on(branch)
    return queryset.filter(**filters)


def scoped(model, *, user=None, context=None):
    context = resolve_context(user=user, context=context)
    if context is not None and context.context_type == "SYSTEM" and not context.is_valid:
        return model.objects.none()
    # Preserve the established branch / assignment / legacy role contracts when
    # no university restriction was assigned. This adds School to those rules.
    if context is not None and context.scope in {"SCHOOL", "SCHOOL_BRANCH"} and not context.is_valid:
        return model.objects.none()
    if context is None or (
        not getattr(context, "school", None)
        and not getattr(context, "branch", None)
    ):
        return model.objects.all()
    return scope_queryset(model.objects.all(), context=context)


def require_object_scope(obj, *, user=None, context=None):
    if not scoped(type(obj), user=user, context=context).filter(pk=obj.pk).exists():
        raise PermissionDenied("Cet objet est hors du contexte école/campus autorisé.")


def scoped_get_object_or_404(queryset, *, user=None, context=None, **lookup):
    """Charge un objet par identifiant dans le périmètre école/campus.

    Un objet d'une autre école répond 404, comme un objet inexistant, pour ne
    pas révéler son existence. Le DG et les comptes université gardent l'accès
    complet ; ``queryset`` peut être un modèle ou un queryset déjà préparé.
    """
    from django.shortcuts import get_object_or_404

    if isinstance(queryset, type):
        queryset = queryset.objects.all()
    allowed = scoped(queryset.model, user=user, context=context)
    if allowed.query.where or allowed.query.is_empty():
        queryset = queryset.filter(pk__in=allowed.values("pk"))
    return get_object_or_404(queryset, **lookup)


def object_in_scope(obj, *, user):
    return scoped(type(obj), user=user).filter(pk=obj.pk).exists()


def scoped_queryset_assignments(context):
    from portal.models import DirectorTeacherAssignment

    return scope_queryset(DirectorTeacherAssignment.objects.all(), context=context)


def scoped_other_school_ids(school_id):
    from core.models import School

    return School.objects.exclude(pk=school_id).values("pk")


def branch_filters(branch, *, path="branch"):
    """Allow existing campus selectors to aggregate a school across campuses."""
    context = resolve_context()
    if branch is None and context is not None and context.scope == "SCHOOL":
        return {}
    return {path: branch}


def school_wide_scope():
    context = resolve_context()
    return context is not None and context.scope == "SCHOOL" and context.is_valid


def student_branch_filter(branch):
    """Current student lists follow the current enrollment, with legacy fallback."""
    return Q(current_academic_enrollment__branch=branch) | Q(
        current_academic_enrollment__isnull=True, inscription__candidature__branch=branch,
    )


def permits_university_operations(user):
    """An explicit local assignment cannot administer university-wide resources.

    Existing legacy role checks remain responsible for authentication/permissions.
    This helper adds the organizational restriction only.
    """
    institutional = getattr(user, "institutional_profile", None)
    if institutional is not None and (institutional.school_id or institutional.access_scope):
        context = resolve_context(user=user)
        return context.is_valid and context.scope == "GLOBAL"
    return True
