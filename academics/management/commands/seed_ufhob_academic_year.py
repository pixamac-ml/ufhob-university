"""Idempotent, scoped demonstration data for the UFHOB 2026-2027 year."""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import MD5PasswordHasher
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import (
    AcademicClass, AcademicEnrollment, AcademicScheduleEvent, AcademicYear,
    EC, ECChapter, ECContent, ECGrade, Semester, UE,
)
from academics.services.schedule_service import create_schedule_event
from admissions.models import Candidature
from accounts.models import InstitutionalProfile, Profile
from core.models import School, SchoolBranch
from formations.models import Programme
from inscriptions.models import Inscription
from inscriptions.services import create_inscription_from_candidature
from payments.models import Payment, PaymentAgent
from portal.models import DirectorTeacherAssignment
from students.models import Student


User = get_user_model()
YEAR_NAME = "2026-2027"
SCHOOL_CODES = ("ESMED", "ESGA", "FATEC")
DATA_PREFIX = "ufhob.demo.2026"
DEMO_PASSWORD_HASH = MD5PasswordHasher().encode("UFHOB-demo-2026", "ufhob-2026-demo")
MINIMAL_RECEIPT_PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Count 0 >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"


class Command(BaseCommand):
    help = "Peuple de facon idempotente l'annee demo UFHOB 2026-2027 (ESMED, ESGA, FATEC)."

    def add_arguments(self, parser):
        parser.add_argument("--year", default=YEAR_NAME)

    def handle(self, *args, **options):
        year_name = options["year"]
        if year_name != YEAR_NAME:
            raise CommandError("Cette commande est volontairement limitee au dataset 2026-2027.")

        self.counts = {key: 0 for key in (
            "classes", "semesters", "ues", "ecs", "staff", "students", "inscriptions",
            "payments", "contents", "schedules", "grades", "candidatures", "assignments",
        )}
        academic_year = self._academic_year()
        schools = self._schools()
        programmes = self._select_programmes(schools)
        for school in schools:
            # A school is an independent, restartable unit.  Keeping its work
            # atomic prevents a half-created academic chain without holding
            # one database transaction across signal-driven access updates.
            with transaction.atomic():
                programme, branch = programmes[school.code]
                staff = self._staff_for_school(school, branch)
                academic_class, semesters, ecs = self._academic_structure(
                    academic_year, school, programme, branch
                )
                self._assign_teachers(academic_class, ecs, staff, academic_year)
                self._students_and_finance(
                    academic_year, school, programme, branch, academic_class, staff
                )
                self._course_content(ecs[0])
                self._timetable(academic_year, academic_class, branch, ecs, staff["teachers"])
                self._grades(academic_class, ecs)

        self.stdout.write(self.style.SUCCESS("Dataset UFHOB 2026-2027 termine (idempotent)."))
        for key, value in self.counts.items():
            self.stdout.write(f" - {key}: {value}")

    def _academic_year(self):
        year, created = AcademicYear.objects.get_or_create(
            name=YEAR_NAME,
            defaults={"start_date": date(2026, 10, 1), "end_date": date(2027, 7, 31), "is_active": True},
        )
        if created:
            AcademicYear.objects.exclude(pk=year.pk).update(is_active=False)
        return year

    def _schools(self):
        schools = list(School.objects.filter(code__in=SCHOOL_CODES, is_active=True).order_by("code"))
        if {school.code for school in schools} != set(SCHOOL_CODES):
            raise CommandError("ESMED, ESGA et FATEC doivent deja exister et etre actives.")
        return schools

    def _select_programmes(self, schools):
        selected = {}
        for school in schools:
            availability = SchoolBranch.objects.filter(school=school, is_active=True, branch__is_active=True)
            branch_ids = list(availability.values_list("branch_id", flat=True))
            programme = Programme.objects.filter(
                school=school, is_active=True, is_archived=False
            ).order_by("title").first()
            if programme is None or not branch_ids:
                raise CommandError(f"Aucun programme/campus actif disponible pour {school.code}.")
            # Selecting the first existing SchoolBranch makes availability an enforced domain fact.
            selected[school.code] = (programme, availability.order_by("branch__code").first().branch)
        return selected

    def _user(self, username, first_name, last_name, *, position, role, school, branch, scope):
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "first_name": first_name, "last_name": last_name,
                "email": f"{username}@demo.ufhob.invalid", "is_staff": position != "student", "is_active": True,
            },
        )
        if created:
            user.password = DEMO_PASSWORD_HASH
            user.save(update_fields=["password"])
            self.counts["staff"] += position != "student"
        # These are deliberate bulk updates.  Profile/InstitutionalProfile
        # post-save signals synchronise groups one field at a time and can
        # deadlock when a whole demo team is provisioned in one transaction.
        # The seed owns these synthetic accounts and writes their final,
        # complete assignment atomically instead.
        Profile.objects.get_or_create(user=user)
        Profile.objects.filter(user=user).update(
            role=role, user_type="staff", position=position, branch=branch,
            employee_code=username.upper()[:30], employment_status="active", is_public=False,
        )
        InstitutionalProfile.objects.bulk_create([
            InstitutionalProfile(
                user=user, position=position, school=school, branch=branch,
                access_scope=scope, employee_code=username.upper()[:30], employment_status="active",
            )
        ], ignore_conflicts=True)
        InstitutionalProfile.objects.filter(user=user).update(
            position=position, school=school, branch=branch, access_scope=scope,
            employee_code=username.upper()[:30], employment_status="active",
        )
        return user

    def _staff_for_school(self, school, branch):
        base = f"{DATA_PREFIX}.{school.code.lower()}"
        director = self._user(f"{base}.de", "Direction", school.code, position="director_of_studies", role="executive", school=school, branch=branch, scope="SCHOOL_BRANCH")
        manager = self._user(f"{base}.gestion", "Gestion", school.code, position="branch_manager", role="finance", school=school, branch=branch, scope="SCHOOL_BRANCH")
        self._user(f"{base}.secretariat", "Secretariat", school.code, position="secretary", role="admissions", school=school, branch=branch, scope="SCHOOL_BRANCH")
        self._user(f"{base}.informatique", "Support", school.code, position="it_support", role="superadmin", school=school, branch=branch, scope="SCHOOL_BRANCH")
        self._user(f"{base}.surveillance", "Surveillance", school.code, position="academic_supervisor", role="executive", school=school, branch=branch, scope="SCHOOL_BRANCH")
        teachers = []
        for index in range(1, 5):
            teachers.append(self._user(
                f"{base}.enseignant{index}", f"Enseignant {index}", school.code,
                position="teacher", role="teacher", school=school, branch=branch, scope="SCHOOL_BRANCH",
            ))
        if school.code == "ESMED":
            self._user(f"{base}.moniteur", "Moniteur", school.code, position="moniteur", role="teacher", school=school, branch=branch, scope="SCHOOL_BRANCH")
        PaymentAgent.objects.get_or_create(user=manager, defaults={"branch": branch, "is_active": True})
        return {"director": director, "manager": manager, "teachers": teachers}

    def _academic_structure(self, year, school, programme, branch):
        level = f"{programme.cycle.name} 1"
        name = f"{school.code} - {programme.cycle.name} 1 - {year.name}"
        academic_class, created = AcademicClass.objects.get_or_create(
            programme=programme, branch=branch, academic_year=year, level=level, name=name,
            defaults={"study_level": "LICENCE", "validation_threshold": Decimal("10.00"), "is_active": True},
        )
        self.counts["classes"] += created
        semesters, ecs = [], []
        for number in (1, 2):
            semester, created = Semester.objects.get_or_create(
                academic_class=academic_class, number=number,
                defaults={"status": Semester.STATUS_NORMAL_ENTRY, "total_required_credits": Decimal("12.00")},
            )
            if semester.status == Semester.STATUS_DRAFT:
                semester.status = Semester.STATUS_NORMAL_ENTRY
                semester.save(update_fields=["status"])
            self.counts["semesters"] += created
            semesters.append(semester)
            for unit in range(1, 3):
                code = f"UFHOB26-{school.code}-{programme.pk}-S{number}U{unit}"
                ue, ue_created = UE.objects.get_or_create(
                    semester=semester, code=code,
                    defaults={"title": f"Unite fondamentale {unit} - {programme.title}", "structure_status": UE.STRUCTURE_COMPLETE},
                )
                self.counts["ues"] += ue_created
                for component in range(1, 3):
                    title = f"{programme.cycle.name} : module {number}.{unit}.{component}"
                    ec, ec_created = EC.objects.get_or_create(
                        ue=ue, title=title,
                        defaults={"credit_required": Decimal("3.00"), "coefficient": Decimal("2.00"), "structure_status": EC.STRUCTURE_COMPLETE},
                    )
                    self.counts["ecs"] += ec_created
                    ecs.append(ec)
        return academic_class, semesters, ecs

    def _assign_teachers(self, academic_class, ecs, staff, year):
        for index, ec in enumerate(ecs):
            teacher = staff["teachers"][index % len(staff["teachers"])]
            _, created = DirectorTeacherAssignment.objects.get_or_create(
                teacher=teacher, scope_type=DirectorTeacherAssignment.SCOPE_EC,
                academic_class=academic_class, semester=ec.ue.semester, ue=ec.ue, ec=ec,
                starts_on=year.start_date, ends_on=year.end_date,
                defaults={"branch": academic_class.branch, "room_label": f"Salle {101 + index}", "planned_hours": Decimal("20.00"), "created_by": staff["director"], "updated_by": staff["director"]},
            )
            self.counts["assignments"] += created

    def _students_and_finance(self, year, school, programme, branch, academic_class, staff):
        due = programme.get_inscription_amount_for_year(1)
        if due <= 0:
            raise CommandError(f"Le programme {programme.title} n'a pas de frais reels pour l'annee 1.")
        agent = PaymentAgent.objects.get(user=staff["manager"])
        for index in range(1, 6):
            username = f"{DATA_PREFIX}.etudiant.{school.code.lower()}.{index}"
            email = f"{username}@demo.ufhob.invalid"
            candidature, cand_created = Candidature.objects.get_or_create(
                email=email, programme=programme, academic_year=year.name,
                defaults={"branch": branch, "entry_year": 1, "first_name": f"Etudiant{index}", "last_name": school.code, "birth_date": date(2000 + index, 1, index), "birth_place": "Donnee synthetique", "gender": "female" if index % 2 else "male", "phone": f"+2237000{school.id:02d}{index:02d}", "status": "accepted", "admin_comment": "Dataset de demonstration UFHOB 2026-2027."},
            )
            self.counts["candidatures"] += cand_created
            inscription = create_inscription_from_candidature(candidature=candidature, amount_due=due, academic_class=academic_class, status=Inscription.STATUS_PARTIAL, actor=staff["director"])
            self.counts["inscriptions"] += int(inscription.created_at >= timezone.now() - timedelta(seconds=2))
            user, user_created = User.objects.get_or_create(username=username, defaults={"email": email, "first_name": candidature.first_name, "last_name": candidature.last_name, "is_active": True})
            if user_created or not user.has_usable_password():
                user.password = DEMO_PASSWORD_HASH
                user.save(update_fields=["password"])
            Profile.objects.get_or_create(user=user)
            Profile.objects.filter(user=user).update(
                role="student", user_type="staff", position="student", is_public=False
            )
            student, student_created = Student.objects.get_or_create(
                inscription=inscription, defaults={"user": user, "matricule": f"UFHOB26-{school.code}-{index:03d}", "is_active": True}
            )
            self.counts["students"] += student_created
            enrollment, _ = AcademicEnrollment.objects.get_or_create(
                inscription=inscription,
                defaults={"student": user, "programme": programme, "branch": branch, "academic_year": year, "academic_class": academic_class, "status": AcademicEnrollment.STATUS_ACTIVE},
            )
            if student.current_academic_enrollment_id != enrollment.id:
                student.current_academic_enrollment = enrollment
                student.save(update_fields=["current_academic_enrollment"])
            amounts = {1: [due // 2], 2: [due], 3: [due // 3, due // 3], 4: [due // 4], 5: [due // 2]}[index]
            with self._minimal_demo_receipts():
                for payment_number, amount in enumerate(amounts, start=1):
                    reference = f"UFHOB26-{school.code}-{index}-{payment_number}"
                    payment, created = Payment.objects.get_or_create(
                        reference=reference,
                        defaults={"inscription": inscription, "agent": agent, "amount": amount, "method": Payment.METHOD_CASH, "status": Payment.STATUS_VALIDATED},
                    )
                    self.counts["payments"] += created
        # Three non-enrolled admission states exercise admissions dashboards without contaminating student data.
        for state_index, status in enumerate(("submitted", "under_review", "to_complete"), start=1):
            email = f"{DATA_PREFIX}.candidature.{school.code.lower()}.{status}@demo.ufhob.invalid"
            _, created = Candidature.objects.get_or_create(
                email=email, programme=programme, academic_year=year.name,
                defaults={"branch": branch, "entry_year": 1, "first_name": "Candidat", "last_name": f"{school.code}{state_index}", "birth_date": date(2001, state_index, 1), "birth_place": "Donnee synthetique", "gender": "male", "phone": f"+2237100{school.id:02d}{state_index:02d}", "status": status, "admin_comment": "Dataset de demonstration UFHOB 2026-2027."},
            )
            self.counts["candidatures"] += created

    def _course_content(self, ec):
        chapter, _ = ECChapter.objects.get_or_create(ec=ec, title="Repere pedagogique 2026-2027", defaults={"order": 1})
        _, created = ECContent.objects.get_or_create(
            chapter=chapter, title="Note pedagogique de demonstration",
            defaults={"content_type": ECContent.CONTENT_TYPE_TEXT, "text_content": "Support textuel synthetique destine a la recette fonctionnelle UFHOB 2026-2027.", "order": 1, "status": ECContent.STATUS_PUBLISHED, "is_active": True, "published_at": timezone.now()},
        )
        self.counts["contents"] += created

    def _timetable(self, year, academic_class, branch, ecs, teachers):
        week_start = date(2026, 10, 5)
        for index, ec in enumerate(ecs[:4]):
            start = timezone.make_aware(datetime.combine(week_start + timedelta(days=index), time(8, 0)))
            end = timezone.make_aware(datetime.combine(week_start + timedelta(days=index), time(10, 0)))
            title = f"UFHOB 2026-2027 - {ec.title}"
            if AcademicScheduleEvent.objects.filter(academic_class=academic_class, ec=ec, start_datetime=start, end_datetime=end).exists():
                continue
            create_schedule_event(user=teachers[index % len(teachers)], title=title, description="Seance de demonstration academique UFHOB.", event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE, academic_class=academic_class, ec=ec, teacher=teachers[index % len(teachers)], branch=branch, academic_year=year, start_datetime=start, end_datetime=end, status=AcademicScheduleEvent.STATUS_PLANNED, location=f"Salle {academic_class.id}-{index + 1}", is_online=False, meeting_link="", is_active=True)
            self.counts["schedules"] += 1

    def _grades(self, academic_class, ecs):
        enrollment = AcademicEnrollment.objects.filter(academic_class=academic_class).order_by("id").first()
        if not enrollment:
            return
        for index, ec in enumerate(ecs[:4]):
            grade, created = ECGrade.objects.get_or_create(enrollment=enrollment, ec=ec, defaults={"normal_score": Decimal("12.00") + index})
            self.counts["grades"] += created

    @contextmanager
    def _minimal_demo_receipts(self):
        """Avoid the optional native WeasyPrint stack for synthetic receipts only."""
        import payments.models as payment_models

        original = payment_models.generate_esfe_pdf
        payment_models.generate_esfe_pdf = lambda *args, **kwargs: MINIMAL_RECEIPT_PDF
        try:
            yield
        finally:
            payment_models.generate_esfe_pdf = original
