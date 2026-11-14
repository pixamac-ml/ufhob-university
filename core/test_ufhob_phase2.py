from dataclasses import replace
from datetime import date
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, RequestFactory
from django.http import Http404
from django.utils import timezone

from academics.models import AcademicClass, AcademicYear, Semester
from academics.permissions import can_view_academic_class
from academics.services.programme_structure_service import create_ue
from accounts.access_context import build_access_context
from accounts.dashboards.querysets import get_base_queryset
from accounts.models import InstitutionalProfile
from accounts.policy_v2 import decide
from accounts.scoping import access_scope, scoped, scope_queryset
from admissions.models import Candidature
from branches.models import Branch
from core.models import Institution, School, SchoolBranch
from formations.models import Cycle, Diploma, Filiere, Programme
from portal.views.views import _director_classes_queryset


class UFHOBPhase2Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        institution = Institution.objects.create(name="UFHOB", short_name="UFHOB", address="Test", city="Test", phone="000", email="test@example.invalid")
        cls.schools = [School.objects.create(institution=institution, code=code, short_name=code)
                       for code in ("ESMED", "ESGA", "FATEC")]
        cls.a = Branch.objects.create(name="Campus test A", slug="test-a", code="TSA", city="Test")
        cls.b = Branch.objects.create(name="Campus test B", slug="test-b", code="TSB", city="Test")
        for school in cls.schools:
            SchoolBranch.objects.create(school=school, branch=cls.a)
        SchoolBranch.objects.create(school=cls.schools[0], branch=cls.b)
        cycle = Cycle.objects.create(name="Cycle test", min_duration_years=1, max_duration_years=1)
        diploma = Diploma.objects.create(name="Diplôme test", level="superieur")
        cls.programmes = []
        for school in cls.schools:
            filiere = Filiere.objects.create(name=f"Test {school.code}")
            cls.programmes.append(Programme.objects.create(
                title=f"Programme test {school.code}", school=school, cycle=cycle,
                filiere=filiere, diploma_awarded=diploma, duration_years=1,
                short_description="Test", description="Test"))
        cls.year = AcademicYear.objects.create(name="2026-2027", start_date=date(2026, 9, 1), end_date=date(2027, 8, 31))
        cls.classes = [AcademicClass.objects.create(programme=p, branch=cls.a, academic_year=cls.year, level="L1") for p in cls.programmes]
        cls.other_campus_class = AcademicClass.objects.create(programme=cls.programmes[0], branch=cls.b, academic_year=cls.year, level="L1")
        cls.director = cls.make_user("director", "director_of_studies", cls.a, cls.schools[0])
        cls.global_user = cls.make_user("central", "executive_director")

    @staticmethod
    def make_user(name, position, branch=None, school=None, access_scope=""):
        user = get_user_model().objects.create_user(username=name, password="test-password")
        profile = user.profile
        profile.position = position
        profile.branch = branch
        profile.save()
        institutional = InstitutionalProfile.objects.get(user=user)
        institutional.school = school
        institutional.access_scope = access_scope
        institutional.save()
        return get_user_model().objects.get(pk=user.pk)

    def candidature(self, programme, branch=None):
        return Candidature.objects.create(programme=programme, branch=branch or self.a,
            academic_year=self.year.name, birth_date=date(2000, 1, 1), first_name="Test", last_name="Test",
            email="test@example.invalid", gender="female", phone="000", birth_place="Test")

    def test_a_same_campus_school_isolation_in_director_selector(self):
        context = build_access_context(self.director)
        self.assertEqual(context.scope, "SCHOOL_BRANCH")
        with access_scope(context):
            self.assertEqual(list(_director_classes_queryset(self.a)), [self.classes[0]])
            self.assertFalse(scoped(AcademicClass).filter(pk=self.classes[1].pk).exists())
        self.assertFalse(can_view_academic_class(self.director, self.classes[1]))
        self.assertTrue(can_view_academic_class(self.director, self.classes[0]))

    def test_b_global_context_retains_all_schools_and_campuses(self):
        context = build_access_context(self.global_user)
        self.assertEqual(context.scope, "GLOBAL")
        self.assertEqual(scope_queryset(AcademicClass.objects.all(), context=context).count(), 4)
        self.assertIsNone(context.school)

    def test_c_direct_offering_and_admission_reject_missing_schoolbranch(self):
        for model in ("class", "admission"):
            with self.subTest(model=model), self.assertRaises(ValidationError):
                if model == "class":
                    AcademicClass.objects.create(programme=self.programmes[1], branch=self.b, academic_year=self.year, level="L1")
                else:
                    self.candidature(self.programmes[1], self.b)
        self.assertFalse(Programme.objects.available_on(self.b).filter(pk=self.programmes[1].pk).exists())

    def test_d_adding_schoolbranch_enables_offering(self):
        SchoolBranch.objects.create(school=self.schools[1], branch=self.b)
        self.assertTrue(Programme.objects.available_on(self.b).filter(pk=self.programmes[1].pk).exists())
        self.candidature(self.programmes[1], self.b)

    def test_e_cross_school_workflow_is_denied(self):
        semester = Semester.objects.create(academic_class=self.classes[1], number=1)
        with self.assertRaises(PermissionDenied):
            create_ue(actor=self.director, semester=semester, code="FOREIGN", title="Test")

    def test_f_legacy_branch_only_context_still_works(self):
        user = self.make_user("legacy", "director_of_studies", self.a)
        context = build_access_context(user)
        self.assertTrue(context.is_valid)
        self.assertEqual(context.scope, "BRANCH")
        self.assertIsNone(context.school)
        self.assertEqual(scope_queryset(AcademicClass.objects.all(), context=context).count(), 3)

    def test_branch_only_helper_never_returns_another_campus_queryset(self):
        """Campus-only roles must be constrained even without a School scope."""
        campus_user = self.make_user("campus-only", "secretary", self.a)
        other_campus_user = self.make_user("other-campus", "secretary", self.b)
        context = build_access_context(campus_user)

        classes = scoped(AcademicClass, context=context)
        users = scoped(get_user_model(), context=context)

        self.assertEqual(classes.count(), 3)
        self.assertFalse(classes.filter(pk=self.other_campus_class.pk).exists())
        self.assertTrue(users.filter(pk=campus_user.pk).exists())
        self.assertFalse(users.filter(pk=other_campus_user.pk).exists())

    def test_g_school_wide_context_covers_two_campuses(self):
        user = self.make_user("school-wide", "director_of_studies", school=self.schools[0])
        context = build_access_context(user)
        self.assertTrue(context.is_valid)
        self.assertEqual(context.scope, "SCHOOL")
        self.assertEqual(scope_queryset(AcademicClass.objects.all(), context=context).count(), 2)

    def test_h_i_j_many_to_many_and_unique_pair(self):
        self.assertEqual(SchoolBranch.objects.filter(branch=self.a).count(), 3)
        self.assertEqual(SchoolBranch.objects.filter(school=self.schools[0]).count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SchoolBranch.objects.create(school=self.schools[0], branch=self.a)

    def test_policy_checks_school_and_campus_separately(self):
        context = build_access_context(self.director)
        self.assertFalse(decide(context, resource_school=self.schools[1], resource_branch=self.a).allowed)
        self.assertFalse(decide(context, resource_school=self.schools[0], resource_branch=self.b).allowed)
        self.assertTrue(decide(context, resource_school=self.schools[0], resource_branch=self.a).allowed)

    def test_admissions_shared_dashboard_queryset_is_scoped(self):
        from secretary.selectors import get_classes_queryset

        own = self.candidature(self.programmes[0])
        self.candidature(self.programmes[1])
        self.assertEqual(list(get_base_queryset(self.director, "candidature")), [own])
        self.assertEqual(get_base_queryset(self.global_user, "candidature").count(), 2)
        self.assertEqual(list(get_classes_queryset(user=self.director)), [self.classes[0]])

    def test_closed_campus_history_can_be_updated_but_new_records_rejected(self):
        old = self.candidature(self.programmes[0])
        SchoolBranch.objects.filter(school=self.schools[0], branch=self.a).update(is_active=False)
        old.admin_comment = "Historical record retained"
        old.save(update_fields=["admin_comment"])
        with self.assertRaises(ValidationError):
            self.candidature(self.programmes[0])

    def test_context_reset_prevents_request_leakage(self):
        with self.assertRaises(RuntimeError):
            with access_scope(build_access_context(self.director)):
                self.assertEqual(scoped(AcademicClass).count(), 1)
                raise RuntimeError("test")
        self.assertEqual(scoped(AcademicClass).count(), 4)

    def test_invalid_school_campus_context_fails_closed(self):
        SchoolBranch.objects.filter(school=self.schools[0], branch=self.a).update(is_active=False)
        context = build_access_context(self.director)
        self.assertFalse(context.is_valid)
        self.assertFalse(scope_queryset(AcademicClass.objects.all(), context=context).exists())

    def test_scope_paths_match_real_models(self):
        from django.apps import apps
        from accounts.scoping import SCOPE_PATHS

        context = build_access_context(self.director)
        for label in SCOPE_PATHS:
            with self.subTest(model=label):
                str(scope_queryset(apps.get_model(label).objects.all(), context=context).query)

    def test_htmx_detail_and_mutation_reject_foreign_id(self):
        from accounts.dashboards.htmx_candidatures import candidature_detail, candidature_accept

        user = self.make_user("admissions-scoped", "admissions", self.a, self.schools[0])
        foreign = self.candidature(self.programmes[1])
        for view, method in ((candidature_detail, "get"), (candidature_accept, "post")):
            request = getattr(RequestFactory(), method)("/", HTTP_HX_REQUEST="true")
            request.user = user
            with self.subTest(view=view.__name__), self.assertRaises(Http404):
                view(request, pk=foreign.pk)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, "submitted")

    def test_school_wide_programme_dashboard_aggregates_campuses(self):
        from portal.services.director.programme_service import _active_classes

        user = self.make_user("school-programmes", "director_of_studies", school=self.schools[0])
        with access_scope(build_access_context(user)):
            self.assertEqual(_active_classes(None).count(), 2)

    def test_registration_rejects_closed_schoolbranch(self):
        from inscriptions.models import Inscription

        candidature = self.candidature(self.programmes[0])
        candidature.status = "accepted"
        candidature.save()
        SchoolBranch.objects.filter(school=self.schools[0], branch=self.a).update(is_active=False)
        with self.assertRaises(ValidationError):
            Inscription.objects.create(candidature=candidature, amount_due=100, status="active")

    def test_programme_school_cannot_rewrite_existing_history(self):
        programme = self.programmes[0]
        programme.school = self.schools[1]
        with self.assertRaises(ValidationError):
            programme.save()

    def test_calendar_school_entries_and_common_events(self):
        from academics.models import AcademicCalendar, AcademicCalendarEntry
        from academics.services.calendar_service import create_calendar_entry, update_calendar_entry, create_calendar_revision

        calendar = AcademicCalendar.objects.create(branch=self.a, academic_year=self.year, created_by=self.global_user, updated_by=self.global_user)
        data = dict(calendar=calendar, event_type="other", title="Test",
                    start_datetime=timezone.make_aware(datetime(2026, 10, 1, 8)),
                    end_datetime=timezone.make_aware(datetime(2026, 10, 1, 9)))
        common = create_calendar_entry(actor=self.global_user, **data)
        own = create_calendar_entry(actor=self.director, target_scope="school", school=self.schools[0], **data)
        foreign = create_calendar_entry(actor=self.global_user, target_scope="school", school=self.schools[1], **data)
        self.assertEqual(set(scoped(AcademicCalendarEntry, user=self.director)), {common, own})
        with self.assertRaises(PermissionDenied):
            update_calendar_entry(foreign, actor=self.director, title="Invalid")
        with self.assertRaises(PermissionDenied):
            update_calendar_entry(common, actor=self.director, title="Invalid")

    def test_teacher_with_cross_school_assignments_is_not_forced_to_one_school(self):
        from portal.models import DirectorTeacherAssignment
        from accounts.models import Profile

        teacher = self.make_user("shared-teacher", "teacher", self.a)
        for academic_class in self.classes[:2]:
            DirectorTeacherAssignment.objects.create(teacher=teacher, academic_class=academic_class, branch=self.a, room_label="Test", planned_hours=1)
        self.assertTrue(scoped(Profile, user=self.director).filter(user=teacher).exists())
        self.assertEqual(DirectorTeacherAssignment.objects.filter(teacher=teacher).count(), 2)
        self.assertIsNone(build_access_context(teacher).school)

    def test_explicit_global_scope_is_separate_from_position(self):
        user = self.make_user("central-it", "it_support", access_scope="GLOBAL")
        context = build_access_context(user)
        self.assertTrue(context.is_valid)
        self.assertEqual(context.position, "it_support")
        self.assertEqual(scope_queryset(AcademicClass.objects.all(), context=context).count(), 4)

    def test_evaluation_campaign_preserves_school_boundary(self):
        from academics.models import AcademicCalendar, AcademicCalendarEntry
        from academics.services.evaluation_campaign_service import create_evaluation_campaign
        from accounts.scoping import object_in_scope

        calendar = AcademicCalendar.objects.create(branch=self.a, academic_year=self.year, status="validated",
            created_by=self.global_user, updated_by=self.global_user)
        data = dict(calendar=calendar, event_type="exam_session", title="Test",
            start_datetime=timezone.make_aware(datetime(2026, 10, 1, 8)),
            end_datetime=timezone.make_aware(datetime(2026, 10, 1, 9)),
            created_by=self.global_user, updated_by=self.global_user)
        common = AcademicCalendarEntry.objects.create(**data)
        with self.assertRaises(PermissionDenied):
            create_evaluation_campaign(actor=self.director, calendar_entry=common)
        own_entry = AcademicCalendarEntry.objects.create(target_scope="school", school=self.schools[0], **data)
        campaign = create_evaluation_campaign(actor=self.director, calendar_entry=own_entry)
        self.assertEqual(list(campaign.scopes.values_list("academic_class_id", flat=True)), [self.classes[0].pk])
        self.assertTrue(object_in_scope(campaign, user=self.director))
        mixed = create_evaluation_campaign(actor=self.global_user, calendar_entry=common)
        self.assertFalse(object_in_scope(mixed, user=self.director))
