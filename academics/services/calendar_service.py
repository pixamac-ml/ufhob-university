from accounts.scoping import scoped
from accounts.scoping import resolve_context, require_object_scope
from datetime import datetime
import re

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

from academics.models import (
    AcademicCalendar,
    AcademicCalendarAdjustment,
    AcademicCalendarDisruption,
    AcademicCalendarEntry,
    AcademicScheduleEvent,
    AcademicYear,
)
from academics.permissions.calendar_permissions import (
    is_global_calendar_user,
    require_calendar_access,
    require_calendar_branch_access,
)


CALENDAR_MUTABLE_FIELDS = {
    "official_title",
    "administrative_reference",
    "general_observations",
}
ENTRY_MUTABLE_FIELDS = {
    "school",
    "title",
    "description",
    "event_type",
    "start_datetime",
    "end_datetime",
    "all_day",
    "target_scope",
    "programme",
    "academic_class",
    "semester",
    "color",
    "icon",
    "is_blocking",
    "status",
}


def _require_common_calendar_scope(actor):
    from accounts.scoping import resolve_context
    from django.core.exceptions import PermissionDenied

    context = resolve_context(user=actor)
    # A school-wide profile has no physical campus selected and therefore
    # cannot alter the campus calendar shared by all its schools. During an
    # HTTP request, resolve_operational_context promotes a legitimate school
    # user who selected an authorised campus to SCHOOL_BRANCH. The previous
    # check used context.school and rejected that valid operational context.
    if getattr(context, "scope", None) == "SCHOOL":
        raise PermissionDenied("La gestion du calendrier commun exige un périmètre campus ou université.")


def _require_entry_school_access(entry, actor, target_semesters=()):
    context = resolve_context(user=actor)
    if not getattr(context, "school", None):
        return
    # Selecting a campus narrows a school assignment; it does not authorize
    # edits to events shared with the other schools on that campus.
    if not context.is_valid or entry.target_scope == AcademicCalendarEntry.SCOPE_BRANCH:
        from django.core.exceptions import PermissionDenied

        raise PermissionDenied("Une affectation école ne permet pas de modifier un événement commun au campus.")
    for obj in (entry.school, entry.programme, entry.academic_class, entry.semester, *target_semesters):
        if obj is not None:
            require_object_scope(obj, user=actor)


@transaction.atomic
def activate_academic_year(*, academic_year, actor, reason=""):
    """Ouvre l'annee institutionnelle unique utilisee par les workflows academiques."""
    from academic_cycle.services.audit_service import log_action

    if not is_global_calendar_user(actor):
        raise ValidationError(
            "L'activation d'une annee academique est reservee a la Direction generale."
        )

    locked_years = AcademicYear.objects.select_for_update().order_by("id")
    target_year = locked_years.filter(pk=academic_year.pk).first()
    if target_year is None:
        raise ValidationError("Annee academique introuvable.")

    previous_active = list(
        locked_years.filter(is_active=True)
        .exclude(pk=target_year.pk)
        .values_list("name", flat=True)
    )
    AcademicYear.objects.filter(is_active=True).exclude(pk=target_year.pk).update(
        is_active=False
    )
    if not target_year.is_active:
        target_year.is_active = True
        target_year.save(update_fields=["is_active"])

    log_action(
        actor,
        "academic_year.activated",
        target_year,
        old_values={
            "is_active": academic_year.is_active,
            "previous_active_years": previous_active,
        },
        new_values={"is_active": True},
        reason=(reason or "Activation institutionnelle depuis le dashboard DG.").strip(),
        academic_year=target_year,
    )
    return target_year


@transaction.atomic
def create_academic_year(*, actor, name, start_date, end_date, activate=False):
    """Cree la reference AcademicYear existante, avec activation DG optionnelle."""
    from academic_cycle.services.audit_service import log_action

    if not is_global_calendar_user(actor):
        raise ValidationError(
            "La creation d'une annee academique est reservee a la Direction generale."
        )
    name = (name or "").strip()
    if not re.fullmatch(r"\d{4}-\d{4}", name):
        raise ValidationError(
            "Le nom doit respecter le format AAAA-AAAA (exemple : 2027-2028)."
        )

    # Lock the catalogue before deciding whether this is the first usable
    # institutional year.  The first year must be active immediately: without
    # it, a clean installation cannot open a branch calendar or any academic
    # workflow after the DG has clicked the ordinary "Créer" action.
    locked_years = AcademicYear.objects.select_for_update()
    if locked_years.filter(name=name).exists():
        raise ValidationError(f"L'annee academique « {name} » existe deja.")
    should_activate = not locked_years.filter(is_active=True).exists()
    academic_year = AcademicYear(
        name=name,
        start_date=start_date,
        end_date=end_date,
        is_active=should_activate,
    )
    academic_year.full_clean()
    academic_year.save()
    log_action(
        actor,
        "academic_year.created",
        academic_year,
        new_values={
            "name": academic_year.name,
            "start_date": academic_year.start_date.isoformat(),
            "end_date": academic_year.end_date.isoformat(),
            "is_active": academic_year.is_active,
        },
        reason="Creation institutionnelle depuis le dashboard DG.",
        academic_year=academic_year,
    )
    if activate and not academic_year.is_active:
        academic_year = activate_academic_year(
            academic_year=academic_year,
            actor=actor,
            reason="Creation et activation institutionnelle depuis le dashboard DG.",
        )
    return academic_year


def get_calendar_document_reference(calendar):
    """Référence stable d'une version de calendrier, sans saisie manuelle."""
    if calendar.administrative_reference.strip():
        return calendar.administrative_reference.strip()
    return f"ESFE/{(calendar.branch.code or 'ANNEXE').upper()}/CAL/{calendar.academic_year.name}/V{calendar.version:02d}"


def _academic_year_dependencies(academic_year):
    """Liste les objets lies a une annee ; une suppression doit etre sans effet de bord."""
    from django.core.exceptions import ObjectDoesNotExist

    dependencies = []
    for relation in academic_year._meta.related_objects:
        accessor = relation.get_accessor_name()
        if not accessor or accessor.endswith("+"):
            continue
        try:
            related = getattr(academic_year, accessor)
            exists = related.exists() if hasattr(related, "exists") else related is not None
        except ObjectDoesNotExist:
            exists = False
        if exists:
            dependencies.append(relation.related_model._meta.verbose_name_plural)
    return dependencies


@transaction.atomic
def delete_academic_year(*, academic_year, actor, confirmation, branch=None):
    """Purge une annee inactive et ses calendriers de preparation, sans toucher a l'active."""
    from academic_cycle.services.audit_service import log_action

    confirmation = (confirmation or "").strip()
    if confirmation != academic_year.name:
        raise ValidationError(
            f"Pour confirmer la suppression, saisissez exactement : {academic_year.name}."
        )

    if not is_global_calendar_user(actor):
        raise ValidationError(
            "La suppression d'une annee academique est reservee a la Direction generale."
        )
    if academic_year.is_active:
        raise ValidationError(
            "L'annee academique active est protegee. Seul le Directeur General peut "
            "autoriser sa suppression."
        )

    # Une annee inactive peut etre abandonnee avec ses calendriers de travail.
    # Les avenants et perturbations protegent le calendrier : on les retire
    # explicitement avant les entrees et le calendrier lui-meme.
    calendars = academic_year.calendars.all()
    if branch is not None:
        calendars = calendars.filter(branch=branch)
    calendars = list(calendars)
    for calendar in calendars:
        calendar.adjustments.all().delete()
        calendar.disruptions.all().delete()
        calendar.entries.all().delete()
    if calendars:
        calendar_ids = [calendar.id for calendar in calendars]
        scoped(AcademicCalendar, user=actor).filter(revision_of_id__in=calendar_ids).update(
            revision_of=None
        )
        scoped(AcademicCalendar, user=actor).filter(id__in=calendar_ids).delete()

    dependencies = _academic_year_dependencies(academic_year)
    if dependencies:
        readable = ", ".join(sorted(set(dependencies))[:5])
        raise ValidationError(
            "Cette annee contient encore des donnees academiques qui ne peuvent pas "
            f"etre effacees automatiquement : {readable}."
        )

    old_values = {
        "name": academic_year.name,
        "start_date": academic_year.start_date.isoformat(),
        "end_date": academic_year.end_date.isoformat(),
        "is_active": academic_year.is_active,
    }
    log_action(
        actor,
        "academic_year.deleted",
        academic_year,
        old_values=old_values,
        reason="Suppression confirmee de l'annee et de ses calendriers de preparation.",
    )
    academic_year.delete()


def _apply_changes(instance, changes, allowed_fields):
    unknown = set(changes) - allowed_fields
    if unknown:
        raise ValidationError(f"Champs non modifiables : {', '.join(sorted(unknown))}.")
    for field, value in changes.items():
        setattr(instance, field, value)


def _calendar_is_editable(calendar):
    return calendar.status in {
        AcademicCalendar.STATUS_DRAFT,
        AcademicCalendar.STATUS_REJECTED,
    }


def _validate_entry_target_semesters(*, calendar, target_scope, semester, target_semesters):
    """Valide une cible semestre simple ou composee dans le perimetre du calendrier."""
    semesters = list(target_semesters or ())
    if target_scope != AcademicCalendarEntry.SCOPE_SEMESTER:
        if semesters:
            raise ValidationError("Les semestres ne peuvent etre renseignes que pour une portee semestre.")
        return []

    if not semesters and semester is not None:
        semesters = [semester]
    if not semesters:
        raise ValidationError("Au moins un semestre est obligatoire pour cette portee.")

    unique_semesters = []
    seen_ids = set()
    for target in semesters:
        if target.pk in seen_ids:
            continue
        seen_ids.add(target.pk)
        academic_class = target.academic_class
        if academic_class.branch_id != calendar.branch_id:
            raise ValidationError("Un semestre cible doit appartenir a l'annexe du calendrier.")
        if academic_class.academic_year_id != calendar.academic_year_id:
            raise ValidationError("Un semestre cible doit appartenir a l'annee du calendrier.")
        unique_semesters.append(target)
    return unique_semesters


def _validate_calendar_for_submission(calendar):
    if not calendar.entries.exists():
        raise ValidationError("Un calendrier vide ne peut pas etre soumis.")
    for entry in calendar.entries.all():
        entry.full_clean()
    _validate_no_entry_overlap(calendar)
    errors = [
        item["message"]
        for item in get_calendar_readiness(calendar)
        if item["level"] == "error"
    ]
    if errors:
        raise ValidationError(errors)


@transaction.atomic
def create_calendar(*, actor, branch, academic_year, version=1):
    _require_common_calendar_scope(actor)
    require_calendar_branch_access(actor, branch)
    if not academic_year.is_active and not is_global_calendar_user(actor):
        raise ValidationError(
            "Une annee doit etre ouverte par la Direction generale avant la preparation de son calendrier."
        )
    calendar = AcademicCalendar(
        branch=branch,
        academic_year=academic_year,
        version=version,
        status=AcademicCalendar.STATUS_DRAFT,
        created_by=actor,
        updated_by=actor,
    )
    calendar.full_clean()
    calendar.save()
    return calendar


@transaction.atomic
def update_calendar(calendar, *, actor, **changes):
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    if not _calendar_is_editable(calendar):
        raise ValidationError("Seul un calendrier brouillon ou retourne peut etre modifie.")
    _apply_changes(calendar, changes, CALENDAR_MUTABLE_FIELDS)
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    return calendar


@transaction.atomic
def submit_calendar(calendar, *, actor):
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    if not _calendar_is_editable(calendar):
        raise ValidationError("Seul un calendrier brouillon ou retourne peut etre soumis.")
    _validate_calendar_for_submission(calendar)
    calendar.status = AcademicCalendar.STATUS_SUBMITTED
    calendar.submitted_by = actor
    calendar.submitted_at = timezone.now()
    calendar.rejected_by = None
    calendar.rejected_at = None
    calendar.rejection_reason = ""
    calendar.updated_by = actor
    calendar.save()
    return calendar


@transaction.atomic
def validate_calendar(calendar, *, actor):
    """Valide une soumission ; conserve le flux direct minimal des anciennes API."""
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    if calendar.status == AcademicCalendar.STATUS_DRAFT:
        # Compatibilite : les integrations historiques valident directement un
        # brouillon. Le nouveau parcours DE passe obligatoirement par submit.
        if not calendar.entries.exists():
            raise ValidationError("Un calendrier vide ne peut pas etre valide.")
        for entry in calendar.entries.all():
            entry.full_clean()
        _validate_no_entry_overlap(calendar)
    elif calendar.status == AcademicCalendar.STATUS_SUBMITTED:
        _validate_calendar_for_submission(calendar)
    else:
        raise ValidationError("Seul un calendrier soumis peut etre valide.")
    calendar.status = AcademicCalendar.STATUS_VALIDATED
    calendar.validated_by = actor
    calendar.validated_at = timezone.now()
    calendar.updated_by = actor
    calendar.save()
    return calendar


@transaction.atomic
def reject_calendar(calendar, *, actor, reason):
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    reason = (reason or "").strip()
    if calendar.status not in {
        AcademicCalendar.STATUS_SUBMITTED,
        AcademicCalendar.STATUS_VALIDATED,
    }:
        raise ValidationError("Seul un calendrier soumis ou valide peut etre retourne.")
    if not reason:
        raise ValidationError("Le motif de retour est obligatoire.")
    calendar.status = AcademicCalendar.STATUS_REJECTED
    calendar.rejected_by = actor
    calendar.rejected_at = timezone.now()
    calendar.rejection_reason = reason
    calendar.updated_by = actor
    calendar.save()
    return calendar


def _target_scope_overlaps(left, right):
    """Indique si deux cibles académiques couvrent au moins le même public."""
    if (
        left.target_scope == AcademicCalendarEntry.SCOPE_BRANCH
        or right.target_scope == AcademicCalendarEntry.SCOPE_BRANCH
    ):
        return True

    def _semester_targets(item):
        target_manager = getattr(item, "target_semesters", None)
        targets = list(target_manager.all()) if target_manager is not None else []
        if not targets and getattr(item, "semester", None) is not None:
            targets = [item.semester]
        return targets

    def _target_ids(item):
        semesters = _semester_targets(item)
        return {
            "schools": ({item.school_id} if item.school_id else set())
            | ({item.programme.school_id} if item.programme_id else set())
            | ({item.academic_class.programme.school_id} if item.academic_class_id else set())
            | {semester.academic_class.programme.school_id for semester in semesters},
            "semesters": {semester.pk for semester in semesters},
            "classes": ({item.academic_class_id} if item.academic_class_id else set())
            | {semester.academic_class_id for semester in semesters},
            "programmes": ({item.programme_id} if item.programme_id else set())
            | {semester.academic_class.programme_id for semester in semesters},
        }

    left_targets = _target_ids(left)
    right_targets = _target_ids(right)
    left_scope, right_scope = left.target_scope, right.target_scope
    if AcademicCalendarEntry.SCOPE_SCHOOL in {left_scope, right_scope}:
        return bool(left_targets["schools"] & right_targets["schools"])

    if left_scope == AcademicCalendarEntry.SCOPE_SEMESTER:
        if right_scope == AcademicCalendarEntry.SCOPE_SEMESTER:
            return bool(left_targets["semesters"] & right_targets["semesters"])
        if right_scope == AcademicCalendarEntry.SCOPE_CLASS:
            return bool(left_targets["classes"] & right_targets["classes"])
        if right_scope == AcademicCalendarEntry.SCOPE_PROGRAMME:
            return bool(left_targets["programmes"] & right_targets["programmes"])
    if right_scope == AcademicCalendarEntry.SCOPE_SEMESTER:
        return _target_scope_overlaps(right, left)

    if left_scope == AcademicCalendarEntry.SCOPE_CLASS and right_scope == AcademicCalendarEntry.SCOPE_CLASS:
        return bool(left_targets["classes"] & right_targets["classes"])
    if left_scope == AcademicCalendarEntry.SCOPE_CLASS and right_scope == AcademicCalendarEntry.SCOPE_PROGRAMME:
        return bool(left_targets["programmes"] & right_targets["programmes"])
    if left_scope == AcademicCalendarEntry.SCOPE_PROGRAMME and right_scope == AcademicCalendarEntry.SCOPE_CLASS:
        return bool(left_targets["programmes"] & right_targets["programmes"])
    if left_scope == AcademicCalendarEntry.SCOPE_PROGRAMME and right_scope == AcademicCalendarEntry.SCOPE_PROGRAMME:
        return bool(left_targets["programmes"] & right_targets["programmes"])
    return False


def _validate_no_entry_overlap(calendar):
    """Verifie les chevauchements des periodes bloquantes sur la meme audience."""
    entries = list(
        calendar.entries
        .filter(is_blocking=True)
        .exclude(status=AcademicCalendarEntry.STATUS_CANCELLED)
        .select_related("programme", "academic_class", "semester", "semester__academic_class")
        .prefetch_related("target_semesters__academic_class")
    )
    for index, entry in enumerate(entries):
        for other in entries[index + 1:]:
            if entry.start_datetime >= other.end_datetime or entry.end_datetime <= other.start_datetime:
                continue
            if not _target_scope_overlaps(entry, other):
                continue
            raise ValidationError(
                f"Les periodes bloquantes '{entry.title}' et '{other.title}' "
                f"se chevauchent pour une meme audience."
            )


def get_calendar_readiness(calendar):
    """Retourne les controles lisibles avant soumission, sans modifier les donnees."""
    entries = list(calendar.entries.exclude(status=AcademicCalendarEntry.STATUS_CANCELLED))
    event_types = {entry.event_type for entry in entries}
    checks = []

    def add(level, code, message):
        checks.append({"level": level, "code": code, "message": message})

    if not entries:
        add("error", "empty", "Le calendrier ne contient encore aucun jalon.")
        return checks

    if AcademicCalendarEntry.EVENT_ACADEMIC_START not in event_types:
        add("error", "academic_start", "La rentree academique officielle est manquante.")
    if AcademicCalendarEntry.EVENT_ACADEMIC_END not in event_types:
        add("error", "academic_end", "La cloture academique officielle est manquante.")

    has_exam = AcademicCalendarEntry.EVENT_EXAM_SESSION in event_types
    has_retake = AcademicCalendarEntry.EVENT_RETAKE_SESSION in event_types
    has_results = AcademicCalendarEntry.EVENT_RESULT_PUBLICATION in event_types
    has_jury = AcademicCalendarEntry.EVENT_JURY in event_types
    if has_exam and not has_results:
        add("warning", "results", "Une session d'examens existe sans date previsionnelle de publication des resultats.")
    if has_results and not has_exam:
        add("warning", "exam_session", "Une publication de resultats existe sans session d'examens associee dans le calendrier.")
    if has_jury and not has_results:
        add("warning", "jury", "Un jury est programme avant toute publication de resultats dans le calendrier.")
    if has_retake and not has_exam:
        add("warning", "retake", "Un rattrapage est programme sans session normale identifiee.")

    try:
        _validate_no_entry_overlap(calendar)
    except ValidationError as exc:
        for message in exc.messages:
            add("error", "overlap", message)

    if not checks:
        add("success", "ready", "Les jalons structurants et leurs controles sont coherents.")
    return checks


@transaction.atomic
def publish_calendar(calendar, *, actor):
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    calendar = scoped(AcademicCalendar, user=actor).select_for_update().get(pk=calendar.pk)
    if calendar.status != AcademicCalendar.STATUS_VALIDATED:
        raise ValidationError("Seul un calendrier valide peut etre publie.")
    _validate_no_entry_overlap(calendar)
    scoped(AcademicCalendar, user=actor).select_for_update().filter(
        branch=calendar.branch,
        academic_year=calendar.academic_year,
        status=AcademicCalendar.STATUS_PUBLISHED,
    ).exclude(pk=calendar.pk).update(
        status=AcademicCalendar.STATUS_SUPERSEDED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    calendar.status = AcademicCalendar.STATUS_PUBLISHED
    calendar.published_by = actor
    calendar.published_at = timezone.now()
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    calendar.entries.exclude(status=AcademicCalendarEntry.STATUS_CANCELLED).update(
        status=AcademicCalendarEntry.STATUS_PUBLISHED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    return calendar


@transaction.atomic
def create_calendar_revision(calendar, *, actor, reason=""):
    """Clone une version publiee sans jamais ecraser son historique."""
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    calendar = scoped(AcademicCalendar, user=actor).select_for_update().get(pk=calendar.pk)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Seule une version publiee peut etre revisee.")
    next_version = (
        scoped(AcademicCalendar, user=actor).filter(
            branch=calendar.branch,
            academic_year=calendar.academic_year,
        )
        .order_by("-version")
        .values_list("version", flat=True)
        .first()
        or 0
    ) + 1
    revision = scoped(AcademicCalendar, user=actor).create(
        branch=calendar.branch,
        academic_year=calendar.academic_year,
        version=next_version,
        official_title=calendar.official_title,
        administrative_reference=calendar.administrative_reference,
        general_observations=calendar.general_observations,
        revision_of=calendar,
        revision_reason=(reason or "").strip(),
        status=AcademicCalendar.STATUS_DRAFT,
        created_by=actor,
        updated_by=actor,
    )
    entry_fields = [
        "title", "description", "event_type", "start_datetime", "end_datetime",
        "all_day", "target_scope", "school", "programme", "academic_class", "semester",
        "color", "icon", "is_blocking",
    ]
    source_entries = list(calendar.entries.all().prefetch_related("target_semesters"))
    entries = []
    for entry in source_entries:
        values = {field: getattr(entry, field) for field in entry_fields}
        entries.append(
            AcademicCalendarEntry(
                calendar=revision,
                created_by=actor,
                updated_by=actor,
                status=AcademicCalendarEntry.STATUS_DRAFT,
                **values,
            )
        )
    for entry in entries:
        entry.full_clean()
    scoped(AcademicCalendarEntry, user=actor).bulk_create(entries)
    for source, clone in zip(source_entries, entries):
        clone.target_semesters.set(source.target_semesters.all())
    return revision


@transaction.atomic
def publish_calendar_after_readiness(calendar, *, actor):
    """Publie le calendrier depuis le parcours DE sans exposer les etapes techniques."""
    require_calendar_access(actor, calendar)
    calendar = scoped(AcademicCalendar, user=actor).select_for_update().get(pk=calendar.pk)
    if _calendar_is_editable(calendar):
        submit_calendar(calendar, actor=actor)
        calendar.refresh_from_db()
    if calendar.status == AcademicCalendar.STATUS_SUBMITTED:
        validate_calendar(calendar, actor=actor)
        calendar.refresh_from_db()
    if calendar.status != AcademicCalendar.STATUS_VALIDATED:
        raise ValidationError("Ce calendrier ne peut pas encore etre publie.")
    return publish_calendar(calendar, actor=actor)


@transaction.atomic
def delete_calendar(calendar, *, actor):
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    if not _calendar_is_editable(calendar):
        raise ValidationError(
            "Seul un calendrier en brouillon peut etre supprime. "
            "Archivez-le d'abord s'il est publie."
        )
    calendar.entries.all().delete()
    calendar.delete()


@transaction.atomic
def archive_calendar(calendar, *, actor):
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Seul un calendrier publie peut etre archive.")
    calendar.status = AcademicCalendar.STATUS_ARCHIVED
    calendar.updated_by = actor
    calendar.full_clean()
    calendar.save()
    calendar.entries.update(
        status=AcademicCalendarEntry.STATUS_ARCHIVED,
        updated_by=actor,
        updated_at=timezone.now(),
    )
    return calendar


@transaction.atomic
def create_calendar_entry(*, actor, calendar, **data):
    require_calendar_access(actor, calendar)
    if not _calendar_is_editable(calendar):
        raise ValidationError("Seul un calendrier brouillon ou retourne peut recevoir des entrees.")
    target_semesters = _validate_entry_target_semesters(
        calendar=calendar,
        target_scope=data.get("target_scope", AcademicCalendarEntry.SCOPE_BRANCH),
        semester=data.get("semester"),
        target_semesters=data.pop("target_semesters", None),
    )
    if target_semesters:
        # Le champ historique reste renseigne pour les integrations existantes.
        data["semester"] = target_semesters[0]
    entry = AcademicCalendarEntry(
        calendar=calendar,
        created_by=actor,
        updated_by=actor,
        **data,
    )
    _require_entry_school_access(entry, actor, target_semesters)
    entry.full_clean()
    entry.save()
    entry.target_semesters.set(target_semesters)
    return entry


@transaction.atomic
def update_calendar_entry(entry, *, actor, **changes):
    _require_entry_school_access(entry, actor, entry.target_semesters.all())
    require_calendar_access(actor, entry.calendar)
    if not _calendar_is_editable(entry.calendar):
        raise ValidationError("Seule l'entree d'un calendrier brouillon ou retourne peut etre modifiee.")
    requested_target_semesters = changes.pop("target_semesters", None)
    _apply_changes(entry, changes, ENTRY_MUTABLE_FIELDS)
    target_semesters = _validate_entry_target_semesters(
        calendar=entry.calendar,
        target_scope=entry.target_scope,
        semester=entry.semester,
        target_semesters=(
            requested_target_semesters
            if requested_target_semesters is not None
            else (
                entry.target_semesters.all()
                if entry.target_scope == AcademicCalendarEntry.SCOPE_SEMESTER
                else []
            )
        ),
    )
    if target_semesters:
        entry.semester = target_semesters[0]
    entry.updated_by = actor
    _require_entry_school_access(entry, actor, target_semesters)
    entry.full_clean()
    entry.save()
    entry.target_semesters.set(target_semesters)
    return entry


@transaction.atomic
def delete_calendar_entry(entry, *, actor):
    _require_entry_school_access(entry, actor, entry.target_semesters.all())
    require_calendar_access(actor, entry.calendar)
    if not _calendar_is_editable(entry.calendar):
        raise ValidationError("Seule l'entree d'un calendrier brouillon ou retourne peut etre supprimee.")
    entry.delete()


@transaction.atomic
def report_calendar_disruption(*, actor, calendar, **data):
    """Declare une perturbation sans modifier le calendrier officiel."""
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Une perturbation ne peut etre declaree que sur le calendrier publie applicable.")
    disruption = AcademicCalendarDisruption(
        calendar=calendar,
        reported_by=actor,
        status=AcademicCalendarDisruption.STATUS_DRAFT,
        **data,
    )
    disruption.full_clean()
    disruption.save()
    return disruption


@transaction.atomic
def activate_calendar_disruption(disruption, *, actor):
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, disruption.calendar)
    if disruption.status != AcademicCalendarDisruption.STATUS_DRAFT:
        raise ValidationError("Seule une perturbation brouillon peut etre activee.")
    disruption.status = AcademicCalendarDisruption.STATUS_ACTIVE
    disruption.full_clean()
    disruption.save(update_fields=["status", "updated_at"])
    return disruption


@transaction.atomic
def close_calendar_disruption(disruption, *, actor, ends_at=None):
    _require_common_calendar_scope(actor)
    require_calendar_access(actor, disruption.calendar)
    if disruption.status != AcademicCalendarDisruption.STATUS_ACTIVE:
        raise ValidationError("Seule une perturbation en cours peut etre cloturee.")
    if ends_at is not None:
        disruption.ends_at = ends_at
    if disruption.ends_at is None:
        raise ValidationError("La date de fin est obligatoire pour cloturer une perturbation.")
    disruption.status = AcademicCalendarDisruption.STATUS_CLOSED
    disruption.closed_by = actor
    disruption.closed_at = timezone.now()
    disruption.full_clean()
    disruption.save()
    return disruption


@transaction.atomic
def create_calendar_adjustment(*, actor, calendar, calendar_entry, action, reason,
                               disruption=None, effective_start_datetime=None,
                               effective_end_datetime=None, official_reference=""):
    """Prepare un avenant sans changer les dates de l'evenement de reference."""
    _require_entry_school_access(calendar_entry, actor, calendar_entry.target_semesters.all())
    require_calendar_access(actor, calendar)
    if calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Un avenant ne peut viser que le calendrier publie applicable.")
    if calendar_entry.calendar_id != calendar.id:
        raise ValidationError("L'evenement choisi n'appartient pas au calendrier applicable.")
    if disruption is not None and disruption.calendar_id != calendar.id:
        raise ValidationError("La perturbation ne concerne pas ce calendrier.")
    adjustment = AcademicCalendarAdjustment(
        calendar=calendar,
        disruption=disruption,
        calendar_entry=calendar_entry,
        action=action,
        reason=(reason or "").strip(),
        previous_start_datetime=calendar_entry.start_datetime,
        previous_end_datetime=calendar_entry.end_datetime,
        effective_start_datetime=effective_start_datetime,
        effective_end_datetime=effective_end_datetime,
        official_reference=(official_reference or "").strip(),
        created_by=actor,
    )
    adjustment.full_clean()
    adjustment.save()
    return adjustment


@transaction.atomic
def submit_calendar_adjustment(adjustment, *, actor):
    _require_entry_school_access(adjustment.calendar_entry, actor, adjustment.calendar_entry.target_semesters.all())
    require_calendar_access(actor, adjustment.calendar)
    if adjustment.status not in {
        AcademicCalendarAdjustment.STATUS_DRAFT,
        AcademicCalendarAdjustment.STATUS_REJECTED,
    }:
        raise ValidationError("Seul un avenant brouillon ou retourne peut etre soumis.")
    adjustment.status = AcademicCalendarAdjustment.STATUS_SUBMITTED
    adjustment.submitted_by = actor
    adjustment.full_clean()
    adjustment.save()
    return adjustment


@transaction.atomic
def validate_calendar_adjustment(adjustment, *, actor):
    _require_entry_school_access(adjustment.calendar_entry, actor, adjustment.calendar_entry.target_semesters.all())
    require_calendar_access(actor, adjustment.calendar)
    if adjustment.status != AcademicCalendarAdjustment.STATUS_SUBMITTED:
        raise ValidationError("Seul un avenant soumis peut etre valide.")
    adjustment.status = AcademicCalendarAdjustment.STATUS_VALIDATED
    adjustment.validated_by = actor
    adjustment.full_clean()
    adjustment.save()
    return adjustment


@transaction.atomic
def publish_calendar_adjustment(adjustment, *, actor):
    _require_entry_school_access(adjustment.calendar_entry, actor, adjustment.calendar_entry.target_semesters.all())
    require_calendar_access(actor, adjustment.calendar)
    if adjustment.status != AcademicCalendarAdjustment.STATUS_VALIDATED:
        raise ValidationError("Seul un avenant valide peut etre publie.")
    if adjustment.calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        raise ValidationError("Le calendrier de reference n'est plus le calendrier publie applicable.")
    adjustment.status = AcademicCalendarAdjustment.STATUS_PUBLISHED
    adjustment.published_by = actor
    adjustment.published_at = timezone.now()
    adjustment.full_clean()
    adjustment.save()
    return adjustment


def get_effective_calendar_schedule(calendar):
    """Retourne la projection applicable : base publiee + avenants publies.

    Les entrees d'origine ne sont jamais modifiees par cette fonction.
    """
    entries = list(scoped(AcademicCalendarEntry).filter(calendar=calendar).exclude(status=AcademicCalendarEntry.STATUS_CANCELLED))
    adjustments = (
        scoped(AcademicCalendarAdjustment).filter(
            calendar=calendar,
            status=AcademicCalendarAdjustment.STATUS_PUBLISHED,
        )
        .select_related("calendar_entry")
        .order_by("published_at", "id")
    )
    by_entry = {
        entry.id: {
            "entry": entry,
            "start_datetime": entry.start_datetime,
            "end_datetime": entry.end_datetime,
            "is_cancelled": False,
            "delivery_mode": "standard",
            "adjustments": [],
        }
        for entry in entries
    }
    for adjustment in adjustments:
        item = by_entry.get(adjustment.calendar_entry_id)
        if item is None:
            continue
        item["adjustments"].append(adjustment)
        if adjustment.action == AcademicCalendarAdjustment.ACTION_RESCHEDULE:
            item["start_datetime"] = adjustment.effective_start_datetime
            item["end_datetime"] = adjustment.effective_end_datetime
        elif adjustment.action == AcademicCalendarAdjustment.ACTION_CANCEL:
            item["is_cancelled"] = True
        elif adjustment.action == AcademicCalendarAdjustment.ACTION_ONLINE:
            item["delivery_mode"] = "online_continuity"
    return list(by_entry.values())


def _entry_applies_to_calendar_context(
    entry, *, school=None, programme=None, academic_class=None, semester_ids=()
):
    """Return whether an entry targets the supplied academic audience.

    This deliberately lives beside the effective-schedule service: dashboards,
    PDF documents and student views must apply the *same* scope interpretation
    to the same calendar entry, rather than each recreating a queryset.
    """
    scope = entry.target_scope
    if scope == AcademicCalendarEntry.SCOPE_BRANCH:
        return True
    if scope == AcademicCalendarEntry.SCOPE_SCHOOL:
        return bool(school and entry.school_id == school.pk)
    if scope == AcademicCalendarEntry.SCOPE_PROGRAMME:
        return bool(programme and entry.programme_id == programme.pk)
    if scope == AcademicCalendarEntry.SCOPE_CLASS:
        return bool(academic_class and entry.academic_class_id == academic_class.pk)
    if scope == AcademicCalendarEntry.SCOPE_SEMESTER:
        target_ids = set(semester_ids or ())
        if entry.semester_id:
            target_ids_match = entry.semester_id in target_ids
        else:
            target_ids_match = False
        return target_ids_match or entry.target_semesters.filter(pk__in=target_ids).exists()
    return False


def get_effective_calendar_projection(
    calendar,
    *,
    school=None,
    programme=None,
    academic_class=None,
    semester_ids=(),
    public_only=False,
    include_cancelled=False,
):
    """Project the canonical calendar into displayable institutional periods.

    Each row is rooted in :class:`AcademicCalendarEntry` and uses
    ``get_effective_calendar_schedule`` for its dates.  Scheduled assessment
    events are supplementary details only: they never become a parallel
    calendar and are included solely when linked to the period directly or by
    its evaluation campaign.
    """
    if public_only and calendar.status != AcademicCalendar.STATUS_PUBLISHED:
        return []

    effective_items = get_effective_calendar_schedule(calendar)
    if public_only:
        effective_items = [
            item
            for item in effective_items
            if item["entry"].status == AcademicCalendarEntry.STATUS_PUBLISHED
        ]

    filtered_items = []
    for item in effective_items:
        entry = item["entry"]
        if entry.status == AcademicCalendarEntry.STATUS_ARCHIVED:
            continue
        if item["is_cancelled"] and not include_cancelled:
            continue
        if any(value is not None for value in (school, programme, academic_class)) or semester_ids:
            if not _entry_applies_to_calendar_context(
                entry,
                school=school,
                programme=programme,
                academic_class=academic_class,
                semester_ids=semester_ids,
            ):
                continue
        filtered_items.append(item)

    entry_ids = [item["entry"].pk for item in filtered_items]
    details_by_entry_id = {entry_id: [] for entry_id in entry_ids}
    if entry_ids:
        detail_events = (
            AcademicScheduleEvent.objects.filter(
                branch=calendar.branch,
                academic_year=calendar.academic_year,
                is_active=True,
            )
            .exclude(status__in=[
                AcademicScheduleEvent.STATUS_DRAFT,
                AcademicScheduleEvent.STATUS_CANCELLED,
            ])
            .filter(
                Q(calendar_entry_id__in=entry_ids)
                | Q(evaluation_campaign__calendar_entry_id__in=entry_ids)
            )
            .select_related(
                "calendar_entry",
                "evaluation_campaign__calendar_entry",
                "academic_class",
                "ec",
                "ec__ue",
            )
            .order_by("start_datetime", "id")
        )
        if academic_class is not None:
            detail_events = detail_events.filter(academic_class=academic_class)
        elif programme is not None:
            detail_events = detail_events.filter(academic_class__programme=programme)
        elif school is not None:
            detail_events = detail_events.filter(academic_class__programme__school=school)
        for event in detail_events:
            parent_entry_id = (
                event.calendar_entry_id
                or getattr(event.evaluation_campaign, "calendar_entry_id", None)
            )
            if parent_entry_id not in details_by_entry_id:
                continue
            details_by_entry_id[parent_entry_id].append({
                "event": event,
                "start_datetime": event.start_datetime,
                "end_datetime": event.end_datetime,
                "is_within_effective_period": (
                    event.start_datetime >= next(
                        item["start_datetime"]
                        for item in filtered_items
                        if item["entry"].pk == parent_entry_id
                    )
                    and event.end_datetime <= next(
                        item["end_datetime"]
                        for item in filtered_items
                        if item["entry"].pk == parent_entry_id
                    )
                ),
            })

    projection = []
    for item in filtered_items:
        entry = item["entry"]
        projection.append({
            **item,
            "details": details_by_entry_id.get(entry.pk, []),
            "is_single_day": (
                timezone.localtime(item["start_datetime"]).date()
                == timezone.localtime(item["end_datetime"]).date()
            ),
        })
    return sorted(projection, key=lambda item: (item["start_datetime"], item["entry"].pk))


def get_disruption_impacts(disruption):
    """Liste les jalons potentiellement affectes par une perturbation locale.

    Cette analyse n'entraine jamais de changement automatique : elle sert a
    proposer au DE les seuls evenements qu'il doit examiner.
    """
    end_datetime = disruption.ends_at
    if end_datetime is None:
        end_datetime = timezone.make_aware(
            datetime.combine(disruption.calendar.academic_year.end_date, datetime.max.time())
        )
    entries = (
        disruption.calendar.entries
        .exclude(status=AcademicCalendarEntry.STATUS_CANCELLED)
        .filter(
            start_datetime__lt=end_datetime,
            end_datetime__gt=disruption.starts_at,
        )
        .select_related("programme", "academic_class", "semester", "semester__academic_class")
        .order_by("start_datetime", "id")
    )
    return [entry for entry in entries if _target_scope_overlaps(disruption, entry)]


def assert_course_not_blocked(*, branch, academic_year, academic_class, start_datetime, end_datetime):
    scope = Q(target_scope=AcademicCalendarEntry.SCOPE_BRANCH)
    if academic_class is not None:
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_SCHOOL, school_id=academic_class.programme.school_id)
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_PROGRAMME, programme=academic_class.programme)
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_CLASS, academic_class=academic_class)
        scope |= Q(target_scope=AcademicCalendarEntry.SCOPE_SEMESTER, semester__academic_class=academic_class)
    conflict = (
        scoped(AcademicCalendarEntry).filter(
            calendar__branch=branch,
            calendar__academic_year=academic_year,
            calendar__status=AcademicCalendar.STATUS_PUBLISHED,
            status=AcademicCalendarEntry.STATUS_PUBLISHED,
            is_blocking=True,
            start_datetime__lt=end_datetime,
            end_datetime__gt=start_datetime,
        )
        .filter(scope)
        .first()
    )
    if conflict:
        raise ValidationError(f"Cours impossible pendant la periode bloquante : {conflict.title}.")
