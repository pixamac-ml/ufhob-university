from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from urllib.parse import urlencode

from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from notification_center.selectors import (
    get_notification_center_queryset,
    get_notification_center_stats,
    get_notification_filter_options,
    get_user_in_app_messages,
    get_user_unread_count,
)
from notification_center.presentation import NotificationTargetResolver


def _dashboard_url(request):
    context = getattr(request, "access_context", None)
    if not context or context.context_type != "SYSTEM":
        return ""
    from accounts.position_registry import get_position_definition

    definition = get_position_definition(context.position)
    if definition:
        try:
            return reverse(definition.dashboard_url_name)
        except NoReverseMatch:
            pass
    return reverse("accounts_portal:portal_dashboard")


def _role_notification_destination(request, *, notification_id=None):
    """Send the legacy centre URL to the current role's authenticated shell."""
    from accounts.position_registry import get_position_definition, normalize_position

    access = getattr(request, "access_context", None)
    position = normalize_position(getattr(access, "position", ""))
    definition = get_position_definition(position)
    if not definition:
        return _dashboard_url(request) or reverse("accounts_portal:portal_dashboard")

    route_name = definition.dashboard_url_name
    query = {}
    if position == "student":
        query["section"] = "messages"
    elif position in {"teacher", "moniteur"}:
        query["section"] = "notifications"
    elif position == "director_of_studies":
        query["section"] = "notifications"
    elif position == "secretary":
        query["section"] = "notifications"
    elif position in {"executive_director", "deputy_executive_director"}:
        query["section"] = "messaging"
    elif position == "it_support":
        route_name = "accounts_portal:it_notifications_workspace"
    elif position == "academic_supervisor":
        query["section"] = "home"

    try:
        destination = reverse(route_name)
    except NoReverseMatch:
        destination = _dashboard_url(request) or reverse("accounts_portal:portal_dashboard")
    if notification_id and position in {"secretary", "it_support"}:
        query["notification_id"] = str(notification_id)
    if query:
        destination = f"{destination}?{urlencode(query)}"
    return destination


def _widget_context(user):
    return {
        "recent_notifications": get_user_in_app_messages(user, limit=6),
        "notification_unread_count": get_user_unread_count(user),
    }


@login_required
def notifications(request):
    if not request.headers.get("HX-Request"):
        return redirect(_role_notification_destination(request))

    selected_notification = None
    selected_notification_id = request.GET.get("notification_id")
    if selected_notification_id:
        selected_notification = get_object_or_404(
            NotificationMessage.objects.select_related("actor", "event").prefetch_related("delivery_attempts"),
            pk=selected_notification_id,
            recipient=request.user,
        )
        if (
            selected_notification.channel == NotificationMessage.CHANNEL_IN_APP
            and selected_notification.read_at is None
        ):
            NotificationBus.mark_as_read(selected_notification)

    filters = {
        "channel": request.GET.get("channel") or getattr(selected_notification, "channel", NotificationMessage.CHANNEL_IN_APP),
        "status": request.GET.get("status", ""),
        "priority": request.GET.get("priority", ""),
        "source": request.GET.get("source", ""),
        "category": request.GET.get("category", ""),
        "q": request.GET.get("q", "").strip(),
    }
    queryset = get_notification_center_queryset(request.user, filters)

    paginator = Paginator(queryset, 20)
    page = request.GET.get("page", 1)
    try:
        notifications_page = paginator.page(page)
    except PageNotAnInteger:
        notifications_page = paginator.page(1)
    except EmptyPage:
        notifications_page = paginator.page(paginator.num_pages)

    context = {
        "page_title": "Centre de notifications",
        "dashboard_url": _dashboard_url(request),
        "notifications": notifications_page,
        "page_obj": notifications_page,
        "unread_count": get_user_unread_count(request.user),
        "filters": filters,
        "stats": get_notification_center_stats(request.user),
        "selected_notification": selected_notification,
        **get_notification_filter_options(request.user),
    }
    if request.headers.get("HX-Request"):
        return render(request, "notification_center/partials/list.html", context)
    return render(request, "notification_center/partials/list.html", context)


@login_required
def notification_detail(request, pk):
    notification = get_object_or_404(
        NotificationMessage.objects.select_related("actor", "event").prefetch_related("delivery_attempts"),
        pk=pk,
        recipient=request.user,
    )
    if not request.headers.get("HX-Request"):
        return redirect(_role_notification_destination(request, notification_id=notification.pk))
    if (
        notification.channel == NotificationMessage.CHANNEL_IN_APP
        and notification.read_at is None
    ):
        NotificationBus.mark_as_read(notification)
    response = render(
        request,
        "notification_center/partials/detail.html",
        {"notification": notification},
    )
    response["HX-Trigger"] = "notification.read"
    return response


@login_required
def notifications_partial(request):
    context = {
        "notifications": get_user_in_app_messages(request.user, limit=7),
        "unread_count": get_user_unread_count(request.user),
    }
    return render(request, "notification_center/partials/dropdown.html", context)


@login_required
def notifications_widget(request):
    return render(
        request,
        "notification_center/partials/widget.html",
        _widget_context(request.user),
    )


@login_required
@require_POST
def mark_notification_read(request, pk):
    notification = get_object_or_404(
        NotificationMessage,
        pk=pk,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
        archived_at__isnull=True,
    )
    NotificationBus.mark_as_read(notification)
    if request.headers.get("HX-Request"):
        response = render(
            request,
            "notification_center/partials/item.html",
            {"notification": notification},
        )
        response["HX-Trigger"] = "notification.read"
        return response
    return HttpResponse(status=204)


@login_required
@require_POST
def mark_notification_unread(request, pk):
    notification = get_object_or_404(
        NotificationMessage,
        pk=pk,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
        archived_at__isnull=True,
    )
    notification.read_at = None
    notification.status = NotificationMessage.STATUS_DELIVERED
    notification.save(update_fields=["read_at", "status", "updated_at"])
    if request.headers.get("HX-Request"):
        response = render(
            request,
            "notification_center/partials/item.html",
            {"notification": notification},
        )
        response["HX-Trigger"] = "notificationsChanged"
        return response
    return HttpResponse(status=204)


@login_required
@require_POST
def archive_notification(request, pk):
    notification = get_object_or_404(
        NotificationMessage,
        pk=pk,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    NotificationBus.archive(notification)
    if request.headers.get("HX-Request"):
        response = HttpResponse("")
        response["HX-Trigger"] = "notificationsChanged"
        return response
    return redirect("notification_center:notifications")


@login_required
@require_POST
def unarchive_notification(request, pk):
    notification = get_object_or_404(
        NotificationMessage,
        pk=pk,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
        archived_at__isnull=False,
    )
    NotificationBus.unarchive(notification)
    if request.headers.get("HX-Request"):
        response = HttpResponse("")
        response["HX-Trigger"] = "notificationsChanged"
        return response
    return redirect("notification_center:notifications")


@login_required
@require_POST
def mark_all_notifications_read(request):
    now = timezone.now()
    NotificationMessage.objects.filter(
        recipient=request.user,
        read_at__isnull=True,
        archived_at__isnull=True,
        channel=NotificationMessage.CHANNEL_IN_APP,
    ).exclude(event_type="internal_message").update(
        read_at=now,
        status=NotificationMessage.STATUS_READ,
        updated_at=now,
    )
    if request.headers.get("HX-Request"):
        if request.headers.get("HX-Target") == "notification-dropdown-content":
            response = render(request, "notification_center/partials/dropdown.html", {
                "notifications": get_user_in_app_messages(request.user, limit=7),
                "unread_count": 0,
            })
        else:
            response = render(request, "notification_center/partials/widget.html", _widget_context(request.user))
        response["HX-Trigger"] = "notificationsChanged"
        return response
    return redirect("notification_center:notifications")


@login_required
def open_notification(request, pk):
    notification = get_object_or_404(
        NotificationMessage.objects.select_related("event"), pk=pk,
        recipient=request.user, channel=NotificationMessage.CHANNEL_IN_APP,
        deleted_at__isnull=True,
    )
    target = NotificationTargetResolver.resolve(notification, request)
    if notification.read_at is None:
        NotificationBus.mark_as_read(notification)
    return redirect(target or "notification_center:notifications")
