from __future__ import annotations
from accounts.scoping import scoped, require_object_scope

import logging
from decimal import Decimal

logger = logging.getLogger("esfe.reenrollment")

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from academic_cycle import constants as cycle_constants
from academic_cycle.models import (
    StudentAcademicDebt,
    StudentYearDecision as OfficialAnnualDecision,
)
from academics.services.academic_positioning import (
    academic_level_sort_key,
    get_positioning_fee_for_level,
)
from academics.services.year import DECISION_VALIDE, DECISION_ADMISSIBLE, DECISION_NON_ADMIS, carry_forward_debts, compute_annual_decision, compute_annual_result
from accounts.access import get_user_position
from accounts.dashboards.helpers import (
    get_user_branch,
    is_finance,
    is_global_viewer,
    is_manager,
)
from admissions.models import Candidature
from inscriptions.models import Inscription
from portal.models import SupportAuditLog
from portal.services.it_support_service import log_support_action
from students.models import Student, StudentYearDecision


def _semester_averages(enrollment):
    result = compute_annual_decision(enrollment)
    averages = [
        Decimal(str(sr.get("average")))
        for sr in result.get("semester_results", [])
        if sr.get("average") is not None
    ]
    return averages


def _annual_average(enrollment):
    averages = _semester_averages(enrollment)
    if not averages:
        return None
    return (sum(averages) / len(averages)).quantize(Decimal("0.01"))


def _decision_from_annual_result(*, enrollment, annual_result):
    return compute_annual_decision(enrollment)["decision"]


def _decision_from_average(*, academic_class, annual_average):
    if annual_average is None:
        return StudentYearDecision.DECISION_REPEATED

    threshold = academic_class.validation_threshold or Decimal("10.00")
    if annual_average >= threshold:
        return StudentYearDecision.DECISION_PROMOTED
    return StudentYearDecision.DECISION_REPEATED


def _is_terminal_level(level):
    return str(level or "").upper().strip() in {"L3", "M2"}


def _financial_status(inscription):
    if inscription is None:
        return {"status": "missing", "label": "Inscription absente", "balance": 0}
    if inscription.balance > 0:
        return {"status": "debt", "label": "Solde restant", "balance": inscription.balance}
    return {"status": "paid", "label": "A jour", "balance": 0}


def _reenrollment_position(user):
    return getattr(getattr(user, "profile", None), "position", "") or get_user_position(user)


def _reenrollment_role(user):
    return getattr(getattr(user, "profile", None), "role", "")


def can_user_handle_reenrollment(user):
    """Return whether an operational user may consult this workflow.

    This deliberately remains broader than each state transition.  The
    dashboard is shared as a read model, while the transition functions below
    remain the source of truth for the distinct academic and financial roles.
    """
    position = _reenrollment_position(user)
    role = _reenrollment_role(user)
    return user.is_superuser or position in {
        "branch_manager",
        "annex_manager",
        "finance_manager",
        "payment_agent",
        "director_of_studies",
    } or role == "finance" or is_manager(user) or is_finance(user)


def can_user_propose_reenrollment(user):
    """Only the Director of Studies may set the academic decision."""
    return user.is_superuser or _reenrollment_position(user) == "director_of_studies"


def can_user_submit_reenrollment_decision(user):
    """Keep the Phase 1 service compatible with trusted legacy callers.

    The operational HTTP surface below still reserves academic proposal to the
    DE.  Existing back-office service callers may prepare a decision only when
    they already hold the manager capability required by the original engine.
    """
    return can_user_propose_reenrollment(user) or can_user_apply_reenrollment(user)


def can_user_reject_reenrollment(user):
    """A rejection is an academic decision, not a cash-desk action."""
    return can_user_propose_reenrollment(user)


def can_user_validate_academic(user):
    return can_user_propose_reenrollment(user)


def can_user_validate_finance(user):
    position = _reenrollment_position(user)
    role = _reenrollment_role(user)
    return user.is_superuser or position in {"branch_manager", "finance_manager", "payment_agent"} or role == "finance" or is_manager(user) or is_finance(user)


def can_user_apply_reenrollment(user):
    position = _reenrollment_position(user)
    return user.is_superuser or position in {"branch_manager", "annex_manager"} or is_manager(user)


def _decision_target_label(decision):
    return f"{decision.student} - {decision.source_academic_year} - {decision.get_decision_display()}"


def _audit_decision(*, decision, actor, action_type, details):
    return log_support_action(
        actor=actor,
        branch=decision.source_enrollment.branch,
        action_type=action_type,
        target_user=decision.student.user,
        target_label=_decision_target_label(decision),
        details=details,
    )


def _assert_actor_branch_scope(*, actor, branch):
    """Keep service calls safe when they are not initiated by the HTMX view."""
    if actor is None or is_global_viewer(actor) or actor.is_superuser:
        return
    actor_branch = get_user_branch(actor)
    if actor_branch is None or actor_branch.pk != branch.pk:
        raise ValidationError("Cette operation est hors du perimetre de votre annexe.")


def _sync_cycle_reenrollment(*, decision, status):
    """Expose the authoritative portal workflow in the academic-cycle tracker.

    ``AcademicReEnrollment`` already powers the student pre-rentree and access
    policies.  It must therefore be a projection of this workflow, never a
    competing enrollment path.
    """
    if decision.target_academic_year_id is None:
        return None

    from academic_cycle.models import AcademicReEnrollment

    reenrollment, _created = AcademicReEnrollment.objects.update_or_create(
        student=decision.student,
        target_academic_year=decision.target_academic_year,
        defaults={
            "source_academic_year": decision.source_academic_year,
            "source_class": decision.source_class,
            "target_class": decision.target_class,
            "branch": decision.source_enrollment.branch,
            "status": status,
            "prepared_by_system": True,
        },
    )
    return reenrollment


DECISION_MAP_NEW_TO_OLD = {
    DECISION_VALIDE: StudentYearDecision.DECISION_PROMOTED,
    DECISION_ADMISSIBLE: StudentYearDecision.DECISION_PROMOTED_WITH_DEBT,
    DECISION_NON_ADMIS: StudentYearDecision.DECISION_REPEATED,
}

OFFICIAL_DECISION_MAP = {
    cycle_constants.DECISION_PROMOTED: StudentYearDecision.DECISION_PROMOTED,
    cycle_constants.DECISION_PROMOTED_WITH_ACADEMIC_DEBT: StudentYearDecision.DECISION_PROMOTED_WITH_DEBT,
    cycle_constants.DECISION_REPEATED: StudentYearDecision.DECISION_REPEATED,
    cycle_constants.DECISION_GRADUATED: StudentYearDecision.DECISION_COMPLETED,
    cycle_constants.DECISION_DROPPED: StudentYearDecision.DECISION_ABANDONED,
    cycle_constants.DECISION_TRANSFERRED: StudentYearDecision.DECISION_TRANSFERRED,
}


def _map_decision(annual_decision_code):
    return DECISION_MAP_NEW_TO_OLD.get(annual_decision_code, StudentYearDecision.DECISION_REPEATED)


def _map_official_decision(official_code):
    """Translate only a final jury code into the administrative vocabulary."""
    try:
        return OFFICIAL_DECISION_MAP[official_code]
    except KeyError as exc:
        raise ValidationError("La decision annuelle officielle n'autorise pas encore de traitement administratif.") from exc


TARGET_DECISIONS = {
    StudentYearDecision.DECISION_PROMOTED,
    StudentYearDecision.DECISION_PROMOTED_WITH_DEBT,
    StudentYearDecision.DECISION_REPEATED,
}

ADMINISTRATIVE_DECISIONS = {
    StudentYearDecision.DECISION_TRANSFERRED,
    StudentYearDecision.DECISION_SUSPENDED,
    StudentYearDecision.DECISION_ABANDONED,
    StudentYearDecision.DECISION_COMPLETED,
}

FINANCE_CLEARANCE_REQUIRED_DECISIONS = {
    StudentYearDecision.DECISION_PROMOTED,
    StudentYearDecision.DECISION_PROMOTED_WITH_DEBT,
    StudentYearDecision.DECISION_REPEATED,
    StudentYearDecision.DECISION_TRANSFERRED,
    StudentYearDecision.DECISION_COMPLETED,
}

ACADEMIC_RULE_DECISIONS = TARGET_DECISIONS | {StudentYearDecision.DECISION_COMPLETED}


def _decision_payload_from_rule(annual_decision):
    return {
        "rule_source": "computed",
        "rule_code": annual_decision.get("rule_code"),
        "rule_label": annual_decision.get("rule_label"),
        "threshold": str(annual_decision.get("threshold") or ""),
        "admissibility_gap": str(annual_decision.get("admissibility_gap") or ""),
        "requires_academic_debt": bool(annual_decision.get("requires_academic_debt")),
        "debt_subjects": annual_decision.get("debt_subjects", []),
        "reasons": annual_decision.get("reasons", []),
        "semester_results": annual_decision.get("semester_results", []),
    }


def _official_annual_decision_for_enrollment(enrollment):
    """Return the immutable DE deliberation outcome for this exact year."""
    return (
        OfficialAnnualDecision.objects.filter(
            source_enrollment=enrollment,
            academic_year=enrollment.academic_year,
            current_class=enrollment.academic_class,
            is_final=True,
        )
        .exclude(synthesis_snapshot={})
        .first()
    )


def _decision_payload_from_official_deliberation(official_decision):
    synthesis = official_decision.synthesis_snapshot or {}
    return {
        "rule_source": "official_annual_deliberation",
        "official_decision_id": official_decision.id,
        "official_decision": official_decision.decision,
        "academic_decision": synthesis.get("academic_decision"),
        "rule_code": synthesis.get("rule_code"),
        "rule_label": synthesis.get("rule_label"),
        "threshold": str(synthesis.get("threshold") or ""),
        "admissibility_gap": str(synthesis.get("admissibility_gap") or ""),
        "requires_academic_debt": bool(synthesis.get("requires_academic_debt")),
        "debt_subjects": synthesis.get("debt_subjects", []),
        "reasons": synthesis.get("reasons", []),
        "semester_results": synthesis.get("semesters", []),
    }


def _decision_payload_from_manual_average(*, academic_class, annual_average):
    threshold = academic_class.validation_threshold or Decimal("10.00")
    return {
        "rule_source": "manual_average",
        "rule_code": "manual_average_legacy",
        "rule_label": "Moyenne annuelle fournie",
        "threshold": str(threshold),
        "annual_average": str(annual_average) if annual_average is not None else None,
        "reasons": ["Decision calculee depuis une moyenne annuelle fournie au service."],
    }


def _assert_decision_matches_academic_rules(decision):
    if decision.decision not in ACADEMIC_RULE_DECISIONS:
        return
    if decision.decision_payload.get("rule_source") == "manual_average":
        return
    if decision.decision_payload.get("rule_source") == "official_annual_deliberation":
        official_id = decision.decision_payload.get("official_decision_id")
        official = OfficialAnnualDecision.objects.filter(
            pk=official_id,
            source_enrollment=decision.source_enrollment,
            is_final=True,
        ).first()
        if official is None:
            raise ValidationError("La decision annuelle officielle liee a ce dossier est introuvable ou non finalisee.")
        expected = _map_official_decision(official.decision)
        if decision.decision != expected:
            raise ValidationError("La décision de réinscription ne correspond plus à la délibération annuelle officielle.")
        return
    automatic = compute_annual_decision(decision.source_enrollment)
    # ``compute_annual_decision`` and ``StudentYearDecision`` deliberately use
    # different vocabularies.  Compare values in the re-enrollment domain;
    # otherwise a legitimate ``NON_ADMIS`` result is rejected as it is stored
    # as the yearly ``repeated`` decision.
    expected = _map_decision(automatic["decision"])
    if decision.decision != expected:
        expected_label = dict(StudentYearDecision.DECISION_CHOICES).get(expected, expected)
        raise ValidationError(
            "La decision choisie ne correspond pas aux regles academiques automatiques. "
            f"Decision attendue: {expected_label}."
        )


def _validate_decision_ready(decision):
    if decision.decision in ADMINISTRATIVE_DECISIONS:
        return
    if decision.decision not in TARGET_DECISIONS:
        raise ValidationError("Decision annuelle inconnue.")
    if decision.target_class is None or decision.target_academic_year is None:
        raise ValidationError("Classe et annee cible obligatoires.")
    if decision.target_class.academic_year_id != decision.target_academic_year_id:
        raise ValidationError("La classe cible ne correspond pas a l'annee cible.")
    if not decision.target_class.is_active or decision.target_class.is_archived:
        raise ValidationError("La classe cible doit etre active et non archivee.")
    if decision.target_class.programme_id != decision.source_enrollment.programme_id:
        raise ValidationError("La classe cible doit rester dans le meme programme.")
    if decision.target_class.branch_id != decision.source_enrollment.branch_id:
        raise ValidationError("La classe cible doit rester dans la meme annexe.")
    if decision.target_academic_year.start_date <= decision.source_academic_year.start_date:
        raise ValidationError("L'annee cible doit etre posterieure a l'annee source.")
    compatible_ids = {item.pk for item in _compatible_target_classes(
        source_enrollment=decision.source_enrollment,
        target_academic_year=decision.target_academic_year,
        decision=decision.decision,
    )}
    if decision.target_class_id not in compatible_ids:
        raise ValidationError("La classe cible ne correspond pas a l'orientation imposee par la decision officielle.")


def build_reenrollment_candidates(*, source_year=None, source_class=None, branch=None, branch_ids=None, programme=None, search="", target_year=None):
    """Build the real source-year population without one decision query per row."""
    queryset = scoped(AcademicEnrollment).select_related(
        "student",
        "student__student_profile",
        "inscription",
        "academic_class",
        "academic_year",
        "programme",
        "branch",
    )

    if source_year is not None:
        queryset = queryset.filter(academic_year=source_year)
    if source_class is not None:
        queryset = queryset.filter(academic_class=source_class)
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    if branch_ids is not None:
        queryset = queryset.filter(branch_id__in=branch_ids)
    if programme is not None:
        queryset = queryset.filter(programme=programme)
    if search:
        queryset = queryset.filter(
            Q(student__student_profile__matricule__icontains=search)
            | Q(student__first_name__icontains=search)
            | Q(student__last_name__icontains=search)
            | Q(student__username__icontains=search)
        )

    enrollments = list(queryset.order_by("academic_class__level", "student__last_name", "student__first_name"))
    decisions_by_enrollment = {
        decision.source_enrollment_id: decision
        for decision in scoped(StudentYearDecision).filter(
            source_enrollment_id__in=[enrollment.id for enrollment in enrollments],
        ).select_related(
            "target_class",
            "target_academic_year",
            "target_inscription",
            "target_enrollment",
        )
    }
    official_by_enrollment = {
        decision.source_enrollment_id: decision
        for decision in OfficialAnnualDecision.objects.filter(
            source_enrollment_id__in=[enrollment.id for enrollment in enrollments],
            is_final=True,
        ).exclude(synthesis_snapshot={})
    }
    student_ids = [
        enrollment.student.student_profile.id
        for enrollment in enrollments
        if hasattr(enrollment.student, "student_profile")
    ]
    debts_by_student = {}
    source_year_ids = {enrollment.academic_year_id for enrollment in enrollments}
    for debt in StudentAcademicDebt.objects.select_related("ue", "ec", "source_class").filter(
        student_id__in=student_ids,
        source_academic_year_id__in=source_year_ids,
    ).exclude(status=cycle_constants.DEBT_RESOLVED):
        debts_by_student.setdefault((debt.student_id, debt.source_academic_year_id), []).append(debt)
    candidates = []
    for enrollment in enrollments:
        student = getattr(enrollment.student, "student_profile", None)
        official_decision = official_by_enrollment.get(enrollment.id)
        if official_decision is None:
            # No final collective deliberation: this enrollment is deliberately
            # ineligible and must not enter the re-enrollment queue.
            continue
        synthesis = official_decision.synthesis_snapshot or {}
        annual_decision = {
            "decision": synthesis.get("academic_decision"),
            "rule_code": synthesis.get("rule_code"),
            "rule_label": synthesis.get("rule_label"),
            "requires_academic_debt": synthesis.get("requires_academic_debt"),
            "debt_subjects": synthesis.get("debt_subjects", []),
            "semesters": synthesis.get("semesters", []),
        }
        annual_result = {"semester_results": synthesis.get("semesters", [])}
        annual_average = official_decision.annual_average
        # The final jury value, including an individual override, is the only
        # value allowed to drive the administrative workflow.
        proposed_decision = _map_official_decision(official_decision.decision)
        proposed_decision_label = dict(StudentYearDecision.DECISION_CHOICES).get(proposed_decision, proposed_decision)
        year_decision = decisions_by_enrollment.get(enrollment.id)
        proposed_target_class = None
        compatible_target_classes = []
        if target_year is not None and proposed_decision in TARGET_DECISIONS:
            compatible_target_classes = _compatible_target_classes(
                source_enrollment=enrollment,
                target_academic_year=target_year,
                decision=proposed_decision,
            )
            proposed_target_class = compatible_target_classes[0] if compatible_target_classes else None
        debts = debts_by_student.get((getattr(student, "id", None), enrollment.academic_year_id), [])
        candidates.append(
            {
                "student": student,
                "user": enrollment.student,
                "enrollment": enrollment,
                "matricule": getattr(student, "matricule", ""),
                "full_name": getattr(student, "full_name", enrollment.student.get_full_name() or enrollment.student.username),
                "source_class": enrollment.academic_class,
                "source_year": enrollment.academic_year,
                "annual_average": annual_average,
                "annual_result": annual_result,
                "annual_decision": annual_decision,
                "official_annual_decision": official_decision,
                "official_decision_label": official_decision.get_decision_display(),
                "financial_status": _financial_status(enrollment.inscription),
                "proposed_decision": proposed_decision,
                "proposed_decision_label": proposed_decision_label,
                "proposed_target_class": proposed_target_class,
                "compatible_target_classes": compatible_target_classes,
                "year_decision": year_decision,
                "debts": debts,
                "debt_count": len(debts),
                "is_terminal": proposed_decision == StudentYearDecision.DECISION_COMPLETED,
                "administrative_state": _candidate_administrative_state(year_decision),
            }
        )
    return candidates


def _candidate_administrative_state(decision):
    if decision is None:
        return {"code": "ready", "label": "Pret a traiter", "tone": "info"}
    if decision.workflow_status == StudentYearDecision.WORKFLOW_APPLIED:
        return {"code": "completed", "label": "Finalisee", "tone": "success"}
    if decision.target_inscription_id:
        return {"code": "payment", "label": "Paiement attendu", "tone": "warning"}
    if decision.workflow_status == StudentYearDecision.WORKFLOW_FINANCE_VALIDATED:
        return {"code": "validated", "label": "Prete a demarrer", "tone": "success"}
    return {"code": "in_progress", "label": "Prise en charge", "tone": "neutral"}


def _decision_financial_state(decision):
    if decision.workflow_status == StudentYearDecision.WORKFLOW_APPLIED:
        return "active"
    if decision.target_inscription_id:
        if decision.target_inscription.status == Inscription.STATUS_PARTIAL:
            return "partial_payment"
        return "awaiting_payment"
    if decision.workflow_status == StudentYearDecision.WORKFLOW_FINANCE_VALIDATED:
        return "ready"
    return "not_started"


def _filter_decisions_by_finance_state(queryset, finance_state):
    """Translate the dashboard's derived financial state into SQL filters.

    This keeps the dashboard KPIs exact without materialising an arbitrary
    number of decisions in Python.  It intentionally mirrors
    ``_decision_financial_state`` so the queue and its counters cannot drift.
    """
    if finance_state == "active":
        return queryset.filter(workflow_status=StudentYearDecision.WORKFLOW_APPLIED)
    if finance_state == "partial_payment":
        return queryset.exclude(
            workflow_status=StudentYearDecision.WORKFLOW_APPLIED,
        ).filter(target_inscription__status=Inscription.STATUS_PARTIAL)
    if finance_state == "awaiting_payment":
        return queryset.exclude(
            workflow_status=StudentYearDecision.WORKFLOW_APPLIED,
        ).filter(target_inscription__isnull=False).exclude(
            target_inscription__status=Inscription.STATUS_PARTIAL,
        )
    if finance_state == "ready":
        return queryset.filter(
            workflow_status=StudentYearDecision.WORKFLOW_FINANCE_VALIDATED,
            target_inscription__isnull=True,
        )
    if finance_state == "not_started":
        return queryset.exclude(
            workflow_status__in=(
                StudentYearDecision.WORKFLOW_APPLIED,
                StudentYearDecision.WORKFLOW_FINANCE_VALIDATED,
            ),
        ).filter(target_inscription__isnull=True)
    return queryset


def get_reenrollment_dashboard_context(
    *,
    branch,
    branch_ids=None,
    source_year=None,
    source_class=None,
    target_year=None,
    target_class=None,
    programme=None,
    decision_value="",
    workflow_status="",
    finance_state="",
    search="",
    actor=None,
    toast=None,
    surface="manager",
    workspace_target="#reenrollment-workspace",
    subview="",
    page=1,
):
    """Return the shared operational read model for each authorized surface.

    A campaign is deliberately derived from source/target years and the
    authoritative annual decisions.  No parallel campaign table is needed.
    """
    if target_class is not None and actor is not None:
        require_object_scope(target_class, user=actor)
    valid_subviews = {
        "director": {"overview", "passages", "repeated", "debts", "transmission"},
        "manager": {"todo", "in_progress", "payments", "completed", "history"},
    }
    subview = subview if subview in valid_subviews.get(surface, set()) else (
        "overview" if surface == "director" else "todo"
    )
    if source_year is None:
        if surface == "director":
            source_year = AcademicYear.objects.filter(is_active=True).first()
        else:
            official_scope = OfficialAnnualDecision.objects.filter(is_final=True).exclude(synthesis_snapshot={})
            if branch is not None:
                official_scope = official_scope.filter(branch=branch)
            if branch_ids is not None:
                official_scope = official_scope.filter(branch_id__in=branch_ids)
            latest_official = official_scope.select_related("academic_year").order_by("-academic_year__start_date").first()
            source_year = latest_official.academic_year if latest_official else None
    if target_year is None and source_year is not None:
        target_year = AcademicYear.objects.filter(start_date__gt=source_year.start_date).order_by("start_date").first()

    academic_years = AcademicYear.objects.all().order_by("-start_date")
    classes = scoped(AcademicClass, user=actor).select_related("academic_year", "programme", "branch").filter(
        is_archived=False,
    )
    if branch is not None:
        classes = classes.filter(branch=branch)
    if branch_ids is not None:
        classes = classes.filter(branch_id__in=branch_ids)
    classes = classes.order_by("-academic_year__start_date", "programme__title", "level")
    target_classes = scoped(AcademicClass, user=actor).select_related("academic_year", "programme", "branch").filter(
        is_active=True,
        is_archived=False,
    )
    if branch is not None:
        target_classes = target_classes.filter(branch=branch)
    if branch_ids is not None:
        target_classes = target_classes.filter(branch_id__in=branch_ids)
    target_classes = target_classes.order_by("-academic_year__start_date", "programme__title", "level")
    if target_year is not None:
        target_classes = target_classes.filter(academic_year=target_year)
    if programme is not None:
        target_classes = target_classes.filter(programme=programme)
    elif source_class is not None:
        target_classes = target_classes.filter(programme=source_class.programme)

    candidate_filters_required = source_year is None and source_class is None
    candidates = []
    if not candidate_filters_required:
        candidates = build_reenrollment_candidates(
            source_year=source_year,
            source_class=source_class,
            branch=branch,
            branch_ids=branch_ids,
            programme=programme,
            search=search,
            target_year=target_year,
        )
    all_candidates = list(candidates)
    passage_values = {StudentYearDecision.DECISION_PROMOTED, StudentYearDecision.DECISION_PROMOTED_WITH_DEBT}
    if surface == "director":
        if subview == "passages":
            candidates = [row for row in candidates if row["proposed_decision"] in passage_values]
        elif subview == "repeated":
            candidates = [row for row in candidates if row["proposed_decision"] == StudentYearDecision.DECISION_REPEATED]
        elif subview == "debts":
            candidates = [row for row in candidates if row["debt_count"] or row["proposed_decision"] == StudentYearDecision.DECISION_PROMOTED_WITH_DEBT]
    else:
        if subview == "todo":
            candidates = [row for row in candidates if row["year_decision"] is None]
        elif subview == "in_progress":
            candidates = [row for row in candidates if row["year_decision"] is not None and row["administrative_state"]["code"] in {"in_progress", "validated"}]
        elif subview == "payments":
            candidates = [row for row in candidates if row["administrative_state"]["code"] == "payment"]
        elif subview == "completed":
            candidates = [row for row in candidates if row["administrative_state"]["code"] == "completed"]
        elif subview == "history":
            candidates = [row for row in candidates if row["year_decision"] is not None]

    class_summaries = {}
    for row in all_candidates:
        summary = class_summaries.setdefault(row["source_class"].id, {
            "academic_class": row["source_class"], "total": 0, "promoted": 0, "with_debt": 0,
            "repeated": 0, "completed": 0, "ready": 0,
        })
        summary["total"] += 1
        if row["proposed_decision"] == StudentYearDecision.DECISION_PROMOTED:
            summary["promoted"] += 1
        elif row["proposed_decision"] == StudentYearDecision.DECISION_PROMOTED_WITH_DEBT:
            summary["with_debt"] += 1
        elif row["proposed_decision"] == StudentYearDecision.DECISION_REPEATED:
            summary["repeated"] += 1
        elif row["proposed_decision"] == StudentYearDecision.DECISION_COMPLETED:
            summary["completed"] += 1
        if row["official_annual_decision"].is_final:
            summary["ready"] += 1

    candidate_page = Paginator(candidates, 30).get_page(page)

    decisions = scoped(StudentYearDecision, user=actor).select_related(
        "student",
        "student__user",
        "source_enrollment",
        "source_class",
        "source_academic_year",
        "target_class",
        "target_academic_year",
        "target_inscription",
        "target_enrollment",
        "source_enrollment__programme",
        "source_enrollment__branch",
    )
    if branch is not None:
        decisions = decisions.filter(source_enrollment__branch=branch)
    if branch_ids is not None:
        decisions = decisions.filter(source_enrollment__branch_id__in=branch_ids)
    if source_year is not None:
        decisions = decisions.filter(source_academic_year=source_year)
    if source_class is not None:
        decisions = decisions.filter(source_class=source_class)
    if programme is not None:
        decisions = decisions.filter(source_enrollment__programme=programme)
    if decision_value in dict(StudentYearDecision.DECISION_CHOICES):
        decisions = decisions.filter(decision=decision_value)
    else:
        decision_value = ""
    if workflow_status in dict(StudentYearDecision.WORKFLOW_STATUS_CHOICES):
        decisions = decisions.filter(workflow_status=workflow_status)
    else:
        workflow_status = ""
    if search:
        decisions = decisions.filter(
            Q(student__matricule__icontains=search)
            | Q(student__user__first_name__icontains=search)
            | Q(student__user__last_name__icontains=search)
            | Q(student__user__username__icontains=search)
        )
    valid_finance_states = {"not_started", "ready", "awaiting_payment", "partial_payment", "active"}
    if finance_state in valid_finance_states:
        decisions = _filter_decisions_by_finance_state(decisions, finance_state)
    else:
        finance_state = ""
    decisions = decisions.order_by("-created_at", "-id")
    decision_total = decisions.count()
    all_decisions = list(decisions[:160])

    # A candidate with an existing decision must never return to the
    # "non demarree" bucket simply because it is beyond the queue page limit.
    candidate_enrollment_ids = [item["enrollment"].id for item in all_candidates]
    decision_ids = set(
        scoped(StudentYearDecision, user=actor).filter(
            source_enrollment_id__in=candidate_enrollment_ids,
        ).values_list("source_enrollment_id", flat=True)
    )
    unstarted_candidates = [
        item for item in all_candidates
        if item["enrollment"].id not in decision_ids
    ]
    active_count = decisions.filter(workflow_status=StudentYearDecision.WORKFLOW_APPLIED).count()
    awaiting_payment_count = decisions.exclude(
        workflow_status=StudentYearDecision.WORKFLOW_APPLIED,
    ).filter(target_inscription__isnull=False).count()
    ready_count = decisions.filter(
        workflow_status=StudentYearDecision.WORKFLOW_FINANCE_VALIDATED,
        target_inscription__isnull=True,
    ).count()
    academic_pending_count = decisions.filter(
        workflow_status=StudentYearDecision.WORKFLOW_DRAFT,
    ).count()
    blocked_count = decisions.filter(
        Q(workflow_status=StudentYearDecision.WORKFLOW_REJECTED)
        | Q(decision__in=TARGET_DECISIONS, target_class__isnull=True)
    ).count()
    eligible_count = len(unstarted_candidates) + decisions.count()
    reenrollment_metrics = {
        "eligible": eligible_count,
        "not_started": len(unstarted_candidates),
        "academic_pending": academic_pending_count,
        "ready": ready_count,
        "awaiting_payment": awaiting_payment_count,
        "active": active_count,
        "blocked": blocked_count,
        "rate": round((active_count / eligible_count) * 100) if eligible_count else 0,
    }
    pending_official = OfficialAnnualDecision.objects.filter(is_final=False)
    if source_year is not None:
        pending_official = pending_official.filter(academic_year=source_year)
    if branch is not None:
        pending_official = pending_official.filter(branch=branch)
    if branch_ids is not None:
        pending_official = pending_official.filter(branch_id__in=branch_ids)
    official_metrics = {
        "total": len(all_candidates),
        "promoted": sum(row["proposed_decision"] == StudentYearDecision.DECISION_PROMOTED for row in all_candidates),
        "with_debt": sum(row["proposed_decision"] == StudentYearDecision.DECISION_PROMOTED_WITH_DEBT for row in all_candidates),
        "repeated": sum(row["proposed_decision"] == StudentYearDecision.DECISION_REPEATED for row in all_candidates),
        "completed": sum(row["proposed_decision"] == StudentYearDecision.DECISION_COMPLETED for row in all_candidates),
        "blocked": pending_official.count(),
    }
    tab_specs = (
        [("overview", "Vue d'ensemble", "layout-dashboard"), ("passages", "Passages", "move-up-right"),
         ("repeated", "Redoublements", "rotate-ccw"), ("debts", "Dettes / cas particuliers", "triangle-alert"),
         ("transmission", "Transmission", "send")]
        if surface == "director" else
        [("todo", "A traiter", "inbox"), ("in_progress", "En cours", "folder-clock"),
         ("payments", "Paiements / validation", "credit-card"), ("completed", "Finalisees", "circle-check"),
         ("history", "Historique", "history")]
    )
    endpoint = reverse("accounts_portal:reenrollment_workspace")
    fixed = f"surface={surface}"
    if source_year:
        fixed += f"&source_year={source_year.id}"
    if target_year:
        fixed += f"&target_year={target_year.id}"
    tab_counts = {
        "passages": official_metrics["promoted"] + official_metrics["with_debt"],
        "repeated": official_metrics["repeated"],
        "debts": sum(bool(row["debt_count"] or row["proposed_decision"] == StudentYearDecision.DECISION_PROMOTED_WITH_DEBT) for row in all_candidates),
        "transmission": official_metrics["total"],
        "todo": sum(row["year_decision"] is None for row in all_candidates),
        "in_progress": sum(row["administrative_state"]["code"] in {"in_progress", "validated"} for row in all_candidates),
        "payments": sum(row["administrative_state"]["code"] == "payment" for row in all_candidates),
        "completed": sum(row["administrative_state"]["code"] == "completed" for row in all_candidates),
    }
    reenrollment_tabs = [
        {"id": key, "label": label, "icon": icon, "count": tab_counts.get(key),
         "href": f"{endpoint}?{fixed}&reenrollment_view={key}",
         "hx_get": f"{endpoint}?{fixed}&reenrollment_view={key}", "hx_target": workspace_target,
         "hx_push_url": "false"}
        for key, label, icon in tab_specs
    ]
    if toast and toast.get("level") == "error":
        toast = {**toast, "level": "danger"}
    return {
        "branch": branch,
        "source_year": source_year,
        "source_class": source_class,
        "target_year": target_year,
        "target_class": target_class,
        "programme": programme,
        "decision_value": decision_value,
        "workflow_status": workflow_status,
        "finance_state": finance_state,
        "search": search,
        "academic_years": academic_years,
        "classes": classes,
        "target_classes": target_classes,
        "candidates": candidate_page.object_list,
        "candidate_page": candidate_page,
        "all_candidate_count": len(all_candidates),
        "class_summaries": list(class_summaries.values()),
        "official_metrics": official_metrics,
        "reenrollment_tabs": reenrollment_tabs,
        "reenrollment_view": subview,
        "candidate_filters_required": candidate_filters_required,
        "decisions": all_decisions,
        "decision_total": decision_total,
        "reenrollment_metrics": reenrollment_metrics,
        "programme_choices": classes.values_list("programme__id", "programme__title").distinct().order_by("programme__title"),
        "decision_choices": StudentYearDecision.DECISION_CHOICES,
        "workflow_status_choices": StudentYearDecision.WORKFLOW_STATUS_CHOICES,
        "target_decision_values": TARGET_DECISIONS,
        "can_propose": can_user_propose_reenrollment(actor) if actor else False,
        "can_academic_validate": can_user_validate_academic(actor) if actor else False,
        "can_finance_validate": can_user_validate_finance(actor) if actor else False,
        "can_apply": can_user_apply_reenrollment(actor) if actor else False,
        "can_reject": can_user_reject_reenrollment(actor) if actor else False,
        "surface": surface,
        "reenrollment_workspace_target": workspace_target,
        "dashboard_type": "reenrollment",
        "toast": toast,
    }


@transaction.atomic
def archive_enrollment_for_transition(*, enrollment, archived_at=None):
    if not isinstance(enrollment, AcademicEnrollment):
        enrollment = scoped(AcademicEnrollment).select_for_update().get(pk=enrollment)
    else:
        enrollment = scoped(AcademicEnrollment).select_for_update().get(pk=enrollment.pk)

    enrollment.status = AcademicEnrollment.STATUS_ARCHIVED
    enrollment.is_active = False
    enrollment.is_archived = True
    enrollment.archived_at = archived_at or timezone.now()
    enrollment.save(update_fields=["status", "is_active", "is_archived", "archived_at"])
    return enrollment


def _carry_forward_debts(source_enrollment, target_enrollment):
    """
    Reporte les dettes academiques non soldees vers la nouvelle inscription.
    Delegue a academics.services.year.carry_forward_debts().
    """
    carry_forward_debts(source_enrollment, target_enrollment)
    student = getattr(source_enrollment.student, "student_profile", None)
    if student is not None:
        StudentAcademicDebt.objects.filter(
            student=student,
            source_academic_year=source_enrollment.academic_year,
        ).exclude(
            status__in=(cycle_constants.DEBT_RESOLVED, cycle_constants.DEBT_CANCELLED),
        ).update(
            current_academic_year=target_enrollment.academic_year,
            current_class=target_enrollment.academic_class,
        )


def _compatible_target_classes(*, source_enrollment, target_academic_year, decision):
    if target_academic_year is None or decision not in TARGET_DECISIONS:
        return []
    queryset = scoped(AcademicClass).filter(
        programme=source_enrollment.programme,
        branch=source_enrollment.branch,
        academic_year=target_academic_year,
        is_active=True,
        is_archived=False,
    )
    if decision == StudentYearDecision.DECISION_REPEATED and target_academic_year is not None:
        return list(queryset.filter(
            level=source_enrollment.academic_class.level,
        ).order_by("name", "id"))
    if decision in {StudentYearDecision.DECISION_PROMOTED, StudentYearDecision.DECISION_PROMOTED_WITH_DEBT} and target_academic_year is not None:
        source_key = academic_level_sort_key(source_enrollment.academic_class.level)
        eligible = [
            candidate
            for candidate in queryset
            if academic_level_sort_key(candidate.level) > source_key
        ]
        if not eligible:
            return []
        next_key = min(academic_level_sort_key(candidate.level) for candidate in eligible)
        return sorted(
            [candidate for candidate in eligible if academic_level_sort_key(candidate.level) == next_key],
            key=lambda candidate: (candidate.display_name, candidate.id),
        )
    return []


def _resolve_target_class(*, source_enrollment, target_academic_year, decision, target_class=None):
    compatible = _compatible_target_classes(
        source_enrollment=source_enrollment,
        target_academic_year=target_academic_year,
        decision=decision,
    )
    if target_class is not None:
        if target_class.pk not in {item.pk for item in compatible}:
            raise ValidationError("La classe cible choisie ne respecte pas la decision academique officielle.")
        return target_class

    return compatible[0] if compatible else None


@transaction.atomic
def propose_student_decision(
    *,
    student,
    source_enrollment,
    target_academic_year=None,
    target_class=None,
    decision=None,
    annual_average=None,
    proposed_by=None,
    note="",
):
    if source_enrollment is not None and proposed_by is not None:
        require_object_scope(source_enrollment, user=proposed_by)
    if target_class is not None and proposed_by is not None:
        require_object_scope(target_class, user=proposed_by)
    if not isinstance(student, Student):
        student = scoped(Student).select_related("user").get(pk=student)

    source_enrollment_id = (
        source_enrollment.pk
        if isinstance(source_enrollment, AcademicEnrollment)
        else source_enrollment
    )
    # The source enrollment is the serialization point for the whole yearly
    # decision.  Lock it before looking up or creating the unique decision so
    # two simultaneous DE submissions cannot race through ``update_or_create``.
    source_enrollment = scoped(AcademicEnrollment).select_for_update().select_related(
        "academic_class",
        "academic_year",
        "programme",
        "branch",
    ).get(pk=source_enrollment_id)

    if source_enrollment.student_id != student.user_id:
        raise ValidationError("L'inscription academique source ne correspond pas a l'etudiant.")
    if proposed_by is not None:
        if not can_user_submit_reenrollment_decision(proposed_by):
            raise ValidationError("Vous ne pouvez pas proposer cette transition.")
        _assert_actor_branch_scope(actor=proposed_by, branch=source_enrollment.branch)

    if annual_average is not None:
        raise ValidationError("La réinscription ne peut pas être décidée depuis une moyenne annuelle saisie manuellement.")
    official_decision = _official_annual_decision_for_enrollment(source_enrollment)
    if official_decision is None:
        raise ValidationError("La réinscription est bloquée tant que la délibération annuelle officielle n'est pas validée.")
    annual_average = official_decision.annual_average
    decision_from_rule = _map_official_decision(official_decision.decision)
    decision = decision or decision_from_rule
    if decision != decision_from_rule:
        expected_label = dict(StudentYearDecision.DECISION_CHOICES).get(decision_from_rule, decision_from_rule)
        raise ValidationError(
            "La decision academique doit suivre le calcul automatique. "
            f"Decision attendue: {expected_label}."
        )

    if target_academic_year is not None and not isinstance(target_academic_year, AcademicYear):
        target_academic_year = AcademicYear.objects.get(pk=target_academic_year)

    if target_class is not None and not isinstance(target_class, AcademicClass):
        target_class = scoped(AcademicClass).get(pk=target_class)

    target_class = _resolve_target_class(
        source_enrollment=source_enrollment,
        target_academic_year=target_academic_year,
        decision=decision,
        target_class=target_class,
    )
    if target_class is not None and target_academic_year is None:
        target_academic_year = target_class.academic_year

    if (
        target_academic_year is not None
        and target_academic_year.start_date <= source_enrollment.academic_year.start_date
    ):
        raise ValidationError("L'annee cible doit etre posterieure a l'annee source.")

    if target_class and (not target_class.is_active or target_class.is_archived):
        raise ValidationError("La classe cible doit etre active et non archivee.")
    if target_class and target_class.academic_year_id != target_academic_year.id:
        raise ValidationError("La classe cible ne correspond pas a l'annee cible.")
    if target_class and target_class.programme_id != source_enrollment.programme_id:
        raise ValidationError("La classe cible doit rester dans le meme programme.")
    if target_class and target_class.branch_id != source_enrollment.branch_id:
        raise ValidationError("La classe cible doit rester dans la meme annexe.")
    if decision in TARGET_DECISIONS and (
        target_class is None or target_academic_year is None
    ):
        raise ValidationError("Classe et annee cible obligatoires pour un passage ou un redoublement.")
    if decision in ADMINISTRATIVE_DECISIONS:
        target_class = None
        target_academic_year = None

    existing = scoped(StudentYearDecision, user=proposed_by).filter(student=student, source_enrollment=source_enrollment).first()
    if existing:
        same_destination = (
            existing.decision == decision
            and existing.target_academic_year_id == getattr(target_academic_year, "id", None)
            and existing.target_class_id == getattr(target_class, "id", None)
        )
        if same_destination and existing.workflow_status != StudentYearDecision.WORKFLOW_REJECTED:
            # Double clic / requete rejouee: keep the already advanced dossier
            # exactly where it is instead of resetting its financial state.
            return existing
        if existing.workflow_status == StudentYearDecision.WORKFLOW_APPLIED or existing.target_inscription_id:
            raise ValidationError("Ce dossier administratif est deja engage et ne peut plus etre repositionne.")

    decision_obj, created = scoped(StudentYearDecision, user=proposed_by).update_or_create(
        student=student,
        source_enrollment=source_enrollment,
        defaults={
            "source_academic_year": source_enrollment.academic_year,
            "source_class": source_enrollment.academic_class,
            "target_academic_year": target_academic_year,
            "target_class": target_class,
            "decision": decision,
            "annual_average": annual_average,
            "decision_payload": _decision_payload_from_official_deliberation(official_decision),
            "note": note,
            "proposed_by": proposed_by,
            # The academic decision has already been validated by the annual
            # jury.  The administrative dossier starts after that gate.
            "workflow_status": StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED,
            "academic_validated_by": official_decision.decided_by,
            "academic_validated_at": official_decision.decided_at,
            "finance_validated_by": None,
            "finance_validated_at": None,
            "rejected_by": None,
            "rejected_at": None,
            "rejection_reason": "",
        },
    )
    if proposed_by and created:
        _audit_decision(
            decision=decision_obj,
            actor=proposed_by,
            action_type=SupportAuditLog.ACTION_REENROLLMENT_PROPOSED,
            details=(
                f"Decision proposee: {decision_obj.get_decision_display()} | "
                f"Source: {source_enrollment.academic_class} | Cible: {target_class or '-'}"
            ),
        )
    if decision_obj.target_academic_year_id:
        _sync_cycle_reenrollment(
            decision=decision_obj,
            status="prepared",
        )
    return decision_obj


@transaction.atomic
def validate_student_decision_academic(*, decision, actor):
    if not can_user_validate_academic(actor):
        raise ValidationError("Vous ne pouvez pas valider pedagogiquement cette decision.")
    decision_pk = decision.pk if isinstance(decision, StudentYearDecision) else decision
    decision = scoped(StudentYearDecision, user=actor).select_related(
        "student",
        "student__user",
        "source_enrollment",
        "target_class",
        "target_academic_year",
    ).select_for_update(of=("self",)).get(pk=decision_pk)
    _assert_actor_branch_scope(actor=actor, branch=decision.source_enrollment.branch)
    if decision.workflow_status != StudentYearDecision.WORKFLOW_DRAFT:
        raise ValidationError("Seule une decision en brouillon peut etre validee pedagogiquement.")
    _validate_decision_ready(decision)
    _assert_decision_matches_academic_rules(decision)
    if decision.source_enrollment.status != AcademicEnrollment.STATUS_ACTIVE:
        raise ValidationError("L'inscription source n'est plus active.")
    decision.workflow_status = StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED
    decision.academic_validated_by = actor
    decision.academic_validated_at = timezone.now()
    decision.save(update_fields=["workflow_status", "academic_validated_by", "academic_validated_at", "updated_at"])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_VALIDATED,
        details="Validation pedagogique enregistree.",
    )
    if decision.target_academic_year_id:
        _sync_cycle_reenrollment(decision=decision, status="started")
    return decision


@transaction.atomic
def validate_student_decision_finance(*, decision, actor):
    if not can_user_validate_finance(actor):
        raise ValidationError("Vous ne pouvez pas valider le volet financier.")
    decision_pk = decision.pk if isinstance(decision, StudentYearDecision) else decision
    decision = scoped(StudentYearDecision, user=actor).select_related(
        "student",
        "student__user",
        "source_enrollment",
        "source_enrollment__inscription",
        "target_class",
        "target_academic_year",
    ).select_for_update(of=("self",)).get(pk=decision_pk)
    _assert_actor_branch_scope(actor=actor, branch=decision.source_enrollment.branch)
    if decision.workflow_status != StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED:
        raise ValidationError("La decision doit d'abord etre validee par la direction de l’école.")
    _validate_decision_ready(decision)
    source_inscription = scoped(Inscription, user=actor).select_for_update().get(
        pk=decision.source_enrollment.inscription_id,
    )
    balance = source_inscription.balance
    if balance > 0 and decision.decision in FINANCE_CLEARANCE_REQUIRED_DECISIONS:
        raise ValidationError(f"Solde restant sur l'ancienne inscription: {balance} FCFA.")
    decision.workflow_status = StudentYearDecision.WORKFLOW_FINANCE_VALIDATED
    decision.finance_validated_by = actor
    decision.finance_validated_at = timezone.now()
    decision.save(update_fields=["workflow_status", "finance_validated_by", "finance_validated_at", "updated_at"])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_VALIDATED,
        details="Visa financier enregistre.",
    )
    return decision


@transaction.atomic
def reject_student_decision(*, decision, actor, reason=""):
    if not can_user_reject_reenrollment(actor):
        raise ValidationError("Vous ne pouvez pas rejeter cette decision.")
    decision_pk = decision.pk if isinstance(decision, StudentYearDecision) else decision
    decision = scoped(StudentYearDecision, user=actor).select_related(
        "student",
        "student__user",
        "source_enrollment",
    ).select_for_update(of=("self",)).get(pk=decision_pk)
    _assert_actor_branch_scope(actor=actor, branch=decision.source_enrollment.branch)
    if decision.workflow_status == StudentYearDecision.WORKFLOW_APPLIED:
        raise ValidationError("Une decision appliquee ne peut pas etre rejetee.")
    if decision.target_inscription_id:
        raise ValidationError(
            "Une decision avec inscription cible preparee ne peut plus etre rejetee. "
            "Annulez d'abord cette inscription par le workflow financier approprie."
        )
    decision.workflow_status = StudentYearDecision.WORKFLOW_REJECTED
    decision.rejected_by = actor
    decision.rejected_at = timezone.now()
    decision.rejection_reason = reason.strip()
    decision.save(update_fields=["workflow_status", "rejected_by", "rejected_at", "rejection_reason", "updated_at"])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_REJECTED,
        details=decision.rejection_reason or "Decision rejetee.",
    )
    if decision.target_academic_year_id:
        _sync_cycle_reenrollment(decision=decision, status="cancelled")
    return decision


def _target_entry_year(target_class):
    digits = "".join(ch for ch in str(target_class.level or "") if ch.isdigit())
    return int(digits) if digits else 1


def _finalize_source_enrollment(*, decision, actor):
    source_enrollment = decision.source_enrollment
    status_by_decision = {
        StudentYearDecision.DECISION_TRANSFERRED: AcademicEnrollment.STATUS_TRANSFERRED,
        StudentYearDecision.DECISION_SUSPENDED: AcademicEnrollment.STATUS_SUSPENDED,
        StudentYearDecision.DECISION_ABANDONED: AcademicEnrollment.STATUS_ABANDONED,
        StudentYearDecision.DECISION_COMPLETED: AcademicEnrollment.STATUS_COMPLETED,
    }
    inscription_status_by_decision = {
        StudentYearDecision.DECISION_TRANSFERRED: Inscription.STATUS_COMPLETED,
        StudentYearDecision.DECISION_SUSPENDED: Inscription.STATUS_SUSPENDED,
        StudentYearDecision.DECISION_ABANDONED: Inscription.STATUS_CANCELLED,
        StudentYearDecision.DECISION_COMPLETED: Inscription.STATUS_COMPLETED,
    }
    if decision.decision not in status_by_decision:
        raise ValidationError("Cette decision administrative n'est pas prise en charge.")

    source_enrollment.status = status_by_decision[decision.decision]
    source_enrollment.is_active = False
    source_enrollment.is_archived = True
    source_enrollment.archived_at = timezone.now()
    source_enrollment.save(update_fields=["status", "is_active", "is_archived", "archived_at"])

    inscription = source_enrollment.inscription
    inscription.status = inscription_status_by_decision[decision.decision]
    inscription.is_archived = True
    inscription.archived_at = timezone.now()
    inscription.save(update_fields=["status", "is_archived", "archived_at", "updated_at"])

    decision.student.current_academic_enrollment = None
    if decision.decision in {
        StudentYearDecision.DECISION_TRANSFERRED,
        StudentYearDecision.DECISION_SUSPENDED,
        StudentYearDecision.DECISION_ABANDONED,
    }:
        decision.student.is_active = False
        decision.student.save(update_fields=["current_academic_enrollment", "is_active"])
    else:
        decision.student.save(update_fields=["current_academic_enrollment"])

    decision.workflow_status = StudentYearDecision.WORKFLOW_APPLIED
    decision.applied_by = actor
    decision.applied_at = timezone.now()
    decision.save(update_fields=["workflow_status", "applied_by", "applied_at", "updated_at"])
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_APPLIED,
        details=f"Decision administrative appliquee: {decision.get_decision_display()}.",
    )
    return decision


@transaction.atomic
def apply_student_decision(*, decision, actor):
    if not can_user_apply_reenrollment(actor):
        raise ValidationError("Vous ne pouvez pas appliquer cette transition.")
    decision_pk = decision.pk if isinstance(decision, StudentYearDecision) else decision
    decision = scoped(StudentYearDecision, user=actor).select_for_update(of=("self",)).select_related(
        "student",
        "student__user",
        "source_enrollment",
        "source_enrollment__inscription",
        "source_enrollment__inscription__candidature",
        "target_class",
        "target_academic_year",
    ).get(pk=decision_pk)
    _assert_actor_branch_scope(actor=actor, branch=decision.source_enrollment.branch)

    if decision.workflow_status == StudentYearDecision.WORKFLOW_APPLIED:
        return decision
    if decision.workflow_status != StudentYearDecision.WORKFLOW_FINANCE_VALIDATED:
        raise ValidationError("La decision doit d'abord etre validee par la direction et la finance.")
    _validate_decision_ready(decision)

    source_enrollment = decision.source_enrollment
    if source_enrollment.status != AcademicEnrollment.STATUS_ACTIVE or not source_enrollment.is_active:
        raise ValidationError("L'inscription source n'est plus active.")
    if decision.decision in ADMINISTRATIVE_DECISIONS:
        return _finalize_source_enrollment(decision=decision, actor=actor)
    if decision.target_inscription_id:
        _sync_cycle_reenrollment(decision=decision, status="pending_payment")
        return decision

    existing_target = scoped(AcademicEnrollment, user=actor).filter(
        student=decision.student.user,
        programme=source_enrollment.programme,
        academic_year=decision.target_academic_year,
        status=AcademicEnrollment.STATUS_ACTIVE,
        is_active=True,
        is_archived=False,
    ).exclude(pk=decision.target_enrollment_id).first()
    if existing_target:
        raise ValidationError("Cet etudiant a deja une inscription academique active pour cette annee cible.")

    source_candidature = source_enrollment.inscription.candidature
    entry_year = _target_entry_year(decision.target_class)
    amount_due = get_positioning_fee_for_level(source_enrollment.programme, decision.target_class.level)
    if amount_due <= 0:
        amount_due = source_enrollment.inscription.amount_due

    candidature, _created = scoped(Candidature, user=actor).get_or_create(
        email=source_candidature.email,
        programme=source_enrollment.programme,
        academic_year=decision.target_academic_year.name,
        defaults={
            "branch": source_enrollment.branch,
            "entry_year": entry_year,
            "first_name": source_candidature.first_name,
            "last_name": source_candidature.last_name,
            "birth_date": source_candidature.birth_date,
            "birth_place": source_candidature.birth_place,
            "gender": source_candidature.gender,
            "phone": source_candidature.phone,
            "address": source_candidature.address,
            "city": source_candidature.city,
            "country": source_candidature.country,
            "status": "accepted",
            "reviewed_by": actor,
            "reviewed_at": timezone.now(),
            "admin_comment": f"Reinscription interne depuis {source_enrollment.academic_year}.",
        },
    )
    if candidature.status not in {"accepted", "accepted_with_reserve"}:
        candidature.status = "accepted"
        candidature.reviewed_by = actor
        candidature.reviewed_at = timezone.now()
        candidature.save(update_fields=["status", "reviewed_by", "reviewed_at", "updated_at"])
    if candidature.branch_id != source_enrollment.branch_id:
        raise ValidationError("La candidature cible existe deja dans une autre annexe.")

    inscription, inscription_created = scoped(Inscription, user=actor).get_or_create(
        candidature=candidature,
        defaults={
            "academic_class": decision.target_class,
            "academic_level": decision.target_class.level,
            "amount_due": amount_due,
            "status": Inscription.STATUS_AWAITING_PAYMENT,
        },
    )
    # An existing paid/assigned inscription has already entered another
    # financial or academic workflow.  Attaching it retroactively would both
    # bypass the payment-triggered activation and risk merging identities.
    inscription = scoped(Inscription, user=actor).select_for_update().get(pk=inscription.pk)
    if not inscription_created and (
        inscription.payments.exists()
        or scoped(AcademicEnrollment, user=actor).filter(inscription=inscription).exists()
    ):
        raise ValidationError(
            "Une inscription cible deja financee ou affectee existe pour cette annee. "
            "Elle ne peut pas etre rattachee a cette decision de reinscription."
        )
    if decision.target_inscription_id and decision.target_inscription_id != inscription.id:
        raise ValidationError("La decision pointe deja vers une autre inscription cible.")
    if inscription.academic_class_id != decision.target_class_id:
        if inscription.payments.exists():
            raise ValidationError("L'inscription cible a deja des paiements et ne peut plus etre repositionnee.")
        inscription.academic_class = decision.target_class
        inscription.academic_level = decision.target_class.level
        inscription.amount_due = amount_due
        inscription.save(update_fields=["academic_class", "academic_level", "amount_due", "updated_at"])
    elif not inscription.payments.exists() and inscription.status == Inscription.STATUS_CREATED:
        inscription.status = Inscription.STATUS_AWAITING_PAYMENT
        inscription.save(update_fields=["status", "updated_at"])

    decision.target_inscription = inscription
    decision.save(update_fields=["target_inscription", "updated_at"])
    _sync_cycle_reenrollment(decision=decision, status="pending_payment")
    _audit_decision(
        decision=decision,
        actor=actor,
        action_type=SupportAuditLog.ACTION_REENROLLMENT_APPLIED,
        details=(
            f"Inscription cible preparee vers {decision.target_class} "
            f"({decision.target_academic_year}); paiement cible attendu."
        ),
    )
    return decision


@transaction.atomic
def activate_reenrollment_from_payment(*, inscription):
    """Activate the target annual enrollment after its first validated payment.

    The ordinary payment workflow calls this function after updating the
    target ``Inscription``.  It keeps the permanent ``Student`` / ``User``
    identity and only then archives the source annual enrollment.
    """
    from payments.models import Payment

    inscription_pk = inscription.pk if isinstance(inscription, Inscription) else inscription
    decision = (
        scoped(StudentYearDecision).select_for_update(of=("self",))
        .select_related(
            "student",
            "student__user",
            "source_enrollment",
            "source_enrollment__inscription",
            "target_class",
            "target_academic_year",
            "finance_validated_by",
        )
        .filter(target_inscription_id=inscription_pk)
        .first()
    )
    if decision is None:
        return None
    if decision.workflow_status == StudentYearDecision.WORKFLOW_APPLIED:
        return decision
    if decision.workflow_status != StudentYearDecision.WORKFLOW_FINANCE_VALIDATED:
        raise ValidationError("La reinscription cible n'est pas prete pour activation.")

    target_inscription = scoped(Inscription).select_for_update().get(pk=inscription_pk)
    if not target_inscription.payments.filter(status=Payment.STATUS_VALIDATED).exists():
        raise ValidationError("Un paiement valide est requis pour activer la reinscription.")
    _validate_decision_ready(decision)

    source_enrollment = decision.source_enrollment
    target_enrollment, _created = scoped(AcademicEnrollment).get_or_create(
        inscription=target_inscription,
        defaults={
            "student": decision.student.user,
            "programme": source_enrollment.programme,
            "branch": source_enrollment.branch,
            "academic_year": decision.target_academic_year,
            "academic_class": decision.target_class,
            "status": AcademicEnrollment.STATUS_ACTIVE,
        },
    )
    if target_enrollment.student_id != decision.student.user_id:
        raise ValidationError("L'inscription academique cible appartient a un autre etudiant.")
    if (
        target_enrollment.programme_id != source_enrollment.programme_id
        or target_enrollment.branch_id != source_enrollment.branch_id
        or target_enrollment.academic_year_id != decision.target_academic_year_id
        or target_enrollment.academic_class_id != decision.target_class_id
    ):
        raise ValidationError("L'inscription academique cible existante ne correspond pas a la decision.")
    if target_enrollment.status != AcademicEnrollment.STATUS_ACTIVE or not target_enrollment.is_active:
        target_enrollment.status = AcademicEnrollment.STATUS_ACTIVE
        target_enrollment.save(update_fields=["status"])

    if source_enrollment.status == AcademicEnrollment.STATUS_ACTIVE and source_enrollment.is_active:
        archive_enrollment_for_transition(enrollment=source_enrollment)
    elif source_enrollment.status != AcademicEnrollment.STATUS_ARCHIVED:
        raise ValidationError("L'inscription academique source ne peut plus etre archivee pour cette transition.")

    _carry_forward_debts(source_enrollment, target_enrollment)
    decision.student.current_academic_enrollment = target_enrollment
    decision.student.save(update_fields=["current_academic_enrollment"])
    decision.target_enrollment = target_enrollment
    decision.workflow_status = StudentYearDecision.WORKFLOW_APPLIED
    decision.applied_by = decision.finance_validated_by
    decision.applied_at = timezone.now()
    decision.save(update_fields=[
        "target_enrollment",
        "workflow_status",
        "applied_by",
        "applied_at",
        "updated_at",
    ])
    _sync_cycle_reenrollment(decision=decision, status="activated")
    from academic_cycle.services.dashboard_access_service import compute_student_access_policy

    compute_student_access_policy(decision.student, decision.target_academic_year)
    if decision.applied_by_id:
        _audit_decision(
            decision=decision,
            actor=decision.applied_by,
            action_type=SupportAuditLog.ACTION_REENROLLMENT_APPLIED,
            details=(
                f"Reinscription activee apres paiement cible vers {decision.target_class} "
                f"({decision.target_academic_year})."
            ),
        )
    return decision
