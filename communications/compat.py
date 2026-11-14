"""Move the historical dashboard entry points to one human-message UI."""

from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse


def redirect_legacy_messages(request):
    destination = reverse("communications:inbox")
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = destination
        return response
    return redirect(destination)


def redirect_legacy_message_detail(request, notification_id):
    from communications.models import Message
    from notifier.models import NotificationMessage

    row = Message.objects.filter(legacy_notification_id=notification_id, conversation__participants__user=request.user).first()
    if row:
        destination = f"{reverse('communications:conversation', args=[row.conversation_id])}?message={row.pk}"
    elif NotificationMessage.objects.filter(pk=notification_id, recipient=request.user, event_type="internal_message").exists():
        # The source row remains preserved even if migration could not map it.
        destination = reverse("communications:inbox") + "?section=archives"
    else:
        destination = reverse("notification_center:open_notification", args=[notification_id])
    if request.headers.get("HX-Request"):
        response = HttpResponse(status=204)
        response["HX-Redirect"] = destination
        return response
    return redirect(destination)
