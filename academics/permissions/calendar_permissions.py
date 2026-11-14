from django.core.exceptions import PermissionDenied

from accounts.access import get_user_annexe, get_user_position


GLOBAL_CALENDAR_POSITIONS = {
    "super_admin",
    "executive_director",
    "deputy_executive_director",
}
SCOPED_CALENDAR_POSITIONS = {"director_of_studies"}


def is_global_calendar_user(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    from accounts.scoping import resolve_context

    if getattr(resolve_context(user=user), "school", None):
        return False
    return bool(user.is_superuser or get_user_position(user) in GLOBAL_CALENDAR_POSITIONS)


def can_access_calendar_branch(user, branch) -> bool:
    if not user or not user.is_authenticated or branch is None:
        return False
    from accounts.scoping import resolve_context, object_in_scope

    context = resolve_context(user=user)
    if getattr(context, "school", None):
        return bool(context.is_valid and context.position in GLOBAL_CALENDAR_POSITIONS | SCOPED_CALENDAR_POSITIONS and object_in_scope(branch, user=user))
    if is_global_calendar_user(user):
        return True
    if get_user_position(user) not in SCOPED_CALENDAR_POSITIONS:
        return False
    user_branch = get_user_annexe(user)
    return bool(user_branch and user_branch.pk == branch.pk)


def can_view_calendar(user, calendar) -> bool:
    return bool(calendar and can_access_calendar_branch(user, calendar.branch))


def can_manage_calendar(user, calendar) -> bool:
    return can_view_calendar(user, calendar)


def require_calendar_branch_access(user, branch):
    if not can_access_calendar_branch(user, branch):
        raise PermissionDenied("Acces refuse a ce calendrier academique.")
    return branch


def require_calendar_access(user, calendar):
    if not can_manage_calendar(user, calendar):
        raise PermissionDenied("Acces refuse a ce calendrier academique.")
    return calendar


def calendar_queryset_for_user(user, queryset=None):
    from academics.models import AcademicCalendar
    from accounts.scoping import resolve_context

    queryset = queryset if queryset is not None else AcademicCalendar.objects.all()
    if is_global_calendar_user(user):
        return queryset
    context = resolve_context(user=user)
    # A SCHOOL profile is promoted to SCHOOL_BRANCH by the request context
    # after it selects one of its authorised campuses.  Do not fall back to
    # the static profile branch here: it is intentionally empty for a
    # school-wide profile and would make a calendar it is allowed to manage
    # disappear from the API listing.
    if getattr(context, "school", None):
        if not context.is_valid or context.position not in SCOPED_CALENDAR_POSITIONS:
            return queryset.none()
        queryset = queryset.filter(
            branch__school_branches__school_id=context.school.pk,
            branch__school_branches__is_active=True,
        )
        if context.branch is not None:
            queryset = queryset.filter(branch=context.branch)
        return queryset.distinct()
    if get_user_position(user) in SCOPED_CALENDAR_POSITIONS:
        branch = get_user_annexe(user)
        return queryset.filter(branch=branch) if branch else queryset.none()
    return queryset.none()
