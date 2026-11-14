from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q

from academics.models import AcademicEnrollment, AcademicScheduleEvent, ECPedagogicalAnswer, ECPedagogicalQuestion
from portal.models import DirectorTeacherAssignment
from notifier.realtime.service import send_to_user


def student_questions(*, enrollment, ec):
    return ECPedagogicalQuestion.objects.filter(
        academic_year=enrollment.academic_year,
        academic_class=enrollment.academic_class,
        branch=enrollment.branch,
        ec=ec,
        is_active=True,
    ).select_related("author", "lesson__chapter").annotate(answer_count=Count("answers"))


def teacher_can_access_question(*, teacher, question):
    if AcademicScheduleEvent.objects.filter(
        teacher=teacher, branch=question.branch, academic_year=question.academic_year,
        academic_class=question.academic_class, ec=question.ec, is_active=True,
    ).exclude(status__in=[AcademicScheduleEvent.STATUS_DRAFT, AcademicScheduleEvent.STATUS_CANCELLED]).exists():
        return True
    return DirectorTeacherAssignment.objects.filter(
        teacher=teacher,
        branch=question.branch,
        is_active=True,
        status=DirectorTeacherAssignment.STATUS_ACTIVE,
    ).filter(
        Q(scope_type=DirectorTeacherAssignment.SCOPE_EC, ec=question.ec)
        | Q(scope_type=DirectorTeacherAssignment.SCOPE_UE, ue=question.ec.ue)
        | Q(scope_type=DirectorTeacherAssignment.SCOPE_SEMESTER, semester=question.ec.ue.semester)
        | Q(scope_type=DirectorTeacherAssignment.SCOPE_CLASS, academic_class=question.academic_class)
    ).exists()


def _publish_interaction_event(*, question, actor_id, action):
    """Signal authorised recipients after commit; HTML remains served by Django."""
    student_ids = AcademicEnrollment.objects.filter(
        academic_year=question.academic_year,
        academic_class=question.academic_class,
        branch=question.branch,
        status=AcademicEnrollment.STATUS_ACTIVE,
        is_active=True,
    ).values_list("student_id", flat=True)
    assignments = DirectorTeacherAssignment.objects.filter(
        branch=question.branch,
        is_active=True,
        status=DirectorTeacherAssignment.STATUS_ACTIVE,
    )
    teacher_ids = assignments.filter(
        Q(scope_type=DirectorTeacherAssignment.SCOPE_EC, ec=question.ec)
        | Q(scope_type=DirectorTeacherAssignment.SCOPE_UE, ue=question.ec.ue)
        | Q(scope_type=DirectorTeacherAssignment.SCOPE_SEMESTER, semester=question.ec.ue.semester)
        | Q(scope_type=DirectorTeacherAssignment.SCOPE_CLASS, academic_class=question.academic_class)
    ).values_list("teacher_id", flat=True)
    recipient_ids = set(student_ids).union(teacher_ids)
    recipient_ids.update(AcademicScheduleEvent.objects.filter(
        branch=question.branch, academic_year=question.academic_year,
        academic_class=question.academic_class, ec=question.ec, is_active=True,
    ).exclude(status__in=[AcademicScheduleEvent.STATUS_DRAFT, AcademicScheduleEvent.STATUS_CANCELLED]).values_list("teacher_id", flat=True))
    recipient_ids.discard(actor_id)
    payload = {
        "type": "pedagogical.interaction",
        "action": action,
        "question_id": question.id,
        "ec_id": question.ec_id,
    }
    transaction.on_commit(lambda: [send_to_user(user_id, payload) for user_id in recipient_ids])


@transaction.atomic
def create_student_question(*, student, enrollment, ec, lesson, title, body):
    if lesson is not None and lesson.chapter.ec_id != ec.id:
        raise ValidationError("La leçon ne correspond pas à cette matière.")
    title, body = (title or "").strip(), (body or "").strip()
    if not title or not body:
        raise ValidationError("Le titre et la question sont obligatoires.")
    question = ECPedagogicalQuestion.objects.create(
        academic_year=enrollment.academic_year,
        academic_class=enrollment.academic_class,
        branch=enrollment.branch,
        ec=ec,
        lesson=lesson,
        author=student,
        title=title,
        body=body,
    )
    _publish_interaction_event(question=question, actor_id=student.id, action="question.created")
    return question


@transaction.atomic
def create_student_answer(*, student, enrollment, question, body):
    if not student_questions(enrollment=enrollment, ec=question.ec).filter(pk=question.pk).exists():
        raise PermissionDenied("Cette discussion n'est pas accessible.")
    body = (body or "").strip()
    if not body:
        raise ValidationError("La réponse est obligatoire.")
    answer = ECPedagogicalAnswer.objects.create(question=question, author=student, body=body)
    question.save(update_fields=["updated_at"])
    _publish_interaction_event(question=question, actor_id=student.id, action="answer.created")
    return answer


@transaction.atomic
def create_teacher_answer(*, teacher, question, body):
    if not teacher_can_access_question(teacher=teacher, question=question):
        raise PermissionDenied("Cette discussion ne concerne pas vos affectations.")
    body = (body or "").strip()
    if not body:
        raise ValidationError("La réponse est obligatoire.")
    answer = ECPedagogicalAnswer.objects.create(
        question=question,
        author=teacher,
        body=body,
        is_teacher_response=True,
    )
    question.save(update_fields=["updated_at"])
    _publish_interaction_event(question=question, actor_id=teacher.id, action="answer.created")
    return answer
