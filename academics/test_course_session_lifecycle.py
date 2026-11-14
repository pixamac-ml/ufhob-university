from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile, TeacherHonorariumEntry
from academics.models import (
    AcademicClass,
    AcademicScheduleEvent,
    AcademicYear,
    CourseSessionAuditLog,
    CourseSessionAssistSession,
    EC,
    LessonLog,
    Semester,
    UE,
)
from academics.services.course_session_lifecycle import (
    check_missing_checkins,
    create_assisted_session,
    end_teacher_session,
    get_effective_status,
    report_service_anomaly,
    teacher_check_in,
    validate_service_by_supervisor,
    validate_service_exception,
)
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from notifier.models import NotificationMessage
from students.models import TeacherAttendance

User = get_user_model()


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    COURSE_CHECKIN_GRACE_MINUTES=10,
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class CourseSessionLifecycleTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Campus cycle", code="CYC", slug="campus-cycle")
        self.other_branch = Branch.objects.create(name="Autre campus", code="CYX", slug="autre-campus-cycle")
        cycle = Cycle.objects.create(name="Cycle seance", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplome seance", level="superieur")
        filiere = Filiere.objects.create(name="Filiere seance")
        self.programme = Programme.objects.create(
            title="Programme seance",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="Test",
            description="Test cycle seance",
        )
        self.year = AcademicYear.objects.create(
            name="2047-2048",
            start_date=date(2047, 1, 1),
            end_date=date(2048, 12, 31),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.year,
            level="L1",
            validation_threshold=Decimal("10.00"),
        )
        semester = Semester.objects.create(academic_class=self.academic_class, number=1)
        ue = UE.objects.create(semester=semester, code="CYC101", title="Cycle")
        self.ec = EC.objects.create(ue=ue, title="Anatomie", credit_required=3, coefficient=2)
        self.director = self._user("cycle_director", "director_of_studies", self.branch)
        self.teacher = self._user("cycle_teacher", "teacher", self.branch)
        self.other_teacher = self._user("cycle_other_teacher", "teacher", self.branch)
        self.supervisor = self._user("cycle_supervisor", "academic_supervisor", self.branch)
        self.manager = self._user("cycle_manager", "branch_manager", self.branch)
        self.other_manager = self._user("cycle_other_manager", "branch_manager", self.other_branch)

    def _user(self, username, position, branch):
        user = User.objects.create_user(username=username, password="pass1234")
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.position = position
        profile.role = "teacher" if position == "teacher" else "executive"
        profile.branch = branch
        profile.employment_status = "active"
        profile.save()
        return user

    def _event(self, *, start, end, teacher=None, status=AcademicScheduleEvent.STATUS_PLANNED):
        return AcademicScheduleEvent.objects.create(
            title="Anatomie",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=teacher or self.teacher,
            branch=self.branch,
            academic_year=self.year,
            start_datetime=start,
            end_datetime=end,
            status=status,
            created_by=self.director,
            updated_by=self.director,
        )

    def _submitted_log(self, event):
        local_start = timezone.localtime(event.start_datetime)
        local_end = timezone.localtime(event.end_datetime)
        return LessonLog.objects.create(
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            schedule_event=event,
            date=local_start.date(),
            start_time=local_start.time(),
            end_time=local_end.time(),
            status=LessonLog.STATUS_SUBMITTED,
            content="Chapitre effectivement traite",
            branch=self.branch,
            created_by=self.teacher,
            certified_at=timezone.now(),
            submitted_at=timezone.now(),
        )

    def test_late_checkin_uses_server_time_without_shifting_schedule(self):
        now = timezone.now().replace(second=0, microsecond=0)
        start, end = now - timedelta(minutes=17), now + timedelta(minutes=103)
        event = self._event(start=start, end=end)

        result = teacher_check_in(event=event, teacher=self.teacher, now=now)

        event.refresh_from_db()
        self.assertEqual(result.attendance.checked_in_at, now)
        self.assertEqual(result.attendance.late_minutes, 17)
        self.assertEqual(event.start_datetime, start)
        self.assertEqual(event.end_datetime, end)
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_ONGOING)

    def test_early_checkin_records_presence_but_does_not_start_course(self):
        now = timezone.now()
        event = self._event(start=now + timedelta(minutes=15), end=now + timedelta(hours=2))

        result = teacher_check_in(event=event, teacher=self.teacher, now=now)

        event.refresh_from_db()
        self.assertEqual(result.effective_status, "scheduled")
        self.assertEqual(event.status, AcademicScheduleEvent.STATUS_PLANNED)
        self.assertFalse(event.execution_logs.exists())

    def test_start_after_scheduled_end_is_rejected_and_flagged(self):
        now = timezone.now()
        event = self._event(start=now - timedelta(hours=2), end=now)
        with self.assertRaises(ValidationError):
            teacher_check_in(event=event, teacher=self.teacher, now=now)
        self.assertTrue(event.workflow_audit_logs.filter(action=CourseSessionAuditLog.ACTION_REVIEW_REQUIRED).exists())

    def test_other_teacher_cannot_check_in_or_end_session(self):
        now = timezone.now()
        event = self._event(start=now - timedelta(minutes=5), end=now + timedelta(hours=1))
        with self.assertRaises(PermissionDenied):
            teacher_check_in(event=event, teacher=self.other_teacher, now=now)
        teacher_check_in(event=event, teacher=self.teacher, now=now)
        with self.assertRaises(PermissionDenied):
            end_teacher_session(event=event, teacher=self.other_teacher, now=now + timedelta(minutes=30))

    def test_end_records_real_end_and_preserves_scheduled_end(self):
        now = timezone.now().replace(microsecond=0)
        scheduled_end = now + timedelta(hours=1)
        event = self._event(start=now - timedelta(minutes=10), end=scheduled_end)
        teacher_check_in(event=event, teacher=self.teacher, now=now)

        execution = end_teacher_session(event=event, teacher=self.teacher, now=now + timedelta(minutes=20))

        event.refresh_from_db()
        self.assertEqual(execution.ended_at, now + timedelta(minutes=20))
        self.assertEqual(event.end_datetime, scheduled_end)
        self.assertEqual(get_effective_status(event, now=now + timedelta(minutes=21)), "journal_pending")

    def test_supervisor_validation_requires_observed_service_and_becomes_payable(self):
        now = timezone.now()
        event = self._event(start=now - timedelta(minutes=10), end=now - timedelta(minutes=1), status=AcademicScheduleEvent.STATUS_COMPLETED)
        attendance = TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=event,
            date=timezone.localdate(event.start_datetime),
            status=TeacherAttendance.STATUS_PRESENT,
            checked_in_at=event.start_datetime,
            late_minutes=0,
            course_delivered=True,
            recorded_by=self.supervisor,
            branch=self.branch,
        )
        self.assertIsNotNone(attendance.pk)
        log = self._submitted_log(event)

        validate_service_by_supervisor(lesson_log=log, supervisor=self.supervisor, now=now)

        log.refresh_from_db()
        self.assertEqual(log.status, LessonLog.STATUS_DONE)
        self.assertEqual(log.validation_mode, LessonLog.VALIDATION_SUPERVISOR)
        self.assertEqual(get_effective_status(event, now=now, lesson_log=log), "ready_for_payment")
        self.assertTrue(event.workflow_audit_logs.filter(action=CourseSessionAuditLog.ACTION_READY_FOR_PAYMENT).exists())

    def test_validated_service_feeds_existing_monthly_honorarium_engine(self):
        teacher_profile = Profile.objects.get(user=self.teacher)
        teacher_profile.teacher_hourly_rate = 10000
        teacher_profile.save(update_fields=["teacher_hourly_rate"])
        local_day = timezone.localdate()
        start = timezone.make_aware(datetime.combine(local_day, time(8, 0)))
        end = timezone.make_aware(datetime.combine(local_day, time(10, 0)))
        event = self._event(
            start=start,
            end=end,
            status=AcademicScheduleEvent.STATUS_COMPLETED,
        )
        TeacherAttendance.objects.create(
            teacher=self.teacher,
            schedule_event=event,
            date=local_day,
            status=TeacherAttendance.STATUS_PRESENT,
            checked_in_at=start,
            late_minutes=0,
            course_delivered=True,
            recorded_by=self.supervisor,
            branch=self.branch,
        )
        log = self._submitted_log(event)

        validate_service_by_supervisor(lesson_log=log, supervisor=self.supervisor, now=end)

        entry = TeacherHonorariumEntry.objects.get(
            branch=self.branch,
            teacher=self.teacher,
            period_month=local_day.replace(day=1),
        )
        self.assertEqual(entry.validated_hours, Decimal("2"))
        self.assertEqual(entry.status, TeacherHonorariumEntry.STATUS_DRAFT)
        self.assertEqual(entry.net_amount, 20000)

        entry.status = TeacherHonorariumEntry.STATUS_READY
        entry.paid_amount = entry.net_amount
        entry.updated_by = self.manager
        entry.save()

        self.assertTrue(event.workflow_audit_logs.filter(
            action=CourseSessionAuditLog.ACTION_PAYMENT_RECORDED,
            metadata__honorarium_entry_id=entry.pk,
        ).exists())

    def test_manager_exception_requires_reason_comment_and_scope(self):
        now = timezone.now()
        event = self._event(start=now - timedelta(minutes=10), end=now - timedelta(minutes=1), status=AcademicScheduleEvent.STATUS_COMPLETED)
        log = self._submitted_log(event)
        with self.assertRaises(ValidationError):
            validate_service_exception(lesson_log=log, manager=self.manager, reason="other", comment="")
        with self.assertRaises(PermissionDenied):
            validate_service_exception(
                lesson_log=log,
                manager=self.other_manager,
                reason="supervisor_unavailable",
                comment="Surveillant indisponible.",
            )

        validate_service_exception(
            lesson_log=log,
            manager=self.manager,
            reason="supervisor_unavailable",
            comment="Surveillant indisponible; presence constatee.",
            now=now,
        )

        log.refresh_from_db()
        self.assertEqual(log.validation_mode, LessonLog.VALIDATION_MANAGER_EXCEPTION)
        self.assertEqual(log.validated_by, self.manager)
        self.assertTrue(event.workflow_audit_logs.filter(action=CourseSessionAuditLog.ACTION_VALIDATION_EXCEPTION).exists())

    def test_anomaly_blocks_ready_for_payment(self):
        now = timezone.now()
        event = self._event(start=now - timedelta(minutes=10), end=now - timedelta(minutes=1), status=AcademicScheduleEvent.STATUS_COMPLETED)
        log = self._submitted_log(event)
        report_service_anomaly(lesson_log=log, supervisor=self.supervisor, reason="Presence non constatee", now=now)
        log.refresh_from_db()
        self.assertEqual(log.status, LessonLog.STATUS_RETURNED)
        self.assertEqual(get_effective_status(event, now=now, lesson_log=log), "review_required")
        self.assertFalse(event.workflow_audit_logs.filter(action=CourseSessionAuditLog.ACTION_READY_FOR_PAYMENT).exists())

    def test_missing_checkin_notification_is_idempotent(self):
        now = timezone.now()
        event = self._event(start=now - timedelta(minutes=20), end=now + timedelta(hours=1))

        self.assertEqual(check_missing_checkins(now=now), 1)
        self.assertEqual(check_missing_checkins(now=now), 0)

        self.assertEqual(
            event.workflow_audit_logs.filter(action=CourseSessionAuditLog.ACTION_CHECKIN_MISSING).count(),
            1,
        )
        recipients = set(NotificationMessage.objects.filter(
            event_type="course_checkin_missing",
            channel=NotificationMessage.CHANNEL_IN_APP,
        ).values_list("recipient_id", flat=True))
        self.assertTrue({self.supervisor.pk, self.manager.pk, self.director.pk}.issubset(recipients))

    def test_assisted_terminal_keeps_teacher_as_author_and_manager_as_assistant(self):
        now = timezone.now()
        event = self._event(
            start=now - timedelta(minutes=10),
            end=now - timedelta(minutes=1),
            status=AcademicScheduleEvent.STATUS_COMPLETED,
        )
        assist_session, raw_token = create_assisted_session(event=event, manager=self.manager, now=now)
        self.client.force_login(self.manager)

        response = self.client.post(
            reverse("academics:course_session_assist", args=[raw_token]),
            {
                "username": self.teacher.username,
                "password": "pass1234",
                "content": "Contenu saisi par l'enseignant sur la tablette",
                "chapter_progress": "Chapitre 2",
                "session_outcome": LessonLog.OUTCOME_NORMAL,
                "certified": "on",
            },
        )

        self.assertEqual(response.status_code, 200)
        log = LessonLog.objects.get(schedule_event=event)
        assist_session.refresh_from_db()
        self.assertEqual(log.teacher, self.teacher)
        self.assertEqual(log.created_by, self.teacher)
        self.assertEqual(log.assisted_by, self.manager)
        self.assertEqual(log.status, LessonLog.STATUS_SUBMITTED)
        self.assertIsNotNone(assist_session.used_at)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.manager.pk)
        self.assertEqual(
            self.client.get(reverse("academics:course_session_assist", args=[raw_token])).status_code,
            410,
        )
        self.assertEqual(CourseSessionAssistSession.objects.filter(event=event).count(), 1)
