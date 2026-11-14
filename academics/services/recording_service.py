"""Private Backblaze B2 handling for BigBlueButton recording metadata and files."""

from __future__ import annotations

from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from academics.models import AcademicEnrollment, OnlineClassRecording
from academics.storage import build_recording_download_url, get_recording_s3_client
from academics.services.online_class_service import BigBlueButtonProvider


def _path_part(value: object, fallback: str) -> str:
    cleaned = slugify(str(value or ""))[:80]
    return cleaned or fallback


def build_recording_object_key(*, recording: OnlineClassRecording) -> str:
    """Build a deterministic key from server-side academic context only."""
    event = recording.event
    return str(
        PurePosixPath(
            "recordings",
            _path_part(event.academic_year.name, f"year-{event.academic_year_id}"),
            _path_part(event.branch.code or event.branch.name, f"branch-{event.branch_id}"),
            f"class-{event.academic_class_id}",
            f"event-{event.pk}",
            _path_part(recording.provider_recording_id, f"recording-{recording.pk}"),
            "recording.mp4",
        )
    )


def sync_bbb_recordings(*, event, provider=None) -> list[OnlineClassRecording]:
    """Persist BBB discovery state without claiming its playback URL is a media file."""
    provider = provider or BigBlueButtonProvider()
    if not isinstance(provider, BigBlueButtonProvider):
        raise ValidationError("La synchronisation des enregistrements est disponible pour BigBlueButton uniquement.")

    synced = []
    for item in provider.get_recordings(event=event):
        defaults = {
            "event": event,
            "meeting_id": item["meeting_id"],
            "title": item["name"],
            "provider_playback_url": item["playback_url"],
            "duration_seconds": int(item["duration_seconds"]) if item["duration_seconds"] else None,
            "provider_metadata": {"provider_state": item["state"]},
        }
        recording, _ = OnlineClassRecording.objects.update_or_create(
            provider=provider.name,
            provider_recording_id=item["recording_id"],
            defaults=defaults,
        )
        synced.append(recording)
    return synced


def upload_recording_stream(*, recording: OnlineClassRecording, stream, content_type="video/mp4", size_bytes=None, checksum=""):
    """Copy an already-obtained provider media stream to the private B2 bucket."""
    if not getattr(settings, "B2_RECORDINGS_CONFIGURED", False):
        raise ValidationError("Le stockage privé des enregistrements n'est pas configuré.")
    if recording.status == OnlineClassRecording.STATUS_TRANSFERRED and recording.object_key:
        return recording

    object_key = build_recording_object_key(recording=recording)
    try:
        get_recording_s3_client().upload_fileobj(
            stream,
            settings.B2_RECORDINGS_BUCKET,
            object_key,
            ExtraArgs={"ContentType": content_type or "video/mp4"},
        )
    except Exception as exc:
        OnlineClassRecording.objects.filter(pk=recording.pk).update(
            status=OnlineClassRecording.STATUS_FAILED,
            failure_reason="Le transfert vers le stockage privé a échoué.",
        )
        raise ValidationError("Le transfert de l'enregistrement a échoué.") from exc

    with transaction.atomic():
        recording = OnlineClassRecording.objects.select_for_update().get(pk=recording.pk)
        recording.storage_backend = "backblaze_b2_s3"
        recording.bucket = settings.B2_RECORDINGS_BUCKET
        recording.object_key = object_key
        recording.size_bytes = size_bytes
        recording.mime_type = content_type or "video/mp4"
        recording.checksum = checksum
        recording.status = OnlineClassRecording.STATUS_TRANSFERRED
        recording.transferred_at = timezone.now()
        recording.failure_reason = ""
        recording.save()
    return recording


def _is_authorized_for_recording(*, user, recording: OnlineClassRecording) -> bool:
    event = recording.event
    if user.pk in {event.teacher_id, event.original_teacher_id}:
        return True
    return AcademicEnrollment.objects.filter(
        student=user,
        academic_class=event.academic_class,
        academic_year=event.academic_year,
        branch=event.branch,
        is_active=True,
        status=AcademicEnrollment.STATUS_ACTIVE,
    ).exists()


def recording_status_presentation(recording: OnlineClassRecording) -> dict[str, str]:
    if recording.status == OnlineClassRecording.STATUS_TRANSFERRED and recording.object_key:
        return {"label": "Disponible", "tone": "success"}
    if recording.status == OnlineClassRecording.STATUS_FAILED:
        return {"label": "Échec / indisponible", "tone": "danger"}
    if recording.status == OnlineClassRecording.STATUS_TRANSFER_PENDING:
        return {"label": "Transfert vers stockage", "tone": "warning"}
    return {"label": "Disponible chez le fournisseur", "tone": "info"}


def get_recording_download_url_for_user(*, user, recording: OnlineClassRecording, force_download=False) -> str:
    """Authorize against academic context before minting a short-lived B2 URL."""
    recording = OnlineClassRecording.objects.select_related(
        "event__academic_class", "event__academic_year", "event__branch"
    ).get(pk=recording.pk)
    if not _is_authorized_for_recording(user=user, recording=recording):
        raise PermissionDenied("Vous n'êtes pas autorisé à consulter cet enregistrement.")
    is_teacher = user.pk in {recording.event.teacher_id, recording.event.original_teacher_id}
    if not is_teacher and recording.published_at is None:
        raise PermissionDenied("Cet enregistrement n'est pas encore publié.")
    if recording.status != OnlineClassRecording.STATUS_TRANSFERRED or not recording.object_key:
        raise ValidationError("Cet enregistrement est encore en cours de traitement.")
    return build_recording_download_url(
        object_key=recording.object_key,
        force_download=force_download,
    )
