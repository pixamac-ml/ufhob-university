from datetime import date, datetime
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from accounts.access_context import build_access_context
from accounts.models import FinancialAuditLog
from core import test_ufhob_phase2 as fixtures
from core.models import SchoolBranch
from formations.models import Programme
from inscriptions.models import Inscription
from portal.dg.context import SESSION_KEY
from portal.models import DirectorTeacherAssignment, SupportAuditLog
from students.models import Student


class DgUniversityTests(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)
    candidature = fixtures.UFHOBPhase2Tests.candidature

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        cls.previous = AcademicYear.objects.create(name="2025-2026", start_date=date(2025, 9, 1), end_date=date(2026, 8, 31))

    def setUp(self):
        self.client.force_login(self.global_user)

    def section(self, section, **params):
        params.setdefault("academic_year_id", self.year.pk)
        return self.client.get(reverse("accounts_portal:dg_section", args=[section]), params, HTTP_HX_REQUEST="true")

    def student(self, programme, academic_class, *, username="student", user=None, year=None):
        candidature = self.candidature(programme, academic_class.branch)
        candidature.academic_year = (year or self.year).name
        candidature.status = "accepted"
        candidature.save()
        inscription = Inscription.objects.create(candidature=candidature, amount_due=100, status="active")
        user = user or get_user_model().objects.create_user(username=username)
        student, _ = Student.objects.get_or_create(user=user, defaults={"inscription": inscription, "matricule": username})
        enrollment = AcademicEnrollment.objects.create(inscription=inscription, student=user, programme=programme,
            branch=academic_class.branch, academic_year=year or self.year, academic_class=academic_class)
        student.current_academic_enrollment = enrollment
        student.save(update_fields=["current_academic_enrollment"])
        return student, enrollment

    def test_inscription_creation_audit_keeps_its_academic_scope(self):
        from inscriptions.services import create_inscription_from_candidature

        candidature = self.candidature(self.programmes[0], self.a)
        candidature.academic_year = self.year.name
        candidature.status = "accepted"
        candidature.save(update_fields=["academic_year", "status"])
        inscription = create_inscription_from_candidature(
            candidature=candidature,
            amount_due=100,
            academic_class=self.classes[0],
            actor=self.global_user,
        )
        audit = SupportAuditLog.objects.get(action_type=SupportAuditLog.ACTION_INSCRIPTION_CREATED)
        self.assertEqual(audit.branch_id, self.a.id)
        self.assertEqual(audit.school_id, self.programmes[0].school_id)
        self.assertEqual(audit.academic_year_id, self.year.id)
        self.assertIn(inscription.public_reference, audit.target_label)

        response = self.section("audit", scope_school_id=self.programmes[0].school_id, scope_branch_id=self.a.id)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inscription creee")

    def test_global_indicators_are_distinct_across_shared_campus(self):
        response = self.section("overview")
        self.assertEqual(response.status_code, 200)
        data = response.context["university_indicators"]
        self.assertEqual((data["schools"], data["campuses"], data["implantations"], data["programmes"]), (3, 2, 4, 3))

    def test_school_covers_its_two_campuses(self):
        response = self.section("classes", scope_school_id=self.schools[0].pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["backoffice_result_count"], 2)
        self.assertNotContains(response, self.programmes[1].title)

    def test_branch_covers_its_multiple_schools(self):
        response = self.section("classes", scope_branch_id=self.a.pk)
        self.assertEqual(response.context["backoffice_result_count"], 3)

    def test_intersection_excludes_same_campus_other_school(self):
        response = self.section("classes", scope_branch_id=self.a.pk, scope_school_id=self.schools[0].pk)
        self.assertEqual(response.context["backoffice_result_count"], 1)
        self.assertNotContains(response, self.programmes[1].title)

    def test_invalid_pair_does_not_modify_saved_context(self):
        self.section("overview", scope_school_id=self.schools[0].pk)
        saved = self.client.session[SESSION_KEY]
        response = self.section("overview", scope_school_id=self.schools[1].pk, scope_branch_id=self.b.pk)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.session[SESSION_KEY], saved)

    def test_explicit_invalid_ids_never_fall_back_to_global(self):
        for params in ({"scope_school_id": "999999"}, {"scope_branch_id": "999999"}):
            with self.subTest(params=params):
                self.assertEqual(self.section("classes", **params).status_code, 400)

    def test_school_selector_restricts_campuses(self):
        response = self.section("classes", scope_school_id=self.schools[1].pk)
        self.assertEqual([b.pk for b in response.context["available_branches"]], [self.a.pk])

    def test_branch_selector_restricts_schools(self):
        response = self.section("classes", scope_branch_id=self.b.pk)
        self.assertEqual([s.pk for s in response.context["available_schools"]], [self.schools[0].pk])

    def test_year_survives_school_switch_and_global_return(self):
        self.section("classes", academic_year_id=self.previous.pk, scope_school_id=self.schools[0].pk)
        response = self.client.get(reverse("accounts_portal:dg_section", args=["classes"]), {"scope_school_id": "", "scope_branch_id": ""})
        self.assertEqual(response.context["selected_academic_year"], self.previous)
        self.assertEqual(response.context["dashboard_mode"], "global")
        self.assertEqual(AcademicYear.objects.count(), 2)
        self.assertEqual(build_access_context(self.global_user).scope, "GLOBAL")

    def test_programme_availability_applies_in_catalogue(self):
        response = self.section("formations", scope_branch_id=self.b.pk)
        self.assertContains(response, self.programmes[0].title)
        self.assertNotContains(response, self.programmes[1].title)
        with self.assertRaises(ValidationError):
            self.candidature(self.programmes[1], self.b)

    def test_new_implantation_enables_programme_without_new_engine(self):
        SchoolBranch.objects.create(school=self.schools[1], branch=self.b)
        self.assertTrue(Programme.objects.available_on(self.b).filter(pk=self.programmes[1].pk).exists())
        response = self.section("formations", scope_branch_id=self.b.pk, scope_school_id=self.schools[1].pk)
        self.assertContains(response, self.programmes[1].title)

    def test_admission_list_is_scoped_by_programme(self):
        self.candidature(self.programmes[0])
        self.candidature(self.programmes[1])
        response = self.section("admissions", scope_school_id=self.schools[0].pk)
        self.assertEqual(response.context["admission_page"].paginator.count, 1)
        self.assertNotContains(response, self.programmes[1].title)

    def test_historical_student_list_and_export_agree_after_school_change(self):
        old_class = AcademicClass.objects.create(programme=self.programmes[0], branch=self.b, academic_year=self.previous, level="L1")
        student, _ = self.student(self.programmes[0], old_class, year=self.previous)
        self.student(self.programmes[1], self.classes[1], user=student.user)
        response = self.section("students", academic_year_id=self.previous.pk, scope_school_id=self.schools[0].pk, scope_branch_id=self.b.pk)
        self.assertEqual(response.context["backoffice_result_count"], 1)
        export = self.client.get(reverse("accounts_portal:dg_export"), {"kind": "students"})
        self.assertEqual(export.status_code, 200)
        self.assertContains(export, self.programmes[0].title)
        self.assertNotContains(export, self.programmes[1].title)
        self.assertContains(export, student.matricule)

    def test_student_filters_match_same_enrollment(self):
        old_class = AcademicClass.objects.create(programme=self.programmes[0], branch=self.b, academic_year=self.previous, level="L1")
        student, _ = self.student(self.programmes[0], old_class, year=self.previous)
        self.student(self.programmes[1], self.classes[1], user=student.user)
        response = self.section("students", programme_id=self.programmes[0].pk)
        self.assertEqual(response.context["backoffice_result_count"], 0)

    def test_cross_school_teacher_is_visible_through_teaching_assignments(self):
        teacher = self.make_user("transversal", "teacher", self.b)
        teacher.profile.user_type = "staff"
        teacher.profile.save()
        for academic_class in self.classes[:2]:
            DirectorTeacherAssignment.objects.create(teacher=teacher, academic_class=academic_class, branch=self.a, room_label="Test", planned_hours=1)
        for school in self.schools[:2]:
            response = self.section("rh", scope_school_id=school.pk, scope_branch_id=self.a.pk)
            self.assertContains(response, "transversal")
        self.assertIsNone(build_access_context(teacher).school)

    def test_foreign_drawer_is_denied(self):
        self.section("classes", scope_school_id=self.schools[0].pk)
        response = self.client.get(reverse("accounts_portal:dg_drawer"), {"kind": "academic_class", "id": self.classes[1].pk})
        self.assertEqual(response.status_code, 403)

    def test_structure_and_main_sections_render_in_school_context(self):
        for section in ("university", "overview", "admissions", "enrollments", "assignments", "finance", "finance_reports", "schedule", "evaluations", "results", "progression", "academic_calendar", "analytics"):
            with self.subTest(section=section):
                response = self.section(section, scope_school_id=self.schools[0].pk, scope_branch_id=self.a.pk)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-dg-scope-label=')
                self.assertContains(response, 'hx-swap-oob="outerHTML"')
                self.assertIn("scope_school_id=", response["HX-Push-Url"])

    def test_non_executive_cannot_use_navigation_to_widen_access(self):
        self.client.force_login(self.director)
        self.assertEqual(self.section("overview", scope_school_id="").status_code, 403)

    def test_payment_totals_and_export_keep_school_and_year(self):
        from payments.models import Payment
        _, own = self.student(self.programmes[0], self.classes[0], username="own")
        _, foreign = self.student(self.programmes[1], self.classes[1], username="foreign")
        paid_at = timezone.make_aware(datetime(2026, 10, 2, 10))
        # Reading fixtures bypass the receipt/email workflow deliberately.
        Payment.objects.bulk_create([
            Payment(inscription=own.inscription, amount=40, status="validated", method="cash", reference="OWN-PAY", paid_at=paid_at),
            Payment(inscription=foreign.inscription, amount=90, status="validated", method="cash", reference="FOREIGN-PAY", paid_at=paid_at),
        ])
        response = self.section("finance", scope_school_id=self.schools[0].pk)
        self.assertEqual(response.context["finance"]["revenue"], 40)
        self.assertTrue(response.context["dg_school_finance"])
        self.assertFalse(response.context["dg_mixed_campus_finance"])
        self.assertContains(response, "non ventil")
        export = self.client.get(reverse("accounts_portal:dg_export"), {"kind": "payments"})
        self.assertContains(export, "OWN-PAY")
        self.assertNotContains(export, "FOREIGN-PAY")
        # October is outside the current admissions watch window; it still
        # belongs in the selected academic-year payment export.
        self.assertEqual(export.status_code, 200)

    def test_branch_finance_keeps_early_payment_of_selected_dossier_year(self):
        from payments.models import Payment
        from portal.dg.selectors import get_branch_finance, get_latest_payments_for_branch

        _, enrollment = self.student(self.programmes[0], self.classes[0], username="early-payment")
        early_paid_at = timezone.make_aware(datetime(2026, 9, 12, 10))
        payment = Payment.objects.create(
            inscription=enrollment.inscription,
            amount=250000,
            status=Payment.STATUS_VALIDATED,
            method=Payment.METHOD_CASH,
            reference="EARLY-2026-2027",
            paid_at=early_paid_at,
        )
        revenue, _expenses, _balance = get_branch_finance(self.a, academic_year=self.year)
        self.assertEqual(revenue, 250000)
        self.assertEqual(get_latest_payments_for_branch(self.a, academic_year=self.year)[0], payment)

    def test_validated_payment_audit_uses_the_same_school_context_as_finance(self):
        """A payment trace must follow its dossier, never a branch-only fallback."""
        from payments.models import Payment

        _, enrollment = self.student(self.programmes[0], self.classes[0], username="audited-payment")
        paid_at = timezone.make_aware(datetime(2026, 10, 2, 10))
        with (
            patch("payments.models.generate_esfe_pdf", return_value=b"%PDF-test"),
            patch("payments.models.create_student_after_first_payment"),
            patch("payments.models.send_payment_confirmation_email"),
            patch("payments.models.run_first_payment_validated_workflow"),
        ):
            payment = Payment.objects.create(
                inscription=enrollment.inscription,
                amount=40,
                status=Payment.STATUS_VALIDATED,
                method=Payment.METHOD_CASH,
                paid_at=paid_at,
            )

        audit = FinancialAuditLog.objects.get(
            target_model="payments.payment", target_id=payment.pk
        )
        self.assertEqual(audit.branch_id, self.a.pk)
        self.assertEqual(audit.new_state["school_id"], self.schools[0].pk)
        self.assertEqual(audit.new_state["academic_year"], self.year.name)

        response = self.section("audit", scope_school_id=self.schools[0].pk)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, payment.public_reference)

        export = self.client.get(reverse("accounts_portal:dg_export"), {"kind": "audit"})
        self.assertEqual(export.status_code, 200)
        self.assertContains(export, payment.public_reference)

    def test_school_plus_campus_exposes_campus_ledgers(self):
        from accounts.models import BranchExpense
        from payments.models import Payment

        _, own = self.student(self.programmes[0], self.classes[0], username="own-mix")
        paid_at = timezone.make_aware(datetime(2026, 10, 2, 10))
        Payment.objects.bulk_create([
            Payment(inscription=own.inscription, amount=55, status="validated", method="cash", reference="MIX-PAY", paid_at=paid_at),
        ])
        BranchExpense.objects.create(
            branch=self.a,
            title="Fournitures campus",
            amount=20,
            status=BranchExpense.STATUS_PAID,
            expense_date=self.year.start_date,
            created_by=self.global_user,
        )
        response = self.section("finance", scope_school_id=self.schools[0].pk, scope_branch_id=self.a.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["dg_school_finance"])
        self.assertTrue(response.context["dg_mixed_campus_finance"])
        self.assertEqual(response.context["finance"]["revenue"], 55)
        self.assertEqual(response.context["finance"]["expenses"], 20)
        self.assertContains(response, "écritures de campus")

    def test_teacher_assignment_to_semester_derives_school_and_year(self):
        from academics.models import Semester
        teacher = self.make_user("semester-teacher", "teacher", self.b)
        teacher.profile.user_type = "staff"
        teacher.profile.save()
        semester = Semester.objects.create(academic_class=self.classes[1], number=1)
        DirectorTeacherAssignment.objects.create(teacher=teacher, semester=semester, scope_type="semester", branch=self.a, planned_hours=1)
        response = self.section("rh", scope_school_id=self.schools[1].pk, scope_branch_id=self.a.pk)
        self.assertContains(response, teacher.username)
        export = self.client.get(reverse("accounts_portal:dg_export"), {"kind": "staff"})
        self.assertContains(export, teacher.username)

    def test_calendar_pdf_uses_same_school_entries(self):
        from academics.models import AcademicCalendar, AcademicCalendarEntry
        calendar = AcademicCalendar.objects.create(branch=self.a, academic_year=self.year, created_by=self.global_user, updated_by=self.global_user)
        data = dict(calendar=calendar, event_type="other", start_datetime=timezone.make_aware(datetime(2026, 10, 1, 8)), end_datetime=timezone.make_aware(datetime(2026, 10, 1, 9)), created_by=self.global_user, updated_by=self.global_user)
        common = AcademicCalendarEntry.objects.create(title="Commun", **data)
        own = AcademicCalendarEntry.objects.create(title="ESMED", target_scope="school", school=self.schools[0], **data)
        AcademicCalendarEntry.objects.create(title="ESGA", target_scope="school", school=self.schools[1], **data)
        self.section("classes", scope_school_id=self.schools[0].pk, scope_branch_id=self.a.pk)
        with patch("portal.views.views.render_to_string", return_value="<html></html>") as render, patch("weasyprint.HTML") as html:
            html.return_value.write_pdf.return_value = b"%PDF-test"
            response = self.client.get(reverse("accounts_portal:director_calendar_pdf", args=[calendar.pk]))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(set(render.call_args.args[1]["entries"]), {common, own})

    def test_deactivated_saved_campus_requires_explicit_new_context(self):
        self.section("classes", scope_branch_id=self.b.pk)
        self.b.is_active = False
        self.b.save(update_fields=["is_active"])
        response = self.section("classes")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.section("classes", scope_branch_id="").status_code, 200)
