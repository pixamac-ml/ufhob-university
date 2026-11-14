from django.core.exceptions import PermissionDenied

from accounts.access import get_user_position
from accounts.access_context import build_access_context


GLOBAL_TEACHER_ASSIGNMENT_POSITIONS = {"super_admin", "executive_director", "deputy_executive_director"}
SCOPED_TEACHER_ASSIGNMENT_POSITIONS = {"director_of_studies"}


def is_global_teacher_assignment_user(user):
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_superuser or get_user_position(user) in GLOBAL_TEACHER_ASSIGNMENT_POSITIONS)


def can_manage_teacher_assignments(user, branch, *, school=None):
    """Check the real institutional scope, never just the UI campus filter.

    A Director of Studies can be assigned to a campus, to a school across its
    campuses, or to a school+campus pair.  A campus alone is not enough to
    decide access when several schools share it, so school-scoped decisions
    fail closed until the pedagogical target supplies its school.
    """
    if not user or not user.is_authenticated or branch is None:
        return False
    if is_global_teacher_assignment_user(user):
        return True
    context = build_access_context(user)
    if get_user_position(user) not in SCOPED_TEACHER_ASSIGNMENT_POSITIONS or not context.is_valid:
        return False
    if context.scope == "BRANCH":
        return bool(context.branch and context.branch.pk == branch.pk)
    if context.scope == "SCHOOL":
        return bool(context.school and school is not None and context.school.pk == school.pk)
    if context.scope == "SCHOOL_BRANCH":
        return bool(
            context.branch and context.branch.pk == branch.pk
            and context.school
            and school is not None
            and context.school.pk == school.pk
        )
    return False


def require_teacher_assignment_access(user, branch, *, school=None):
    if not can_manage_teacher_assignments(user, branch, school=school):
        raise PermissionDenied("Acces refuse a la gestion des affectations de cette annexe.")
    return True
