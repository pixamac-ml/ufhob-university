from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from accounts.access_context import build_access_context
from accounts.scoping import access_scope
from academics.models import AcademicClass, AcademicYear, Semester
from core import test_ufhob_phase2 as fixtures
from portal import test_dg_university as dg_fixtures
from portal.models import DirectorTeacherAssignment, SupportAuditLog, SupportTicket
from portal.services.it_support_service import get_scoped_staff_queryset, get_support_ticket_queryset, get_recent_support_logs
from secretary.forms import RegistryEntryForm
from secretary.selectors import get_students_by_class


class UniversityDashboardAlignmentTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)
    candidature = fixtures.UFHOBPhase2Tests.candidature
    student = dg_fixtures.DgUniversityTests.student

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        cls.actors = {}
        for position in ("it_support", "secretary", "annex_manager", "finance_manager", "academic_supervisor", "admissions"):
            actor = cls.make_user(position, position, cls.a, cls.schools[0])
            actor.profile.user_type = "staff"
            actor.profile.save()
            cls.actors[position] = actor
        cls.foreign_staff = cls.make_user("foreign-staff-esga", "secretary", cls.a, cls.schools[1])
        cls.teacher = cls.make_user("cross-campus-teacher", "teacher", cls.a, cls.schools[0])
        cls.monitor = cls.make_user("cross-campus-monitor", "moniteur", cls.a)
        for teacher in (cls.teacher, cls.monitor):
            teacher.profile.user_type = "staff"
            teacher.profile.save()
            DirectorTeacherAssignment.objects.create(teacher=teacher, academic_class=cls.other_campus_class, branch=cls.b, planned_hours=1, room_label="Salle test")

    def login(self, user):
        self.client.force_login(user)

    def test_main_staff_dashboards_render_visible_school_and_campus(self):
        routes = {
            "it_support": "accounts_portal:portal_it_v2",
            "secretary": "secretary:secretary_dashboard",
            "annex_manager": "accounts_portal:portal_annex_manager",
            "finance_manager": "accounts_portal:portal_finance",
            "academic_supervisor": "accounts_portal:portal_dashboard",
            "admissions": "accounts_portal:portal_admissions",
        }
        for role, route in routes.items():
            with self.subTest(role=role):
                self.login(self.actors[role])
                response = self.client.get(reverse(route), follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "data-university-context")
                self.assertContains(response, "ESMED")
                self.assertContains(response, self.a.name)

    def test_director_dashboard_and_form_choices_exclude_other_school(self):
        self.login(self.director)
        response = self.client.get(reverse("accounts_portal:portal_dashboard"), {"section": "programme"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-university-context")
        self.assertNotContains(response, self.programmes[1].title)

    def test_it_staff_search_is_school_scoped(self):
        with access_scope(build_access_context(self.actors["it_support"])):
            users = get_scoped_staff_queryset(branch=self.a)
            self.assertTrue(users.filter(pk=self.actors["secretary"].pk).exists())
            self.assertFalse(users.filter(pk=self.foreign_staff.pk).exists())

    def test_it_cannot_open_foreign_account_modal(self):
        self.login(self.actors["it_support"])
        response = self.client.get(reverse("accounts_portal:it_user_modal", args=[self.foreign_staff.pk]), HTTP_HX_REQUEST="true")
        self.assertIn(response.status_code, {403, 404})

    def test_it_tickets_and_logs_follow_target_school(self):
        own = SupportTicket.objects.create(title="Own", branch=self.a, requester_user=self.actors["secretary"], created_by=self.actors["secretary"])
        foreign = SupportTicket.objects.create(title="Foreign", branch=self.a, requester_user=self.foreign_staff, created_by=self.foreign_staff)
        SupportAuditLog.objects.create(actor=self.global_user, target_user=self.foreign_staff, branch=self.a, action_type="diagnostic_viewed")
        with access_scope(build_access_context(self.actors["it_support"])):
            self.assertEqual(list(get_support_ticket_queryset(branch=self.a)), [own])
            self.assertNotIn(foreign, get_support_ticket_queryset(branch=self.a))
            self.assertEqual(list(get_recent_support_logs(branch=self.a)), [])

    def test_secretary_form_rejects_foreign_staff_id(self):
        actor = self.actors["secretary"]
        form = RegistryEntryForm(user=actor, branch=self.a, data={"related_staff": self.foreign_staff.pk})
        self.assertFalse(form.fields["related_staff"].queryset.filter(pk=self.foreign_staff.pk).exists())
        self.assertFalse(form.is_valid())
        self.assertIn("related_staff", form.errors)

    def test_secretary_class_search_and_student_snapshot_are_scoped(self):
        own, _ = self.student(self.programmes[0], self.classes[0], username="own-student")
        foreign, _ = self.student(self.programmes[1], self.classes[1], username="foreign-student")
        actor = self.actors["secretary"]
        self.assertEqual(list(get_students_by_class(self.classes[0], user=actor, branch=self.a)), [own])
        self.login(actor)
        own_response = self.client.get(reverse("secretary:student_snapshot", args=[own.pk]), HTTP_HX_REQUEST="true")
        self.assertEqual(own_response.status_code, 200)
        self.assertContains(own_response, own.matricule)
        response = self.client.get(reverse("secretary:student_snapshot", args=[foreign.pk]), HTTP_HX_REQUEST="true")
        self.assertIn(response.status_code, {403, 404})

    def test_teacher_and_monitor_can_select_assigned_second_campus(self):
        for teacher in (self.teacher, self.monitor):
            with self.subTest(position=teacher.profile.position):
                self.login(teacher)
                response = self.client.get(reverse("accounts_portal:portal_teacher"), {"teaching_branch_id": self.b.pk, "section": "classes"}, HTTP_HX_REQUEST="true")
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["branch"], self.b)
                self.assertContains(response, "data-teaching-campus")
                self.assertContains(response, self.programmes[0].title)
                self.assertIn("teaching_branch_id=", response["HX-Push-Url"])
                continued = self.client.get(reverse("accounts_portal:portal_teacher"), HTTP_HX_REQUEST="true")
                self.assertEqual(continued.context["branch"], self.b)

    def test_teacher_rejects_unassigned_campus(self):
        from branches.models import Branch
        foreign = Branch.objects.create(name="Campus interdit test", code="NO", slug="campus-interdit-test")
        self.login(self.teacher)
        response = self.client.get(reverse("accounts_portal:portal_teacher"), {"teaching_branch_id": foreign.pk}, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 403)

    def test_teaching_primary_school_does_not_hide_other_school_assignments(self):
        from portal.services.teacher_dashboard_service import _get_teacher_class_queryset
        semester = Semester.objects.create(academic_class=self.classes[1], number=1)
        DirectorTeacherAssignment.objects.create(teacher=self.teacher, semester=semester, scope_type="semester", branch=self.a, planned_hours=1)
        self.assertIsNone(build_access_context(self.teacher).school)
        self.assertTrue(_get_teacher_class_queryset(teacher=self.teacher, branch=self.a).filter(pk=self.classes[1].pk).exists())

    def test_it_upload_refuses_foreign_class_before_parsing_workbook(self):
        self.login(self.actors["it_support"])
        semester = Semester.objects.create(academic_class=self.classes[1], number=1)
        with patch("academics.views_import.import_grades") as importer:
            response = self.client.post(reverse("academics:upload_grades"), {
                "class_id": self.classes[1].pk, "semester_id": semester.pk,
                "file": SimpleUploadedFile("grades.xlsx", b"not-read"),
            })
            self.assertEqual(response.status_code, 403)
            importer.assert_not_called()

    def test_it_import_accepts_own_school_workbook(self):
        from academics.models import UE, EC, ECGrade
        from academics.imports.template_service import generate_notes_workbook

        _, enrollment = self.student(self.programmes[0], self.classes[0], username="import-own")
        semester = Semester.objects.create(academic_class=self.classes[0], number=1, status=Semester.STATUS_NORMAL_ENTRY)
        ue = UE.objects.create(semester=semester, code="TEST101", title="UE test")
        ec = EC.objects.create(ue=ue, title="EC test", credit_required=3, coefficient=1)
        workbook = generate_notes_workbook(self.classes[0], semester, session_type="normal", scores_by_cell={(enrollment.pk, ec.pk): "14.00"})
        self.login(self.actors["it_support"])
        response = self.client.post(reverse("academics:upload_grades"), {
            "class_id": self.classes[0].pk, "semester_id": semester.pk,
            "file": SimpleUploadedFile("notes.xlsx", workbook.getvalue()),
        })
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(ECGrade.objects.get(enrollment=enrollment, ec=ec).normal_score, 14)

    def test_manager_payment_screen_and_csv_share_school_campus_scope(self):
        from payments.models import Payment
        _, own = self.student(self.programmes[0], self.classes[0], username="own-pay")
        own.inscription.candidature.email = "own-pay@example.test"
        own.inscription.candidature.save(update_fields=["email"])
        _, foreign = self.student(self.programmes[1], self.classes[1], username="foreign-pay")
        _, remote = self.student(self.programmes[0], self.other_campus_class, username="remote-pay")
        Payment.objects.bulk_create([
            Payment(inscription=enrollment.inscription, amount=amount, status="validated", method="cash", reference=ref, paid_at=timezone.now())
            for enrollment, amount, ref in ((own, 40, "OWN-PAY"), (foreign, 90, "FOREIGN-PAY"), (remote, 70, "REMOTE-PAY"))
        ])
        self.login(self.actors["annex_manager"])
        screen = self.client.get(reverse("accounts_portal:portal_annex_manager"), {"section": "paiements"}, follow=True)
        self.assertEqual(screen.status_code, 200)
        self.assertContains(screen, "OWN-PAY")
        self.assertNotContains(screen, "FOREIGN-PAY")
        self.assertNotContains(screen, "REMOTE-PAY")
        response = self.client.get(reverse("accounts:export_payments_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OWN-PAY")
        self.assertNotContains(response, "FOREIGN-PAY")
        self.assertNotContains(response, "REMOTE-PAY")

    def test_it_service_refuses_foreign_account_without_request_middleware(self):
        from portal.services.it_support_service import suspend_account
        with self.assertRaises(PermissionDenied):
            suspend_account(actor=self.actors["it_support"], branch=self.a, target_user=self.foreign_staff)
        self.foreign_staff.refresh_from_db()
        self.assertTrue(self.foreign_staff.is_active)

    def test_supervisor_aggregates_and_planning_exclude_foreign_school(self):
        from academics.models import AcademicScheduleEvent, UE, EC
        from academics.services.analytics_service import compute_branch_pedagogy_snapshot
        from academics.services.schedule_service import get_branch_week_schedule
        now = timezone.now()
        for academic_class, title in ((self.classes[0], "Own lesson"), (self.classes[1], "Foreign lesson")):
            semester = Semester.objects.create(academic_class=academic_class, number=1)
            ue = UE.objects.create(semester=semester, code="TEST101", title="UE test")
            ec = EC.objects.create(ue=ue, title="EC test", credit_required=3, coefficient=1)
            AcademicScheduleEvent.objects.create(academic_class=academic_class, branch=self.a, academic_year=self.year,
                title=title, ec=ec, teacher=self.teacher, created_by=self.director, updated_by=self.director,
                start_datetime=now, end_datetime=now + timedelta(hours=1), status="planned")
        with access_scope(build_access_context(self.actors["academic_supervisor"])):
            self.assertEqual(compute_branch_pedagogy_snapshot(branch=self.a)["scheduled_courses"], 1)
            schedule = get_branch_week_schedule(self.a, timezone.localdate())
            self.assertIn("Own lesson", str(schedule))
            self.assertNotIn("Foreign lesson", str(schedule))

    def test_secretary_creator_cannot_broaden_record_campus(self):
        from secretary.models import RegistryEntry
        from secretary.selectors import get_registry_queryset
        actor = self.actors["secretary"]
        own = RegistryEntry.objects.create(title="Own registry", branch=self.a, created_by=actor, entry_type="complaint")
        RegistryEntry.objects.create(title="Remote registry", branch=self.b, created_by=actor, entry_type="complaint")
        self.assertEqual(list(get_registry_queryset(user=actor, branch=self.a)), [own])

    def test_school_wide_it_and_supervisor_choose_only_authorized_campuses(self):
        for position in ("it_support", "academic_supervisor"):
            with self.subTest(position=position):
                actor = self.make_user(f"school-wide-{position}", position, school=self.schools[0])
                self.login(actor)
                response = self.client.get(reverse("accounts_portal:portal_dashboard"), {"context_branch_id": self.b.pk})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "data-operational-campus")
                self.assertEqual(response.wsgi_request.access_context.branch, self.b)
                self.assertEqual(response.wsgi_request.access_context.school, self.schools[0])
                continued = self.client.get(reverse("accounts_portal:portal_dashboard"), HTTP_HX_REQUEST="true")
                self.assertEqual(continued.wsgi_request.access_context.branch, self.b)
                denied = self.client.get(reverse("accounts_portal:portal_dashboard"), {"context_branch_id": "999999"})
                self.assertEqual(denied.status_code, 403)

    def test_local_marketing_and_admin_cannot_open_global_operations(self):
        from marketing.permissions import user_can_access_marketing
        from superadmin.views import superuser_required
        local = self.make_user("local-marketing", "marketing_manager", self.a, self.schools[0])
        self.assertFalse(user_can_access_marketing(local))
        central = self.make_user("central-marketing", "marketing_manager")
        self.assertTrue(user_can_access_marketing(central))
        local.is_superuser = True
        local.save(update_fields=["is_superuser"])
        self.assertFalse(superuser_required(local))

    def test_it_school_actor_cannot_modify_campus_common_settings(self):
        from portal.services.informaticien_workflows import update_branch_settings
        with self.assertRaises(PermissionDenied):
            update_branch_settings(actor=self.actors["it_support"], branch=self.a,
                validation_threshold=10, active_academic_year=self.year.name, local_config="{}")

    def test_student_school_campus_follow_historical_enrollment(self):
        previous = AcademicYear.objects.create(name="2025-2026", start_date=date(2025, 9, 1), end_date=date(2026, 8, 31))
        old_class = AcademicClass.objects.create(programme=self.programmes[0], branch=self.b, academic_year=previous, level="L1")
        student, _ = self.student(self.programmes[0], old_class, year=previous, username="history-student")
        self.student(self.programmes[1], self.classes[1], user=student.user)
        student.user.profile.position = "student"
        student.user.profile.save()
        self.login(student.user)
        response = self.client.get(reverse("portal_student:dashboard"), {"academic_year_id": previous.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["academic_school"], self.schools[0])
        self.assertEqual(response.context["academic_branch"], self.b)
        self.assertContains(response, "data-university-context")
        self.assertContains(response, previous.name)
        for route in ("courses_partial", "academics_partial", "timetable_partial", "finance_partial"):
            with self.subTest(partial=route):
                partial = self.client.get(reverse(f"portal_student:{route}"), {"academic_year_id": previous.pk}, HTTP_HX_REQUEST="true")
                self.assertEqual(partial.status_code, 200)
                self.assertEqual(partial.context["academic_school"], self.schools[0])
                self.assertEqual(partial.context["academic_branch"], self.b)
                if route != "finance_partial":
                    self.assertContains(partial, "data-context-school>ESMED")
                    self.assertContains(partial, previous.name)

    def test_it_audit_and_class_selection_share_school_scope(self):
        from portal.selectors.informaticien import academic_classes_for_branch, audit_logs_for_branch
        SupportAuditLog.objects.create(actor=self.global_user, target_user=self.foreign_staff, branch=self.a, action_type="diagnostic_viewed")
        with access_scope(build_access_context(self.actors["it_support"])):
            self.assertEqual(list(academic_classes_for_branch(branch=self.a)), [self.classes[0]])
            self.assertFalse(audit_logs_for_branch(branch=self.a).exists())

    def test_student_cannot_open_foreign_course_by_identifier(self):
        from academics.models import UE, EC
        student, _ = self.student(self.programmes[0], self.classes[0], username="course-student")
        student.user.profile.position = "student"
        student.user.profile.save()
        semester = Semester.objects.create(academic_class=self.classes[1], number=1)
        ue = UE.objects.create(semester=semester, code="FOREIGN101", title="Foreign UE")
        ec = EC.objects.create(ue=ue, title="Foreign EC", credit_required=3, coefficient=1)
        self.login(student.user)
        response = self.client.get(reverse("portal_student:ec_detail", args=[ec.pk]))
        self.assertIn(response.status_code, {403, 404})
