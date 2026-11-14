from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from academics.models import AcademicScheduleEvent, EvaluationRequirement


class TeacherDashboardV1ModelTests(SimpleTestCase):
    def test_online_event_can_be_planned_before_provider_creates_a_link(self):
        event = AcademicScheduleEvent(is_online=True, meeting_status="not_required")

        event.clean()

        self.assertEqual(event.meeting_status, "pending_provider")

    def test_submitted_subject_requires_a_file_or_composed_content(self):
        requirement = EvaluationRequirement(
            submission_status=EvaluationRequirement.SUBMISSION_SUBMITTED,
        )

        with self.assertRaises(ValidationError) as raised:
            requirement.clean()

        self.assertIn("submission_status", raised.exception.message_dict)
