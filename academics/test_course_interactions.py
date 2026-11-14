from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from academics.models import AcademicClass, AcademicYear, EC, ECChapter, ECContent, Semester, UE
from academics.services.course_interaction_service import (
    create_student_answer,
    create_student_question,
    create_teacher_answer,
    student_questions,
)
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.models import DirectorTeacherAssignment


class CourseInteractionServiceTests(TestCase):
    def setUp(self):
        self.student = get_user_model().objects.create_user(username="interaction_student", password="pass")
        self.teacher = get_user_model().objects.create_user(username="interaction_teacher", password="pass")
        self.branch = Branch.objects.create(name="Annexe interactions", code="INT", slug="annexe-interactions")
        programme = Programme.objects.create(
            title="Programme interactions", filiere=Filiere.objects.create(name="Filiere interactions"),
            cycle=Cycle.objects.create(name="Cycle interactions", theme="accent", min_duration_years=1, max_duration_years=3),
            diploma_awarded=Diploma.objects.create(name="Diplome interactions", level="superieur"), duration_years=3,
        )
        year = AcademicYear.objects.create(name="2040-2041", start_date=date(2040, 10, 1), end_date=date(2041, 7, 1), is_active=True)
        self.academic_class = AcademicClass.objects.create(programme=programme, branch=self.branch, academic_year=year, level="L1")
        semester = Semester.objects.create(academic_class=self.academic_class, number=1, total_required_credits=Decimal("3"))
        self.ec = EC.objects.create(ue=UE.objects.create(semester=semester, code="INT101", title="Interactions"), title="Éthique", credit_required=Decimal("3"), coefficient=Decimal("1"))
        self.lesson = ECContent.objects.create(chapter=ECChapter.objects.create(ec=self.ec, title="Chapitre", order=1), title="Leçon", content_type="text", text_content="Texte", status="published")
        self.enrollment = SimpleNamespace(academic_year=year, academic_class=self.academic_class, branch=self.branch)

    def test_question_is_scoped_and_teacher_response_is_server_identified(self):
        question = create_student_question(student=self.student, enrollment=self.enrollment, ec=self.ec, lesson=self.lesson, title="Question", body="Contenu")
        DirectorTeacherAssignment.objects.create(
            branch=self.branch, teacher=self.teacher, scope_type=DirectorTeacherAssignment.SCOPE_EC,
            academic_class=self.academic_class, semester=self.ec.ue.semester, ue=self.ec.ue, ec=self.ec,
            room_label="A1", planned_hours=Decimal("2"), status=DirectorTeacherAssignment.STATUS_ACTIVE,
        )
        answer = create_teacher_answer(teacher=self.teacher, question=question, body="Réponse")
        self.assertTrue(answer.is_teacher_response)
        self.assertEqual(student_questions(enrollment=self.enrollment, ec=self.ec).get(), question)

    def test_student_cannot_answer_outside_his_academic_context(self):
        question = create_student_question(student=self.student, enrollment=self.enrollment, ec=self.ec, lesson=self.lesson, title="Question", body="Contenu")
        foreign_enrollment = SimpleNamespace(academic_year=self.enrollment.academic_year, academic_class=AcademicClass.objects.create(programme=self.academic_class.programme, branch=self.branch, academic_year=self.enrollment.academic_year, level="L2"), branch=self.branch)
        with self.assertRaises(PermissionDenied):
            create_student_answer(student=self.student, enrollment=foreign_enrollment, question=question, body="Interdit")
