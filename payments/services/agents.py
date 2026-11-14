"""Helpers for the automatic cash-agent profile used by branch managers."""

from django.db import transaction

from accounts.position_registry import ANNEX_MANAGER, normalize_position
from payments.models import PaymentAgent


@transaction.atomic
def ensure_cash_agent_for_manager(*, user, branch=None):
    """Ensure an annex manager can immediately receive cash payments."""
    profile = getattr(user, "profile", None)
    if profile is None or normalize_position(profile.position) != ANNEX_MANAGER:
        return None
    branch = branch or profile.branch
    if branch is None:
        return None
    agent, _created = PaymentAgent.objects.get_or_create(
        user=user,
        defaults={"branch": branch, "is_active": True},
    )
    updates = []
    if agent.branch_id != branch.pk:
        agent.branch = branch
        updates.append("branch")
    if not agent.is_active:
        agent.is_active = True
        updates.append("is_active")
    if updates:
        agent.save(update_fields=updates)
    return agent
