"""Droits du cycle académique par campus.

Le poste est lu par la couche centrale (``accounts.access``) et le périmètre
école/campus par ``accounts.scoping`` : un directeur d'école ne voit que les
campus où son école est implantée, un compte sans poste interne ne voit rien.
"""

from accounts.position_registry import normalize_position

GLOBAL_CYCLE_POSITIONS = {"super_admin", "executive_director", "deputy_executive_director"}
CLOSURE_POSITIONS = GLOBAL_CYCLE_POSITIONS | {"director_of_studies"}
CORRECTION_POSITIONS = GLOBAL_CYCLE_POSITIONS | {"it_support", "director_of_studies"}
MANAGER_POSITIONS = GLOBAL_CYCLE_POSITIONS | {"annex_manager", "branch_manager", "finance_manager", "payment_agent"}


def get_profile(user):
    return getattr(user, "profile", None)


def _is_authenticated(user):
    return bool(user and getattr(user, "is_authenticated", False))


def user_position(user):
    if not _is_authenticated(user):
        return None
    from accounts.access import get_user_position

    return normalize_position(get_user_position(user)) or None


def is_global_cycle_user(user):
    if not _is_authenticated(user):
        return False
    from accounts.scoping import permits_university_operations

    if not permits_university_operations(user):
        return False
    if user.is_superuser:
        return True
    return user_position(user) in GLOBAL_CYCLE_POSITIONS


def user_branch(user):
    if not _is_authenticated(user):
        return None
    from accounts.access_context import build_access_context

    return build_access_context(user).branch


def has_branch_scope(user, branch):
    """Vrai si le campus est dans le périmètre école/campus de l'utilisateur."""
    if not _is_authenticated(user) or branch is None:
        return False
    if is_global_cycle_user(user):
        return True
    from accounts.access_context import build_access_context
    from accounts.scoping import scoped
    from branches.models import Branch

    context = build_access_context(user)
    if not context.is_valid or context.context_type != "SYSTEM":
        return False
    if context.school is None and context.branch is None:
        # Un compte local sans école ni campus n'a aucun périmètre.
        return False
    return scoped(Branch, context=context).filter(pk=branch.pk).exists()


def has_cycle_position(user, positions):
    if not _is_authenticated(user):
        return False
    if is_global_cycle_user(user):
        return True
    return user_position(user) in positions


def can_view_branch_cycle(user, branch):
    return has_cycle_position(user, CLOSURE_POSITIONS) and has_branch_scope(user, branch)


def can_close_branch_cycle(user, branch_cycle):
    if not _is_authenticated(user) or branch_cycle is None:
        return False
    if is_global_cycle_user(user):
        return True
    return user_position(user) in CLOSURE_POSITIONS and has_branch_scope(user, branch_cycle.branch)


def can_change_branch_year(user):
    """Ouvrir les réinscriptions / activer une année touche toutes les écoles
    d'un campus : réservé à la direction générale et au super-admin."""
    return is_global_cycle_user(user)


def can_handle_correction(user, correction):
    if not _is_authenticated(user) or correction is None:
        return False
    if is_global_cycle_user(user):
        return True
    return user_position(user) in CORRECTION_POSITIONS and has_branch_scope(user, correction.branch)


def can_manage_reenrollment(user, branch):
    if not _is_authenticated(user):
        return False
    if is_global_cycle_user(user):
        return True
    return user_position(user) in MANAGER_POSITIONS and has_branch_scope(user, branch)
