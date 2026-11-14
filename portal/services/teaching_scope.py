"""Teaching context follows actual assignments, including cross-campus work."""

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.functions import Coalesce

from academics.models import AcademicScheduleEvent, WeeklyScheduleSlot
from branches.models import Branch
from portal.models import DirectorTeacherAssignment


def teaching_assignments(teacher):
    paths = ("academic_class", "semester__academic_class", "ue__semester__academic_class", "ec__ue__semester__academic_class")
    return DirectorTeacherAssignment.objects.filter(teacher=teacher, is_active=True).annotate(
        teaching_class_id=Coalesce(*(f"{path}__pk" for path in paths)),
    )


def teaching_branches(teacher):
    profile = getattr(teacher, "institutional_profile", None) or getattr(teacher, "profile", None)
    primary_id = getattr(profile, "branch_id", None)
    events = AcademicScheduleEvent.objects.filter(teacher=teacher, is_active=True).exclude(status__in={"draft", "cancelled"})
    slots = WeeklyScheduleSlot.objects.filter(teacher=teacher, is_active=True)
    return Branch.objects.filter(is_active=True).filter(
        Q(pk=primary_id)
        | Q(pk__in=events.values("branch_id"))
        | Q(pk__in=slots.values("branch_id"))
        | Q(pk__in=teaching_assignments(teacher).values("branch_id"))
    ).order_by("name")


def resolve_teaching_branch(request):
    if hasattr(request, "_teaching_branch"):
        return request._teaching_branch
    choices = list(teaching_branches(request.user))
    raw = request.GET.get("teaching_branch_id") if "teaching_branch_id" in request.GET else request.POST.get("teaching_branch_id")
    selected_id = raw if raw is not None else request.session.get("teaching_dashboard_branch_id")
    selected = next((branch for branch in choices if str(branch.pk) == str(selected_id)), None)
    if selected_id and selected is None:
        raise PermissionDenied("Ce campus ne fait pas partie de vos affectations pédagogiques actives.")
    profile = getattr(request.user, "institutional_profile", None) or getattr(request.user, "profile", None)
    if selected is None:
        selected = next((branch for branch in choices if branch.pk == getattr(profile, "branch_id", None)), None) or next(iter(choices), None)
    request._teaching_branch = selected
    request.teaching_branches = choices
    if selected:
        request.session["teaching_dashboard_branch_id"] = selected.pk
    return selected
