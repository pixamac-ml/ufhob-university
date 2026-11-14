from django.urls import path
from . import views

app_name = "communications"
urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("contacts/", views.contacts, name="contacts"),
    path("start/<int:user_id>/", views.start_direct, name="start_direct"),
    path("<int:conversation_id>/", views.conversation_detail, name="conversation"),
    path("<int:conversation_id>/send/", views.send, name="send"),
    path("<int:conversation_id>/messages/", views.messages_partial, name="messages_partial"),
    path("<int:conversation_id>/action/", views.participant_action, name="participant_action"),
    path("<int:conversation_id>/messages/<int:message_id>/delete/", views.delete_message, name="delete_message"),
    path("groups/create/", views.group_create, name="group_create"),
    path("attachments/<int:attachment_id>/", views.attachment_download, name="attachment_download"),
]
