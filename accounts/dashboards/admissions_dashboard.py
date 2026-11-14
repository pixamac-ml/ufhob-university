"""Compatibility entrypoint for Admissions inside the manager workspace."""

from django.contrib.auth.decorators import login_required

from accounts.services.redirects import redirect_dashboard_alias


@login_required
def admissions_dashboard(request):
    """Open Admissions in the certified DE shell, never in a parallel dashboard."""

    if request.resolver_match and request.resolver_match.namespace == "accounts":
        return redirect_dashboard_alias(request, "accounts_portal:portal_admissions")

    from accounts.dashboards.manager_dashboard import manager_dashboard

    return manager_dashboard(request, default_section="candidatures")
