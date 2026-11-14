from datetime import datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.access import can_access
from accounts.models import PayrollEntry, Profile, TeacherHonorariumEntry
from accounts.services.manager_intelligence import get_teacher_honorarium_validated_hours, refresh_teacher_honorarium_entry
from academics.models import AcademicClass, AcademicYear, AcademicScheduleChangeLog, EC, ECChapter, ECContent, LessonLog, Semester, UE
from academics.services.lesson_log_service import create_lesson_log, get_daily_lesson_status
from academics.services.schedule_service import complete_schedule_event, replace_schedule_teacher, update_schedule_event
from academics.services.teacher_assignment_service import create_teacher_assignment
from portal import test_teacher_service_monitoring as fixtures
from portal.dg.forms import DgRecruitmentForm, DgStaffLifecycleForm
from portal.dg.rh_service import apply_staff_lifecycle_action, create_staff_from_recruitment
from portal.services.director.teacher_assignment_service import build_teacher_service_monitoring_context
from portal.services.teacher_dashboard_service import _get_teacher_ecs_for_class, set_teacher_content_publication
from students.models import TeacherAttendance


class MonitorIntegrationTests(TestCase):
    # Reuse the existing pedagogical fixture, without rerunning its test methods.
    _event = fixtures.TeacherServiceMonitoringTests._event

    def _user(self, username, position, branch):
        user = fixtures.TeacherServiceMonitoringTests._user(self, username, position, branch)
        return type(user).objects.get(pk=user.pk)

    def setUp(self):
        fixtures.TeacherServiceMonitoringTests.setUp(self)
        self.monitor = self._user("monitor", "moniteur", self.branch)
        self.monitor.profile.main_domain = "Soins infirmiers"
        self.monitor.profile.user_type = "staff"
        self.monitor.profile.salary_base = 180000
        self.monitor.profile.save()
        start = timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=1), time(8)))
        self.event = self._event(start=start, end=start + timedelta(hours=2))

    def replace(self, **kwargs):
        return replace_schedule_teacher(**{
            "user": self.director, "event": self.event, "monitor": self.monitor,
            "reason": "Enseignant indisponible", **kwargs,
        })

    def test_recruitment_uses_staff_identity_specialty_and_fixed_salary(self):
        form = DgRecruitmentForm(data={
            "first_name": "Awa", "last_name": "Traoré", "position": "moniteur",
            "branch": self.branch.pk, "main_domain": "Sage-femme", "salary_base": 200000,
        })
        self.assertTrue(form.is_valid(), form.errors)
        result = create_staff_from_recruitment(actor=self.director, form=form, request=None)
        profile = result["profile"]
        self.assertEqual(profile.main_domain, "Sage-femme")
        self.assertEqual(profile.position, "moniteur")
        self.assertEqual(profile.role, "teacher")
        self.assertEqual(profile.user_type, "staff")
        self.assertEqual(profile.teacher_hourly_rate, 0)
        self.assertFalse(TeacherHonorariumEntry.objects.filter(teacher=profile.user).exists())
        invalid = DgRecruitmentForm(data={**form.data, "teacher_hourly_rate": 5000, "main_domain": ""})
        self.assertFalse(invalid.is_valid())
        self.assertIn("main_domain", invalid.errors)
        self.assertIn("teacher_hourly_rate", invalid.errors)
        without_salary = DgRecruitmentForm(data={**form.data, "salary_base": 0})
        self.assertFalse(without_salary.is_valid())
        self.assertIn("salary_base", without_salary.errors)

    def test_role_reassignment_enforces_permanent_staff_invariants(self):
        candidate = self._user("monitor_candidate", "teacher", self.branch)
        candidate.profile.user_type = "staff"
        candidate.profile.teacher_hourly_rate = 7500
        candidate.profile.save(update_fields=["user_type", "teacher_hourly_rate", "updated_at"])
        form = DgStaffLifecycleForm(data={
            "profile_id": candidate.profile.pk,
            "action": DgStaffLifecycleForm.ACTION_UPDATE_ASSIGNMENT,
            "reason": "Intégration au personnel permanent",
            "branch": self.branch.pk,
            "position": "moniteur",
        })
        self.assertTrue(form.is_valid(), form.errors)
        with self.assertRaises(ValidationError):
            apply_staff_lifecycle_action(actor=self.director, form=form)

        candidate.profile.main_domain = "Soins infirmiers"
        candidate.profile.salary_base = 190000
        candidate.profile.save(update_fields=["main_domain", "salary_base", "updated_at"])
        apply_staff_lifecycle_action(actor=self.director, form=form)
        candidate.profile.refresh_from_db()
        self.assertEqual(candidate.profile.position, "moniteur")
        self.assertEqual(candidate.profile.role, "teacher")
        self.assertEqual(candidate.profile.teacher_hourly_rate, 0)
        self.assertTrue(PayrollEntry.objects.filter(employee=candidate, base_salary=190000).exists())

    def test_login_dashboard_sections_and_regular_course_studio(self):
        login_response = self.client.post(reverse("accounts:login"), {"username": "monitor", "password": "pass1234"})
        self.assertEqual(login_response.status_code, 302)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.monitor.pk)
        self.assertTrue(can_access(self.monitor, "view_portal", "teacher"))
        self.assertFalse(can_access(self.monitor, "view_dashboard", "director_studies"))
        create_teacher_assignment(actor=self.director, teacher=self.monitor, branch=self.branch,
                                  ec=self.ec, room_label="Salle 1", planned_hours=Decimal("20"))
        for section in ("overview", "schedule", "classes", "supports", "logs", "salary", "settings", "notifications"):
            with self.subTest(section=section):
                response = self.client.get(reverse("accounts_portal:portal_teacher"), {"section": section}, HTTP_HX_REQUEST="true")
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.content.strip())
        response = self.client.get(reverse("accounts_portal:portal_teacher"))
        self.assertContains(response, "Espace Moniteur / Monitrice")
        self.assertContains(response, "Mon salaire")
        response = self.client.get(reverse("accounts_portal:teacher_course_studio"), {"class_id": self.academic_class.pk, "ec_id": self.ec.pk})
        self.assertEqual(response.status_code, 200)

    def test_replacement_keeps_history_notifies_and_is_idempotent(self):
        with patch("notifier.services.NotificationBus.notify") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                self.replace()
            self.assertEqual(notify.call_count, 1)
            self.assertIn("Remplacement", notify.call_args.kwargs["body"])
            self.assertIn(self.ec.title, notify.call_args.kwargs["body"])
        self.replace()
        self.event.refresh_from_db()
        self.assertEqual(self.event.original_teacher, self.teacher)
        self.assertEqual(self.event.teacher, self.monitor)
        changes = self.event.change_logs.filter(action_type=AcademicScheduleChangeLog.ACTION_REPLACED)
        self.assertEqual(changes.count(), 1)
        self.assertEqual(changes.get().old_teacher, self.teacher)
        self.assertEqual(changes.get().new_teacher, self.monitor)
        self.assertEqual(changes.get().changed_by, self.director)
        with self.assertRaises(ValidationError):
            update_schedule_event(self.event, user=self.director, teacher=self.teacher)

    def test_replacement_publication_and_validated_service_never_generate_honoraria(self):
        self.replace()
        self.event.refresh_from_db()
        self.assertEqual([ec.pk for ec in _get_teacher_ecs_for_class(teacher=self.monitor, branch=self.branch, academic_class=self.academic_class)], [self.ec.pk])
        chapter = ECChapter.objects.create(ec=self.ec, title="Préparation")
        content = ECContent.objects.create(chapter=chapter, title="Leçon", content_type="text", text_content="Leçon préparée")
        set_teacher_content_publication(teacher=self.monitor, branch=self.branch, content_id=content.pk, publication_status="published")
        content.refresh_from_db()
        self.assertTrue(content.is_published)
        with self.assertRaises(ValidationError):
            set_teacher_content_publication(teacher=self.other_teacher, branch=self.other_branch, content_id=content.pk, publication_status="draft")
        # Simulate a stale/incorrect hourly rate entered outside the recruitment form.
        self.monitor.profile.teacher_hourly_rate = 9000
        self.monitor.profile.save()
        log = create_lesson_log(academic_class=self.academic_class, ec=self.ec, teacher=self.monitor,
                               branch=self.branch, schedule_event=self.event, date=self.event.start_datetime.date(),
                               start_time=time(8), end_time=time(10), created_by=self.monitor,
                               status=LessonLog.STATUS_DONE, content="Cours dispensé")
        log.validated_by = self.director
        log.save()
        execution = complete_schedule_event(self.event, self.director)
        self.assertEqual(execution.actual_teacher, self.monitor)
        self.assertIsNone(refresh_teacher_honorarium_entry(self.branch, self.monitor, log.date.replace(day=1)))
        self.assertEqual(get_teacher_honorarium_validated_hours(self.branch, self.monitor, log.date.replace(day=1)), 0)
        self.assertFalse(TeacherHonorariumEntry.objects.filter(teacher=self.monitor).exists())
        self.assertTrue(PayrollEntry.objects.filter(employee=self.monitor, base_salary=180000).exists())
        row = build_teacher_service_monitoring_context(branch=self.branch, academic_year=self.year, teacher_ids=[self.monitor.pk])["teacher_service_rows"][0]
        self.assertEqual(row["validated_hours"], Decimal("2"))
        self.assertEqual(row["payable_hours"], Decimal("0"))
        self.assertEqual(row["replacement_count"], 1)
        with self.assertRaises(ValidationError):
            TeacherHonorariumEntry.objects.create(branch=self.branch, teacher=self.monitor, period_month=log.date.replace(day=1))

    def test_replacement_permissions_branch_conflict_and_existing_service(self):
        with self.assertRaises(PermissionDenied):
            self.replace(user=self.monitor)
        other_monitor = self._user("other_monitor", "moniteur", self.other_branch)
        with self.assertRaises(ValidationError):
            self.replace(monitor=other_monitor)
        with self.assertRaises(ValidationError):
            self.replace(reason="")
        with self.assertRaises(ValidationError):
            create_teacher_assignment(actor=self.director, teacher=other_monitor, branch=self.branch,
                                      ec=self.ec, room_label="Salle", planned_hours=Decimal("10"))
        TeacherAttendance.objects.create(teacher=self.teacher, branch=self.branch, schedule_event=self.event,
                                         date=self.event.start_datetime.date(), status=TeacherAttendance.STATUS_PRESENT,
                                         recorded_by=self.director)
        with self.assertRaises(ValidationError):
            self.replace()

    def test_replacement_endpoint_updates_fragment_and_denies_other_branch(self):
        self.client.force_login(self.director)
        url = reverse("accounts_portal:director_timetable_replacement", args=[self.event.pk])
        self.assertContains(self.client.get(url, {"q": "Soins"}), "monitor")
        response = self.client.post(url, {"monitor": self.monitor.pk, "reason": "Indisponibilité"}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Retarget", response.headers, getattr(response.context.get("form"), "errors", ""))
        self.assertEqual(response["HX-Retarget"], "#director-timetable-subcontent")
        self.assertIn("ui:toast", response["HX-Trigger"])
        self.assertTrue(response.content.strip())
        drawer = self.client.get(reverse("accounts_portal:director_timetable_event_drawer"), {"class_id": self.academic_class.pk, "event_id": self.event.pk})
        self.assertContains(drawer, "Enseignant initial")
        self.assertContains(drawer, "svc_teacher")
        self.assertContains(drawer, "Indisponibilité")
        local_start = timezone.localtime(self.event.start_datetime)
        local_end = timezone.localtime(self.event.end_datetime)
        invalid_update = self.client.post(reverse("accounts_portal:director_timetable_event_action"), {
            "action": "save", "class_id": self.academic_class.pk, "event_id": self.event.pk,
            "week_start": local_start.date().isoformat(), "date": local_start.date().isoformat(),
            "start_time": local_start.time().strftime("%H:%M"),
            "end_time": local_end.time().strftime("%H:%M"), "ec_id": self.ec.pk,
            "teacher_id": self.teacher.pk, "room": self.event.location, "is_online": "",
        }, HTTP_HX_REQUEST="true")
        self.assertEqual(invalid_update.status_code, 200)
        self.assertContains(invalid_update, "Indisponibilité")
        self.client.force_login(self.monitor)
        self.assertContains(self.client.get(reverse("accounts_portal:portal_teacher"), {"section": "schedule", "week_start": self.event.start_datetime.date().isoformat()}, HTTP_HX_REQUEST="true"), "Remplacement")
        other_director = self._user("other_director", "director_of_studies", self.other_branch)
        self.client.force_login(other_director)
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_original_absence_is_preserved_without_becoming_monitors_absence(self):
        attendance = TeacherAttendance.objects.create(
            teacher=self.teacher, branch=self.branch, schedule_event=self.event,
            date=self.event.start_datetime.date(), status=TeacherAttendance.STATUS_ABSENT,
            recorded_by=self.director,
        )
        self.replace()
        attendance.refresh_from_db()
        self.assertEqual(attendance.teacher, self.teacher)
        status = get_daily_lesson_status(self.branch, attendance.date)
        self.assertEqual(status["critical_count"], 0)
        self.assertEqual(status["missing_lesson_logs_count"], 1)
        row = build_teacher_service_monitoring_context(branch=self.branch, academic_year=self.year, teacher_ids=[self.monitor.pk])["teacher_service_rows"][0]
        self.assertEqual(row["absence_count"], 0)

    def test_conflicting_replacement_is_rejected_without_mutation(self):
        other_event = self._event(start=self.event.start_datetime, end=self.event.end_datetime)
        other_event.teacher = self.monitor
        other_event.save()
        with self.assertRaises(ValidationError):
            self.replace()
        self.event.refresh_from_db()
        self.assertEqual(self.event.teacher, self.teacher)
        self.assertIsNone(self.event.original_teacher_id)

    def test_replacement_does_not_grant_another_subject_or_academic_year(self):
        self.replace()
        unrelated = EC.objects.create(ue=self.ec.ue, title="Autre discipline", credit_required=1, coefficient=1)
        chapter = ECChapter.objects.create(ec=unrelated, title="Privé")
        content = ECContent.objects.create(chapter=chapter, title="Privé", content_type="text", text_content="Cours réservé")
        self.client.force_login(self.monitor)
        self.assertEqual(self.client.get(reverse("accounts_portal:teacher_course_preview", args=[content.pk])).status_code, 403)
        with self.assertRaises(ValidationError):
            set_teacher_content_publication(teacher=self.monitor, branch=self.branch, content_id=content.pk, publication_status="published")
        year = AcademicYear.objects.create(name="2040-2041", start_date="2040-10-01", end_date="2041-07-31")
        historical_class = AcademicClass.objects.create(programme=self.academic_class.programme, branch=self.branch,
                                                        academic_year=year, level="L1", study_level="LICENCE", validation_threshold=10)
        semester = Semester.objects.create(academic_class=historical_class, number=1)
        ue = UE.objects.create(semester=semester, code="OLD", title="Historique")
        EC.objects.create(ue=ue, title=self.ec.title, credit_required=1, coefficient=1)
        self.assertEqual(_get_teacher_ecs_for_class(teacher=self.monitor, branch=self.branch, academic_class=historical_class), [])
        self.assertEqual(build_teacher_service_monitoring_context(branch=self.branch, academic_year=year, teacher_ids=[self.monitor.pk])["teacher_service_rows"][0]["scheduled_hours"], 0)

    def test_replacement_allows_pedagogical_answers_in_its_scope(self):
        from academics.models import ECPedagogicalQuestion
        from academics.services.course_interaction_service import create_teacher_answer
        from portal.views.views import _teacher_question_queryset

        question = ECPedagogicalQuestion.objects.create(
            academic_year=self.year, academic_class=self.academic_class, branch=self.branch,
            ec=self.ec, author=self.teacher, title="Question", body="Précision sur le cours",
        )
        self.assertFalse(_teacher_question_queryset(teacher=self.monitor, branch=self.branch).exists())
        with self.assertRaises(PermissionDenied):
            create_teacher_answer(teacher=self.monitor, question=question, body="Réponse")
        self.replace()
        self.assertTrue(_teacher_question_queryset(teacher=self.monitor, branch=self.branch).filter(pk=question.pk).exists())
        answer = create_teacher_answer(teacher=self.monitor, question=question, body="Explication")
        self.assertTrue(answer.is_teacher_response)
        self.assertEqual(answer.author, self.monitor)

    @override_settings(AUTH_POLICY_V2_ENABLED=True, AUTH_PORTAL_ROUTING_V2_ENABLED=True)
    def test_monitor_uses_institutional_policy_v2_and_class_assignment(self):
        from portal.permissions import get_post_login_portal_url

        self.assertTrue(can_access(self.monitor, "view_portal", "teacher"))
        self.assertEqual(get_post_login_portal_url(self.monitor), reverse("accounts_portal:portal_teacher"))
        self.assertFalse(can_access(self.monitor, "view_dashboard", "finance"))
        create_teacher_assignment(actor=self.director, teacher=self.monitor, branch=self.branch,
                                  academic_class=self.academic_class, room_label="Salle 1", planned_hours=10)
        self.assertEqual([ec.pk for ec in _get_teacher_ecs_for_class(teacher=self.monitor, branch=self.branch, academic_class=self.academic_class)], [self.ec.pk])
