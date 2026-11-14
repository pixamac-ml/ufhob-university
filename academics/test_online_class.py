from datetime import date, datetime, time, timedelta
import hashlib
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from xml.etree import ElementTree

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Profile
from academics.models import AcademicClass, AcademicEnrollment, AcademicScheduleEvent, AcademicYear, EC, OnlineClassRecording, Semester, UE
from academics.services.online_class_service import (
    BBB_ROLE_MODERATOR,
    BBB_ROLE_VIEWER,
    BigBlueButtonProvider,
    OnlineClassNotReady,
    ProviderMeetingStatus,
    get_online_session_access_state,
    get_student_online_session_join_url,
    prepare_teacher_online_session,
)
from academics.services.teaching_metrics import consolidated_interval_minutes, teaching_time_metrics
from academics.services.recording_service import get_recording_download_url_for_user
from admissions.models import Candidature
from branches.models import Branch
from formations.models import Cycle, Diploma, Filiere, Programme
from inscriptions.models import Inscription
from students.models import Student


User = get_user_model()


@override_settings(
    BBB_API_URL="https://bbb.example.test/bigbluebutton/api",
    BBB_SECRET="server-only-secret",
    BBB_API_TIMEOUT=3,
    BBB_MEETING_ID_PREFIX="esfe-test",
    BASE_URL="https://core.example.test",
)
class BigBlueButtonProviderTests(SimpleTestCase):
    def setUp(self):
        self.provider = BigBlueButtonProvider()
        self.event = SimpleNamespace(
            pk=42,
            online_provider="",
            external_meeting_id="",
            duration_minutes=90,
            ec=SimpleNamespace(title="Ethique professionnelle"),
            academic_class=SimpleNamespace(display_name="L1 Sage-femme"),
        )
        self.user = SimpleNamespace(
            pk=7,
            get_full_name=lambda: "Awa Test",
            get_username=lambda: "awa.test",
        )

    def test_checksum_is_server_side_and_role_is_fixed_in_signed_join_url(self):
        join_url = self.provider.build_join_url(
            event=self.event,
            user=self.user,
            role=BBB_ROLE_VIEWER,
        )
        parsed = urlsplit(join_url)
        params = parse_qs(parsed.query)
        self.assertNotIn("role", params)
        self.assertEqual(
            params["password"],
            [self.provider._meeting_password(self.provider._meeting_id(self.event), BBB_ROLE_VIEWER)],
        )
        self.assertNotIn("server-only-secret", join_url)

        unsigned_query = urlencode(
            {
                "meetingID": self.provider._meeting_id(self.event),
                "fullName": "Awa Test",
                "password": self.provider._meeting_password(
                    self.provider._meeting_id(self.event), BBB_ROLE_VIEWER
                ),
                "userID": "ufhob_7",
                "redirect": "true",
            }
        )
        expected = hashlib.sha1(
            f"join{unsigned_query}server-only-secret".encode("utf-8")
        ).hexdigest()
        self.assertEqual(params["checksum"], [expected])

    def test_status_retrieves_running_meeting_information(self):
        running = ElementTree.fromstring(
            b"<response><returncode>SUCCESS</returncode><running>true</running></response>"
        )
        info = ElementTree.fromstring(
            b"<response><returncode>SUCCESS</returncode><participantCount>2</participantCount><createTime>123</createTime></response>"
        )
        with patch.object(self.provider, "_api_call", side_effect=[running, info]) as api_call:
            status = self.provider.get_status(event=self.event)
        self.assertTrue(status.is_running)
        self.assertEqual(status.status, "running")
        self.assertEqual(status.participant_count, 2)
        self.assertEqual([call.args[0] for call in api_call.call_args_list], ["isMeetingRunning", "getMeetingInfo"])

    def test_network_errors_are_translated_without_leaking_configuration(self):
        with patch("academics.services.online_class_service.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(ValidationError) as raised:
                self.provider._api_call("getMeetings", {})
        self.assertNotIn("server-only-secret", str(raised.exception))
        self.assertIn("indisponible", str(raised.exception))

    def test_connectivity_check_uses_a_signed_read_only_api_call(self):
        response = ElementTree.fromstring(
            b"<response><returncode>SUCCESS</returncode><running>false</running></response>"
        )
        with patch.object(self.provider, "_api_call", return_value=response) as api_call:
            health = self.provider.check_connectivity()
        self.assertEqual(health, {"ok": True, "reason": ""})
        api_call.assert_called_once_with(
            "isMeetingRunning", {"meetingID": "ufhob-healthcheck"}
        )

    def test_invalid_client_selected_role_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.provider.build_join_url(event=self.event, user=self.user, role="OWNER")

    def test_bbb_create_registers_the_authenticated_ufhob_meeting_end_url(self):
        response = ElementTree.fromstring(
            b"<response><returncode>SUCCESS</returncode><meetingID>bbb-42</meetingID></response>"
        )
        ready = ProviderMeetingStatus("bbb-42", "ready", False)
        with patch.object(self.provider, "_api_call", return_value=response) as api_call, patch.object(
            self.provider, "get_status_by_id", return_value=ready
        ):
            self.provider.create_or_get(event=self.event)

        create_params = api_call.call_args.args[1]
        self.assertEqual(
            create_params["meetingEndedURL"],
            "https://core.example.test/portal/online/events/42/ended/",
        )

    def test_end_uses_the_server_calculated_moderator_password(self):
        response = ElementTree.fromstring(b"<response><returncode>SUCCESS</returncode></response>")
        with patch.object(self.provider, "_api_call", return_value=response) as api_call:
            self.provider.end_meeting(event=self.event)
        params = api_call.call_args.args[1]
        self.assertEqual(params["meetingID"], self.provider._meeting_id(self.event))
        self.assertEqual(
            params["password"],
            self.provider._meeting_password(self.provider._meeting_id(self.event), BBB_ROLE_MODERATOR),
        )


class TeachingTimeMetricsTests(SimpleTestCase):
    def test_reconnections_are_consolidated_and_capped_by_official_session(self):
        start = timezone.now()
        event = SimpleNamespace(
            duration_minutes=120,
            start_datetime=start,
            end_datetime=start + timedelta(minutes=120),
        )
        intervals = [
            (start, start + timedelta(minutes=40)),
            (start + timedelta(minutes=35), start + timedelta(minutes=90)),
            (start + timedelta(minutes=92), start + timedelta(minutes=240)),
        ]
        self.assertEqual(consolidated_interval_minutes(intervals), 238)
        execution_logs = [SimpleNamespace(started_at=a, ended_at=b, is_completed=True) for a, b in intervals]
        metrics = teaching_time_metrics(event=event, execution_logs=execution_logs)
        self.assertEqual(metrics["planned_minutes"], 120)
        self.assertEqual(metrics["actual_minutes"], 238)
        self.assertEqual(metrics["validatable_minutes"], 120)
        self.assertEqual(metrics["overrun_minutes"], 118)

    def test_missing_evidence_never_becomes_planned_or_payable_time(self):
        start = timezone.now()
        event = SimpleNamespace(
            duration_minutes=120,
            start_datetime=start,
            end_datetime=start + timedelta(minutes=120),
        )
        metrics = teaching_time_metrics(event=event)
        self.assertIsNone(metrics["actual_minutes"])
        self.assertEqual(metrics["validatable_minutes"], 0)


@override_settings(DEBUG=True, ONLINE_CLASSROOM_TIME_BYPASS=False)
class OnlineSessionAccessStateTests(SimpleTestCase):
    def test_temporal_states_are_upcoming_active_then_ended_without_bypass(self):
        now = timezone.now()
        event = SimpleNamespace(
            start_datetime=now + timedelta(minutes=20),
            end_datetime=now + timedelta(minutes=80),
        )
        self.assertEqual(get_online_session_access_state(event=event, now=now)["state"], "upcoming")

        event.start_datetime = now - timedelta(minutes=20)
        event.end_datetime = now + timedelta(minutes=20)
        self.assertEqual(get_online_session_access_state(event=event, now=now)["state"], "active")

        event.start_datetime = now - timedelta(minutes=80)
        event.end_datetime = now - timedelta(minutes=20)
        self.assertEqual(get_online_session_access_state(event=event, now=now)["state"], "ended")

    def test_exact_scheduled_end_is_already_closed(self):
        now = timezone.now()
        event = SimpleNamespace(
            start_datetime=now - timedelta(hours=2),
            end_datetime=now,
        )
        self.assertEqual(get_online_session_access_state(event=event, now=now)["state"], "ended")


class FakeOnlineClassroomProvider:
    name = "bigbluebutton"

    def __init__(self, *, running=True):
        self.running = running
        self.roles = []
        self.create_calls = 0

    def create_or_get(self, *, event):
        self.create_calls += 1
        return ProviderMeetingStatus("esfe_test_event", "running", True, participant_count=1)

    def get_status(self, *, event):
        return ProviderMeetingStatus(
            "esfe_test_event",
            "running" if self.running else "not_started",
            self.running,
        )

    def build_join_url(self, *, event, user, role):
        self.roles.append((user.pk, role))
        return f"https://bbb.example.test/join?event={event.pk}&role={role}"


@override_settings(AUTH_POLICY_V2_ENABLED=False)
class OnlineClassWorkflowTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(name="Annexe BBB", code="BBB", slug="annexe-bbb")
        self.other_branch = Branch.objects.create(name="Annexe autre", code="BBX", slug="annexe-bbb-autre")
        cycle = Cycle.objects.create(name="Cycle BBB", min_duration_years=1, max_duration_years=3)
        diploma = Diploma.objects.create(name="Diplome BBB", level="superieur")
        filiere = Filiere.objects.create(name="Filiere BBB")
        self.programme = Programme.objects.create(
            title="Programme BBB",
            filiere=filiere,
            cycle=cycle,
            diploma_awarded=diploma,
            duration_years=3,
            short_description="POC",
            description="POC BigBlueButton",
        )
        today = timezone.localdate()
        self.year = AcademicYear.objects.create(
            name="2048-2049",
            start_date=today - timedelta(days=30),
            end_date=today + timedelta(days=300),
            is_active=True,
        )
        self.academic_class = AcademicClass.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.year,
            level="L1",
            study_level="LICENCE",
            is_active=True,
        )
        semester = Semester.objects.create(academic_class=self.academic_class, number=1)
        ue = UE.objects.create(semester=semester, code="BBB101", title="UE BBB")
        self.ec = EC.objects.create(ue=ue, title="Cours BBB", credit_required=3, coefficient=2)
        self.director = self._user("bbb_director", "director_of_studies", self.branch)
        self.teacher = self._user("bbb_teacher", "teacher", self.branch)
        self.other_teacher = self._user("bbb_other_teacher", "teacher", self.branch)
        self.monitor = self._user("bbb_monitor", "moniteur", self.branch)
        self.student = self._user("bbb_student", "student", self.branch)
        self.other_student = self._user("bbb_other_student", "student", self.other_branch)
        self._enroll(self.student, "BBB-STUDENT-1")

        start = timezone.now() - timedelta(minutes=15)
        self.event = AcademicScheduleEvent.objects.create(
            title="Cours en ligne POC",
            event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
            academic_class=self.academic_class,
            ec=self.ec,
            teacher=self.teacher,
            branch=self.branch,
            academic_year=self.year,
            start_datetime=start,
            end_datetime=start + timedelta(hours=2),
            status=AcademicScheduleEvent.STATUS_PLANNED,
            is_online=True,
            created_by=self.director,
            updated_by=self.director,
        )

    def _user(self, username, position, branch):
        user = User.objects.create_user(username=username, password="pass1234")
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.position = position
        profile.role = "student" if position == "student" else "teacher"
        profile.branch = branch
        profile.employment_status = "active"
        profile.save()
        return user

    def _enroll(self, user, matricule):
        candidature = Candidature.objects.create(
            programme=self.programme,
            branch=self.branch,
            academic_year=self.year.name,
            first_name="Etudiant",
            last_name="POC",
            birth_date=date(2000, 1, 1),
            birth_place="Bamako",
            gender="female",
            phone="70000000",
            email=f"{user.username}@example.test",
            status="accepted",
        )
        inscription = Inscription.objects.create(
            candidature=candidature,
            academic_class=self.academic_class,
            amount_due=100000,
            status=Inscription.STATUS_ACTIVE,
        )
        Student.objects.create(user=user, inscription=inscription, matricule=matricule)
        return AcademicEnrollment.objects.create(
            inscription=inscription,
            student=user,
            programme=self.programme,
            branch=self.branch,
            academic_year=self.year,
            academic_class=self.academic_class,
            status=AcademicEnrollment.STATUS_ACTIVE,
            is_active=True,
        )

    def test_assigned_teacher_starts_idempotently_as_moderator(self):
        provider = FakeOnlineClassroomProvider()
        first = prepare_teacher_online_session(
            teacher=self.teacher,
            branch=self.branch,
            event_id=self.event.pk,
            provider=provider,
        )
        second = prepare_teacher_online_session(
            teacher=self.teacher,
            branch=self.branch,
            event_id=self.event.pk,
            provider=provider,
        )
        self.event.refresh_from_db()
        self.assertEqual(provider.create_calls, 2)
        self.assertEqual(first.join_url, second.join_url)
        self.assertEqual(provider.roles, [(self.teacher.pk, BBB_ROLE_MODERATOR)] * 2)
        self.assertEqual(self.event.external_meeting_id, "esfe_test_event")
        self.assertEqual(self.event.meeting_status, "running")
        self.assertEqual(self.event.meeting_link, "")

    def test_unassigned_teacher_cannot_start_room(self):
        provider = FakeOnlineClassroomProvider()
        with self.assertRaises(ValidationError):
            prepare_teacher_online_session(
                teacher=self.other_teacher,
                branch=self.branch,
                event_id=self.event.pk,
                provider=provider,
            )
        self.assertEqual(provider.create_calls, 0)

    def test_official_monitor_replacement_starts_as_moderator(self):
        self.event.original_teacher = self.teacher
        self.event.teacher = self.monitor
        self.event.save(update_fields=["original_teacher", "teacher", "updated_at"])
        provider = FakeOnlineClassroomProvider()
        prepare_teacher_online_session(
            teacher=self.monitor,
            branch=self.branch,
            event_id=self.event.pk,
            provider=provider,
        )
        self.assertEqual(provider.roles, [(self.monitor.pk, BBB_ROLE_MODERATOR)])

    def test_enrolled_student_is_viewer_and_other_student_is_refused(self):
        provider = FakeOnlineClassroomProvider()
        join_url = get_student_online_session_join_url(
            student=self.student,
            event_id=self.event.pk,
            provider=provider,
        )
        self.assertIn(f"role={BBB_ROLE_VIEWER}", join_url)
        self.assertEqual(provider.roles, [(self.student.pk, BBB_ROLE_VIEWER)])
        with self.assertRaises(ValidationError):
            get_student_online_session_join_url(
                student=self.other_student,
                event_id=self.event.pk,
                provider=provider,
            )

    def test_student_cannot_join_before_teacher_starts(self):
        with self.assertRaises(OnlineClassNotReady):
            get_student_online_session_join_url(
                student=self.student,
                event_id=self.event.pk,
                provider=FakeOnlineClassroomProvider(running=False),
            )

    def test_unauthorized_student_endpoint_is_forbidden(self):
        self.client.force_login(self.other_student)
        response = self.client.get(
            reverse("portal_student:online_session_open", args=[self.event.pk])
        )
        self.assertEqual(response.status_code, 403)

    def test_endpoints_ignore_client_role_and_preserve_server_roles(self):
        provider = FakeOnlineClassroomProvider()
        self.client.force_login(self.teacher)
        with patch(
            "academics.services.online_class_service.get_online_classroom_provider",
            return_value=provider,
        ):
            response = self.client.post(
                reverse("accounts_portal:teacher_online_session_prepare", args=[self.event.pk]),
                {"role": BBB_ROLE_VIEWER},
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"role={BBB_ROLE_MODERATOR}", response["Location"])

        provider.roles.clear()
        self.client.force_login(self.student)
        with patch(
            "academics.services.online_class_service.get_online_classroom_provider",
            return_value=provider,
        ):
            response = self.client.get(
                reverse("portal_student:online_session_open", args=[self.event.pk]),
                {"role": BBB_ROLE_MODERATOR},
            )
        self.assertEqual(response.status_code, 302)
        self.assertIn(f"role={BBB_ROLE_VIEWER}", response["Location"])

    def test_student_dashboard_shows_join_action_without_persisted_join_url(self):
        self.client.force_login(self.student)
        response = self.client.get(
            reverse("portal_student:timetable_partial"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rejoindre le cours en ligne")

    def test_teacher_dashboard_shows_start_action_for_online_event(self):
        self.client.force_login(self.teacher)
        response = self.client.get(
            reverse("accounts_portal:portal_teacher"),
            {"section": "schedule", "week_start": timezone.localdate().isoformat()},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Demarrer le cours en ligne")

    @override_settings(DEBUG=False, ONLINE_CLASSROOM_TIME_BYPASS=False)
    def test_ended_session_is_visible_but_time_gate_refuses_join(self):
        self.event.start_datetime = timezone.now() - timedelta(hours=2)
        self.event.end_datetime = timezone.now() - timedelta(hours=1)
        self.event.save(update_fields=["start_datetime", "end_datetime", "updated_at"])
        access = get_online_session_access_state(event=self.event)
        self.assertFalse(access["is_available"])
        self.assertEqual(access["state"], "ended")
        with self.assertRaises(ValidationError):
            prepare_teacher_online_session(
                teacher=self.teacher,
                branch=self.branch,
                event_id=self.event.pk,
                provider=FakeOnlineClassroomProvider(),
            )

    @override_settings(DEBUG=True, ONLINE_CLASSROOM_TIME_BYPASS=True)
    def test_local_time_bypass_never_reopens_an_ended_session(self):
        self.event.start_datetime = timezone.now() - timedelta(hours=2)
        self.event.end_datetime = timezone.now() - timedelta(hours=1)
        self.event.save(update_fields=["start_datetime", "end_datetime", "updated_at"])
        access = get_online_session_access_state(event=self.event)
        self.assertFalse(access["is_available"])
        self.assertEqual(access["state"], "ended")
        with self.assertRaises(ValidationError):
            prepare_teacher_online_session(
                teacher=self.teacher,
                branch=self.branch,
                event_id=self.event.pk,
                provider=FakeOnlineClassroomProvider(),
            )
        with self.assertRaises(ValidationError):
            get_student_online_session_join_url(
                student=self.student,
                event_id=self.event.pk,
                provider=FakeOnlineClassroomProvider(),
            )
        with self.assertRaises(ValidationError):
            get_student_online_session_join_url(
                student=self.other_student,
                event_id=self.event.pk,
                provider=FakeOnlineClassroomProvider(),
            )

    def test_authorized_student_receives_a_short_lived_recording_url_only_after_publication(self):
        recording = OnlineClassRecording.objects.create(
            event=self.event,
            provider="bigbluebutton",
            meeting_id="bbb-event-1",
            provider_recording_id="bbb-recording-1",
            object_key="recordings/2048-2049/bbb/class-1/event-1/recording.mp4",
            status=OnlineClassRecording.STATUS_TRANSFERRED,
            published_at=timezone.now(),
        )
        with patch(
            "academics.services.recording_service.build_recording_download_url",
            return_value="https://b2.example.test/short-lived",
        ) as build_url:
            url = get_recording_download_url_for_user(user=self.student, recording=recording)
        self.assertEqual(url, "https://b2.example.test/short-lived")
        build_url.assert_called_once_with(
            object_key=recording.object_key,
            force_download=False,
        )

    def test_out_of_scope_student_never_receives_a_recording_url(self):
        recording = OnlineClassRecording.objects.create(
            event=self.event,
            provider="bigbluebutton",
            meeting_id="bbb-event-2",
            provider_recording_id="bbb-recording-2",
            object_key="recordings/2048-2049/bbb/class-1/event-1/recording.mp4",
            status=OnlineClassRecording.STATUS_TRANSFERRED,
            published_at=timezone.now(),
        )
        with self.assertRaises(PermissionDenied):
            get_recording_download_url_for_user(user=self.other_student, recording=recording)
