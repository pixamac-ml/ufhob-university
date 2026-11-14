from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from accounts.access_context import build_access_context
from academics.models import AcademicEnrollment
from portal.services.teaching_scope import teaching_assignments

from .models import Conversation, ConversationParticipant, Message, MessageAttachment


STUDENT_SUPPORT_POSITIONS = {"director_of_studies", "secretary", "admissions", "branch_manager"}


def _active_enrollments():
    return AcademicEnrollment.objects.filter(is_active=True, is_archived=False, academic_class__is_active=True, academic_class__is_archived=False)


def _student_contacts(user, context):
    enrollment = _active_enrollments().filter(student=user).order_by("-created_at", "-pk").first()
    if enrollment is None or context.school is None or context.branch is None:
        return Q(pk__in=[])
    class_id = enrollment.academic_class_id
    from portal.models import DirectorTeacherAssignment
    teacher_ids = DirectorTeacherAssignment.objects.filter(
        is_active=True, status=DirectorTeacherAssignment.STATUS_ACTIVE,
        branch_id=enrollment.branch_id,
    ).filter(
        Q(academic_class_id=class_id)
        | Q(semester__academic_class_id=class_id)
        | Q(ue__semester__academic_class_id=class_id)
        | Q(ec__ue__semester__academic_class_id=class_id)
    ).values("teacher_id")
    peer_ids = _active_enrollments().filter(
        academic_class_id=class_id, branch_id=enrollment.branch_id,
        programme__school_id=context.school.pk, academic_year_id=enrollment.academic_year_id,
    ).values("student_id")
    staff = Q(institutional_profile__school_id=context.school.pk,
              institutional_profile__branch_id=context.branch.pk,
              institutional_profile__position__in=STUDENT_SUPPORT_POSITIONS)
    return Q(pk__in=peer_ids) | Q(pk__in=teacher_ids) | staff


def _teacher_contacts(user):
    from academics.models import AcademicClass
    class_ids = teaching_assignments(user).values("teaching_class_id")
    classes = AcademicClass.objects.filter(pk__in=class_ids, is_active=True, is_archived=False)
    students = _active_enrollments().filter(academic_class_id__in=classes.values("pk")).values("student_id")
    staff = Q()
    for school_id, branch_id in classes.values_list("programme__school_id", "branch_id").distinct():
        staff |= Q(institutional_profile__school_id=school_id, institutional_profile__branch_id=branch_id)
    return Q(pk__in=students) | staff


def _staff_contacts(context):
    school_id = getattr(context.school, "pk", None)
    branch_id = getattr(context.branch, "pk", None)
    if not school_id:
        # Branch-only scope must not reveal every school on the same campus.
        return Q(pk__in=[])
    staff = Q(institutional_profile__school_id=school_id)
    students = _active_enrollments().filter(programme__school_id=school_id)
    if branch_id:
        staff &= Q(institutional_profile__branch_id=branch_id)
        students = students.filter(branch_id=branch_id)
    return staff | Q(pk__in=students.values("student_id"))


def get_visible_contacts(user, query=""):
    User = get_user_model()
    if not user.is_authenticated or not user.is_active:
        return User.objects.none()
    context = build_access_context(user)
    if not context.is_valid:
        return User.objects.none()
    if context.scope == "GLOBAL" or user.is_superuser:
        scope = Q()
    elif context.position == "student":
        scope = _student_contacts(user, context)
    elif context.position in {"teacher", "moniteur"}:
        scope = _teacher_contacts(user)
    else:
        scope = _staff_contacts(context)
    queryset = User.objects.filter(is_active=True).exclude(pk=user.pk).filter(scope).select_related(
        "profile", "institutional_profile__school", "institutional_profile__branch",
    )
    if query:
        queryset = queryset.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(username__icontains=query) | Q(institutional_profile__employee_code__icontains=query))
    return queryset.distinct().order_by("first_name", "last_name", "username")


def can_contact(sender, recipient):
    return get_visible_contacts(sender).filter(pk=recipient.pk).exists()


@transaction.atomic
def get_or_create_direct_conversation(sender, recipient):
    if sender.pk == recipient.pk or not can_contact(sender, recipient):
        raise PermissionError("Ce contact n'est pas disponible dans votre périmètre.")
    key = ":".join(str(value) for value in sorted((sender.pk, recipient.pk)))
    try:
        conversation, created = Conversation.objects.get_or_create(direct_key=key, defaults={"created_by": sender, "kind": Conversation.KIND_DIRECT})
    except IntegrityError:
        conversation, created = Conversation.objects.get(direct_key=key), False
    if created:
        ConversationParticipant.objects.bulk_create([ConversationParticipant(conversation=conversation, user=sender), ConversationParticipant(conversation=conversation, user=recipient)])
    return conversation


def require_participant(conversation, user):
    return ConversationParticipant.objects.filter(conversation=conversation, user=user).first()


@transaction.atomic
def create_group(*, creator, title, members, academic_class=None):
    context = build_access_context(creator)
    teacher = context.position in {"teacher", "moniteur"}
    if not context.is_valid or context.position == "student" or (context.scope != "GLOBAL" and context.school is None and not teacher):
        raise PermissionError("Création de groupe non autorisée.")
    if teacher and (academic_class is None or not teaching_assignments(creator).filter(teaching_class_id=academic_class.pk).exists()):
        raise PermissionError("Seules vos classes affectées peuvent avoir un groupe officiel.")
    members = list(dict.fromkeys(members))
    maximum = 200 if academic_class is not None else 30
    if not title.strip() or not members or len(members) > maximum:
        raise ValidationError(f"Le nom et au moins un contact sont requis ({maximum} maximum).")
    member_ids = {member.pk for member in members}
    visible_ids = set(get_visible_contacts(creator).filter(pk__in=member_ids).values_list("pk", flat=True))
    if member_ids != visible_ids:
        raise PermissionError("Un contact est hors de votre périmètre.")
    if academic_class is not None:
        if not academic_class.is_active or academic_class.is_archived:
            raise PermissionError("Cette classe n'est plus active.")
        if not teacher and context.scope != "GLOBAL" and (
            academic_class.programme.school_id != context.school.pk
            or context.branch and academic_class.branch_id != context.branch.pk
        ):
            raise PermissionError("Classe hors de votre périmètre.")
        from portal.models import DirectorTeacherAssignment
        teacher_ids = DirectorTeacherAssignment.objects.filter(
            is_active=True, status=DirectorTeacherAssignment.STATUS_ACTIVE,
            branch_id=academic_class.branch_id,
        ).filter(
            Q(academic_class=academic_class)
            | Q(semester__academic_class=academic_class)
            | Q(ue__semester__academic_class=academic_class)
            | Q(ec__ue__semester__academic_class=academic_class)
        ).values("teacher_id")
        student_ids = _active_enrollments().filter(academic_class=academic_class).values("student_id")
        permitted = set(get_user_model().objects.filter(pk__in=member_ids).filter(
            Q(pk__in=student_ids) | Q(pk__in=teacher_ids)
            | Q(institutional_profile__school_id=academic_class.programme.school_id,
                institutional_profile__branch_id=academic_class.branch_id)
        ).values_list("pk", flat=True))
        if member_ids != permitted:
            raise PermissionError("Un membre n'appartient pas à cette classe.")
        kind = Conversation.KIND_CLASS
    else:
        kind = Conversation.KIND_GROUP
    if academic_class is not None and Conversation.objects.filter(kind=Conversation.KIND_CLASS, academic_class=academic_class).exists():
        existing = Conversation.objects.get(kind=Conversation.KIND_CLASS, academic_class=academic_class)
        if require_participant(existing, creator) is None:
            raise PermissionError("Ce groupe officiel existe déjà ; contactez son responsable.")
        return existing
    conversation = Conversation.objects.create(created_by=creator, kind=kind, title=title.strip(), academic_class=academic_class)
    ConversationParticipant.objects.bulk_create([ConversationParticipant(conversation=conversation, user=user) for user in [creator, *members]])
    return conversation


@transaction.atomic
def send_message(*, conversation, sender, body, attachment=None, reply_to=None):
    from .forms import MessageForm

    validation = MessageForm({"body": body}, {"attachment": attachment} if attachment is not None else None)
    if not validation.is_valid():
        raise ValidationError("Message ou pièce jointe invalide.")
    if require_participant(conversation, sender) is None:
        raise PermissionError("Conversation non autorisée.")
    if conversation.kind == Conversation.KIND_DIRECT:
        recipient = conversation.participants.exclude(user=sender).select_related("user").first()
        if recipient is None or not can_contact(sender, recipient.user):
            raise PermissionError("Ce contact n'est plus dans votre périmètre.")
    else:
        member_ids = set(conversation.participants.exclude(user=sender).values_list("user_id", flat=True))
        allowed_ids = set(get_visible_contacts(sender).filter(pk__in=member_ids).values_list("pk", flat=True))
        if member_ids != allowed_ids:
            raise PermissionError("Un membre du groupe n'est plus dans votre périmètre.")
    if reply_to is not None and reply_to.conversation_id != conversation.pk:
        raise ValidationError("Réponse hors conversation.")
    body = (body or "").strip()
    if not body and attachment is None:
        raise ValidationError("Le message est vide.")
    message = Message.objects.create(conversation=conversation, sender=sender, body=body, reply_to=reply_to)
    if attachment:
        MessageAttachment.objects.create(message=message, uploaded_by=sender, file=attachment, original_name=attachment.name, mime_type=getattr(attachment, "content_type", "") or "", size=attachment.size)
    Conversation.objects.filter(pk=conversation.pk).update(last_message_at=message.created_at)
    ConversationParticipant.objects.filter(conversation=conversation, archived_at__isnull=False).update(archived_at=None)
    _notify_message(message)
    transaction.on_commit(lambda conversation_id=conversation.pk, message_id=message.pk: _announce_message(conversation_id, message_id))
    return message


def _announce_message(conversation_id, message_id):
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    layer = get_channel_layer()
    if layer is not None:
        try:
            async_to_sync(layer.group_send)(f"conversation_{conversation_id}", {"type": "conversation.changed", "message_id": message_id})
        except Exception:
            # Redis/channel backends use different exception classes. Never
            # turn an already committed message into a misleading HTTP 500.
            pass


def _notify_message(message):
    from notifier.models import NotificationMessage
    from notifier.services import NotificationBus

    for participant in message.conversation.participants.exclude(user_id=message.sender_id).select_related("user"):
        if participant.muted_until and participant.muted_until > timezone.now():
            continue
        if NotificationMessage.objects.filter(
            recipient=participant.user,
            event_type="new_human_message",
            legacy_source="communications.message",
            legacy_object_id=str(message.pk),
        ).exists():
            continue
        NotificationBus.notify(
            recipient=participant.user, actor=message.sender,
            event_type="new_human_message", title=f"Nouveau message de {message.sender.get_full_name() or message.sender.username}",
            body="Ouvrez la conversation pour le consulter.", source_app="communications",
            channels=(NotificationMessage.CHANNEL_IN_APP, NotificationMessage.CHANNEL_WEBSOCKET),
            metadata={"target_type": "message", "message_id": message.pk, "conversation_id": message.conversation_id},
            legacy_source="communications.message", legacy_object_id=str(message.pk),
        )


def mark_conversation_read(conversation, user):
    ConversationParticipant.objects.filter(conversation=conversation, user=user).filter(
        Q(last_read_at__isnull=True) | Q(last_read_at__lt=conversation.last_message_at)
    ).update(last_read_at=timezone.now())
