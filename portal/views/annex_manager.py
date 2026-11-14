"""Entrée Portal officielle de la gestionnaire d'annexe."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from accounts.services.redirects import redirect_dashboard_alias

from accounts.dashboards.manager_dashboard import (
    manager_dashboard,
    manager_subcontent,
    manager_workspace,
)


def annex_manager_portal(request):
    return manager_dashboard(request)


def annex_manager_workspace(request):
    """Return only the Gestionnaire workspace for certified HTMX navigation."""

    return manager_workspace(request)


def annex_manager_subcontent(request):
    """Return only the active Gestionnaire subview for tab navigation."""

    return manager_subcontent(request)


@login_required
def legacy_manager_entry(request):
    return redirect_dashboard_alias(request, "accounts_portal:portal_annex_manager")


@login_required
def access_regularization(request):
    """État contrôlé : aucun dashboard approximatif n'est autorisé."""
    from accounts.access_context import build_access_context

    context = build_access_context(request.user)
    missing = []
    if context.reason_code in {"branch_required", "school_branch_invalid"}:
        missing.append("Campus non affecté ou non compatible")
    if context.reason_code in {"school_required", "school_branch_invalid"}:
        missing.append("École non affectée ou non compatible")
    return render(request, "portal/access_regularization.html", {
        "missing_assignments": missing,
        "position": context.position,
    }, status=403)
