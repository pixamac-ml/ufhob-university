"""Private S3/B2 storage used by pedagogical resources and BBB recordings."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import FileSystemStorage


def _build_course_resource_storage():
    if getattr(settings, "COURSE_MEDIA_S3_CONFIGURED", False):
        from storages.backends.s3 import S3Storage

        class CoursePrivateS3Storage(S3Storage):
            bucket_name = settings.COURSE_MEDIA_S3_BUCKET
            endpoint_url = settings.COURSE_MEDIA_S3_ENDPOINT_URL
            access_key = settings.COURSE_MEDIA_S3_ACCESS_KEY
            secret_key = settings.COURSE_MEDIA_S3_SECRET_KEY
            region_name = settings.COURSE_MEDIA_S3_REGION
            default_acl = "private"
            querystring_auth = True
            querystring_expire = settings.COURSE_MEDIA_SIGNED_URL_SECONDS
            file_overwrite = False

        return CoursePrivateS3Storage()
    settings.COURSE_MEDIA_PRIVATE_ROOT.mkdir(parents=True, exist_ok=True)
    return FileSystemStorage(location=str(settings.COURSE_MEDIA_PRIVATE_ROOT))


course_resource_storage = _build_course_resource_storage()


def get_recording_s3_client():
    """Return the private B2 client only when recording storage is configured."""
    if not getattr(settings, "B2_RECORDINGS_CONFIGURED", False):
        raise ValidationError(
            "Le stockage privé des enregistrements n'est pas configuré. "
            "Vérifiez les variables B2_RECORDINGS_* sans les exposer."
        )
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.B2_RECORDINGS_ENDPOINT,
        region_name=settings.B2_RECORDINGS_REGION,
        aws_access_key_id=settings.B2_RECORDINGS_ACCESS_KEY_ID,
        aws_secret_access_key=settings.B2_RECORDINGS_SECRET_ACCESS_KEY,
    )


def build_recording_download_url(*, object_key: str, expires_in=None, force_download=False) -> str:
    """Issue a short-lived URL for one already-authorized private object."""
    if not object_key:
        raise ValueError("Une clé d'objet est requise pour générer l'accès temporaire.")
    client = get_recording_s3_client()
    lifetime = expires_in or settings.B2_RECORDINGS_SIGNED_URL_SECONDS
    try:
        params = {"Bucket": settings.B2_RECORDINGS_BUCKET, "Key": object_key}
        if force_download:
            params["ResponseContentDisposition"] = "attachment"
        return client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=max(1, int(lifetime)),
        )
    except Exception as exc:
        raise ValidationError(
            "L'accès temporaire à l'enregistrement est indisponible. Réessayez dans quelques instants."
        ) from exc
