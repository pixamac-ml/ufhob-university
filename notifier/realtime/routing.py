from django.urls import re_path

from .consumer import NotificationConsumer
from communications.consumers import ConversationConsumer


websocket_urlpatterns = [
    re_path(r"ws/notifications/$", NotificationConsumer.as_asgi()),
    re_path(r"ws/messages/(?P<conversation_id>[0-9]+)/$", ConversationConsumer.as_asgi()),
]
