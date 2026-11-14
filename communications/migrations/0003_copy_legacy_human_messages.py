"""Copy legacy human notifications into private conversations without deleting source rows."""

from django.db import migrations


def copy_legacy(apps, schema_editor):
    alias = schema_editor.connection.alias
    Legacy = apps.get_model("notifier", "NotificationMessage")
    LegacyAttachment = apps.get_model("notifier", "MessageAttachment")
    Conversation = apps.get_model("communications", "Conversation")
    Participant = apps.get_model("communications", "ConversationParticipant")
    Message = apps.get_model("communications", "Message")
    Attachment = apps.get_model("communications", "MessageAttachment")
    queryset = Legacy.objects.using(alias).filter(event_type="internal_message", channel="in_app", actor_id__isnull=False, recipient_id__isnull=False).order_by("created_at", "pk")
    for old in queryset.iterator(chunk_size=200):
        if old.actor_id == old.recipient_id or Message.objects.using(alias).filter(legacy_notification_id=old.pk).exists():
            continue
        key = ":".join(str(value) for value in sorted((old.actor_id, old.recipient_id)))
        conversation, _ = Conversation.objects.using(alias).get_or_create(
            direct_key=key, defaults={"created_by_id": old.actor_id, "last_message_at": old.created_at, "kind": "direct"},
        )
        author, _ = Participant.objects.using(alias).get_or_create(conversation_id=conversation.pk, user_id=old.actor_id)
        recipient, _ = Participant.objects.using(alias).get_or_create(conversation_id=conversation.pk, user_id=old.recipient_id)
        for member in (author, recipient):
            if member.joined_at > old.created_at:
                Participant.objects.using(alias).filter(pk=member.pk).update(joined_at=old.created_at)
                member.joined_at = old.created_at
        body = f"{old.title}\n\n{old.body}" if old.title and old.body else old.title or old.body or ""
        row = Message.objects.using(alias).create(
            conversation_id=conversation.pk, sender_id=old.actor_id,
            body=body, legacy_notification_id=old.pk, deleted_at=old.deleted_at,
        )
        Message.objects.using(alias).filter(pk=row.pk).update(created_at=old.created_at)
        if old.read_at and (recipient.last_read_at is None or recipient.last_read_at < old.read_at):
            recipient.last_read_at = old.read_at
            recipient.save(update_fields=["last_read_at"])
        if old.created_at > conversation.last_message_at:
            Conversation.objects.using(alias).filter(pk=conversation.pk).update(last_message_at=old.created_at)
        if not old.batch_id:
            continue
        for source in LegacyAttachment.objects.using(alias).filter(batch_id=old.batch_id).iterator(chunk_size=20):
            # A missing old file remains in the untouched legacy table for audit;
            # the migration never destroys or rewrites its source reference.
            try:
                with source.file.open("rb") as stream:
                    target = Attachment(message_id=row.pk, uploaded_by_id=source.uploaded_by_id,
                                        original_name=source.original_name, mime_type=source.content_type, size=source.size)
                    target.file.save(source.original_name, stream, save=False)
                    target.save(using=alias)
            except (FileNotFoundError, OSError):
                continue


class Migration(migrations.Migration):
    dependencies = [
        ("communications", "0002_conversation_academic_class_conversation_kind_and_more"),
        ("notifier", "0003_notificationmessage_batch_id_and_more"),
    ]
    operations = [migrations.RunPython(copy_legacy, migrations.RunPython.noop)]
