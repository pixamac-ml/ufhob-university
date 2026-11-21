"""Helpers for the automatic cash-agent profile used by branch managers."""

from django.db import transaction

from accounts.position_registry import ANNEX_MANAGER, normalize_position
from payments.models import PaymentAgent


def _manager_position_and_branch(user):
    """Poste et campus officiels : affectation institutionnelle d'abord."""
    institutional = getattr(user, "institutional_profile", None)
    profile = getattr(user, "profile", None)
    position = getattr(institutional, "position", None) or getattr(profile, "position", None)
    branch = getattr(institutional, "branch", None) or getattr(profile, "branch", None)
    return normalize_position(position), branch


@transaction.atomic
def ensure_cash_agent_for_manager(*, user, branch=None):
    """La gestionnaire est l'agent de caisse de son école (décision D3).

    Crée ou met à jour son profil d'agent sur son campus. L'école est celle de
    son affectation institutionnelle : un agent ne peut donc encaisser que
    pour son école, même sur un campus partagé.
    """
    position, assigned_branch = _manager_position_and_branch(user)
    if position != ANNEX_MANAGER:
        return None
    branch = branch or assigned_branch
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
