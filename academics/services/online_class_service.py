"""Provider-independent online classrooms for scheduled academic events.

ESFE remains authoritative for scheduling, identity and permissions. Providers
only supply the virtual room attached to an existing ``AcademicScheduleEvent``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import hmac
import logging
import math
import re
import socket
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicEnrollment, AcademicScheduleEvent
from notifier.models import NotificationMessage
from notifier.services import NotificationBus


BBB_ROLE_MODERATOR = "MODERATOR"
BBB_ROLE_VIEWER = "VIEWER"
MAX_BBB_RESPONSE_BYTES = 1024 * 1024
BBB_SERVICE_UNAVAILABLE_MESSAGE = (
    "Le service de classe virtuelle est momentanement indisponible. "
    "Veuillez reessayer dans quelques instants."
)
logger = logging.getLogger(__name__)


class OnlineClassNotReady(ValidationError):
    """The user is authorized, but the moderator has not started the room."""


class BigBlueButtonProviderError(ValidationError):
    """A safe, user-facing BBB failure with a non-sensitive diagnostic reason."""

    def __init__(self, reason: str):
        super().__init__(BBB_SERVICE_UNAVAILABLE_MESSAGE)
        self.reason = reason


def get_online_session_access_state(*, event, now=None) -> dict:
    """Return the one temporal rule shared by dashboards and BBB actions.

    Authorization is deliberately not decided here: callers must first prove
    teacher assignment or student enrollment.  The optional bypass is limited
    to local development and changes *only* the temporal rule.
    """
    now = now or timezone.now()
    bypass_enabled = bool(
        getattr(settings, "DEBUG", False)
        and getattr(settings, "ONLINE_CLASSROOM_TIME_BYPASS", False)
    )
    # La fin programmee est une barriere absolue, y compris en environnement
    # local : aucun bypass ne doit recreer une URL de participation apres elle.
    if now >= event.end_datetime:
        return {
            "is_available": False,
            "state": "ended",
            "label": "Seance terminee",
            "detail": "La fenetre de classe virtuelle est fermee.",
        }
    if bypass_enabled:
        return {
            "is_available": True,
            "state": "test_bypass",
            "label": "Acces test temporaire",
            "detail": "Bypass temporel local actif.",
        }
    if now < event.start_datetime:
        return {
            "is_available": False,
            "state": "upcoming",
            "label": "Disponible a partir de " + event.start_datetime.strftime("%H:%M"),
            "detail": "La classe virtuelle ouvrira a l'heure prevue.",
        }
    return {
        "is_available": True,
        "state": "active",
        "label": "En cours",
        "detail": "La classe virtuelle est disponible.",
    }


def ensure_online_session_time_access(*, event, now=None) -> None:
    access = get_online_session_access_state(event=event, now=now)
    if not access["is_available"]:
        raise ValidationError(access["label"] + ". " + access["detail"])


@dataclass(frozen=True)
class ProviderMeetingStatus:
    meeting_id: str
    status: str
    is_running: bool
    participant_count: int = 0
    create_time: str = ""


@dataclass(frozen=True)
class OnlineClassPreparation:
    event_id: int
    provider: str
    status: str
    participant_user_ids: tuple[int, ...]
    join_url: str
    role: str = BBB_ROLE_MODERATOR


class OnlineClassroomProvider(ABC):
    """Minimal provider contract consumed by dashboards and domain services."""

    name: str

    @abstractmethod
    def create_or_get(self, *, event) -> ProviderMeetingStatus:
        raise NotImplementedError

    @abstractmethod
    def get_status(self, *, event) -> ProviderMeetingStatus:
        raise NotImplementedError

    @abstractmethod
    def build_join_url(self, *, event, user, role: str) -> str:
        raise NotImplementedError

    def end_meeting(self, *, event) -> ProviderMeetingStatus:
        raise ValidationError("Ce fournisseur ne permet pas de terminer la reunion depuis ESFE.")


class BigBlueButtonProvider(OnlineClassroomProvider):
    """Server-side adapter for the signed BigBlueButton XML API."""

    name = "bigbluebutton"

    def __init__(self, *, api_url=None, secret=None, timeout=None):
        self._api_url = (api_url if api_url is not None else getattr(settings, "BBB_API_URL", "")).strip()
        self._secret = (secret if secret is not None else getattr(settings, "BBB_SECRET", "")).strip()
        self._timeout = timeout if timeout is not None else getattr(settings, "BBB_API_TIMEOUT", 10)

    @property
    def is_configured(self) -> bool:
        return bool(self._api_url and self._secret)

    def _api_base_url(self) -> str:
        if not self.is_configured:
            raise BigBlueButtonProviderError("configuration")
        raw_url = self._api_url.rstrip("/")
        parsed = urlsplit(raw_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise BigBlueButtonProviderError("configuration")
        if raw_url.endswith("/bigbluebutton/api") or raw_url.endswith("/api"):
            return raw_url
        if raw_url.endswith("/bigbluebutton"):
            return f"{raw_url}/api"
        # Hosted BBB accounts may expose a tenant URL such as
        # ``.../bigbluebutton/<account>/``.  It already contains the BBB
        # application path, so append only the API segment.
        if "/bigbluebutton/" in parsed.path:
            return f"{raw_url}/api"
        return f"{raw_url}/bigbluebutton/api"

    def build_api_url(self, call_name: str, params: dict[str, object]) -> str:
        """Build a signed URL without ever exposing the shared secret itself."""
        query = urlencode([(key, str(value)) for key, value in params.items()])
        checksum = hashlib.sha1(
            f"{call_name}{query}{self._secret}".encode("utf-8")
        ).hexdigest()
        separator = "&" if query else ""
        return f"{self._api_base_url()}/{call_name}?{query}{separator}checksum={checksum}"

    def _api_call(self, call_name: str, params: dict[str, object]):
        request = Request(
            self.build_api_url(call_name, params),
            headers={"Accept": "application/xml", "User-Agent": "UFHOB-Core/BBB"},
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                payload = response.read(MAX_BBB_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, socket.timeout, OSError) as exc:
            # Never log the signed request URL: it contains a checksum.
            logger.warning("BBB API call %s failed: %s", call_name, type(exc).__name__)
            raise BigBlueButtonProviderError("network") from exc
        if len(payload) > MAX_BBB_RESPONSE_BYTES:
            logger.warning("BBB API call %s returned an oversized response", call_name)
            raise BigBlueButtonProviderError("response")
        try:
            root = ElementTree.fromstring(payload)
        except ElementTree.ParseError as exc:
            logger.warning("BBB API call %s returned invalid XML", call_name)
            raise BigBlueButtonProviderError("response") from exc
        if (root.findtext("returncode") or "").upper() != "SUCCESS":
            message_key = (root.findtext("messageKey") or "apiError").strip()
            logger.warning("BBB API call %s was refused (%s)", call_name, message_key)
            reason = "authentication" if any(
                token in message_key.lower() for token in ("checksum", "auth", "security")
            ) else "provider"
            raise BigBlueButtonProviderError(reason)
        return root

    def check_connectivity(self) -> dict[str, str | bool]:
        """Perform one signed, read-only BBB API call without creating a room."""
        if not self.is_configured:
            return {"ok": False, "reason": "configuration"}
        try:
            # A deterministic non-meeting verifies the expected BBB XML API,
            # signature/checksum and provider reachability without side effects.
            self._api_call("isMeetingRunning", {"meetingID": "ufhob-healthcheck"})
        except BigBlueButtonProviderError as exc:
            return {"ok": False, "reason": exc.reason}
        return {"ok": True, "reason": ""}

    def _meeting_id(self, event) -> str:
        if getattr(event, "online_provider", "") == self.name and getattr(event, "external_meeting_id", ""):
            return event.external_meeting_id
        configured_prefix = getattr(settings, "BBB_MEETING_ID_PREFIX", "ufhob")
        prefix = re.sub(r"[^A-Za-z0-9_-]", "_", configured_prefix).strip("_")[:24] or "ufhob"
        deployment_key = hashlib.sha256(
            getattr(settings, "BASE_URL", "ufhob").encode("utf-8")
        ).hexdigest()[:8]
        return f"{prefix}_{deployment_key}_event_{event.pk}"

    def _meeting_password(self, meeting_id: str, role: str) -> str:
        """Derive a server-only BBB password for one room role."""
        if role not in {BBB_ROLE_MODERATOR, BBB_ROLE_VIEWER}:
            raise ValidationError("Le role de classe virtuelle est invalide.")
        digest = hmac.new(
            self._secret.encode("utf-8"),
            f"{meeting_id}:{role}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return digest[:32]

    @staticmethod
    def _meeting_name(event) -> str:
        ec_title = getattr(getattr(event, "ec", None), "title", "Cours")
        class_name = getattr(getattr(event, "academic_class", None), "display_name", "Classe UFHOB")
        return f"UFHOB - {ec_title} - {class_name}"[:255]

    @staticmethod
    def _meeting_ended_url(event) -> str:
        """Return participants to the authenticated UFHOB workflow after BBB ends.

        BBB calls this URL when the *meeting* ends.  The view still confirms
        provider state server-side, so a participant leaving temporarily can
        never close the academic session merely through a browser redirect.
        """
        from django.urls import reverse

        return f"{settings.BASE_URL}{reverse('accounts_portal:online_session_ended', args=[event.pk])}"

    def create_or_get(self, *, event) -> ProviderMeetingStatus:
        meeting_id = self._meeting_id(event)
        scheduled_end = getattr(event, "end_datetime", None)
        remaining_minutes = None
        if scheduled_end is not None:
            remaining_minutes = math.ceil((scheduled_end - timezone.now()).total_seconds() / 60)
        # BBB's duration is a technical room lifetime, never a new academic
        # end time.  A late start therefore cannot shift the official session.
        nominal_duration = int(getattr(event, "duration_minutes", 60) or 60)
        duration = max(1, min(nominal_duration, remaining_minutes)) if remaining_minutes is not None else max(1, nominal_duration)
        root = self._api_call(
            "create",
            {
                "name": self._meeting_name(event),
                "meetingID": meeting_id,
                "attendeePW": self._meeting_password(meeting_id, BBB_ROLE_VIEWER),
                "moderatorPW": self._meeting_password(meeting_id, BBB_ROLE_MODERATOR),
                # Recording stays opt-in.  Current hosted BBB capabilities
                # must be verified before a recording is published or copied.
                "record": str(bool(getattr(settings, "ONLINE_CLASSROOM_RECORDING_ENABLED", False))).lower(),
                "autoStartRecording": str(bool(getattr(settings, "ONLINE_CLASSROOM_RECORDING_ENABLED", False))).lower(),
                "allowStartStopRecording": str(bool(getattr(settings, "ONLINE_CLASSROOM_RECORDING_ENABLED", False))).lower(),
                "duration": duration,
                "meetingExpireIfNoUserJoinedInMinutes": 30,
                "meetingExpireWhenLastUserLeftInMinutes": 5,
                "meetingEndedURL": self._meeting_ended_url(event),
                "meta_ufhob_event_id": event.pk,
            },
        )
        response_meeting_id = (root.findtext("meetingID") or meeting_id).strip()
        status = self.get_status_by_id(response_meeting_id)
        if status.is_running:
            return status
        return ProviderMeetingStatus(
            meeting_id=response_meeting_id,
            status="ready",
            is_running=False,
            create_time=(root.findtext("createTime") or "").strip(),
        )

    def get_status_by_id(self, meeting_id: str) -> ProviderMeetingStatus:
        running_root = self._api_call("isMeetingRunning", {"meetingID": meeting_id})
        is_running = (running_root.findtext("running") or "false").strip().lower() == "true"
        if not is_running:
            return ProviderMeetingStatus(meeting_id, "not_started", False)
        info_root = self._api_call("getMeetingInfo", {"meetingID": meeting_id})
        raw_count = (info_root.findtext("participantCount") or "0").strip()
        return ProviderMeetingStatus(
            meeting_id=meeting_id,
            status="running",
            is_running=True,
            participant_count=int(raw_count) if raw_count.isdigit() else 0,
            create_time=(info_root.findtext("createTime") or "").strip(),
        )

    def get_status(self, *, event) -> ProviderMeetingStatus:
        return self.get_status_by_id(self._meeting_id(event))

    def get_recordings(self, *, event) -> list[dict[str, str]]:
        """Read BBB recording metadata; BBB playback is not assumed downloadable."""
        meeting_id = self._meeting_id(event)
        root = self._api_call("getRecordings", {"meetingID": meeting_id})
        recordings = []
        for node in root.findall("./recordings/recording"):
            recording_id = (node.findtext("recordID") or "").strip()
            if not recording_id:
                continue
            playback_url = (node.findtext("./playback/format/url") or "").strip()
            raw_length = (node.findtext("playback/format/length") or "").strip()
            recordings.append(
                {
                    "recording_id": recording_id,
                    "meeting_id": (node.findtext("meetingID") or meeting_id).strip(),
                    "name": (node.findtext("name") or "").strip(),
                    "playback_url": playback_url,
                    "duration_seconds": raw_length if raw_length.isdigit() else "",
                    "state": (node.findtext("state") or "").strip(),
                }
            )
        return recordings

    def build_join_url(self, *, event, user, role: str) -> str:
        meeting_id = self._meeting_id(event)
        full_name = (user.get_full_name() or user.get_username()).strip()[:85]
        if not full_name:
            full_name = f"Utilisateur UFHOB {user.pk}"
        return self.build_api_url(
            "join",
            {
                "meetingID": meeting_id,
                "fullName": full_name,
                # BBB uses this password, rather than a caller-controlled
                # role parameter, to distinguish attendees and moderators.
                "password": self._meeting_password(meeting_id, role),
                "userID": f"ufhob_{user.pk}",
                "redirect": "true",
            },
        )

    def end_meeting(self, *, event) -> ProviderMeetingStatus:
        meeting_id = self._meeting_id(event)
        self._api_call(
            "end",
            {
                "meetingID": meeting_id,
                "password": self._meeting_password(meeting_id, BBB_ROLE_MODERATOR),
            },
        )
        return ProviderMeetingStatus(meeting_id, "ending", False)


class ExternalMeetingLinkProvider(OnlineClassroomProvider):
    """Compatibility adapter for already persisted non-BBB meeting links."""

    name = "external_link"

    @staticmethod
    def _link(event):
        link = (getattr(event, "meeting_link", "") or "").strip()
        if not link:
            raise ValidationError("Le lien de classe virtuelle externe n'est pas disponible.")
        return link

    def create_or_get(self, *, event) -> ProviderMeetingStatus:
        self._link(event)
        return ProviderMeetingStatus(str(event.pk), "ready", True)

    def get_status(self, *, event) -> ProviderMeetingStatus:
        return self.create_or_get(event=event)

    def build_join_url(self, *, event, user, role: str) -> str:
        return self._link(event)


class GoogleWorkspaceMeetingProvider(ExternalMeetingLinkProvider):
    """Compatibility name for pre-existing Google Workspace links."""

    name = "google_workspace"


def get_online_classroom_provider(*, event=None) -> OnlineClassroomProvider:
    provider_name = (getattr(event, "online_provider", "") or "").strip().lower()
    if not provider_name and getattr(event, "meeting_link", ""):
        provider_name = "external_link"
    if not provider_name:
        provider_name = getattr(settings, "ONLINE_CLASSROOM_PROVIDER", "bigbluebutton").strip().lower()
    if provider_name == "bigbluebutton":
        return BigBlueButtonProvider()
    if provider_name == "google_workspace":
        return GoogleWorkspaceMeetingProvider()
    if provider_name in {"external", "external_link"}:
        return ExternalMeetingLinkProvider()
    raise ValidationError(f"Le fournisseur de classe virtuelle '{provider_name}' n'est pas pris en charge.")


def get_online_session_participant_user_ids(*, event):
    """Return active students for exactly the event's academic context."""
    return tuple(
        AcademicEnrollment.objects.filter(
            academic_class=event.academic_class,
            academic_year=event.academic_year,
            branch=event.branch,
            is_active=True,
            status=AcademicEnrollment.STATUS_ACTIVE,
        ).values_list("student_id", flat=True)
    )


def get_teacher_online_session(*, teacher, branch, event_id):
    event = (
        AcademicScheduleEvent.objects.select_related(
            "academic_class", "academic_year", "branch", "teacher", "ec"
        )
        .filter(
            pk=event_id,
            teacher=teacher,
            branch=branch,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            is_active=True,
            is_online=True,
        )
        .exclude(status__in=[AcademicScheduleEvent.STATUS_DRAFT, AcademicScheduleEvent.STATUS_CANCELLED])
        .first()
    )
    if event is None:
        raise ValidationError("Cette seance en ligne n'est pas accessible pour cet enseignant.")
    return event


def get_student_online_session(*, student, event_id):
    event = (
        AcademicScheduleEvent.objects.select_related(
            "academic_class", "academic_year", "branch", "teacher", "ec"
        )
        .filter(
            pk=event_id,
            is_active=True,
            is_online=True,
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
        )
        .exclude(status__in=[AcademicScheduleEvent.STATUS_DRAFT, AcademicScheduleEvent.STATUS_CANCELLED])
        .first()
    )
    if event is None or not AcademicEnrollment.objects.filter(
        student=student,
        academic_class=event.academic_class,
        academic_year=event.academic_year,
        branch=event.branch,
        is_active=True,
        status=AcademicEnrollment.STATUS_ACTIVE,
    ).exists():
        raise ValidationError("Cette seance en ligne n'est pas accessible pour cet etudiant.")
    return event


def _persist_provider_status(*, event, provider, status):
    metadata = dict(event.provider_metadata or {})
    metadata[provider.name] = {
        "last_status": status.status,
        "participant_count": status.participant_count,
        "create_time": status.create_time,
    }
    event.online_provider = provider.name
    event.external_meeting_id = status.meeting_id
    event.meeting_status = status.status
    event.meeting_updated_at = timezone.now()
    event.provider_metadata = metadata
    if provider.name == BigBlueButtonProvider.name:
        # A BBB join URL is role- and user-specific and must never be persisted.
        event.meeting_link = ""
    if status.status in {"ready", "running"} and event.meeting_created_at is None:
        event.meeting_created_at = timezone.now()
    event.save(
        update_fields=[
            "online_provider",
            "external_meeting_id",
            "meeting_status",
            "meeting_created_at",
            "meeting_updated_at",
            "provider_metadata",
            "meeting_link",
            "updated_at",
        ]
    )


def notify_online_mode_change(*, event, actor):
    """Use the central notifier after the DE switches an existing session online."""
    recipients = [event.teacher_id, *get_online_session_participant_user_ids(event=event)]
    from django.contrib.auth import get_user_model

    for recipient in get_user_model().objects.filter(pk__in={recipient_id for recipient_id in recipients if recipient_id}):
        NotificationBus.notify(
            recipient=recipient,
            actor=actor,
            event_type="schedule_event_online",
            title="Seance basculee en ligne",
            body=f"{event.ec.title} - {event.academic_class.display_name} - {event.start_datetime:%d/%m %H:%M}",
            source_app="academics",
            priority=NotificationMessage.PRIORITY_HIGH,
            metadata={"event_id": event.id, "branch_id": event.branch_id},
            legacy_source="academics.schedule_event",
            legacy_object_id=f"event:{event.id}:online:{event.updated_at:%Y%m%d%H%M%S}",
        )


def prepare_teacher_online_session(*, teacher, branch, event_id, provider=None):
    """Idempotently create/recover the room and issue a MODERATOR join URL."""
    event = get_teacher_online_session(teacher=teacher, branch=branch, event_id=event_id)
    ensure_online_session_time_access(event=event)
    from academics.services.course_session_lifecycle import teacher_check_in

    teacher_check_in(event=event, teacher=teacher)
    participants = get_online_session_participant_user_ids(event=event)
    provider = provider or get_online_classroom_provider(event=event)
    status = provider.create_or_get(event=event)

    with transaction.atomic():
        event = (
            AcademicScheduleEvent.objects.select_for_update()
            .filter(
                pk=event_id,
                teacher=teacher,
                branch=branch,
                event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
                is_active=True,
                is_online=True,
            )
            .exclude(
                status__in=[
                    AcademicScheduleEvent.STATUS_DRAFT,
                    AcademicScheduleEvent.STATUS_CANCELLED,
                ]
            )
            .first()
        )
        if event is None:
            raise ValidationError(
                "L'affectation de cette seance a change. L'acces a la salle est refuse."
            )
        _persist_provider_status(event=event, provider=provider, status=status)

    return OnlineClassPreparation(
        event_id=event.id,
        provider=provider.name,
        status=status.status,
        participant_user_ids=participants,
        join_url=provider.build_join_url(
            event=event, user=teacher, role=BBB_ROLE_MODERATOR
        ),
    )


def end_teacher_online_session(*, teacher, branch, event_id, provider=None, now=None):
    """Close BBB when configured, then close the shared academic session."""
    event = get_teacher_online_session(teacher=teacher, branch=branch, event_id=event_id)
    provider = provider or get_online_classroom_provider(event=event)
    provider_status = None
    if not isinstance(provider, BigBlueButtonProvider) or provider.is_configured:
        try:
            provider_status = provider.end_meeting(event=event)
        except ValidationError:
            if isinstance(provider, BigBlueButtonProvider):
                raise
    from academics.services.course_session_lifecycle import end_teacher_session
    from academics.models import AcademicScheduleExecutionLog, CourseSessionAuditLog

    execution = end_teacher_session(
        event=event,
        teacher=teacher,
        now=now,
        end_reason=AcademicScheduleExecutionLog.END_REASON_TEACHER,
    )
    CourseSessionAuditLog.objects.get_or_create(
        event_key=f"course:{event.pk}:bbb-ended",
        defaults={
            "event": event,
            "actor": teacher,
            "action": CourseSessionAuditLog.ACTION_BBB_ENDED,
            "reason": "teacher",
            "metadata": {"provider": provider.name},
        },
    )
    return execution, provider_status


def get_teacher_online_session_join_url(*, teacher, branch, event_id, provider=None):
    """Join an already prepared room without allowing a client-selected role."""
    event = get_teacher_online_session(teacher=teacher, branch=branch, event_id=event_id)
    ensure_online_session_time_access(event=event)
    provider = provider or get_online_classroom_provider(event=event)
    status = provider.get_status(event=event)
    if not status.is_running:
        raise OnlineClassNotReady("La classe virtuelle n'est pas encore demarree.")
    event = get_teacher_online_session(
        teacher=teacher, branch=branch, event_id=event_id
    )
    _persist_provider_status(event=event, provider=provider, status=status)
    return provider.build_join_url(event=event, user=teacher, role=BBB_ROLE_MODERATOR)


def get_student_online_session_join_url(*, student, event_id, provider=None):
    """Issue a VIEWER URL only after enrollment and room status are verified."""
    event = get_student_online_session(student=student, event_id=event_id)
    ensure_online_session_time_access(event=event)
    provider = provider or get_online_classroom_provider(event=event)
    status = provider.get_status(event=event)
    if not status.is_running:
        raise OnlineClassNotReady(
            "Le cours en ligne n'a pas encore ete demarre par l'enseignant."
        )
    event = get_student_online_session(student=student, event_id=event_id)
    _persist_provider_status(event=event, provider=provider, status=status)
    return provider.build_join_url(event=event, user=student, role=BBB_ROLE_VIEWER)
