from datetime import date, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from academics.models import (
    AcademicCalendarEntry,
    AcademicClass,
    AcademicScheduleEvent,
    AcademicYear,
    EC,
    Semester,
    UE,
)
from academics.services.calendar_document_service import build_calendar_document_context
from academics.services.calendar_service import (
    create_calendar,
    create_calendar_adjustment,
    create_calendar_entry,
    get_effective_calendar_projection,
    publish_calendar,
    publish_calendar_adjustment,
    submit_calendar,
    submit_calendar_adjustment,
    validate_calendar,
    validate_calendar_adjustment,
)
from academics.services.evaluation_campaign_service import create_evaluation_campaign
from branches.models import Branch
from core.models import Institution, School, SchoolBranch
from formations.models import Cycle, Diploma, Filiere, Programme


class AcademicCalendarProjectionTests(TestCase):
    """Regression tests for the one-source calendar projection."""

    def setUp(self):
        self.actor = get_user_model().objects.create_superuser("projection", "projection@test.local", "pass")
        self.branch = Branch.objects.create(name="Campus Projection", code="PRJ", slug="campus-projection")
        self.year = AcademicYear.objects.create(
            name="2040-2041", start_date=date(2040, 10, 1), end_date=date(2041, 8, 31), is_active=True
        )
        institution = Institution.objects.create(name="Institution Projection", address="A", city="B", phone="0", email="p@test.local")
        self.school = School.objects.create(institution=institution, code="SCP", short_name="École Projection")
        self.other_school = School.objects.create(institution=institution, code="OTH", short_name="Autre École")
        SchoolBranch.objects.create(school=self.school, branch=self.branch, is_active=True)
        SchoolBranch.objects.create(school=self.other_school, branch=self.branch, is_active=True)
        cycle = Cycle.objects.create(name="Cycle Projection", theme="primary", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplôme Projection", level="superieur")
        filiere = Filiere.objects.create(name="Filière Projection")
        self.programme = Programme.objects.create(title="Programme Projection", school=self.school, filiere=filiere, cycle=cycle, diploma_awarded=diploma, duration_years=3, short_description="P", description="P")
        self.academic_class = AcademicClass.objects.create(programme=self.programme, branch=self.branch, academic_year=self.year, level="L1", study_level="LICENCE")
        self.semester = Semester.objects.create(academic_class=self.academic_class, number=1)
        self.ec = EC.objects.create(ue=UE.objects.create(semester=self.semester, code="UE-P", title="UE Projection"), title="Anatomie", credit_required=1, coefficient=1)
        self.calendar = create_calendar(actor=self.actor, branch=self.branch, academic_year=self.year)
        self._entry("Rentrée", AcademicCalendarEntry.EVENT_ACADEMIC_START, 2040, 10, 1, 2040, 10, 1)
        self.session = self._entry("Session normale", AcademicCalendarEntry.EVENT_EXAM_SESSION, 2040, 11, 1, 2040, 11, 15, target_scope=AcademicCalendarEntry.SCOPE_SCHOOL, school=self.school)
        self._entry("Clôture", AcademicCalendarEntry.EVENT_ACADEMIC_END, 2041, 8, 31, 2041, 8, 31)
        submit_calendar(self.calendar, actor=self.actor)
        validate_calendar(self.calendar, actor=self.actor)
        publish_calendar(self.calendar, actor=self.actor)
        self.session.refresh_from_db()

    def _entry(self, title, event_type, sy, sm, sd, ey, em, ed, **extra):
        return create_calendar_entry(
            actor=self.actor, calendar=self.calendar, title=title, event_type=event_type,
            start_datetime=timezone.make_aware(datetime(sy, sm, sd, 8)),
            end_datetime=timezone.make_aware(datetime(ey, em, ed, 18)),
            target_scope=extra.pop("target_scope", AcademicCalendarEntry.SCOPE_BRANCH), **extra,
        )

    def test_session_projects_linked_exam_and_effective_amendment(self):
        campaign = create_evaluation_campaign(actor=self.actor, calendar_entry=self.session)
        event = AcademicScheduleEvent.objects.create(
            title="Épreuve d'anatomie", event_type=AcademicScheduleEvent.EVENT_TYPE_EXAM,
            academic_class=self.academic_class, ec=self.ec, teacher=self.actor,
            branch=self.branch, academic_year=self.year, evaluation_campaign=campaign,
            start_datetime=timezone.make_aware(datetime(2040, 11, 5, 9)),
            end_datetime=timezone.make_aware(datetime(2040, 11, 5, 11)),
            status=AcademicScheduleEvent.STATUS_PLANNED, created_by=self.actor, updated_by=self.actor,
        )
        projection = get_effective_calendar_projection(self.calendar, school=self.school, programme=self.programme, academic_class=self.academic_class, semester_ids=[self.semester.id], public_only=True)
        session = next(item for item in projection if item["entry"].pk == self.session.pk)
        self.assertEqual([detail["event"].pk for detail in session["details"]], [event.pk])

        amendment = create_calendar_adjustment(actor=self.actor, calendar=self.calendar, calendar_entry=self.session, action="reschedule", reason="Décision officielle", effective_start_datetime=timezone.make_aware(datetime(2040, 11, 2, 8)), effective_end_datetime=timezone.make_aware(datetime(2040, 11, 16, 18)))
        amendment = submit_calendar_adjustment(amendment, actor=self.actor)
        amendment = validate_calendar_adjustment(amendment, actor=self.actor)
        publish_calendar_adjustment(amendment, actor=self.actor)
        session = next(item for item in get_effective_calendar_projection(self.calendar, school=self.school, public_only=True) if item["entry"].pk == self.session.pk)
        self.assertEqual(session["start_datetime"].date(), date(2040, 11, 2))
        context = build_calendar_document_context(self.calendar, school=self.school, programme=self.programme, academic_class=self.academic_class, semester_ids=[self.semester.id], public_only=True)
        self.assertEqual(next(item for item in context["projection"] if item["entry"].pk == self.session.pk)["start_datetime"].date(), date(2040, 11, 2))

    def test_school_scope_excludes_other_school(self):
        visible = get_effective_calendar_projection(self.calendar, school=self.school, public_only=True)
        hidden = get_effective_calendar_projection(self.calendar, school=self.other_school, public_only=True)
        self.assertIn(self.session.pk, [item["entry"].pk for item in visible])
        self.assertNotIn(self.session.pk, [item["entry"].pk for item in hidden])
