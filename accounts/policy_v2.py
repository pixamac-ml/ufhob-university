"""Policy V2 deny-by-default pour les ressources institutionnelles."""

from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason_code: str


def decide(context, *, capability=None, resource_branch=None, resource_school=None, allowed_positions=None):
    if context.context_type != "SYSTEM":
        return PolicyDecision(False, "system_context_required")
    if not context.is_valid:
        return PolicyDecision(False, context.reason_code)
    if allowed_positions and context.position not in set(allowed_positions):
        return PolicyDecision(False, "position_denied")
    if resource_branch is not None and context.scope in {"BRANCH", "SCHOOL_BRANCH"}:
        if context.branch is None or context.branch.pk != resource_branch.pk:
            return PolicyDecision(False, "cross_branch_denied")
    school = getattr(context, "school", None)
    if resource_school is not None and school is not None and school.pk != resource_school.pk:
        return PolicyDecision(False, "cross_school_denied")
    if capability and capability not in context.capabilities:
        return PolicyDecision(False, "capability_missing")
    return PolicyDecision(True, "allowed")
