from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Prefetch, Q, OuterRef, Subquery
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.http import FileResponse, Http404, HttpResponseBadRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from uuid import uuid4

from .forms import MessageForm
from .models import Conversation, ConversationParticipant, Message, MessageAttachment
from .services import (
    get_or_create_direct_conversation,
    get_visible_contacts,
    mark_conversation_read,
    require_participant,
    send_message,
    create_group,
)


def _shell_context(request):
    from ui.services.standalone_shell import build_standalone_shell
    return build_standalone_shell(request, key="messages", title="Messagerie", access=_require_messaging_access(request))


def _require_messaging_access(request):
    from accounts.access_context import build_access_context
    if not hasattr(request, "_messaging_access"):
        request._messaging_access = build_access_context(request.user)
    if not request._messaging_access.is_valid:
        raise PermissionDenied("Votre compte n'est pas activé pour la messagerie.")
    return request._messaging_access


def _conversations_for(user, *, archived=False):
    participant_qs = ConversationParticipant.objects.select_related("user__profile", "user__institutional_profile")
    queryset = Conversation.objects.filter(participants__user=user, participants__archived_at__isnull=not archived)
    return queryset.select_related("created_by", "academic_class").prefetch_related(
        Prefetch("participants", queryset=participant_qs)
    ).annotate(
        last_preview=Subquery(Message.objects.filter(conversation=OuterRef("pk"), deleted_at__isnull=True).order_by("-created_at", "-pk").values("body")[:1]),
        unread_count=Count(
            "messages",
            filter=Q(messages__deleted_at__isnull=True) & ~Q(messages__sender=user)
            & (Q(participants__last_read_at__isnull=True, messages__created_at__gte=F("participants__joined_at"))
               | Q(messages__created_at__gt=F("participants__last_read_at"))),
            distinct=True,
        )
    ).order_by("-last_message_at", "-id")


def _other_participant(conversation, user):
    return next((item.user for item in conversation.participants.all() if item.user_id != user.pk), None)


def _has_older_messages(conversation, rows):
    if not rows:
        return False
    oldest = rows[0]
    return conversation.messages.filter(
        Q(created_at__lt=oldest.created_at) | Q(created_at=oldest.created_at, pk__lt=oldest.pk)
    ).exists()


@login_required
@never_cache
def inbox(request):
    _require_messaging_access(request)
    from accounts.access_context import build_access_context
    from academics.models import AcademicClass

    section = (request.GET.get("section") or "conversations").lower()
    if section not in {"conversations", "directory", "groups", "files", "archives", "security"}:
        raise Http404
    query = (request.GET.get("q") or "").strip()
    if query and section in {"directory", "groups"} and not cache.add(f"communications:search:{request.user.pk}", True, timeout=1):
        return HttpResponse("Recherche trop fréquente.", status=429)
    conversations = Paginator(_conversations_for(request.user, archived=section == "archives").filter(
        kind__in=[Conversation.KIND_GROUP, Conversation.KIND_CLASS] if section == "groups" else [Conversation.KIND_DIRECT, Conversation.KIND_GROUP, Conversation.KIND_CLASS]
    ), 25).get_page(request.GET.get("page") or 1)
    for conversation in conversations:
        conversation.other_user = _other_participant(conversation, request.user)
    attachments = MessageAttachment.objects.none()
    if section == "files":
        attachments = MessageAttachment.objects.filter(
            message__conversation__participants__user=request.user,
            message__deleted_at__isnull=True,
        ).select_related(
            "message__conversation", "uploaded_by"
        ).distinct().order_by("-created_at")[:50]
    access = build_access_context(request.user)
    group_classes = AcademicClass.objects.none()
    if section == "groups" and access.position != "student" and (access.scope == "GLOBAL" or access.school or access.position in {"teacher", "moniteur"}):
        group_classes = AcademicClass.objects.filter(is_active=True, is_archived=False).select_related("programme", "branch")
        if access.position in {"teacher", "moniteur"}:
            from portal.services.teaching_scope import teaching_assignments
            group_classes = group_classes.filter(pk__in=teaching_assignments(request.user).values("teaching_class_id"))
        elif access.scope != "GLOBAL":
            group_classes = group_classes.filter(programme__school=access.school)
            if access.branch:
                group_classes = group_classes.filter(branch=access.branch)
        group_classes = group_classes.order_by("programme__title", "level")[:50]
    return render(request, "communications/inbox.html", {
        **_shell_context(request),
        "conversations": conversations,
        "contacts": get_visible_contacts(request.user, query)[:20] if len(query) >= 2 else [],
        "query": query,
        "section": section,
        "attachments": attachments,
        "group_classes": group_classes,
        "can_create_group": access.position != "student" and (access.scope == "GLOBAL" or access.school is not None or access.position in {"teacher", "moniteur"}),
    })


@login_required
def contacts(request):
    _require_messaging_access(request)
    query = (request.GET.get("q") or "").strip()
    if query and not cache.add(f"communications:search:{request.user.pk}", True, timeout=1):
        return HttpResponse("Recherche trop fréquente.", status=429)
    return render(request, "communications/partials/contacts.html", {
        "contacts": get_visible_contacts(request.user, query)[:30] if len(query) >= 2 else [], "query": query,
    })


@login_required
@require_POST
def start_direct(request, user_id):
    _require_messaging_access(request)
    if not cache.add(f"communications:start:{request.user.pk}", True, timeout=2):
        return HttpResponse("Veuillez patienter avant de créer une autre conversation.", status=429)
    recipient = get_object_or_404(get_user_model(), pk=user_id, is_active=True)
    try:
        conversation = get_or_create_direct_conversation(request.user, recipient)
    except PermissionError:
        raise Http404
    return redirect("communications:conversation", conversation_id=conversation.pk)


@login_required
@never_cache
def conversation_detail(request, conversation_id):
    _require_messaging_access(request)
    conversation = get_object_or_404(_conversations_for(request.user, archived=False), pk=conversation_id)
    participant = require_participant(conversation, request.user)
    if participant is None:
        raise Http404
    source = conversation.messages.select_related("sender__profile", "reply_to").prefetch_related("attachments")
    highlighted = (request.GET.get("message") or "").strip()
    if highlighted.isdigit():
        target = source.filter(pk=highlighted).first()
        if target is not None:
            source = source.filter(Q(created_at__lt=target.created_at) | Q(created_at=target.created_at, pk__lte=target.pk))
        else:
            highlighted = ""
    else:
        highlighted = ""
    before = (request.GET.get("before") or "").strip()
    if before.isdigit() and not highlighted:
        cursor = source.filter(pk=before).first()
        if cursor is not None:
            source = source.filter(Q(created_at__lt=cursor.created_at) | Q(created_at=cursor.created_at, pk__lt=cursor.pk))
        else:
            before = ""
    else:
        before = ""
    messages_qs = list(source.order_by("-created_at", "-id")[:50])[::-1]
    mark_conversation_read(conversation, request.user)
    return render(request, "communications/conversation.html", {
        **_shell_context(request),
        "conversation": conversation,
        "other_user": _other_participant(conversation, request.user),
        "message_list": messages_qs,
        "has_older": _has_older_messages(conversation, messages_qs),
        "older_cursor": messages_qs[0].pk if messages_qs else None,
        "history_page": bool(before),
        "highlighted_message_id": highlighted,
        "submission_key": uuid4().hex,
        "form": MessageForm(),
    })


@login_required
@require_POST
def send(request, conversation_id):
    _require_messaging_access(request)
    conversation = get_object_or_404(_conversations_for(request.user), pk=conversation_id)
    form = MessageForm(request.POST, request.FILES)
    submitted_key = (request.POST.get("submission_key") or "").strip()
    idempotency_key = (
        f"communications:submission:{request.user.pk}:{submitted_key}"
        if len(submitted_key) == 32 and all(character in "0123456789abcdef" for character in submitted_key)
        else ""
    )
    if form.is_valid():
        if idempotency_key and not cache.add(idempotency_key, True, timeout=300):
            form.add_error(None, "Ce message a déjà été envoyé.")
        elif not cache.add(f"communications:send:{request.user.pk}", True, timeout=2):
            if idempotency_key:
                cache.delete(idempotency_key)
            form.add_error(None, "Veuillez patienter avant un nouvel envoi.")
        else:
            try:
                reply_id = (request.POST.get("reply_to") or "").strip()
                reply_to = get_object_or_404(Message, pk=reply_id, conversation=conversation) if reply_id else None
                send_message(conversation=conversation, sender=request.user, body=form.cleaned_data["body"], attachment=form.cleaned_data.get("attachment"), reply_to=reply_to)
            except (PermissionError, ValidationError):
                cache.delete(f"communications:send:{request.user.pk}")
                if idempotency_key:
                    cache.delete(idempotency_key)
                raise Http404
            messages.success(request, "Message envoyé.")
            return redirect("communications:conversation", conversation_id=conversation.pk)
    return render(request, "communications/conversation.html", {
        **_shell_context(request),
        "conversation": conversation,
        "other_user": _other_participant(conversation, request.user),
        "message_list": list(conversation.messages.select_related("sender__profile").prefetch_related("attachments").order_by("-created_at", "-id")[:50])[::-1],
        "submission_key": submitted_key or uuid4().hex,
        "form": form,
    }, status=400)


@login_required
@never_cache
def attachment_download(request, attachment_id):
    _require_messaging_access(request)
    attachment = get_object_or_404(MessageAttachment.objects.select_related("message__conversation"), pk=attachment_id, message__deleted_at__isnull=True)
    if require_participant(attachment.message.conversation, request.user) is None:
        raise Http404
    if not attachment.file:
        raise Http404
    try:
        stream = attachment.file.open("rb")
    except (OSError, ValueError):
        raise Http404
    preview_type = ""
    if request.GET.get("preview") == "1" and attachment.is_image:
        header = stream.read(12)
        stream.seek(0)
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            preview_type = "image/png"
        elif header.startswith(b"\xff\xd8\xff"):
            preview_type = "image/jpeg"
        elif header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            preview_type = "image/webp"
    response = FileResponse(
        stream, as_attachment=not preview_type, filename=attachment.original_name,
        content_type=preview_type or "application/octet-stream",
    )
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
@require_POST
def participant_action(request, conversation_id):
    _require_messaging_access(request)
    conversation = get_object_or_404(Conversation, pk=conversation_id, participants__user=request.user)
    participant = require_participant(conversation, request.user)
    action = request.POST.get("action")
    if action == "archive":
        participant.archived_at = timezone.now()
        participant.save(update_fields=["archived_at"])
    elif action == "restore":
        participant.archived_at = None
        participant.save(update_fields=["archived_at"])
    elif action == "mute":
        from datetime import timedelta
        participant.muted_until = timezone.now() + timedelta(days=7)
        participant.save(update_fields=["muted_until"])
    elif action == "unmute":
        participant.muted_until = None
        participant.save(update_fields=["muted_until"])
    else:
        return HttpResponseBadRequest("Action inconnue.")
    return redirect("communications:inbox")


@login_required
@require_POST
def group_create(request):
    _require_messaging_access(request)
    if not cache.add(f"communications:group:{request.user.pk}", True, timeout=10):
        return HttpResponse("Veuillez patienter avant de créer un autre groupe.", status=429)
    from academics.models import AcademicClass
    members = list(get_user_model().objects.filter(pk__in=request.POST.getlist("members"), is_active=True))
    academic_class = get_object_or_404(AcademicClass, pk=request.POST["academic_class_id"]) if request.POST.get("academic_class_id") else None
    try:
        conversation = create_group(creator=request.user, title=request.POST.get("title", ""), members=members, academic_class=academic_class)
    except (PermissionError, ValidationError):
        raise Http404
    return redirect("communications:conversation", conversation_id=conversation.pk)


@login_required
@never_cache
def messages_partial(request, conversation_id):
    _require_messaging_access(request)
    conversation = get_object_or_404(Conversation, pk=conversation_id, participants__user=request.user)
    mark_conversation_read(conversation, request.user)
    rows = list(conversation.messages.select_related("sender", "reply_to").prefetch_related("attachments").order_by("-created_at", "-id")[:50])[::-1]
    return render(request, "communications/partials/messages.html", {
        "message_list": rows, "conversation": conversation,
        "has_older": _has_older_messages(conversation, rows),
        "older_cursor": rows[0].pk if rows else None,
    })


@login_required
@require_POST
def delete_message(request, conversation_id, message_id):
    _require_messaging_access(request)
    message = get_object_or_404(
        Message, pk=message_id, conversation_id=conversation_id,
        conversation__participants__user=request.user, sender=request.user,
    )
    if message.deleted_at is None:
        message.deleted_at = timezone.now()
        message.save(update_fields=["deleted_at"])
    return redirect("communications:conversation", conversation_id=conversation_id)
