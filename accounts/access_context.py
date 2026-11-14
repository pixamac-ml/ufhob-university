"""Contexte d'accès institutionnel calculé une seule fois par requête."""

from dataclasses import dataclass

from accounts.access import get_user_annexe
from accounts.position_registry import get_position_definition, normalize_position


def _student_academic_context(user):
    """Resolve a student's scope from the current academic path."""
    from academics.models import AcademicEnrollment

    enrollment = (
        AcademicEnrollment.objects.select_related("programme__school", "branch")
        .filter(student=user, is_active=True, is_archived=False)
        .order_by("-created_at", "-id")
        .first()
    )
    if enrollment is None:
        enrollment = (
            AcademicEnrollment.objects.select_related("programme__school", "branch")
            .filter(student=user)
            .order_by("-created_at", "-id")
            .first()
        )
    if enrollment is not None:
        return {
            "school": getattr(enrollment.programme, "school", None),
            "branch": enrollment.branch,
            "enrollment": enrollment,
        }

    student = getattr(user, "student_profile", None)
    inscription = getattr(student, "inscription", None)
    candidature = getattr(inscription, "candidature", None)
    if candidature is not None:
        return {
            "school": getattr(candidature.programme, "school", None),
            "branch": candidature.branch,
            "enrollment": None,
        }
    return {"school": None, "branch": None, "enrollment": None}


@dataclass(frozen=True)
class AccessContext:
    user: object
    context_type: str
    position: str | None
    category: str | None
    scope: str | None
    branch: object | None
    account_state: str
    capabilities: frozenset[str]
    is_valid: bool
    reason_code: str
    school: object | None = None


def build_access_context(user):
    if not getattr(user, "is_authenticated", False):
        return AccessContext(user, "ANONYMOUS", None, None, None, None, "anonymous", frozenset(), False, "anonymous")

    profile = getattr(user, "profile", None)
    institutional_profile = getattr(user, "institutional_profile", None)
    # Policy V2 ne déduit jamais une position depuis un groupe, ``role``,
    # ``is_staff`` ou un objet métier historique. Une position SYSTEM doit être
    # une affectation institutionnelle explicite.
    raw_position = getattr(institutional_profile, "position", None)
    if institutional_profile is None:
        raw_position = getattr(profile, "position", None)
    position = normalize_position(raw_position) or None
    # Student accounts created from an inscription often have no staff-style
    # institutional position. Their Student record is the role source.
    if position is None and getattr(profile, "role", None) == "student" and hasattr(user, "student_profile"):
        position = "student"
    definition = get_position_definition(position)
    context_type = "SYSTEM" if definition else "PUBLIC"
    student_context = _student_academic_context(user) if position == "student" else None
    if student_context is not None:
        branch = student_context["branch"]
    elif definition and institutional_profile is not None:
        branch = institutional_profile.branch
    else:
        branch = get_user_annexe(user) if definition else None

    support_state = getattr(user, "support_state", None)
    if not user.is_active:
        account_state = "inactive"
    elif support_state and support_state.is_suspended:
        account_state = "suspended"
    elif support_state and support_state.is_blocked:
        account_state = "blocked"
    elif support_state and support_state.must_change_password:
        account_state = "password_change_required"
    else:
        account_state = "active"

    school = (
        student_context["school"]
        if student_context is not None
        else getattr(institutional_profile, "school", None)
    )
    scope = getattr(institutional_profile, "scope", None) or (definition.scope if definition else None)
    if student_context is not None:
        scope = "SCHOOL_BRANCH"
    elif scope in {"GLOBAL", "SCHOOL"}:
        branch = None
    if position in {"teacher", "moniteur"}:
        # A primary HR School must not erase cross-school teaching assignments.
        # Teaching endpoints still enforce the user's actual classes and ECs.
        school, scope = None, "BRANCH"
        branch = getattr(institutional_profile, "branch", None) or branch
        if branch is None:
            from portal.services.teaching_scope import teaching_branches

            branch = teaching_branches(user).first()
    reason_code = "allowed"
    is_valid = account_state in {"active", "password_change_required"}
    if definition and scope in {"BRANCH", "SCHOOL_BRANCH"} and branch is None:
        is_valid = False
        reason_code = "branch_required"
    elif not definition:
        reason_code = "public_context"
    elif not is_valid:
        reason_code = f"account_{account_state}"

    if scope in {"SCHOOL", "SCHOOL_BRANCH"} and school is None:
        is_valid, reason_code = False, "school_required"
    if school is not None:
        from core.models import SchoolBranch

        if not school.is_active:
            is_valid, reason_code = False, "school_inactive"
        elif branch is not None and not SchoolBranch.objects.filter(
            school=school, branch=branch, is_active=True,
        ).exists():
            is_valid, reason_code = False, "school_branch_invalid"

    return AccessContext(
        user=user,
        context_type=context_type,
        position=position,
        category=definition.category if definition else None,
        scope=scope,
        branch=branch,
        account_state=account_state,
        capabilities=frozenset(user.get_all_permissions()),
        is_valid=is_valid,
        reason_code=reason_code,
        school=school,
    )


def get_request_access_context(request):
    if not hasattr(request, "_esfe_access_context"):
        from accounts.operational_context import resolve_operational_context

        request._esfe_access_context = resolve_operational_context(request, build_access_context(request.user))
    return request._esfe_access_context
