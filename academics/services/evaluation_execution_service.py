"""Execution réelle des épreuves et certification des surveillants externes."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from academics.models import (
    AcademicEnrollment,
    AcademicScheduleEvent,
    EvaluationProctor,
    EvaluationProctorAssignment,
    EvaluationScriptBatch,
)
from students.models import Student, StudentAttendance
from accounts.scoping import require_object_scope


def _event_for_branch(*, event_id, branch):
    event = AcademicScheduleEvent.objects.select_for_update(of=("self",)).filter(
        pk=event_id,
        branch=branch,
        evaluation_campaign__isnull=False,
        event_type__in=(
            AcademicScheduleEvent.EVENT_TYPE_EXAM,
            AcademicScheduleEvent.EVENT_TYPE_PRACTICAL,
        ),
    ).first()
    if event is None:
        raise ValidationError("Épreuve introuvable dans cette annexe.")
    return event


@transaction.atomic
def record_exam_attendance(*, actor, branch, event_id, attendance_by_student):
    """Enregistre les présences connues pour une épreuve et synchronise les copies attendues."""
    event = _event_for_branch(event_id=event_id, branch=branch)
    require_object_scope(event, user=actor)
    enrollments = list(
        AcademicEnrollment.objects.select_related("student")
        .filter(
            academic_class=event.academic_class,
            academic_year=event.academic_year,
            branch=branch,
            status=AcademicEnrollment.STATUS_ACTIVE,
            is_active=True,
        )
    )
    student_profiles = {
        item.user_id: item
        for item in Student.objects.filter(user_id__in=[enrollment.student_id for enrollment in enrollments])
    }
    allowed_statuses = dict(StudentAttendance.STATUS_CHOICES)
    event_date = timezone.localtime(event.start_datetime).date()
    recorded = 0
    for enrollment in enrollments:
        raw_status = attendance_by_student.get(str(enrollment.student_id))
        if raw_status not in allowed_statuses:
            continue
        student = student_profiles.get(enrollment.student_id)
        if student is None:
            continue
        attendance, _ = StudentAttendance.objects.select_for_update(of=("self",)).get_or_create(
            student=student,
            schedule_event=event,
            defaults={
                "academic_class": event.academic_class,
                "date": event_date,
                "status": raw_status,
                "recorded_by": actor,
                "branch": branch,
            },
        )
        if attendance.status != raw_status:
            attendance.status = raw_status
            attendance.arrival_time = None
            attendance.recorded_by = actor
            attendance.save(update_fields=["status", "arrival_time", "recorded_by", "updated_at"])
        recorded += 1

    present_count = StudentAttendance.objects.filter(
        schedule_event=event,
        status__in=(StudentAttendance.STATUS_PRESENT, StudentAttendance.STATUS_LATE),
    ).count()
    batch, _ = EvaluationScriptBatch.objects.select_for_update(of=("self",)).get_or_create(event=event)
    batch.expected_count = present_count
    batch.save(update_fields=["expected_count"])
    return {"event": event, "recorded": recorded, "present_count": present_count}


@transaction.atomic
def record_proctor_service(*, actor, branch, assignment_id, present, actual_started_at=None, actual_ended_at=None, observations=""):
    assignment = (
        EvaluationProctorAssignment.objects.select_for_update(of=("self",))
        .select_related("event", "proctor")
        .filter(pk=assignment_id, event__branch=branch, event__evaluation_campaign__isnull=False)
        .first()
    )
    if assignment is None:
        raise ValidationError("Affectation de surveillant introuvable dans cette annexe.")
    require_object_scope(assignment.event, user=actor)
    if assignment.certified_at:
        raise ValidationError("Un service déjà certifié ne peut plus être modifié.")
    if assignment.service_completed:
        raise ValidationError("Le service déjà constaté ne peut plus être modifié silencieusement.")
    if actual_started_at and actual_ended_at and actual_ended_at <= actual_started_at:
        raise ValidationError("La fin effective doit suivre le début effectif.")
    assignment.present = present
    assignment.signed_at = timezone.now() if present else None
    assignment.actual_started_at = actual_started_at if present else None
    assignment.actual_ended_at = actual_ended_at if present else None
    assignment.service_completed = bool(present and actual_started_at and actual_ended_at)
    assignment.observations = (observations or "").strip()
    assignment.validated_by = actor
    assignment.validated_at = timezone.now()
    assignment.full_clean()
    assignment.save()
    return assignment


@transaction.atomic
def certify_external_proctor_service(*, actor, branch, assignment_id):
    """Certifie un service externe réellement fait et le remet à la caisse comme dépense à payer."""
    assignment = (
        EvaluationProctorAssignment.objects.select_for_update(of=("self",))
        .select_related("event", "event__evaluation_campaign", "proctor")
        .filter(pk=assignment_id, event__branch=branch, event__evaluation_campaign__isnull=False)
        .first()
    )
    if assignment is None:
        raise ValidationError("Affectation de surveillant introuvable dans cette annexe.")
    require_object_scope(assignment.event, user=actor)
    if assignment.proctor.kind != EvaluationProctor.KIND_EXTERNAL:
        raise ValidationError("Le personnel interne ne génère pas de vacation financière.")
    if assignment.expense_id:
        raise ValidationError("Cette vacation a déjà été certifiée et transmise à la Gestionnaire.")
    if not (assignment.present and assignment.service_completed and assignment.actual_started_at and assignment.actual_ended_at):
        raise ValidationError("Confirmez d'abord le service réellement effectué avec ses heures effectives.")
    if assignment.proctor.hourly_rate <= 0:
        raise ValidationError("Le tarif horaire du surveillant externe doit être renseigné avant certification.")

    elapsed_seconds = (assignment.actual_ended_at - assignment.actual_started_at).total_seconds()
    certified_hours = (Decimal(str(elapsed_seconds)) / Decimal("3600")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if certified_hours <= 0:
        raise ValidationError("La durée certifiée doit être strictement positive.")
    certified_amount = int(certified_hours * assignment.proctor.hourly_rate)

    from accounts.models import BranchExpense
    from accounts.services.accounting_documents import ensure_expense_reference

    expense = BranchExpense.objects.create(
        branch=branch,
        title=f"Vacation de surveillance — {assignment.proctor.display_name}",
        category=BranchExpense.CATEGORY_EXAM_INVIGILATION,
        amount=certified_amount,
        expense_date=timezone.localtime(assignment.event.start_datetime).date(),
        supplier=assignment.proctor.display_name,
        status=BranchExpense.STATUS_SUBMITTED,
        created_by=actor,
        notes=(
            f"Service certifié par le Directeur des Études pour {assignment.event.title}. "
            f"Session : {assignment.event.evaluation_campaign.title}. "
            f"{certified_hours} h × {assignment.proctor.hourly_rate} FCFA/h."
        ),
    )
    ensure_expense_reference(expense)
    assignment.certified_hours = certified_hours
    assignment.certified_rate = assignment.proctor.hourly_rate
    assignment.certified_amount = certified_amount
    assignment.certified_by = actor
    assignment.certified_at = timezone.now()
    assignment.expense = expense
    assignment.full_clean()
    assignment.save()
    return assignment
