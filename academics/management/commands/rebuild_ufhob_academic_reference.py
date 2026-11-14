"""Install the 2026-2027 FATEC/ESGA academic reference without demo data.

This is deliberately narrower than ``reset_business_data``: it never deletes
users, profiles, inscriptions or payments.  Older operational academic rows are
archived so their institutional trace remains recoverable from the local backup.
"""

from __future__ import annotations

from datetime import date, datetime, time

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from academics.models import (
    AcademicCalendar,
    AcademicCalendarEntry,
    AcademicClass,
    AcademicEnrollment,
    AcademicScheduleEvent,
    AcademicYear,
    EvaluationCampaign,
    EC,
    Semester,
    UE,
)
from branches.models import Branch
from core.models import School, SchoolBranch
from formations.models import Cycle, Filiere, Programme
from portal.models import DirectorTeacherAssignment
from students.models import Student
from academics.services.calendar_service import validate_calendar
from academics.services.evaluation_campaign_service import create_evaluation_campaign


YEAR_NAME = "2026-2027"
BRANCH_CODE = "MBG"
YEAR_START = date(2026, 10, 5)
YEAR_END = date(2027, 8, 31)
CALENDAR_TITLE = "Calendrier académique 2026-2027 — Moribabougou (provisoire à confirmer)"

# Programme is cycle + filière in the current shared engine.  There is no
# separate academic-class code field, so the human class name is canonical.
REFERENCE = {
    "FATEC": (
        ("IG", "Informatique de Gestion", "Informatique de gestion"),
        ("GL", "Génie Logiciel", "Génie logiciel"),
        ("RT", "Réseau et Télécommunication", "Réseau et télécommunication"),
        ("AM", "Audiovisuel Multimédia", "Audiovisuel multimédia"),
    ),
    "ESGA": (
        ("FC", "Finance / Comptabilité", "Finance / Comptabilité"),
        ("GEA", "Gestion des Entreprises et Administration", "Gestion des entreprises et administration"),
        ("GRH", "Gestion des Ressources Humaines", "Gestion des ressources humaines"),
        ("MC", "Marketing Communication", "Marketing communication"),
    ),
}

CYCLES = (
    ("DUT", (("DUT 1", (1, 2)), ("DUT 2", (3, 4)))),
    ("Licence", (("Licence 1", (1, 2)), ("Licence 2", (3, 4)), ("Licence 3", (5, 6)))),
    ("Master", (("Master 1", (7, 8)), ("Master 2", (9, 10)))),
)

# These dates are an explicitly provisional operational calendar for the DG
# demonstration.  They are not a substitute for an approved institutional UE/EC
# catalogue or an official board decision.
PROVISIONAL_OBSERVATION = (
    "Calendrier operationnel provisoire de recette/demonstration : a confirmer "
    "et, si necessaire, a reviser par la gouvernance academique."
)
ODD_SEMESTERS = (1, 3, 5, 7, 9)
EVEN_SEMESTERS = (2, 4, 6, 8, 10)

CALENDAR_MILESTONES = (
    ("Periode 1 - semestres impairs (provisoire)", AcademicCalendarEntry.EVENT_SEMESTER_START, date(2026, 10, 5), date(2027, 2, 6)),
    ("Pause institutionnelle de fin d'annee (provisoire)", AcademicCalendarEntry.EVENT_HOLIDAY, date(2026, 12, 21), date(2027, 1, 3)),
    ("Revisions - semestre impair (provisoire)", AcademicCalendarEntry.EVENT_OTHER, date(2027, 2, 8), date(2027, 2, 13)),
    ("Transition intersemestrielle (provisoire)", AcademicCalendarEntry.EVENT_OTHER, date(2027, 3, 1), date(2027, 3, 7)),
    ("Periode 2 - semestres pairs (provisoire)", AcademicCalendarEntry.EVENT_SEMESTER_START, date(2027, 3, 8), date(2027, 7, 3)),
    ("Revisions - semestre pair (provisoire)", AcademicCalendarEntry.EVENT_OTHER, date(2027, 7, 5), date(2027, 7, 10)),
    ("Deliberations - semestre pair (provisoire)", AcademicCalendarEntry.EVENT_JURY, date(2027, 7, 26), date(2027, 7, 31)),
    ("Deliberations finales et documents (provisoire)", AcademicCalendarEntry.EVENT_RESULT_PUBLICATION, date(2027, 8, 23), date(2027, 8, 31)),
)


class Command(BaseCommand):
    help = (
        "Reconstruit le référentiel académique 2026-2027 FATEC/ESGA de "
        "Moribabougou, sans supprimer utilisateurs, inscriptions ni paiements."
    )

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True, help="Utilisateur traçable exécutant la maintenance.")
        parser.add_argument("--apply", action="store_true", help="Applique la reconstruction ; sans ce flag, affiche seulement le plan.")

    def handle(self, *args, **options):
        actor = get_user_model().objects.filter(username=options["actor"], is_active=True).first()
        if actor is None:
            raise CommandError("L'acteur indiqué est introuvable ou inactif.")
        branch = Branch.objects.filter(code=BRANCH_CODE, is_active=True).first()
        if branch is None:
            raise CommandError("Campus Moribabougou (MBG) introuvable ou inactif.")

        plan = self._plan(branch)
        self.stdout.write(
            "Plan : {classes} classes, {semesters} semestres, {legacy_classes} anciennes classes à archiver, "
            "{legacy_enrollments} inscriptions académiques à archiver.".format(**plan)
        )
        if not options["apply"]:
            self.stdout.write(self.style.WARNING("Dry-run : aucune donnée modifiée."))
            return

        with transaction.atomic():
            year = self._ensure_year()
            schools = self._ensure_schools_and_availability(branch)
            programmes = self._normalise_catalogue(schools)
            legacy = self._archive_legacy_operational_data(year=year, branch=branch, actor=actor)
            created = self._ensure_classes_and_semesters(
                year=year, branch=branch, schools=schools, programmes=programmes
            )
            calendar, calendar_created = self._ensure_provisional_calendar(
                year=year, branch=branch, actor=actor
            )
            campaign_count = self._ensure_evaluation_campaigns(calendar=calendar, actor=actor)

        self.stdout.write(self.style.SUCCESS("Référentiel académique reconstruit."))
        self.stdout.write(f"Classes créées : {created['classes']}; semestres créés : {created['semesters']}.")
        self.stdout.write(
            "Anciennes classes archivées : {classes}; enrollments archivés : {enrollments}; "
            "affectations archivées : {assignments}; séances annulées : {events}; "
            "UE archivées : {ues}; EC archivés : {ecs}; campagnes annulées : {campaigns}; "
            "calendriers archivés : {calendars}.".format(**legacy)
        )
        self.stdout.write(
            f"Calendrier provisoire : #{calendar.pk} ({'créé' if calendar_created else 'réutilisé'})."
        )

    def _plan(self, branch):
        classes = sum(len(levels) for _, levels in CYCLES) * sum(len(rows) for rows in REFERENCE.values())
        legacy_classes = self._legacy_classes(
            year=AcademicYear.objects.filter(name=YEAR_NAME).first(), branch=branch
        )
        return {
            "classes": classes,
            "semesters": classes * 2,
            "legacy_classes": legacy_classes.filter(is_active=True, is_archived=False).count(),
            "legacy_enrollments": AcademicEnrollment.objects.filter(
                academic_class__in=legacy_classes, status=AcademicEnrollment.STATUS_ACTIVE
            ).count(),
        }

    def _legacy_classes(self, *, year, branch):
        if year is None:
            return AcademicClass.objects.none()
        canonical_names = {
            (programme.pk, level, f"{level} — {display_name}")
            for school_code, rows in REFERENCE.items()
            for _, _, display_name in rows
            for cycle_name, levels in CYCLES
            for level, _ in levels
            for programme in [Programme.objects.get(
                school__code=school_code,
                cycle__name=cycle_name,
                filiere__name=display_name,
                is_archived=False,
            )]
        }
        candidates = AcademicClass.objects.filter(
            academic_year=year, branch=branch, programme__school__code__in=REFERENCE
        )
        return AcademicClass.objects.filter(
            pk__in=[
                row.pk for row in candidates.select_related("programme")
                if (row.programme_id, row.level, row.name) not in canonical_names
            ]
        )

    def _ensure_year(self):
        AcademicYear.objects.exclude(name=YEAR_NAME).filter(is_active=True).update(is_active=False)
        year, _ = AcademicYear.objects.get_or_create(
            name=YEAR_NAME,
            defaults={"start_date": YEAR_START, "end_date": YEAR_END, "is_active": True},
        )
        year.start_date = YEAR_START
        year.end_date = YEAR_END
        year.is_active = True
        year.save(update_fields=["start_date", "end_date", "is_active"])
        return year

    def _ensure_schools_and_availability(self, branch):
        schools = {}
        for code in REFERENCE:
            school = School.objects.filter(code=code, is_active=True).first()
            if school is None:
                raise CommandError(f"École active {code} introuvable : le catalogue institutionnel doit être installé d'abord.")
            SchoolBranch.objects.update_or_create(
                school=school, branch=branch, defaults={"is_active": True}
            )
            schools[code] = school
        return schools

    def _normalise_catalogue(self, schools):
        programmes = {}
        for school_code, filieres in REFERENCE.items():
            for _, stored_filiere_name, display_filiere_name in filieres:
                filiere = Filiere.objects.filter(
                    name__in=(stored_filiere_name, display_filiere_name), is_active=True
                ).first()
                if filiere is None:
                    raise CommandError(f"Filière active introuvable : {stored_filiere_name}.")
                if filiere.name != display_filiere_name:
                    filiere.name = display_filiere_name
                    filiere.save(update_fields=["name"])
                for cycle_name, _ in CYCLES:
                    cycle = Cycle.objects.filter(name=cycle_name, is_active=True).first()
                    if cycle is None:
                        raise CommandError(f"Cycle actif introuvable : {cycle_name}.")
                    programme = Programme.objects.filter(
                        school=schools[school_code], cycle=cycle, filiere=filiere, is_archived=False
                    ).first()
                    if programme is None:
                        raise CommandError(
                            f"Programme institutionnel introuvable : {cycle_name} — {display_filiere_name} ({school_code})."
                        )
                    expected_title = f"{cycle_name} — {display_filiere_name}"
                    if programme.title != expected_title:
                        programme.title = expected_title
                        programme.save(update_fields=["title", "updated_at"])
                    programmes[(school_code, cycle_name, display_filiere_name)] = programme
        return programmes

    def _archive_legacy_operational_data(self, *, year, branch, actor):
        now = timezone.now()
        legacy_classes = self._legacy_classes(year=year, branch=branch)
        legacy_enrollments = AcademicEnrollment.objects.filter(
            academic_class__in=legacy_classes, status=AcademicEnrollment.STATUS_ACTIVE
        )
        enrollment_ids = list(legacy_enrollments.values_list("pk", flat=True))

        Student.objects.filter(current_academic_enrollment_id__in=enrollment_ids).update(
            current_academic_enrollment=None
        )
        enrollment_count = legacy_enrollments.update(
            status=AcademicEnrollment.STATUS_ARCHIVED,
            is_active=False,
            is_archived=True,
            archived_at=now,
        )
        assignment_count = DirectorTeacherAssignment.objects.filter(
            academic_class__in=legacy_classes
        ).exclude(status=DirectorTeacherAssignment.STATUS_ARCHIVED).update(
            status=DirectorTeacherAssignment.STATUS_ARCHIVED,
            updated_at=now,
        )
        event_count = AcademicScheduleEvent.objects.filter(academic_class__in=legacy_classes).exclude(
            status=AcademicScheduleEvent.STATUS_CANCELLED
        ).update(
            status=AcademicScheduleEvent.STATUS_CANCELLED,
            is_active=False,
            updated_at=now,
        )
        class_count = legacy_classes.filter(is_active=True).update(
            is_active=False,
            is_archived=True,
            archived_at=now,
        )
        legacy_semesters = Semester.objects.filter(academic_class__in=legacy_classes)
        ue_count = UE.objects.filter(semester__in=legacy_semesters).exclude(
            structure_status=UE.STRUCTURE_ARCHIVED
        ).update(structure_status=UE.STRUCTURE_ARCHIVED, archived_at=now)
        ec_count = EC.objects.filter(ue__semester__in=legacy_semesters).exclude(
            structure_status=EC.STRUCTURE_ARCHIVED
        ).update(structure_status=EC.STRUCTURE_ARCHIVED, archived_at=now)

        old_calendars = AcademicCalendar.objects.filter(branch=branch, academic_year=year).exclude(
            official_title=CALENDAR_TITLE
        ).exclude(status=AcademicCalendar.STATUS_ARCHIVED)
        campaign_count = EvaluationCampaign.objects.filter(calendar_entry__calendar__in=old_calendars).exclude(
            status=EvaluationCampaign.STATUS_CANCELLED
        ).update(status=EvaluationCampaign.STATUS_CANCELLED, updated_at=now)
        old_calendars.update(status=AcademicCalendar.STATUS_ARCHIVED, updated_by=actor, updated_at=now)
        AcademicCalendarEntry.objects.filter(calendar__in=old_calendars).update(
            status=AcademicCalendarEntry.STATUS_ARCHIVED,
            updated_by=actor,
            updated_at=now,
        )
        return {
            "classes": class_count,
            "enrollments": enrollment_count,
            "assignments": assignment_count,
            "events": event_count,
            "ues": ue_count,
            "ecs": ec_count,
            "campaigns": campaign_count,
            "calendars": old_calendars.count(),
        }

    def _ensure_classes_and_semesters(self, *, year, branch, schools, programmes):
        created = {"classes": 0, "semesters": 0}
        for school_code, rows in REFERENCE.items():
            for _, _, display_filiere_name in rows:
                for cycle_name, levels in CYCLES:
                    programme = programmes[(school_code, cycle_name, display_filiere_name)]
                    for level, semester_numbers in levels:
                        academic_class, class_created = AcademicClass.objects.get_or_create(
                            programme=programme,
                            branch=branch,
                            academic_year=year,
                            level=level,
                            name=f"{level} — {display_filiere_name}",
                            defaults={
                                "study_level": "MASTER" if cycle_name == "Master" else "LICENCE",
                                "validation_threshold": None,
                                "is_active": True,
                                "is_archived": False,
                            },
                        )
                        if not academic_class.is_active or academic_class.is_archived:
                            academic_class.is_active = True
                            academic_class.is_archived = False
                            academic_class.archived_at = None
                            academic_class.save(update_fields=["is_active", "is_archived", "archived_at"])
                        created["classes"] += int(class_created)
                        for number in semester_numbers:
                            _, semester_created = Semester.objects.get_or_create(
                                academic_class=academic_class,
                                number=number,
                                defaults={
                                    "status": Semester.STATUS_DRAFT,
                                    "total_required_credits": "0.00",
                                },
                            )
                            created["semesters"] += int(semester_created)
        return created

    def _legacy_calendar_bootstrap(self, *, year, branch, actor):
        calendar = AcademicCalendar.objects.filter(
            branch=branch, academic_year=year, official_title=CALENDAR_TITLE
        ).first()
        created = calendar is None
        if calendar is None:
            version = (AcademicCalendar.objects.filter(branch=branch, academic_year=year).aggregate(
                value=Max("version")
            )["value"] or 0) + 1
            calendar = AcademicCalendar.objects.create(
                branch=branch,
                academic_year=year,
                version=version,
                official_title=CALENDAR_TITLE,
                general_observations=PROVISIONAL_OBSERVATION + (
                    "Dates des semestres, sessions, jurys et publications à confirmer par la gouvernance académique."
                ),
                status=AcademicCalendar.STATUS_DRAFT,
                created_by=actor,
                updated_by=actor,
            )
        else:
            calendar.status = AcademicCalendar.STATUS_DRAFT
            calendar.updated_by = actor
            calendar.general_observations = (
                "Dates des semestres, sessions, jurys et publications à confirmer par la gouvernance académique."
            )
            calendar.save(update_fields=["status", "updated_by", "general_observations", "updated_at"])

        entries = (
            ("Début de l'année académique 2026-2027", AcademicCalendarEntry.EVENT_ACADEMIC_START, YEAR_START),
            ("Fin de l'année académique 2026-2027", AcademicCalendarEntry.EVENT_ACADEMIC_END, YEAR_END),
        )
        for title, event_type, day in entries:
            start = timezone.make_aware(datetime.combine(day, time.min))
            end = timezone.make_aware(datetime.combine(day, time.max))
            AcademicCalendarEntry.objects.update_or_create(
                calendar=calendar,
                title=title,
                defaults={
                    "event_type": event_type,
                    "start_datetime": start,
                    "end_datetime": end,
                    "all_day": True,
                    "target_scope": AcademicCalendarEntry.SCOPE_BRANCH,
                    "is_blocking": event_type == AcademicCalendarEntry.EVENT_ACADEMIC_START,
                    "status": AcademicCalendarEntry.STATUS_DRAFT,
                    "updated_by": actor,
                    "created_by": actor,
                },
            )
        return calendar, created

    # Kept separately from the initial reference rebuild so a rerun is
    # idempotent and never reopens a validated provisional calendar.
    def _ensure_provisional_calendar(self, *, year, branch, actor):
        calendar = AcademicCalendar.objects.filter(
            branch=branch, academic_year=year, official_title=CALENDAR_TITLE
        ).first()
        created = calendar is None
        if calendar is None:
            version = (AcademicCalendar.objects.filter(branch=branch, academic_year=year).aggregate(
                value=Max("version")
            )["value"] or 0) + 1
            calendar = AcademicCalendar.objects.create(
                branch=branch,
                academic_year=year,
                version=version,
                official_title=CALENDAR_TITLE,
                general_observations=PROVISIONAL_OBSERVATION,
                status=AcademicCalendar.STATUS_DRAFT,
                created_by=actor,
                updated_by=actor,
            )
        if calendar.status == AcademicCalendar.STATUS_DRAFT:
            calendar.general_observations = PROVISIONAL_OBSERVATION
            calendar.updated_by = actor
            calendar.save(update_fields=["general_observations", "updated_by", "updated_at"])
            self._upsert_calendar_entries(calendar=calendar, actor=actor)
            # EvaluationCampaign is intentionally created through its service:
            # validated is the shared engine's prerequisite, whereas the title
            # and observation preserve the provisional nature of these dates.
            validate_calendar(calendar, actor=actor)
        return calendar, created

    def _upsert_calendar_entries(self, *, calendar, actor):
        entries = [
            ("D\u00e9but de l'ann\u00e9e acad\u00e9mique 2026-2027", AcademicCalendarEntry.EVENT_ACADEMIC_START, YEAR_START, YEAR_START),
            ("Fin de l'ann\u00e9e acad\u00e9mique 2026-2027", AcademicCalendarEntry.EVENT_ACADEMIC_END, YEAR_END, YEAR_END),
            *CALENDAR_MILESTONES,
        ]
        entries.extend(
            (
                f"Session normale S{number} - semestre {'impair' if number % 2 else 'pair'} (provisoire)",
                AcademicCalendarEntry.EVENT_EXAM_SESSION,
                date(2027, 2, 15) if number % 2 else date(2027, 7, 12),
                date(2027, 2, 27) if number % 2 else date(2027, 7, 24),
            )
            for number in (*ODD_SEMESTERS, *EVEN_SEMESTERS)
        )
        entries.extend(
            (
                f"Session de rattrapage S{number} (provisoire)",
                AcademicCalendarEntry.EVENT_RETAKE_SESSION,
                date(2027, 8, 9), date(2027, 8, 21),
            )
            for number in (*ODD_SEMESTERS, *EVEN_SEMESTERS)
        )
        for title, event_type, start_day, end_day in entries:
            AcademicCalendarEntry.objects.update_or_create(
                calendar=calendar,
                title=title,
                defaults={
                    "event_type": event_type,
                    "description": PROVISIONAL_OBSERVATION,
                    "start_datetime": timezone.make_aware(datetime.combine(start_day, time.min)),
                    "end_datetime": timezone.make_aware(datetime.combine(end_day, time.max)),
                    "all_day": True,
                    "target_scope": AcademicCalendarEntry.SCOPE_BRANCH,
                    "is_blocking": False,
                    "status": AcademicCalendarEntry.STATUS_DRAFT,
                    "updated_by": actor,
                    "created_by": actor,
                },
            )

    def _ensure_evaluation_campaigns(self, *, calendar, actor):
        if calendar.status not in {AcademicCalendar.STATUS_VALIDATED, AcademicCalendar.STATUS_PUBLISHED}:
            raise CommandError("Le calendrier operationnel doit etre valide avant de preparer les sessions.")
        created = 0
        publication_entry = AcademicCalendarEntry.objects.get(
            calendar=calendar,
            title="Deliberations finales et documents (provisoire)",
        )
        # Branch-wide containers are unsuitable for a school-scoped DE: their
        # scope includes a second school and the permission layer correctly
        # rejects them.  Retire only empty provisional containers, then create
        # one scoped session per school and semester.
        EvaluationCampaign.objects.filter(
            calendar_entry__calendar=calendar,
            calendar_entry__target_scope=AcademicCalendarEntry.SCOPE_BRANCH,
            calendar_entry__event_type__in=[
                AcademicCalendarEntry.EVENT_EXAM_SESSION,
                AcademicCalendarEntry.EVENT_RETAKE_SESSION,
            ],
        ).exclude(status=EvaluationCampaign.STATUS_CANCELLED).update(
            status=EvaluationCampaign.STATUS_CANCELLED,
        )
        for school in School.objects.filter(code__in=REFERENCE, is_active=True).order_by("code"):
            for kind, number in (
                *(('normal', item) for item in (*ODD_SEMESTERS, *EVEN_SEMESTERS)),
                *(('retake', item) for item in (*ODD_SEMESTERS, *EVEN_SEMESTERS)),
            ):
                if kind == "normal":
                    entry_title = f"{school.code} - Session normale S{number} (provisoire)"
                    title = f"{school.code} - Session normale provisoire S{number} - Moribabougou 2026-2027"
                    event_type = AcademicCalendarEntry.EVENT_EXAM_SESSION
                    start_day = date(2027, 2, 15) if number % 2 else date(2027, 7, 12)
                    end_day = date(2027, 2, 27) if number % 2 else date(2027, 7, 24)
                else:
                    entry_title = f"{school.code} - Session de rattrapage S{number} (provisoire)"
                    title = f"{school.code} - Session de rattrapage provisoire S{number} - Moribabougou 2026-2027"
                    event_type = AcademicCalendarEntry.EVENT_RETAKE_SESSION
                    start_day, end_day = date(2027, 8, 9), date(2027, 8, 21)
                entry, _ = AcademicCalendarEntry.objects.update_or_create(
                    calendar=calendar,
                    title=entry_title,
                    defaults={
                        "school": school,
                        "event_type": event_type,
                        "description": PROVISIONAL_OBSERVATION,
                        "start_datetime": timezone.make_aware(datetime.combine(start_day, time.min)),
                        "end_datetime": timezone.make_aware(datetime.combine(end_day, time.max)),
                        "all_day": True,
                        "target_scope": AcademicCalendarEntry.SCOPE_SCHOOL,
                        "is_blocking": False,
                        "status": AcademicCalendarEntry.STATUS_DRAFT,
                        "updated_by": actor,
                        "created_by": actor,
                    },
                )
                campaign = EvaluationCampaign.objects.filter(calendar_entry=entry).exclude(
                    status=EvaluationCampaign.STATUS_CANCELLED
                ).first()
                if campaign is None:
                    create_evaluation_campaign(
                        actor=actor,
                        calendar_entry=entry,
                        title=title,
                        publication_entry=publication_entry,
                        semester_number=number,
                    )
                    created += 1
                    continue
                self._reconcile_campaign_scopes(campaign=campaign)
                if campaign.result_publication_entry_id != publication_entry.id:
                    campaign.result_publication_entry = publication_entry
                    campaign.save(update_fields=["result_publication_entry", "updated_at"])
        return created

    def _reconcile_campaign_scopes(self, *, campaign):
        """Keep pre-existing containers aligned with their semester number.

        Early demonstration containers could contain a class whose curriculum
        did not actually have the selected semester.  They must not become a
        cross-level entry point merely because the branch is shared.
        """
        if not campaign.semester_number:
            return
        campaign.scopes.exclude(semester__number=campaign.semester_number).delete()
