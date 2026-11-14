from django.utils.http import url_has_allowed_host_and_scheme
from django.urls import reverse


ACTION_URL_KEYS = (
    "action_url",
    "dashboard_url",
    "receipt_url",
    "detail_url",
    "login_url",
)


class NotificationTargetResolver:
    """Central gate for notification targets; normal view permissions still apply."""

    @staticmethod
    def resolve(message, request=None):
        metadata = getattr(message, "metadata", None) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        if metadata.get("target_type") == "message":
            from communications.models import Message
            message_id = str(metadata.get("message_id") or "")
            conversation_id = str(metadata.get("conversation_id") or "")
            if not message_id.isdigit() or not conversation_id.isdigit():
                return ""
            row = Message.objects.filter(pk=message_id, conversation_id=conversation_id).first()
            if row is None or request is None or not row.conversation.participants.filter(user=request.user).exists():
                return ""
            return f"{reverse('communications:conversation', args=[row.conversation_id])}?message={row.pk}"
        if metadata.get("target_type") == "course_session":
            from accounts.scoping import object_in_scope
            from academics.models import AcademicScheduleEvent

            event_id = str(metadata.get("event_id") or "")
            if not event_id.isdigit() or request is None:
                return ""
            row = AcademicScheduleEvent.objects.filter(pk=event_id, is_active=True).first()
            if row is None or not object_in_scope(row, user=request.user):
                return ""
            position = str(getattr(getattr(request.user, "profile", None), "position", "") or "")
            allowed = {
                "academic_supervisor", "branch_manager", "annex_manager", "director_of_studies",
                "executive_director", "deputy_executive_director", "super_admin",
            }
            if request.user.pk != row.teacher_id and not request.user.is_superuser and position not in allowed:
                return ""
            return reverse("academics:course_session_detail", args=[row.pk])
        if message.event_type in {"payment_validated", "first_payment_validated_staff", "receipt_generated"}:
            from payments.models import Payment
            payment_id = str(metadata.get("payment_id") or "")
            if not payment_id.isdigit():
                return ""
            row = Payment.objects.select_related("inscription__candidature__programme").filter(pk=payment_id, status="validated").first()
            if row is None or not row.receipt_number or request is None:
                return ""
            if request.user.is_staff:
                from accounts.access_context import build_access_context
                scope = build_access_context(request.user)
                candidature = row.inscription.candidature
                if not scope.is_valid or not scope.scope:
                    return ""
                if scope.scope != "GLOBAL":
                    if scope.school and candidature.programme.school_id != scope.school.pk:
                        return ""
                    if scope.branch and candidature.branch_id != scope.branch.pk:
                        return ""
                    if scope.scope in {"SCHOOL", "SCHOOL_BRANCH"} and scope.school is None:
                        return ""
                    if scope.scope in {"BRANCH", "SCHOOL_BRANCH"} and scope.branch is None:
                        return ""
            else:
                student = getattr(row.inscription, "student", None)
                if student is None or student.user_id != request.user.pk:
                    return ""
            return reverse("payments:receipt_detail", args=[row.receipt_number])
        return _get_safe_action_url(message, request)


def _get_safe_action_url(message, request=None):
    """Retourne uniquement un lien relatif ou appartenant à l'hôte courant."""
    containers = [getattr(message, "metadata", None)]
    event = getattr(message, "event", None)
    if event is not None:
        containers.extend([getattr(event, "payload", None), getattr(event, "metadata", None)])

    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in ACTION_URL_KEYS:
            candidate = container.get(key)
            if not isinstance(candidate, str):
                continue
            candidate = candidate.strip()
            if candidate.startswith("/") and url_has_allowed_host_and_scheme(
                candidate,
                allowed_hosts={request.get_host()} if request else set(),
                require_https=request.is_secure() if request else False,
            ):
                return candidate
            if request and url_has_allowed_host_and_scheme(
                candidate,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return candidate
    return ""


def get_safe_action_url(message, request=None):
    """Backward-compatible alias for the central target resolver."""
    return NotificationTargetResolver.resolve(message, request)
