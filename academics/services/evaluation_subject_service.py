"""Authoritative workflow for teacher-authored evaluation subjects.

`EvaluationRequirement` remains the single persistent subject source. A row
created by a campaign is a requested subject; a row without a campaign is a
subject prepared early by its teacher. Both share the same review rules.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from pathlib import Path

from academics.models import AcademicScheduleEvent, EC, EvaluationCampaign, EvaluationRequirement
from accounts.models import Profile
from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from portal.models import DirectorTeacherAssignment


def _validate_subject_file(subject_file):
    """Keep the Exam Studio upload policy server-side, not only in HTML."""
    if subject_file is None:
        return
    if Path(subject_file.name or "").suffix.lower() not in {".pdf", ".doc", ".docx"}:
        raise ValidationError("Le fichier du sujet doit être un PDF ou un document Word.")


def teacher_subject_contexts(*, teacher, branch):
    """Return only class/EC pairs genuinely assigned to a teacher."""
    contexts = {}
    scheduled = AcademicScheduleEvent.objects.filter(
        branch=branch, teacher=teacher, is_active=True, academic_class__is_active=True,
    ).select_related("academic_class", "ec")
    for event in scheduled:
        contexts[(event.academic_class_id, event.ec_id)] = {
            "academic_class": event.academic_class, "ec": event.ec,
        }

    assignments = DirectorTeacherAssignment.objects.filter(
        branch=branch,
        teacher=teacher,
        status=DirectorTeacherAssignment.STATUS_ACTIVE,
        is_active=True,
        academic_class__is_active=True,
    ).select_related("academic_class", "ec")
    for assignment in assignments:
        if not assignment.academic_class_id:
            continue
        ecs = [assignment.ec] if assignment.ec_id else EC.objects.filter(
            ue__semester__academic_class=assignment.academic_class,
        ).exclude(structure_status=EC.STRUCTURE_ARCHIVED)
        for ec in ecs:
            contexts[(assignment.academic_class_id, ec.id)] = {
                "academic_class": assignment.academic_class, "ec": ec,
            }
    return sorted(
        contexts.values(),
        key=lambda item: (item["academic_class"].display_name, item["ec"].title),
    )


def _teacher_subject_queryset(*, teacher, branch):
    return (
        EvaluationRequirement.objects.select_related(
            "campaign", "campaign__calendar_entry", "academic_class",
            "academic_class__academic_year", "ec__ue__semester", "attached_evaluation",
        )
        .filter(responsible_teacher=teacher, academic_class__branch=branch)
        .filter(
            Q(campaign__isnull=True)
            | ~Q(campaign__status__in=[EvaluationCampaign.STATUS_CANCELLED, EvaluationCampaign.STATUS_CLOSED])
        )
    )


def get_teacher_requirement(*, teacher, branch, requirement_id):
    requirement = _teacher_subject_queryset(teacher=teacher, branch=branch).filter(pk=requirement_id).first()
    if requirement is None:
        raise ValidationError("Ce sujet n'est pas disponible pour votre compte.")
    if requirement.submission_status == EvaluationRequirement.SUBMISSION_VALIDATED:
        raise ValidationError("Ce sujet est valide et ne peut plus etre modifie par l'enseignant.")
    return requirement


def _notify_directors(*, requirement, actor):
    recipients = Profile.objects.filter(
        branch=requirement.academic_class.branch,
        position="director_of_studies",
        user__is_active=True,
    ).select_related("user")
    for profile in recipients:
        NotificationBus.notify(
            recipient=profile.user,
            actor=actor,
            event_type="evaluation_subject_submitted",
            title="Sujet d'evaluation a controler",
            body=f"{requirement.ec.title} · {requirement.academic_class.display_name}",
            source_app="academics",
            priority=NotificationMessage.PRIORITY_HIGH,
            metadata={"requirement_id": requirement.id, "campaign_id": requirement.campaign_id},
            legacy_source="academics.evaluation_subject",
            legacy_object_id=f"requirement:{requirement.id}:submission:{requirement.submitted_at:%Y%m%d%H%M%S}",
        )


def _write_teacher_subject(*, requirement, title, content, subject_file, notes, submit, questions=None, duration_minutes=None):
    requirement.subject_title = (title or "").strip()
    requirement.subject_content = content or ""
    requirement.notes = (notes or "").strip()
    if questions is not None:
        requirement.subject_questions = questions
    if duration_minutes is not None:
        requirement.duration_minutes = duration_minutes
    if subject_file is not None:
        _validate_subject_file(subject_file)
        requirement.subject_file = subject_file
    if submit:
        has_structured_questions = any(
            str(question.get("body") or "").strip()
            for question in (requirement.subject_questions or [])
            if isinstance(question, dict)
        )
        if not (requirement.subject_file or requirement.subject_content.strip() or has_structured_questions):
            raise ValidationError("Ajoutez un fichier, des consignes ou au moins une question avant de transmettre le sujet.")
        requirement.submission_status = EvaluationRequirement.SUBMISSION_SUBMITTED
        requirement.subject_status = EvaluationRequirement.SUBJECT_RECEIVED
        requirement.submitted_at = timezone.now()
        requirement.received_at = requirement.submitted_at
        requirement.received_by = requirement.responsible_teacher
    else:
        requirement.submission_status = EvaluationRequirement.SUBMISSION_DRAFT
    requirement.full_clean()
    requirement.save()
    return requirement


@transaction.atomic
def create_teacher_subject(*, teacher, branch, academic_class_id, ec_id, title, content, subject_file=None, notes="", submit=False, questions=None, duration_minutes=None):
    allowed = {
        (item["academic_class"].id, item["ec"].id): item
        for item in teacher_subject_contexts(teacher=teacher, branch=branch)
    }
    context = allowed.get((academic_class_id, ec_id))
    if context is None:
        raise ValidationError("Vous ne pouvez preparer un sujet que pour une classe et une matiere qui vous sont affectees.")
    requirement = EvaluationRequirement(
        academic_class=context["academic_class"], ec=context["ec"], responsible_teacher=teacher,
    )
    requirement = _write_teacher_subject(
        requirement=requirement, title=title, content=content, subject_file=subject_file,
        notes=notes, submit=submit, questions=questions, duration_minutes=duration_minutes,
    )
    if submit:
        _notify_directors(requirement=requirement, actor=teacher)
    return requirement


@transaction.atomic
def save_teacher_subject(*, teacher, branch, requirement_id, title, content, subject_file=None, notes="", submit=False, questions=None, duration_minutes=None):
    requirement = get_teacher_requirement(teacher=teacher, branch=branch, requirement_id=requirement_id)
    requirement = _write_teacher_subject(
        requirement=requirement, title=title, content=content, subject_file=subject_file,
        notes=notes, submit=submit, questions=questions, duration_minutes=duration_minutes,
    )
    if submit:
        _notify_directors(requirement=requirement, actor=teacher)
    return requirement


@transaction.atomic
def attach_subject_to_evaluation(*, reviewer, branch, requirement_id, evaluation_id):
    """Attach a submitted subject to one compatible scheduled examination."""
    requirement = EvaluationRequirement.objects.select_for_update().select_related(
        "academic_class", "ec"
    ).filter(
        pk=requirement_id,
        academic_class__branch=branch,
        attached_evaluation__isnull=True,
    ).filter(
        Q(submission_status__in=[
            EvaluationRequirement.SUBMISSION_SUBMITTED,
            EvaluationRequirement.SUBMISSION_VALIDATED,
        ]) | Q(subject_status=EvaluationRequirement.SUBJECT_RECEIVED)
    ).first()
    evaluation = AcademicScheduleEvent.objects.select_for_update().filter(
        pk=evaluation_id,
        branch=branch,
        event_type__in=[AcademicScheduleEvent.EVENT_TYPE_EXAM, AcademicScheduleEvent.EVENT_TYPE_PRACTICAL],
        is_active=True,
    ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED).first()
    if requirement is None or evaluation is None:
        raise ValidationError("Sujet ou epreuve introuvable dans cette annexe.")
    if (
        evaluation.academic_class_id != requirement.academic_class_id
        or evaluation.ec_id != requirement.ec_id
    ):
        raise ValidationError(
            "Le sujet doit être rattaché à une épreuve de la même classe et de la même matière."
        )
    if EvaluationRequirement.objects.filter(attached_evaluation=evaluation).exists():
        raise ValidationError("Une autre version de sujet est deja rattachee a cette epreuve.")
    requirement.attached_evaluation = evaluation
    requirement.full_clean()
    requirement.save(update_fields=["attached_evaluation"])
    return requirement


@transaction.atomic
def review_evaluation_subject(*, reviewer, requirement, decision, review_notes=""):
    if requirement.submission_status not in {
        EvaluationRequirement.SUBMISSION_SUBMITTED,
        EvaluationRequirement.SUBMISSION_RETURNED,
    }:
        raise ValidationError("Seul un sujet soumis peut etre controle.")
    if decision not in {EvaluationRequirement.SUBMISSION_VALIDATED, EvaluationRequirement.SUBMISSION_RETURNED}:
        raise ValidationError("Decision de controle invalide.")
    review_notes = (review_notes or "").strip()
    if decision == EvaluationRequirement.SUBMISSION_RETURNED and not review_notes:
        raise ValidationError("Indiquez le motif du retour afin que l'enseignant puisse corriger son sujet.")
    requirement.submission_status = decision
    requirement.review_notes = review_notes
    requirement.reviewed_at = timezone.now()
    requirement.reviewed_by = reviewer
    requirement.full_clean()
    requirement.save()
    if requirement.responsible_teacher_id:
        NotificationBus.notify(
            recipient=requirement.responsible_teacher,
            actor=reviewer,
            event_type="evaluation_subject_reviewed",
            title="Sujet d'evaluation controle",
            body=("Votre sujet est valide." if decision == EvaluationRequirement.SUBMISSION_VALIDATED else "Votre sujet doit etre corrige."),
            source_app="academics",
            priority=NotificationMessage.PRIORITY_HIGH,
            metadata={"requirement_id": requirement.id, "decision": decision},
            legacy_source="academics.evaluation_subject",
            legacy_object_id=f"requirement:{requirement.id}:review:{requirement.reviewed_at:%Y%m%d%H%M%S}",
        )
    return requirement
