"""Canonical dashboard destination and compatibility URL redirects."""

from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.urls import reverse

from portal.permissions import get_post_login_portal_url


def resolve_user_dashboard(user):
    """Keep login and legacy entry points on the same access-aware policy."""
    return get_post_login_portal_url(user)


def redirect_dashboard_alias(request, url_name):
    """Preserve section filters when an old dashboard URL is bookmarked."""
    url = reverse(url_name)
    query = request.GET.urlencode()
    return HttpResponseRedirect(f"{url}?{query}" if query else url)


@login_required
def legacy_executive_dashboard(request):
    """Never serve the pre-certification executive dashboard by its old URL."""
    url = resolve_user_dashboard(request.user)
    query = request.GET.urlencode()
    return HttpResponseRedirect(f"{url}?{query}" if query else url)
