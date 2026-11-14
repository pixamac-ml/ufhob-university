"""S3/B2 direct-upload authorization without exposing storage credentials."""

from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError


def build_private_object_key(*, lesson_id: int, filename: str) -> str:
    return f"lessons/{lesson_id}/{uuid4().hex}{Path(filename or 'media').suffix.lower()}"


def build_direct_upload_authorization(*, lesson_id: int, filename: str, content_type: str):
    if not getattr(settings, "COURSE_MEDIA_S3_CONFIGURED", False):
        raise ValidationError("Le dépôt direct vidéo sera disponible après configuration du stockage B2.")
    import boto3
    key = build_private_object_key(lesson_id=lesson_id, filename=filename)
    client = boto3.client("s3", endpoint_url=settings.COURSE_MEDIA_S3_ENDPOINT_URL, aws_access_key_id=settings.COURSE_MEDIA_S3_ACCESS_KEY, aws_secret_access_key=settings.COURSE_MEDIA_S3_SECRET_KEY, region_name=settings.COURSE_MEDIA_S3_REGION)
    post = client.generate_presigned_post(Bucket=settings.COURSE_MEDIA_S3_BUCKET, Key=key, Fields={"Content-Type": content_type}, Conditions=[{"Content-Type": content_type}, ["content-length-range", 1, settings.COURSE_MEDIA_MAX_UPLOAD_BYTES]], ExpiresIn=settings.COURSE_MEDIA_UPLOAD_URL_SECONDS)
    return {"object_key": key, "upload": post}
