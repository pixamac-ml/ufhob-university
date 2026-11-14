from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.cache import cache
from django.apps import apps
from django.db import connection
from types import SimpleNamespace
from importlib import import_module
from unittest.mock import patch

from .forms import MessageForm
from .models import ConversationParticipant, MessageAttachment
from .models import Message
from .services import create_group, get_or_create_direct_conversation, require_participant, send_message
from .services import get_visible_contacts, _notify_message
from notifier.models import NotificationMessage
from .consumers import _allowed as websocket_allowed


class DirectConversationTests(TestCase):
    def setUp(self):
        cache.clear()
        User = get_user_model()
        self.sender = User.objects.create_superuser("phase2_sender", "sender@example.test", "safe-password-123")
        self.recipient = User.objects.create_user("phase2_recipient", "recipient@example.test", "safe-password-123")
        self.outsider = User.objects.create_user("phase2_outsider", "outsider@example.test", "safe-password-123")

    def test_direct_conversation_is_reused_and_messages_are_persistent(self):
        first = get_or_create_direct_conversation(self.sender, self.recipient)
        second = get_or_create_direct_conversation(self.sender, self.recipient)
        message = send_message(conversation=first, sender=self.sender, body="Bonjour")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ConversationParticipant.objects.filter(conversation=first).count(), 2)
        self.assertEqual(message.body, "Bonjour")

    def test_conversation_creation_endpoint_is_rate_limited(self):
        self.client.force_login(self.sender)
        url = reverse("communications:start_direct", args=[self.recipient.pk])
        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 429)

    def test_authorized_group_persists_members_and_messages(self):
        access = SimpleNamespace(
            is_valid=True, position="super_admin", scope="GLOBAL",
            school=None, branch=None,
        )
        with patch("communications.services.build_access_context", return_value=access):
            group = create_group(
                creator=self.sender,
                title="Groupe contrôlé",
                members=[self.recipient],
            )
            sent = send_message(conversation=group, sender=self.sender, body="Bonjour au groupe")
        self.assertEqual(group.kind, group.KIND_GROUP)
        self.assertEqual(group.participants.count(), 2)
        self.assertEqual(sent.conversation_id, group.pk)

    def test_non_participant_cannot_be_resolved_as_participant(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        self.assertIsNone(require_participant(conversation, self.outsider))

    def test_websocket_participant_gate_rejects_outsider(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        access = SimpleNamespace(is_valid=True, context_type="PUBLIC")
        decision = SimpleNamespace(allowed=True)
        with patch("accounts.authentication.AuthenticationGate.evaluate", return_value=decision), patch(
            "accounts.access_context.build_access_context", return_value=access
        ):
            self.assertTrue(websocket_allowed(self.recipient, conversation.pk, {}))
            self.assertFalse(websocket_allowed(self.outsider, conversation.pk, {}))

    def test_unread_count_clears_when_recipient_opens_conversation(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        send_message(conversation=conversation, sender=self.sender, body="À lire")
        self.client.force_login(self.recipient)
        before = self.client.get(reverse("communications:inbox"))
        self.assertEqual(before.status_code, 200)
        self.assertEqual(before.context["conversations"][0].unread_count, 1)
        self.client.get(reverse("communications:conversation", args=[conversation.pk]))
        after = self.client.get(reverse("communications:inbox"))
        self.assertEqual(after.context["conversations"][0].unread_count, 0)

    def test_direct_conversation_is_private_and_archiving_is_individual(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("communications:conversation", args=[conversation.pk])).status_code, 404)
        self.client.force_login(self.sender)
        response = self.client.post(reverse("communications:participant_action", args=[conversation.pk]), {"action": "archive"})
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(require_participant(conversation, self.sender).archived_at)
        self.assertIsNone(require_participant(conversation, self.recipient).archived_at)
        response = self.client.post(
            reverse("communications:participant_action", args=[conversation.pk]),
            {"action": "restore"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(require_participant(conversation, self.sender).archived_at)

    def test_message_notification_targets_exact_conversation(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        sent = send_message(conversation=conversation, sender=self.sender, body="<script>alert(1)</script>")
        notification = NotificationMessage.objects.get(recipient=self.recipient, event_type="new_human_message", channel="in_app")
        self.assertNotIn("<script>", notification.body)
        self.client.force_login(self.recipient)
        response = self.client.get(reverse("notification_center:open_notification", args=[notification.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('communications:conversation', args=[conversation.pk])}?message={sent.pk}")
        notification.refresh_from_db()
        self.assertIsNotNone(notification.read_at)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("notification_center:open_notification", args=[notification.pk])).status_code, 404)

    def test_message_notification_is_idempotent_for_each_recipient(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        sent = send_message(conversation=conversation, sender=self.sender, body="Un seul événement")
        _notify_message(sent)
        self.assertEqual(
            NotificationMessage.objects.filter(
                recipient=self.recipient,
                event_type="new_human_message",
                legacy_source="communications.message",
                legacy_object_id=str(sent.pk),
            ).count(),
            2,  # One durable in-app record and one WebSocket delivery record.
        )

    def test_muted_conversation_suppresses_alert_but_keeps_message(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        participant = require_participant(conversation, self.recipient)
        from django.utils import timezone
        from datetime import timedelta

        participant.muted_until = timezone.now() + timedelta(days=1)
        participant.save(update_fields=["muted_until"])
        sent = send_message(conversation=conversation, sender=self.sender, body="Message silencieux")
        self.assertTrue(Message.objects.filter(pk=sent.pk).exists())
        self.assertFalse(
            NotificationMessage.objects.filter(
                recipient=self.recipient,
                legacy_source="communications.message",
                legacy_object_id=str(sent.pk),
            ).exists()
        )

    def test_message_html_is_escaped_and_old_dashboard_is_redirected(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        send_message(conversation=conversation, sender=self.sender, body="<script>alert(1)</script>")
        self.client.force_login(self.recipient)
        page = self.client.get(reverse("communications:conversation", args=[conversation.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "&lt;script&gt;alert(1)&lt;/script&gt;", html=False)
        self.client.force_login(self.sender)
        legacy = self.client.get(reverse("accounts_portal:staff_messaging") + "?dash=manager", HTTP_HX_REQUEST="true")
        self.assertEqual(legacy.status_code, 204)
        self.assertEqual(legacy["HX-Redirect"], reverse("communications:inbox"))

    def test_private_attachment_is_not_public_and_requires_participation(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        uploaded = SimpleUploadedFile("test.pdf", b"%PDF-1.4\nexample", content_type="application/pdf")
        self.assertTrue(MessageForm({"body": ""}, {"attachment": uploaded}).is_valid())
        uploaded.seek(0)
        message = send_message(conversation=conversation, sender=self.sender, body="", attachment=uploaded)
        attachment = MessageAttachment.objects.get(message=message)
        self.addCleanup(attachment.file.delete, save=False)
        self.assertRaises(ValueError, lambda: attachment.file.url)
        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(reverse("communications:attachment_download", args=[attachment.pk])).status_code, 404)
        self.client.force_login(self.recipient)
        response = self.client.get(reverse("communications:attachment_download", args=[attachment.pk]))
        self.assertEqual(response.status_code, 200)
        response.close()

    def test_file_signature_is_checked(self):
        uploaded = SimpleUploadedFile("fake.pdf", b"<html>not a PDF</html>", content_type="application/pdf")
        self.assertFalse(MessageForm({"body": "hello"}, {"attachment": uploaded}).is_valid())

    def test_private_image_preview_uses_a_verified_content_type(self):
        conversation = get_or_create_direct_conversation(self.sender, self.recipient)
        uploaded = SimpleUploadedFile(
            "preview.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 24,
            content_type="image/png",
        )
        message = send_message(conversation=conversation, sender=self.sender, body="", attachment=uploaded)
        attachment = MessageAttachment.objects.get(message=message)
        self.addCleanup(attachment.file.delete, save=False)
        self.client.force_login(self.recipient)
        response = self.client.get(
            reverse("communications:attachment_download", args=[attachment.pk]),
            {"preview": "1"},
        )
        status_code = response.status_code
        content_type = response["Content-Type"]
        cache_control = response["Cache-Control"]
        response.close()
        self.assertEqual(status_code, 200)
        self.assertEqual(content_type, "image/png")
        self.assertIn("private", cache_control)
        self.assertIn("no-store", cache_control)

    def test_historic_public_message_paths_are_not_served_by_django(self):
        for path in ("/media/notifier/internal-messages/old.pdf", "/media/communications/old.pdf"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)


class DirectoryScopeTests(TestCase):
    def test_two_schools_on_one_campus_do_not_share_contacts(self):
        from accounts.models import InstitutionalProfile
        from branches.models import Branch
        from core.models import Institution, School, SchoolBranch

        institution = Institution.objects.create(name="Test UFHOB", address="Test", city="Bamako", phone="000", email="test@example.test")
        campus = Branch.objects.create(name="Campus test", code="CT", slug="campus-test")
        first = School.objects.create(institution=institution, code="TESTA", short_name="Test A")
        second = School.objects.create(institution=institution, code="TESTB", short_name="Test B")
        SchoolBranch.objects.create(school=first, branch=campus)
        SchoolBranch.objects.create(school=second, branch=campus)
        User = get_user_model()
        sender = User.objects.create_user("scope_a", "a@example.test", "safe-password-123")
        within = User.objects.create_user("scope_a_peer", "peer@example.test", "safe-password-123")
        outside = User.objects.create_user("scope_b_peer", "other@example.test", "safe-password-123")
        for person, school in [(sender, first), (within, first), (outside, second)]:
            InstitutionalProfile.objects.create(user=person, school=school, branch=campus, position="director_of_studies")
        visible = get_visible_contacts(sender)
        self.assertIn(within, visible)
        self.assertNotIn(outside, visible)
        self.client.force_login(sender)
        self.assertEqual(self.client.post(reverse("communications:start_direct", args=[outside.pk])).status_code, 404)


class LegacyMigrationTests(TestCase):
    def test_old_human_notification_is_copied_once_without_deleting_source(self):
        User = get_user_model()
        author = User.objects.create_user("legacy_sender", "legacy.sender@example.test", "safe-password-123")
        reader = User.objects.create_user("legacy_reader", "legacy.reader@example.test", "safe-password-123")
        old = NotificationMessage.objects.create(
            actor=author, recipient=reader, title="Objet d'archive", body="Ancien texte",
            event_type="internal_message", notification_type="internal_message", channel="in_app",
        )
        migration = import_module("communications.migrations.0003_copy_legacy_human_messages")
        editor = SimpleNamespace(connection=connection)
        migration.copy_legacy(apps, editor)
        migration.copy_legacy(apps, editor)
        row = Message.objects.get(legacy_notification_id=old.pk)
        self.assertEqual(Message.objects.filter(legacy_notification_id=old.pk).count(), 1)
        self.assertEqual(row.body, "Objet d'archive\n\nAncien texte")
        self.assertEqual(row.conversation.participants.count(), 2)
        self.assertTrue(NotificationMessage.objects.filter(pk=old.pk).exists())
