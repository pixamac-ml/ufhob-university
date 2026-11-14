from datetime import datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from accounts.models import Profile
from academics.models import AcademicClass, AcademicScheduleEvent, AcademicYear, EC, LessonLog, Semester, UE
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.models import DirectorTeacherAssignment
from portal.services.director.teacher_assignment_service import build_teacher_service_monitoring_context
from students.models import TeacherAttendance


User = get_user_model()


class TeacherServiceMonitoringTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe service", code="SVC", slug="annexe-service")
        self.other_branch = Branch.objects.create(name="Annexe isolee", code="ISO", slug="annexe-isolee")
        cycle = Cycle.objects.create(name="Cycle service", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplome service", level="superieur")
        filiere = Filiere.objects.create(name="Filiere service")
        programme = Programme.objects.create(
            title="Programme service", filiere=filiere, cycle=cycle,
            diploma_awarded=diploma, duration_years=3,
            short_description="Suivi", description="Suivi du service enseignant.",
        )
        today = timezone.localdate()
        self.year = AcademicYear.objects.create(
            name="2044-2045", start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=30), is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=programme, branch=self.branch, academic_year=self.year,
            level="L1", study_level="LICENCE", validation_threshold=Decimal("10.00"), is_active=True,
        )
        semester = Semester.objects.create(academic_class=self.academic_class, number=1)
        ue = UE.objects.create(semester=semester, code="SVC101", title="Fondamentaux")
        self.ec = EC.objects.create(ue=ue, title="Pedagogie", credit_required=Decimal("3"), coefficient=Decimal("2"))
        self.director = self._user("svc_director", "director_of_studies", self.branch)
        self.teacher = self._user("svc_teacher", "teacher", self.branch)
        self.other_teacher = self._user("svc_other_teacher", "teacher", self.other_branch)

    def _user(self, username, position, branch):
        user = User.objects.create_user(username=username, password="pass1234")
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.position = position
        profile.branch = branch
        profile.save(update_fields=["position", "branch", "updated_at"])
        return user

    def _event(self, *, start, end):
        return AcademicScheduleEvent.objects.create(
            title="Cours de pedagogie", event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class, ec=self.ec, teacher=self.teacher,
            branch=self.branch, academic_year=self.year,
            start_datetime=start, end_datetime=end,
            status=AcademicScheduleEvent.STATUS_PLANNED,
            created_by=self.director, updated_by=self.director,
        )

    def test_validated_service_uses_exact_lesson_duration_and_flags_missing_evidence(self):
        DirectorTeacherAssignment.objects.create(
            branch=self.branch, teacher=self.teacher,
            scope_type=DirectorTeacherAssignment.SCOPE_EC,
            academic_class=self.academic_class, ec=self.ec,
            room_label="Salle 1", planned_hours=Decimal("20"), created_by=self.director,
        )
        today = timezone.localdate()
        start = timezone.make_aware(datetime.combine(today - timedelta(days=2), time(8, 0)))
        event = self._event(start=start, end=start + timedelta(hours=2))
        TeacherAttendance.objects.create(
            teacher=self.teacher, schedule_event=event, date=today - timedelta(days=2),
            status=TeacherAttendance.STATUS_PRESENT, course_delivered=True,
            recorded_by=self.director, branch=self.branch,
        )
        LessonLog.objects.create(
            academic_class=self.academic_class, ec=self.ec, teacher=self.teacher,
            schedule_event=event, date=today - timedelta(days=2), start_time=time(8, 0),
            end_time=time(9, 30), status=LessonLog.STATUS_DONE, content="Cours realise.",
            branch=self.branch, created_by=self.teacher, validated_by=self.director,
        )
        missing_start = timezone.make_aware(datetime.combine(today - timedelta(days=1), time(10, 0)))
        self._event(start=missing_start, end=missing_start + timedelta(hours=2))

        report = build_teacher_service_monitoring_context(branch=self.branch, academic_year=self.year)

        self.assertEqual(len(report["teacher_service_rows"]), 1)
        row = report["teacher_service_rows"][0]
        self.assertEqual(row["assigned_hours"], Decimal("20"))
        self.assertEqual(row["scheduled_hours"], Decimal("4"))
        self.assertEqual(row["actual_hours"], Decimal("1.5"))
        self.assertEqual(row["validated_hours"], Decimal("1.5"))
        self.assertEqual(row["payable_hours"], Decimal("1.5"))
        self.assertEqual(row["missing_evidence_count"], 1)
        self.assertFalse(any(item["kind"] == "absence" for item in row["anomalies"]))

    def test_branch_scope_excludes_other_teacher(self):
        report = build_teacher_service_monitoring_context(branch=self.branch, academic_year=self.year)
        self.assertEqual([row["teacher"].id for row in report["teacher_service_rows"]], [self.teacher.id])
