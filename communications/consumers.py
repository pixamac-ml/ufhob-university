"""Read-only conversation socket; HTTP services own every database write."""

import json
import uuid

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


def _allowed(user, conversation_id, session):
    from accounts.authentication import AuthenticationGate
    from accounts.access_context import build_access_context
    from accounts.session_policy import session_deadline_state
    from communications.models import ConversationParticipant
    from notifier.realtime.consumer import _authoritative_system_session_valid

    if not user.is_authenticated or not AuthenticationGate.evaluate(user).allowed:
        return False
    context = build_access_context(user)
    if not context.is_valid:
        return False
    if context.context_type == "SYSTEM":
        deadline = session_deadline_state(session, context.position)
        if deadline["reason"] or deadline["remaining_seconds"] <= 0:
            return False
        try:
            identifier = uuid.UUID(str(session.get("esfe_system_session_id")))
        except (TypeError, ValueError, AttributeError):
            return False
        if not _authoritative_system_session_valid(user.pk, identifier, getattr(session, "session_key", None)):
            return False
    return ConversationParticipant.objects.filter(conversation_id=conversation_id, user=user).exists()


class ConversationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.conversation_id = self.scope["url_route"]["kwargs"]["conversation_id"]
        if not await database_sync_to_async(_allowed)(self.scope["user"], self.conversation_id, self.scope.get("session", {})):
            await self.close(code=4403)
            return
        self.group_name = f"conversation_{self.conversation_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        # Deliberately no writing over the socket.
        if not await database_sync_to_async(_allowed)(self.scope["user"], self.conversation_id, self.scope.get("session", {})):
            await self.close(code=4403)

    async def conversation_changed(self, event):
        if not await database_sync_to_async(_allowed)(self.scope["user"], self.conversation_id, self.scope.get("session", {})):
            await self.close(code=4403)
            return
        await self.send(text_data=json.dumps({"type": "conversation.changed", "message_id": event["message_id"]}))
