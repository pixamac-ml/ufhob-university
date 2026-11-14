"""Storage for private conversation files; never exposed through MEDIA_URL."""

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class CommunicationPrivateStorage(FileSystemStorage):
    def __init__(self):
        super().__init__(location=str(settings.BASE_DIR / "private_media" / "communications"), base_url=None)

    def url(self, name):
        raise ValueError("Conversation attachments do not have public URLs.")


private_storage = CommunicationPrivateStorage()
