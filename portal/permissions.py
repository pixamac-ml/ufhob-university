from __future__ import annotations

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import reverse

from accounts.access import (
    get_user_annexe,
    get_user_groups,
    get_user_position,
    get_user_profile_role,
    get_user_role as get_canonical_user_role,
)
from accounts.position_registry import get_position_definition, normalize_position


def user_requires_branch_assignment(user):
    """Return whether a SYSTEM user has a branch-scoped role but no branch."""

    from accounts.position_registry import TEACHING_POSITIONS
    # Students derive their campus and school from their academic enrollment;
    # an InstitutionalProfile assignment is a staff concern only.
    if get_user_role(user) == "student" or get_user_position(user) == "student":
        return False
    if get_user_position(user) in TEACHING_POSITIONS:
        from portal.services.teaching_scope import teaching_branches

        return not teaching_branches(user).exists()
    institutional = getattr(user, "institutional_profile", None)
    if institutional is not None and institutional.scope in {"SCHOOL", "GLOBAL"}:
        return False
    definition = get_position_definition(get_user_position(user))
    return bool(definition and definition.branch_required and get_user_annexe(user) is None)


def get_user_role(user):
    if not getattr(user, "is_authenticated", False):
        return None

    canonical_role = get_canonical_user_role(user)
    if canonical_role == "student":
        return "student"
    if canonical_role in {"staff_admin", "directeur_etudes", "directeur_general", "teacher"}:
        return "staff"
    if canonical_role == "super_admin":
        return "admin"

    profile_role = get_user_profile_role(user)
    if profile_role == "student":
        return "student"
    if profile_role in {"teacher", "admissions", "finance", "executive", "secretary", "superadmin"}:
        return "staff" if profile_role != "superadmin" else "admin"

    groups = set(get_user_groups(user))
    if groups.intersection({"students", "student"}):
        return "student"
    if groups.intersection(
        {
            "staff",
            "teacher",
            "teachers",
            "admissions",
            "admissions_managers",
            "finance",
            "finance_agents",
            "gestionnaire",
            "manager",
            "executive",
            "executive_director",
            "deputy_executive_director",
            "secretary",
            "secretaries",
            "marketing",
            "marketing_manager",
        }
    ):
        return "staff"

    if getattr(user, "is_superuser", False):
        return "admin"

    return None


def role_required(expected_role):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            role = get_user_role(request.user)
            if role != expected_role:
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def get_post_login_portal_url(user):
    if not getattr(user, "is_authenticated", False):
        return reverse("accounts_portal:portal_home")

    support_state = getattr(user, "support_state", None)
    if support_state and support_state.must_change_password:
        return reverse("accounts:password_change")

    # This guard applies to both routing policies. It prevents legacy routing
    # from opening an unscoped dashboard while an affectation is pending.
    if user_requires_branch_assignment(user):
        return reverse("accounts_portal:access_regularization")

    from django.conf import settings
    if settings.AUTH_PORTAL_ROUTING_V2_ENABLED:
        from accounts.access_context import build_access_context

        context = build_access_context(user)
        if context.context_type == "PUBLIC":
            return reverse("community:topic_list")
        if not context.is_valid:
            return reverse("accounts_portal:access_regularization")
        definition = get_position_definition(context.position)
        if definition:
            return reverse(definition.dashboard_url_name)
        return reverse("accounts_portal:access_regularization")

    position = get_user_position(user)
    if getattr(user, "is_superuser", False) or position == "super_admin":
        return reverse("superadmin:dashboard")
    if position in {"executive_director", "deputy_executive_director"}:
        return reverse("accounts_portal:portal_dg")
    if position == "marketing_manager":
        return reverse("marketing:dashboard")
    if position in {"annex_manager", "branch_manager"} or {"gestionnaire", "manager"}.intersection(set(get_user_groups(user))):
        return reverse("accounts_portal:portal_annex_manager")

    definition = get_position_definition(position)
    if definition:
        return reverse(definition.dashboard_url_name)

    return reverse("accounts_portal:portal_dashboard")


def portal_redirect(request):
    return redirect(get_post_login_portal_url(request.user))
