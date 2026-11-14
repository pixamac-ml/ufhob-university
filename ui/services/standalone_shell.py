"""Certified shell for standalone authenticated tools such as messages."""

from django.urls import reverse


def build_standalone_shell(request, *, key, title, access=None):
    from accounts.access_context import build_access_context
    from accounts.services.redirects import resolve_user_dashboard
    from notification_center.selectors import get_user_unread_count
    from portal.services.certified_dashboard_shell import build_certified_dashboard_shell

    access = access or build_access_context(request.user)
    dashboard_url = resolve_user_dashboard(request.user)
    context_label = " · ".join(str(item) for item in (access.school, access.branch) if item)
    return {
        **build_certified_dashboard_shell(
            role=access.position or "user", key=key, page_title=f"{title} | UFHOB",
            title=title, subtitle="UFHOB", context_label=context_label,
            user_name=request.user.get_full_name() or request.user.username,
            navigation=[{"label": "Application", "items": [
                {"label": "Dashboard", "url": dashboard_url, "icon": "layout-dashboard"},
                {"label": "Messagerie", "url": reverse("communications:inbox"), "icon": "messages-square", "active": key == "messages"},
                {"label": "Notifications", "url": reverse("notification_center:notifications"), "icon": "bell", "active": key == "notifications"},
            ]}], active_section=key,
            workspace_template="ui_core/partials/empty.html", topbar_template="ui_core/partials/empty.html",
            script_path="", notifications_url=reverse("notification_center:notifications"),
            show_notifications_button=True,
        ),
        "notification_count": get_user_unread_count(request.user),
    }
