from django.core.exceptions import PermissionDenied

from accounts.access import get_user_annexe, get_user_position


GLOBAL_STRUCTURE_POSITIONS = {"super_admin", "executive_director", "deputy_executive_director"}
SCOPED_STRUCTURE_POSITIONS = {"director_of_studies"}


def is_global_structure_user(user):
    if not user or not user.is_authenticated:
        return False
    from accounts.scoping import resolve_context

    if getattr(resolve_context(user=user), "school", None):
        return False
    return bool(user.is_superuser or get_user_position(user) in GLOBAL_STRUCTURE_POSITIONS)


def can_manage_programme_structure(user, branch):
    if not user or not user.is_authenticated or branch is None:
        return False
    from accounts.scoping import resolve_context, object_in_scope

    context = resolve_context(user=user)
    if getattr(context, "school", None):
        return bool(context.is_valid and context.position in GLOBAL_STRUCTURE_POSITIONS | SCOPED_STRUCTURE_POSITIONS and object_in_scope(branch, user=user))
    if is_global_structure_user(user):
        return True
    if get_user_position(user) not in SCOPED_STRUCTURE_POSITIONS:
        return False
    user_branch = get_user_annexe(user)
    return bool(user_branch and user_branch.pk == branch.pk)


def require_programme_structure_access(user, branch):
    if not can_manage_programme_structure(user, branch):
        raise PermissionDenied("Acces refuse a la structure pedagogique de cette annexe.")
    return True
