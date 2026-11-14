"""Read-only BigBlueButton readiness check for presentation preflight."""

from django.core.management.base import BaseCommand
from django.db import connection

from academics.models import AcademicEnrollment, AcademicScheduleEvent
from academics.services.online_class_service import BigBlueButtonProvider


class Command(BaseCommand):
    help = "Verifie la configuration et la connectivite BBB sans creer de reunion."

    def add_arguments(self, parser):
        parser.add_argument(
            "--preflight",
            action="store_true",
            help="Ajoute les controles lecture seule des donnees de presentation.",
        )

    def _result(self, label, ok, reason=""):
        state = self.style.SUCCESS("OK") if ok else self.style.ERROR("FAIL")
        self.stdout.write(f"{label:.<30} {state}")
        if reason:
            self.stdout.write(f"Reason: {reason}")
        return ok

    def _preflight(self):
        try:
            connection.ensure_connection()
            database_ok = True
        except Exception:
            database_ok = False
        if not database_ok:
            return [
                ("Django database", False),
                ("Presentation teacher", False),
                ("Presentation student", False),
                ("Teaching assignment", False),
                ("Presentation class", False),
            ]
        teacher = (
            AcademicScheduleEvent.objects.filter(
                is_active=True,
                is_online=True,
                teacher__isnull=False,
            )
            .select_related("teacher", "academic_class", "academic_year", "branch")
            .order_by("start_datetime", "pk")
            .first()
        )
        teacher_ok = teacher is not None
        student_ok = False
        class_ok = teacher_ok and teacher.academic_class_id is not None
        assignment_ok = teacher_ok and teacher.teacher_id is not None
        if teacher_ok:
            student_ok = AcademicEnrollment.objects.filter(
                academic_class_id=teacher.academic_class_id,
                academic_year_id=teacher.academic_year_id,
                branch_id=teacher.branch_id,
                is_active=True,
                status=AcademicEnrollment.STATUS_ACTIVE,
            ).exists()
        return [
            ("Django database", database_ok),
            ("Presentation teacher", teacher_ok),
            ("Presentation student", student_ok),
            ("Teaching assignment", assignment_ok),
            ("Presentation class", class_ok),
        ]

    def handle(self, *args, **options):
        provider = BigBlueButtonProvider()
        configured = provider.is_configured
        ok = self._result("BBB configuration", configured)
        health = provider.check_connectivity() if configured else {"ok": False, "reason": "configuration"}
        ok = self._result("BBB provider", bool(health["ok"]), health["reason"]) and ok
        ok = self._result("Authentication/checksum", bool(health["ok"]), health["reason"]) and ok
        ok = self._result("API response", bool(health["ok"]), health["reason"]) and ok
        if options["preflight"]:
            for label, passed in self._preflight():
                ok = self._result(label, passed) and ok
        if ok:
            self.stdout.write(self.style.SUCCESS("READY"))
        else:
            self.stdout.write(self.style.ERROR("NOT READY"))
