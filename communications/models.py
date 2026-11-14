import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from .storage import private_storage


def attachment_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1].lower()
    return f"{instance.message.conversation_id}/{uuid.uuid4().hex}{extension}"


class Conversation(models.Model):
    """A durable human conversation; system events never belong here."""

    direct_key = models.CharField(max_length=64, unique=True, null=True, blank=True)
    KIND_DIRECT = "direct"
    KIND_GROUP = "group"
    KIND_CLASS = "class"
    kind = models.CharField(max_length=12, choices=[(KIND_DIRECT, "Directe"), (KIND_GROUP, "Groupe"), (KIND_CLASS, "Classe")], default=KIND_DIRECT)
    title = models.CharField(max_length=160, blank=True)
    academic_class = models.ForeignKey("academics.AcademicClass", null=True, blank=True, on_delete=models.PROTECT, related_name="official_conversations")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="conversations_created")
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_message_at", "-id"]
        constraints = [models.UniqueConstraint(fields=["academic_class"], condition=models.Q(kind="class"), name="communications_one_official_class_group")]


class ConversationParticipant(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="participants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="conversation_participations")
    joined_at = models.DateTimeField(auto_now_add=True)
    last_read_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    muted_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["conversation", "user"], name="communications_unique_participant")]
        indexes = [models.Index(fields=["user", "archived_at"])]


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="messages_sent")
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)
    reply_to = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="replies")
    legacy_notification_id = models.PositiveBigIntegerField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["conversation", "created_at"])]


class MessageAttachment(models.Model):
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    file = models.FileField(upload_to=attachment_upload_path, storage=private_storage)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]

    @property
    def is_image(self):
        return self.mime_type.startswith("image/") or os.path.splitext(self.original_name)[1].lower() in {".jpg", ".jpeg", ".png", ".webp"}

    def clean(self):
        super().clean()
        if self.size > 10 * 1024 * 1024:
            raise ValidationError("La pièce jointe ne doit pas dépasser 10 Mo.")
