from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.scoping import object_in_scope
from academics.models import (
    AcademicScheduleEvent,
    AcademicScheduleExecutionLog,
    CourseSessionAssistSession,
    CourseSessionAuditLog,
    LessonLog,
)
from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from students.models import TeacherAttendance

User = get_user_model()


SCHEDULED = "scheduled"
IN_PROGRESS = "in_progress"
ENDED = "ended"
JOURNAL_PENDING = "journal_pending"
JOURNAL_SUBMITTED = "journal_submitted"
SERVICE_VALIDATED = "service_validated"
REVIEW_REQUIRED = "review_required"
READY_FOR_PAYMENT = "ready_for_payment"
CANCELLED = "cancelled"

MANAGER_POSITIONS = {"branch_manager", "annex_manager"}
SUPERVISOR_POSITIONS = {"academic_supervisor"}
CONTROL_POSITIONS = MANAGER_POSITIONS | SUPERVISOR_POSITIONS | {"director_of_studies"}

EXCEPTION_REASON_SUPERVISOR_UNAVAILABLE = "supervisor_unavailable"
EXCEPTION_REASON_IMMEDIATE_PAYMENT = "immediate_payment"
EXCEPTION_REASON_DIRECTLY_OBSERVED = "directly_observed"
EXCEPTION_REASON_OTHER = "other"
EXCEPTION_REASONS = {
    EXCEPTION_REASON_SUPERVISOR_UNAVAILABLE,
    EXCEPTION_REASON_IMMEDIATE_PAYMENT,
    EXCEPTION_REASON_DIRECTLY_OBSERVED,
    EXCEPTION_REASON_OTHER,
}


@dataclass(frozen=True)
class CheckInResult:
    attendance: TeacherAttendance
    effective_status: str
    starts_at: object


def _position(user) -> str:
    from accounts.models import InstitutionalProfile, Profile

    institutional = InstitutionalProfile.objects.filter(user_id=user.pk).values_list("position", flat=True).first()
    if institutional:
        return str(institutional)
    return str(Profile.objects.filter(user_id=user.pk).values_list("position", flat=True).first() or "")


def _ensure_event_scope(user, event):
    if not object_in_scope(event, user=user):
        raise PermissionDenied("Cette seance est hors de votre perimetre ecole/campus.")


def _ensure_teacher(user, event):
    if not user.is_authenticated or event.teacher_id != user.pk:
        raise PermissionDenied("Seul l'enseignant affecte peut agir sur cette seance.")
    _ensure_event_scope(user, event)


def _ensure_position(user, event, allowed_positions):
    if not user.is_authenticated or (not user.is_superuser and _position(user) not in allowed_positions):
        raise PermissionDenied("Vous n'etes pas autorise a effectuer cette action.")
    _ensure_event_scope(user, event)


def _audit(*, event, action, actor=None, lesson_log=None, reason="", metadata=None, event_key=None):
    defaults = {
        "event": event,
        "lesson_log": lesson_log,
        "actor": actor,
        "action": action,
        "reason": reason,
        "metadata": metadata or {},
    }
    if event_key:
        row, created = CourseSessionAuditLog.objects.get_or_create(event_key=event_key, defaults=defaults)
        return row, created
    return CourseSessionAuditLog.objects.create(**defaults), True


def _lesson_log_for(event):
    return event.lesson_logs.order_by("-created_at", "-id").first()


@transaction.atomic
def create_assisted_session(*, event, manager, now=None):
    now = now or timezone.now()
    event = AcademicScheduleEvent.objects.select_for_update().select_related("teacher", "branch").get(pk=event.pk)
    _ensure_position(manager, event, MANAGER_POSITIONS)
    if event.status == AcademicScheduleEvent.STATUS_CANCELLED:
        raise ValidationError("Cette seance est annulee.")
    if now < event.start_datetime:
        raise ValidationError("Le cahier assiste ne peut pas etre ouvert avant le debut de la seance.")
    CourseSessionAssistSession.objects.filter(
        event=event,
        manager=manager,
        used_at__isnull=True,
        expires_at__gt=now,
    ).update(expires_at=now)
    raw_token, token_hash = CourseSessionAssistSession.issue_token()
    session = CourseSessionAssistSession.objects.create(
        event=event,
        manager=manager,
        token_hash=token_hash,
        expires_at=now + timedelta(minutes=20),
    )
    return session, raw_token


def get_effective_status(event, *, now=None, lesson_log=None):
    """Etat calcule; les horaires restent fiables meme sans scheduler."""
    now = now or timezone.now()
    lesson_log = lesson_log if lesson_log is not None else _lesson_log_for(event)
    if event.status == AcademicScheduleEvent.STATUS_CANCELLED:
        return CANCELLED
    if lesson_log is not None:
        if lesson_log.status == LessonLog.STATUS_RETURNED:
            return REVIEW_REQUIRED
        if lesson_log.status == LessonLog.STATUS_DONE and lesson_log.service_validated_at:
            return READY_FOR_PAYMENT
        if lesson_log.status == LessonLog.STATUS_SUBMITTED:
            return JOURNAL_SUBMITTED
    if event.status == AcademicScheduleEvent.STATUS_COMPLETED:
        return JOURNAL_PENDING
    if now >= event.end_datetime:
        return JOURNAL_PENDING if lesson_log is None or lesson_log.status == LessonLog.STATUS_PLANNED else ENDED
    attendance = event.teacher_attendances.order_by("-created_at").first()
    if now >= event.start_datetime and attendance and attendance.checked_in_at:
        return IN_PROGRESS
    return SCHEDULED


def teacher_check_in(*, event, teacher, now=None, request_metadata=None):
    now = now or timezone.now()
    probe = AcademicScheduleEvent.objects.select_related("teacher", "branch").get(pk=event.pk)
    _ensure_teacher(teacher, probe)
    if probe.status == AcademicScheduleEvent.STATUS_CANCELLED:
        raise ValidationError("Cette seance est annulee.")
    if now >= probe.end_datetime:
        _audit(
            event=probe,
            action=CourseSessionAuditLog.ACTION_REVIEW_REQUIRED,
            actor=teacher,
            reason="checkin_after_scheduled_end",
            metadata=request_metadata,
            event_key=f"course:{probe.pk}:late-checkin-review",
        )
        raise ValidationError("La seance est terminee. Une regularisation administrative est requise.")
    return _teacher_check_in_atomic(
        event=probe,
        teacher=teacher,
        now=now,
        request_metadata=request_metadata,
    )


@transaction.atomic
def _teacher_check_in_atomic(*, event, teacher, now, request_metadata=None):
    event = AcademicScheduleEvent.objects.select_for_update().select_related("teacher", "branch").get(pk=event.pk)
    _ensure_teacher(teacher, event)
    if event.event_type not in {AcademicScheduleEvent.EVENT_TYPE_COURSE, AcademicScheduleEvent.EVENT_TYPE_PRACTICAL}:
        raise ValidationError("Le pointage enseignant est reserve aux seances de cours.")
    if event.status == AcademicScheduleEvent.STATUS_CANCELLED:
        raise ValidationError("Cette seance est annulee.")
    if now >= event.end_datetime:
        _audit(
            event=event,
            action=CourseSessionAuditLog.ACTION_REVIEW_REQUIRED,
            actor=teacher,
            reason="checkin_after_scheduled_end",
            metadata=request_metadata,
            event_key=f"course:{event.pk}:late-checkin-review",
        )
        raise ValidationError("La seance est terminee. Une regularisation administrative est requise.")

    late_minutes = max(0, int((now - event.start_datetime).total_seconds() // 60))
    attendance, created = TeacherAttendance.objects.select_for_update().get_or_create(
        teacher=teacher,
        schedule_event=event,
        defaults={
            "date": timezone.localtime(event.start_datetime).date(),
            "status": TeacherAttendance.STATUS_LATE if late_minutes else TeacherAttendance.STATUS_PRESENT,
            "arrival_time": timezone.localtime(now).time() if late_minutes else None,
            "checked_in_at": now,
            "late_minutes": late_minutes,
            "recorded_by": teacher,
            "branch": event.branch,
        },
    )
    if not created and attendance.checked_in_at is None:
        attendance.status = TeacherAttendance.STATUS_LATE if late_minutes else TeacherAttendance.STATUS_PRESENT
        attendance.arrival_time = timezone.localtime(now).time() if late_minutes else None
        attendance.checked_in_at = now
        attendance.late_minutes = late_minutes
        attendance.recorded_by = teacher
        attendance.save(update_fields=[
            "status", "arrival_time", "checked_in_at", "late_minutes", "recorded_by", "updated_at"
        ])

    if now >= event.start_datetime:
        execution = event.execution_logs.select_for_update().filter(is_completed=False).order_by("-created_at").first()
        if execution is None:
            AcademicScheduleExecutionLog.objects.create(
                event=event,
                started_at=now,
                actual_teacher=teacher,
            )
        elif execution.started_at is None:
            execution.started_at = now
            execution.actual_teacher = teacher
            execution.save(update_fields=["started_at", "actual_teacher"])
        if event.status != AcademicScheduleEvent.STATUS_ONGOING:
            event.status = AcademicScheduleEvent.STATUS_ONGOING
            event.updated_by = teacher
            event.save(update_fields=["status", "updated_by", "updated_at"])

    _audit(
        event=event,
        action=CourseSessionAuditLog.ACTION_CHECKED_IN,
        actor=teacher,
        metadata={"late_minutes": late_minutes, **(request_metadata or {})},
        event_key=f"course:{event.pk}:teacher-checkin",
    )
    return CheckInResult(
        attendance=attendance,
        effective_status=get_effective_status(event, now=now),
        starts_at=event.start_datetime,
    )


@transaction.atomic
def end_teacher_session(*, event, teacher, now=None, end_reason=AcademicScheduleExecutionLog.END_REASON_TEACHER, request_metadata=None):
    now = now or timezone.now()
    event = AcademicScheduleEvent.objects.select_for_update().select_related("teacher", "branch").get(pk=event.pk)
    _ensure_teacher(teacher, event)
    if now < event.start_datetime:
        raise ValidationError("La seance n'a pas encore commence.")
    attendance = event.teacher_attendances.filter(teacher=teacher, checked_in_at__isnull=False).first()
    if attendance is None:
        raise ValidationError("Le pointage enseignant est requis avant la cloture.")
    execution = event.execution_logs.select_for_update().order_by("-created_at").first()
    if execution is None:
        execution = AcademicScheduleExecutionLog.objects.create(
            event=event,
            started_at=attendance.checked_in_at,
            ended_at=now,
            actual_teacher=teacher,
            is_completed=True,
            completed_by=teacher,
            end_reason=end_reason,
        )
    elif not execution.is_completed:
        execution.ended_at = now
        execution.end_reason = end_reason
        execution.is_completed = True
        execution.completed_by = teacher
        execution.actual_teacher = execution.actual_teacher or teacher
        execution.full_clean()
        execution.save(update_fields=[
            "ended_at", "end_reason", "is_completed", "completed_by", "actual_teacher"
        ])
    event.status = AcademicScheduleEvent.STATUS_COMPLETED
    event.updated_by = teacher
    event.save(update_fields=["status", "updated_by", "updated_at"])
    _audit(
        event=event,
        action=CourseSessionAuditLog.ACTION_ENDED,
        actor=teacher,
        reason=end_reason,
        metadata=request_metadata,
        event_key=f"course:{event.pk}:ended",
    )
    return execution


@transaction.atomic
def record_journal_submission(*, lesson_log, teacher, assisted_by=None, now=None, request_metadata=None):
    now = now or timezone.now()
    lesson_log = LessonLog.objects.select_for_update().select_related("schedule_event", "teacher").get(pk=lesson_log.pk)
    if lesson_log.teacher_id != teacher.pk:
        raise PermissionDenied("Le cahier doit etre certifie par l'enseignant de la seance.")
    if lesson_log.schedule_event_id is None:
        raise ValidationError("Le cahier doit etre rattache a une seance programmee.")
    _ensure_teacher(teacher, lesson_log.schedule_event)
    lesson_log.status = LessonLog.STATUS_SUBMITTED
    lesson_log.certified_at = lesson_log.certified_at or now
    lesson_log.submitted_at = lesson_log.submitted_at or now
    if assisted_by is not None:
        _ensure_position(assisted_by, lesson_log.schedule_event, MANAGER_POSITIONS)
        lesson_log.assisted_by = assisted_by
    lesson_log.save(update_fields=[
        "status", "certified_at", "submitted_at", "assisted_by", "updated_at"
    ])
    _audit(
        event=lesson_log.schedule_event,
        lesson_log=lesson_log,
        action=CourseSessionAuditLog.ACTION_JOURNAL_SUBMITTED,
        actor=teacher,
        metadata={"assisted_by_id": lesson_log.assisted_by_id, **(request_metadata or {})},
        event_key=f"course:{lesson_log.schedule_event_id}:journal-submitted",
    )
    return lesson_log


@transaction.atomic
def validate_service_by_supervisor(*, lesson_log, supervisor, now=None, request_metadata=None):
    now = now or timezone.now()
    lesson_log = LessonLog.objects.select_for_update().select_related("schedule_event").get(pk=lesson_log.pk)
    if lesson_log.schedule_event_id is None:
        raise ValidationError("Le cahier doit etre rattache a une seance programmee.")
    _ensure_position(supervisor, lesson_log.schedule_event, SUPERVISOR_POSITIONS)
    if lesson_log.status != LessonLog.STATUS_SUBMITTED:
        raise ValidationError("Seul un cahier soumis peut etre valide.")
    attendance = lesson_log.schedule_event.teacher_attendances.filter(
        teacher=lesson_log.teacher,
        status__in=[TeacherAttendance.STATUS_PRESENT, TeacherAttendance.STATUS_LATE],
        course_delivered=True,
    ).first()
    if attendance is None:
        raise ValidationError("La presence et le service observe doivent etre confirmes avant validation.")
    lesson_log.status = LessonLog.STATUS_DONE
    lesson_log.validated_by = supervisor
    lesson_log.service_validated_at = now
    lesson_log.validation_mode = LessonLog.VALIDATION_SUPERVISOR
    lesson_log.validation_reason = ""
    lesson_log.validation_comment = ""
    lesson_log.reviewed_by = supervisor
    lesson_log.reviewed_at = now
    lesson_log.save(update_fields=[
        "status", "validated_by", "service_validated_at", "validation_mode",
        "validation_reason", "validation_comment", "reviewed_by", "reviewed_at", "updated_at",
    ])
    _record_ready_for_payment(lesson_log, supervisor, request_metadata)
    return lesson_log


@transaction.atomic
def validate_service_exception(*, lesson_log, manager, reason, comment, now=None, request_metadata=None):
    now = now or timezone.now()
    reason = (reason or "").strip()
    comment = (comment or "").strip()
    if reason not in EXCEPTION_REASONS:
        raise ValidationError({"reason": "Selectionnez un motif de validation exceptionnelle valide."})
    if not comment:
        raise ValidationError({"comment": "Le commentaire est obligatoire."})
    lesson_log = LessonLog.objects.select_for_update().select_related("schedule_event").get(pk=lesson_log.pk)
    if lesson_log.schedule_event_id is None:
        raise ValidationError("Le cahier doit etre rattache a une seance programmee.")
    _ensure_position(manager, lesson_log.schedule_event, MANAGER_POSITIONS)
    if lesson_log.status != LessonLog.STATUS_SUBMITTED:
        raise ValidationError("Seul un cahier soumis et non encore valide peut utiliser ce recours.")
    lesson_log.status = LessonLog.STATUS_DONE
    lesson_log.validated_by = manager
    lesson_log.service_validated_at = now
    lesson_log.validation_mode = LessonLog.VALIDATION_MANAGER_EXCEPTION
    lesson_log.validation_reason = reason
    lesson_log.validation_comment = comment
    lesson_log.reviewed_by = manager
    lesson_log.reviewed_at = now
    lesson_log.review_comment = comment
    lesson_log.save(update_fields=[
        "status", "validated_by", "service_validated_at", "validation_mode",
        "validation_reason", "validation_comment", "reviewed_by", "reviewed_at",
        "review_comment", "updated_at",
    ])
    _audit(
        event=lesson_log.schedule_event,
        lesson_log=lesson_log,
        action=CourseSessionAuditLog.ACTION_VALIDATION_EXCEPTION,
        actor=manager,
        reason=reason,
        metadata={"comment": comment, **(request_metadata or {})},
        event_key=f"course:{lesson_log.schedule_event_id}:validation-exception",
    )
    _record_ready_for_payment(lesson_log, manager, request_metadata)
    _notify_controllers(
        event=lesson_log.schedule_event,
        actor=manager,
        event_type="course_service_validation_exception",
        title="Validation exceptionnelle de seance",
        body=f"Une validation exceptionnelle a ete effectuee pour {lesson_log.ec}.",
        positions={"director_of_studies"},
    )
    return lesson_log


@transaction.atomic
def report_service_anomaly(*, lesson_log, supervisor, reason, now=None, request_metadata=None):
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Le motif de l'anomalie est obligatoire."})
    now = now or timezone.now()
    lesson_log = LessonLog.objects.select_for_update().select_related("schedule_event").get(pk=lesson_log.pk)
    if lesson_log.schedule_event_id is None:
        raise ValidationError("Le cahier doit etre rattache a une seance programmee.")
    _ensure_position(supervisor, lesson_log.schedule_event, SUPERVISOR_POSITIONS)
    if lesson_log.status != LessonLog.STATUS_SUBMITTED:
        raise ValidationError("Seul un cahier soumis peut etre signale.")
    lesson_log.status = LessonLog.STATUS_RETURNED
    lesson_log.reviewed_by = supervisor
    lesson_log.reviewed_at = now
    lesson_log.review_comment = reason
    lesson_log.validated_by = None
    lesson_log.service_validated_at = None
    lesson_log.validation_mode = ""
    lesson_log.save(update_fields=[
        "status", "reviewed_by", "reviewed_at", "review_comment", "validated_by",
        "service_validated_at", "validation_mode", "updated_at",
    ])
    _audit(
        event=lesson_log.schedule_event,
        lesson_log=lesson_log,
        action=CourseSessionAuditLog.ACTION_REVIEW_REQUIRED,
        actor=supervisor,
        reason=reason,
        metadata=request_metadata,
        event_key=f"course:{lesson_log.schedule_event_id}:review:{lesson_log.pk}:{lesson_log.updated_at.isoformat()}",
    )
    _notify_controllers(
        event=lesson_log.schedule_event,
        actor=supervisor,
        event_type="course_review_required",
        title="Anomalie de seance a examiner",
        body=f"Une anomalie a ete signalee pour {lesson_log.ec}.",
        positions={"director_of_studies", *MANAGER_POSITIONS},
    )
    return lesson_log


def _record_ready_for_payment(lesson_log, actor, request_metadata=None):
    event = lesson_log.schedule_event
    _audit(
        event=event,
        lesson_log=lesson_log,
        action=CourseSessionAuditLog.ACTION_SERVICE_VALIDATED,
        actor=actor,
        reason=lesson_log.validation_mode,
        metadata=request_metadata,
        event_key=f"course:{event.pk}:service-validated",
    )
    _audit(
        event=event,
        lesson_log=lesson_log,
        action=CourseSessionAuditLog.ACTION_READY_FOR_PAYMENT,
        actor=actor,
        reason=lesson_log.validation_mode,
        event_key=f"course:{event.pk}:ready-for-payment",
    )
    _notify_controllers(
        event=event,
        actor=actor,
        event_type="course_ready_for_payment",
        title="Seance prete pour les honoraires",
        body=f"Le service de {lesson_log.teacher.get_full_name() or lesson_log.teacher.username} pour {lesson_log.ec} est valide.",
        positions=MANAGER_POSITIONS,
    )


def _controller_candidates(event, positions):
    candidates = User.objects.filter(
        is_active=True,
    ).filter(
        Q(profile__position__in=positions) | Q(institutional_profile__position__in=positions)
    ).filter(
        Q(profile__branch=event.branch)
        | Q(institutional_profile__branch=event.branch)
        | Q(institutional_profile__school_id=event.academic_class.programme.school_id)
        | Q(institutional_profile__access_scope="GLOBAL")
    ).distinct()
    return [user for user in candidates if object_in_scope(event, user=user)]


def _notify_controllers(*, event, actor, event_type, title, body, positions):
    for recipient in _controller_candidates(event, positions):
        NotificationBus.notify(
            recipient=recipient,
            actor=actor,
            event_type=event_type,
            title=title,
            body=body,
            source_app="academics",
            priority=NotificationMessage.PRIORITY_HIGH,
            metadata={
                "target_type": "course_session",
                "event_id": event.pk,
                "school_id": event.academic_class.programme.school_id,
                "branch_id": event.branch_id,
            },
            legacy_source="academic_schedule_event",
            legacy_object_id=str(event.pk),
        )


def check_missing_checkins(*, now=None):
    now = now or timezone.now()
    grace = timedelta(minutes=int(getattr(settings, "COURSE_CHECKIN_GRACE_MINUTES", 10)))
    events = AcademicScheduleEvent.objects.select_related(
        "teacher", "branch", "academic_class__programme__school", "ec"
    ).filter(
        is_active=True,
        event_type__in=[AcademicScheduleEvent.EVENT_TYPE_COURSE, AcademicScheduleEvent.EVENT_TYPE_PRACTICAL],
        status__in=[AcademicScheduleEvent.STATUS_PLANNED, AcademicScheduleEvent.STATUS_ONGOING],
        start_datetime__lte=now - grace,
        end_datetime__gt=now,
    ).exclude(teacher_attendances__checked_in_at__isnull=False)
    notified = 0
    for event in events:
        _, created = _audit(
            event=event,
            action=CourseSessionAuditLog.ACTION_CHECKIN_MISSING,
            reason="grace_expired",
            metadata={"grace_minutes": int(grace.total_seconds() // 60)},
            event_key=f"course:{event.pk}:checkin-missing",
        )
        if not created:
            continue
        teacher_name = event.teacher.get_full_name() or event.teacher.username
        _notify_controllers(
            event=event,
            actor=None,
            event_type="course_checkin_missing",
            title="Pointage de seance manquant",
            body=f"{teacher_name} est programme en {event.ec}, mais aucun pointage n'a ete enregistre.",
            positions=CONTROL_POSITIONS,
        )
        notified += 1
    return notified


def notify_courses_ending_soon(*, now=None):
    now = now or timezone.now()
    warning = timedelta(minutes=int(getattr(settings, "COURSE_END_WARNING_MINUTES", 15)))
    events = AcademicScheduleEvent.objects.select_related("teacher", "academic_class__programme__school").filter(
        is_active=True,
        status=AcademicScheduleEvent.STATUS_ONGOING,
        end_datetime__gt=now,
        end_datetime__lte=now + warning,
        teacher_attendances__checked_in_at__isnull=False,
    ).distinct()
    notified = 0
    for event in events:
        _, created = _audit(
            event=event,
            action=CourseSessionAuditLog.ACTION_ENDING_SOON,
            event_key=f"course:{event.pk}:ending-soon",
            metadata={"warning_minutes": int(warning.total_seconds() // 60)},
        )
        if not created:
            continue
        NotificationBus.notify(
            recipient=event.teacher,
            event_type="course_ending_soon",
            title="Fin de seance proche",
            body=f"Votre cours {event.ec} se termine dans environ {int(warning.total_seconds() // 60)} minutes.",
            source_app="academics",
            metadata={"target_type": "course_session", "event_id": event.pk},
            legacy_source="academic_schedule_event",
            legacy_object_id=str(event.pk),
        )
        notified += 1
    return notified


@transaction.atomic
def close_due_sessions(*, now=None):
    now = now or timezone.now()
    event_ids = list(AcademicScheduleEvent.objects.filter(
        is_active=True,
        status=AcademicScheduleEvent.STATUS_ONGOING,
        end_datetime__lte=now,
    ).values_list("pk", flat=True))
    closed = 0
    for event in AcademicScheduleEvent.objects.select_for_update().filter(pk__in=event_ids):
        execution = event.execution_logs.select_for_update().filter(is_completed=False).order_by("-created_at").first()
        if execution:
            execution.ended_at = event.end_datetime
            execution.end_reason = AcademicScheduleExecutionLog.END_REASON_SCHEDULED
            execution.is_completed = True
            execution.full_clean()
            execution.save(update_fields=["ended_at", "end_reason", "is_completed"])
        event.status = AcademicScheduleEvent.STATUS_COMPLETED
        event.save(update_fields=["status", "updated_at"])
        _audit(
            event=event,
            action=CourseSessionAuditLog.ACTION_ENDED,
            reason=AcademicScheduleExecutionLog.END_REASON_SCHEDULED,
            event_key=f"course:{event.pk}:ended",
        )
        closed += 1
    return closed
