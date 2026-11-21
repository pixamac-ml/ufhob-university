from __future__ import annotations

from .scoping import scoped, staff_branch_filter, current_navigation

import json
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.core.paginator import Paginator
from django.db.models import Count, F, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from django.urls import reverse
from django.utils import timezone

from academics.models import (
    AcademicClass,
    AcademicDiplomaAward,
    AcademicEnrollment,
    AcademicScheduleEvent,
    AcademicYear,
    EvaluationCampaign,
    LessonLog,
    WeeklyScheduleSlot,
)
from academics.services.schedule_service import get_class_week_schedule_with_weekly_slots
from accounts.access import get_user_position
from accounts.models import (
    AccountSecurityEvent,
    BranchBankTransfer,
    BranchCashMovement,
    BranchExpense,
    FinancialAuditLog,
    BranchMonthlyClosure,
    Profile,
)
from branches.models import Branch
from core.models import SchoolBranch
from formations.models import Programme
from inscriptions.models import Inscription
from payments.models import Payment
from portal.models import AdministrativeDocument, DirectorTeacherAssignment, SupportAuditLog, SupportTicket
from students.models import Student
from students.models import AttendanceAlert, AttendanceRollSheet, StudentAttendance, StudentCase, StudentYearDecision, TeacherAttendance

from .context import resolve_dg_context
from .navigation import domain_for_section
from .selectors import (
    get_active_branches,
    get_active_branch_directors_of_studies,
    get_academic_year_datetime_bounds,
    get_branch_finance,
    get_dg_base_querysets,
    get_latest_payments_for_branch,
    get_recent_candidatures_count,
    get_top_classes_for_branch,
    get_top_programmes_for_branch,
)


@dataclass(frozen=True)
class DgAlert:
    key: str
    severity: str
    type: str
    branch_name: str
    description: str
    owner: str
    status: str
    age: str
    tone: str
    drawer_url: str
    action_name: str
    action_id: int | None


class DgScopeViolation(LookupError):
    """Raised when a requested DG object is outside the active dashboard scope."""


def _percent(part, total):
    if not total:
        return 0
    return round((part / total) * 100)


def _money(value):
    return int(value or 0)


def _parse_period_scope(request):
    period = (request.GET.get("period") or "month").strip().lower()
    allowed = {
        "today": ("Aujourd’hui", 1),
        "week": ("7 jours", 7),
        "month": ("30 jours", 30),
        "quarter": ("90 jours", 90),
        "year": ("12 mois", 365),
    }
    label, days = allowed.get(period, allowed["month"])
    if period not in allowed:
        period = "month"
    start = timezone.localdate() - timedelta(days=max(days - 1, 0))
    return period, label, days, start


def _age_label(value):
    if not value:
        return "-"
    delta = timezone.now() - value
    if delta.days >= 1:
        return f"{delta.days}j"
    hours = int(delta.total_seconds() // 3600)
    if hours >= 1:
        return f"{hours}h"
    minutes = max(int(delta.total_seconds() // 60), 1)
    return f"{minutes}min"


def _performance_label(student_count, class_count, alert_count, balance):
    """Operational vigilance signal — not a certified institutional grade."""
    ratio = int(student_count / class_count) if class_count else 0
    if alert_count >= 5 or (balance is not None and balance < 0) or ratio > 55:
        return "Vigilance élevée", "orange"
    if alert_count >= 2 or ratio > 42:
        return "Vigilance modérée", "blue"
    if student_count == 0:
        return "À constituer", "gray"
    return "Stable", "green"


def _build_alerts(branches, base):
    alerts = []
    pending_payments_by_branch = dict(
        base["pending_payments"]
        .values("inscription__candidature__branch_id")
        .annotate(total=Count("id"))
        .values_list("inscription__candidature__branch_id", "total")
    )
    open_attendance = (
        base["attendance_alerts"]
        .select_related("branch", "student", "student__user")
        .order_by("-triggered_at")[:8]
    )
    for alert in open_attendance:
        student_name = getattr(alert.student, "full_name", "") or str(alert.student)
        alerts.append(
            DgAlert(
                key=f"attendance-{alert.id}",
                severity="Critique" if alert.count >= 5 else "Elevee",
                type="Assiduite",
                branch_name=alert.branch.name,
                description=f"{alert.get_alert_type_display()} - {student_name}",
                owner="Surveillance",
                status="Nouveau",
                age=_age_label(alert.triggered_at),
                tone="red" if alert.count >= 5 else "orange",
                drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=alert&id={alert.id}",
                action_name="resolve_alert",
                action_id=alert.id,
            )
        )

    if len(alerts) < 8:
        cases = (
            base["student_cases"]
            .exclude(status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE})
            .select_related("branch", "student", "student__user")
            .order_by("-created_at")[: 8 - len(alerts)]
        )
        for case in cases:
            alerts.append(
                DgAlert(
                    key=f"case-{case.id}",
                    severity="Critique" if case.priority == StudentCase.PRIORITY_CRITIQUE else "Elevee",
                    type="Suivi etudiant",
                    branch_name=case.branch.name,
                    description=case.title,
                    owner="Surveillance",
                    status=case.get_status_display(),
                    age=_age_label(case.created_at),
                    tone="red" if case.priority == StudentCase.PRIORITY_CRITIQUE else "orange",
                    drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=case&id={case.id}",
                    action_name="escalate_case",
                    action_id=case.id,
                )
            )

    for branch in branches:
        if len(alerts) >= 10:
            break
        pending_payments = pending_payments_by_branch.get(branch.id, 0)
        if pending_payments >= 10:
            alerts.append(
                DgAlert(
                    key=f"finance-{branch.id}",
                    severity="Elevee",
                    type="Finance",
                    branch_name=branch.name,
                    description=f"{pending_payments} paiements en attente",
                    owner="Comptable",
                    status="Nouveau",
                    age="-",
                    tone="orange",
                    drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=finance&branch_id={branch.id}",
                    action_name="followup_finance",
                    action_id=branch.id,
                )
            )
    return alerts


def _build_workflow(base):
    total = base["year_decisions"].count()
    steps = [
        {
            "key": "academic",
            "number": 1,
            "label": "Decision academique",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_DRAFT).count(),
            "tone": "emerald",
        },
        {
            "key": "finance",
            "number": 2,
            "label": "Validation finance",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED).count(),
            "tone": "blue",
        },
        {
            "key": "apply",
            "number": 3,
            "label": "Application passage",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_FINANCE_VALIDATED).count(),
            "tone": "orange",
        },
        {
            "key": "done",
            "number": 4,
            "label": "Reinscription confirmee",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_APPLIED).count(),
            "tone": "violet",
        },
    ]
    for step in steps:
        step["percent"] = _percent(step["count"], total)
        step["drawer_url"] = reverse("accounts_portal:dg_drawer") + f"?kind=workflow&step={step['key']}"

    blocked = list(
        base["year_decisions"]
        .exclude(workflow_status=StudentYearDecision.WORKFLOW_APPLIED)
        .select_related("student", "student__user", "source_enrollment__branch", "source_class")
        .order_by("created_at")[:6]
    )
    return {
        "total": total,
        "steps": steps,
        "blocked_count": base["year_decisions"].exclude(
            workflow_status__in={StudentYearDecision.WORKFLOW_APPLIED, StudentYearDecision.WORKFLOW_REJECTED}
        ).count(),
        "blocked_rows": blocked,
    }


def _build_branch_summaries(branches, base, *, academic_year=None, include_details=False):
    """Build branch KPIs without issuing a query per KPI and per branch.

    Detailed lists are useful only inside a branch drawer.  Keeping them out of
    the dashboard sections avoids multiplying queries as annexes are added.
    """
    enrollment_stats = list(base["enrollments"].values("branch_id").annotate(
        total=Count("student_id", distinct=True), enrollment_count=Count("pk", distinct=True),
    ))
    student_counts = {item["branch_id"]: item["total"] for item in enrollment_stats}
    enrollment_counts = {item["branch_id"]: item["enrollment_count"] for item in enrollment_stats}
    class_counts = dict(
        base["classes"].values("branch_id").annotate(total=Count("id")).values_list("branch_id", "total")
    )
    inscription_counts = dict(
        base["inscriptions"]
        .values("candidature__branch_id")
        .annotate(total=Count("id"))
        .values_list("candidature__branch_id", "total")
    )
    candidature_stats = {
        item["branch_id"]: item
        for item in base["candidatures"]
        .values("branch_id")
        .annotate(
            total=Count("id"),
            accepted=Count(
                "id",
                filter=Q(status__in={"accepted", "accepted_with_reserve"}),
            ),
        )
    }
    payment_stats_by_branch = {
        item["inscription__candidature__branch_id"]: item
        for item in base["payments"]
        .values("inscription__candidature__branch_id")
        .annotate(total=Sum("amount"), count=Count("id"))
    }
    expense_stats = {
        item["branch_id"]: item
        for item in base["expenses"]
        .values("branch_id")
        .annotate(
            total=Sum(
                "amount",
                filter=Q(
                    status__in={
                        BranchExpense.STATUS_SUBMITTED,
                        BranchExpense.STATUS_APPROVED,
                        BranchExpense.STATUS_PAID,
                    }
                ),
            ),
            pending=Count(
                "id",
                filter=Q(
                    status__in={
                        BranchExpense.STATUS_SUBMITTED,
                        BranchExpense.STATUS_APPROVED,
                    }
                ),
            ),
        )
    }
    alert_counts = dict(
        base["attendance_alerts"]
        .values("branch_id")
        .annotate(total=Count("id"))
        .values_list("branch_id", "total")
    )
    directors_by_branch_id = {}
    branch_ids = [branch.id for branch in branches]
    navigation = current_navigation()
    selected_school = getattr(navigation, "selected_school", None)
    for assignment in get_active_branch_directors_of_studies(
        branch_ids,
        school=selected_school,
    ):
        label = assignment.user.get_full_name() or assignment.user.username
        # A school-wide/global academic assignment covers every campus in the
        # current DG school context. A concrete campus remains concrete.
        covered_branch_ids = [assignment.branch_id] if assignment.branch_id else branch_ids
        for covered_branch_id in covered_branch_ids:
            directors_by_branch_id.setdefault(covered_branch_id, []).append(label)

    summaries = []
    for branch in branches:
        payment_stats = payment_stats_by_branch.get(branch.id) or {}
        revenue = _money(payment_stats.get("total"))
        # T6 : les dépenses portent l'école ; sous une école sélectionnée,
        # seules les siennes sont comptées (filtre par école des modèles de caisse).
        expenses = _money((expense_stats.get(branch.id) or {}).get("total"))
        balance = revenue - expenses
        pending_expense_count = (expense_stats.get(branch.id) or {}).get("pending", 0) or 0
        student_count = student_counts.get(branch.id, 0)
        class_count = class_counts.get(branch.id, 0)
        open_alert_count = alert_counts.get(branch.id, 0)
        label, tone = _performance_label(student_count, class_count, open_alert_count, balance)
        candidature_stat = candidature_stats.get(branch.id) or {}
        candidature_count = candidature_stat.get("total", 0)
        accepted_candidature_count = candidature_stat.get("accepted", 0)
        academic_responsible_names = tuple(
            directors_by_branch_id.get(branch.id, [])
        )
        summaries.append(
            {
                "branch": branch,
                # A branch manager and the academic lead are different roles.
                # Keep the former for manager-specific screens but expose the
                # latter wherever DG labels the column "Responsable".
                "manager_name": " · ".join(academic_responsible_names),
                "academic_responsible_names": academic_responsible_names,
                "branch_manager_name": (
                    branch.manager.get_full_name() or branch.manager.username
                    if branch.manager
                    else "Non assigné"
                ),
                "student_count": student_count,
                "enrollment_count": enrollment_counts.get(branch.id, 0),
                "class_count": class_count,
                "active_inscription_count": inscription_counts.get(branch.id, 0),
                "candidature_count": candidature_count,
                "accepted_candidature_count": accepted_candidature_count,
                "admission_conversion_rate": _percent(
                    accepted_candidature_count, candidature_count
                ),
                "revenue_total": revenue,
                "validated_payment_count": payment_stats.get("count", 0),
                "expense_total": expenses,
                "balance_total": balance,
                "campus_ledgers_available": True,
                "pending_expense_count": pending_expense_count,
                "open_alert_count": open_alert_count,
                "top_classes": get_top_classes_for_branch(branch, academic_year=academic_year) if include_details else [],
                "top_programmes": get_top_programmes_for_branch(branch, academic_year=academic_year) if include_details else [],
                "latest_payments": get_latest_payments_for_branch(branch, academic_year=academic_year) if include_details else [],
                "performance_label": label,
                "performance_tone": tone,
                "drawer_url": reverse("accounts_portal:dg_drawer") + f"?kind=branch&branch_id={branch.id}",
            }
        )
    return summaries


def _build_finance(base, branch_summaries):
    revenue = _money(base["payments"].aggregate(total=Sum("amount"))["total"])
    expenses = _money(base["expenses"].filter(
        status__in={
            BranchExpense.STATUS_SUBMITTED,
            BranchExpense.STATUS_APPROVED,
            BranchExpense.STATUS_PAID,
        }
    ).aggregate(total=Sum("amount"))["total"])
    closures = list(
        base["monthly_closures"]
        .order_by("-period_month", "branch__name")[:12]
    )
    return {
        "revenue": revenue,
        "expenses": expenses,
        "balance": revenue - expenses,
        "balance_chart": abs(revenue - expenses),
        "validated_payments": base["payments"].count(),
        "pending_payments": base["pending_payments"].count(),
        "cancelled_payments": base["cancelled_payments"].count(),
        "latest_payments": list(
            base["payments"]
            .select_related("inscription__candidature", "inscription__candidature__branch")
            .order_by("-paid_at")[:8]
        ),
        "top_revenue_branches": sorted(branch_summaries, key=lambda item: item["revenue_total"], reverse=True)[:5],
        "closures": closures,
    }


def _build_cockpit_finance(base):
    """Return only the finance data displayed on the executive cockpit.

    The finance workspace needs closures, expense composition and chart data;
    the landing cockpit does not.  Keeping this selector narrow prevents the
    overview from rebuilding the complete finance domain on every opening.
    """

    payments = base["payments"]
    totals = payments.aggregate(total=Sum("amount"), count=Count("pk"))
    return {
        "revenue": _money(totals["total"]),
        "validated_payments": totals["count"],
        "latest_payments": list(
            payments.select_related("inscription__candidature", "inscription__candidature__branch")
            .order_by("-paid_at")[:5]
        ),
    }


def _attention_item(*, level, title, description, section, icon, date_label="", drawer_url=""):
    tones = {
        "Information": "info",
        "À surveiller": "warning",
        "Action requise": "danger",
        "Critique": "danger",
    }
    return {
        "level": level,
        "tone": tones[level],
        "title": title,
        "description": description,
        "section": section,
        "icon": icon,
        "date_label": date_label,
        "drawer_url": drawer_url,
    }


def _build_executive_attention(branches, base, *, blocked_workflow_count):
    """Select the small set of business signals requiring DG attention.

    This is deliberately not a notification feed: only pending academic,
    financial, staffing and attendance signals with a concrete destination are
    retained.  Every queryset is already constrained by the DG context.
    """

    items = []
    attendance_alerts = list(
        base["attendance_alerts"]
        .select_related("branch", "student", "student__user")
        .order_by("-triggered_at")[:4]
    )
    for alert in attendance_alerts:
        level = "Critique" if alert.count >= 5 else "À surveiller"
        student_name = getattr(alert.student, "full_name", "") or str(alert.student)
        items.append(
            _attention_item(
                level=level,
                title=f"Assiduité : {alert.get_alert_type_display()}",
                description=f"{student_name} · {alert.branch.name}",
                section="alerts",
                icon="triangle-alert",
                date_label=_age_label(alert.triggered_at),
                drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=alert&id={alert.id}",
            )
        )

    open_cases = list(
        base["student_cases"]
        .exclude(status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE})
        .select_related("branch")
        .order_by("-created_at")[:3]
    )
    for case in open_cases:
        level = "Critique" if case.priority == StudentCase.PRIORITY_CRITIQUE else "À surveiller"
        items.append(
            _attention_item(
                level=level,
                title=case.title,
                description=f"Suivi étudiant · {case.branch.name}",
                section="alerts",
                icon="shield-alert",
                date_label=_age_label(case.created_at),
                drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=case&id={case.id}",
            )
        )

    pending_by_branch = list(
        base["pending_payments"]
        .values("inscription__candidature__branch_id", "inscription__candidature__branch__name")
        .annotate(total=Count("id"))
        .filter(total__gte=10)
        .order_by("-total")[:3]
    )
    for row in pending_by_branch:
        branch_id = row["inscription__candidature__branch_id"]
        items.append(
            _attention_item(
                level="Action requise",
                title=f"{row['total']} paiements en attente",
                description=f"Suivi financier · {row['inscription__candidature__branch__name']}",
                section="finance",
                icon="wallet-cards",
                drawer_url=reverse("accounts_portal:dg_drawer") + f"?kind=finance&branch_id={branch_id}",
            )
        )

    if blocked_workflow_count:
        items.append(
            _attention_item(
                level="Action requise",
                title=f"{blocked_workflow_count} décision(s) de passage à traiter",
                description="Les dossiers non appliqués restent à arbitrer dans le périmètre actif.",
                section="workflows",
                icon="list-checks",
                drawer_url=reverse("accounts_portal:dg_drawer") + "?kind=workflow&step=blocked",
            )
        )

    branches_without_manager = [branch for branch in branches if not branch.manager_id]
    if branches_without_manager:
        items.append(
            _attention_item(
                level="Action requise",
                title=f"{len(branches_without_manager)} campus sans responsable",
                description="Un campus sans gestionnaire assigné requiert une décision de couverture.",
                section="rh",
                icon="building-user",
                drawer_url=reverse("accounts_portal:dg_drawer") + "?kind=rh",
            )
        )

    order = {"Critique": 0, "Action requise": 1, "À surveiller": 2, "Information": 3}
    return sorted(items, key=lambda item: order[item["level"]])[:8]


def _scope_support_audit_logs(queryset, dg_context):
    """Apply the immutable event scope, with a safe legacy fallback."""
    queryset = queryset.filter(
        Q(branch_id__in=dg_context.scoped_branch_ids) | Q(branch__isnull=True)
    )
    if dg_context.selected_school:
        queryset = queryset.filter(
            Q(school=dg_context.selected_school)
            | (
                Q(school__isnull=True)
                & (
                    Q(actor__institutional_profile__school=dg_context.selected_school)
                    | Q(target_user__institutional_profile__school=dg_context.selected_school)
                )
            )
        )
    if dg_context.academic_year:
        start, end = get_academic_year_datetime_bounds(dg_context.academic_year)
        queryset = queryset.filter(
            Q(academic_year=dg_context.academic_year)
            | (Q(academic_year__isnull=True) & Q(created_at__gte=start, created_at__lt=end))
        )
    return queryset


def _build_recent_activity(base, *, dg_context, latest_payments=None):
    """Return real operational events from the same sources as Governance audit."""

    events = []
    if latest_payments is None:
        latest_payments = list(base["payments"].select_related("inscription__candidature", "inscription__candidature__branch").order_by("-paid_at")[:5])
    for payment in latest_payments:
        candidate = payment.inscription.candidature
        events.append(
            {
                "title": "Paiement validé",
                "description": f"{candidate.branch.name} · {payment.amount} FCFA",
                "date": timezone.localtime(payment.paid_at).strftime("%d/%m %H:%M"),
                "sort_at": payment.paid_at,
                "icon": "receipt-text",
                "section": "finance",
            }
        )

    support_logs = _scope_support_audit_logs(SupportAuditLog.objects.all(), dg_context)
    for log in list(
        support_logs
        .select_related("branch")
        .order_by("-created_at")[:5]
    ):
        events.append(
            {
                "title": log.get_action_type_display(),
                "description": f"{log.branch.name if log.branch else 'Établissement'} · {log.target_label or 'opération institutionnelle'}",
                "date": timezone.localtime(log.created_at).strftime("%d/%m %H:%M"),
                "sort_at": log.created_at,
                "icon": "badge-check",
                "section": "realtime",
            }
        )
    for log in list(_dg_security_audit_entries(dg_context)[:5]):
        user_label = log.user.get_full_name() or log.user.username if log.user else "Compte inconnu"
        events.append(
            {
                "title": log.get_event_type_display(),
                "description": user_label,
                "date": timezone.localtime(log.created_at).strftime("%d/%m %H:%M"),
                "sort_at": log.created_at,
                "icon": "shield-check",
                "section": "audit",
            }
        )
    return sorted(events, key=lambda item: item["sort_at"], reverse=True)[:6]


def _last_12_month_keys():
    today = timezone.localdate().replace(day=1)
    months = []
    for offset in range(11, -1, -1):
        year = today.year
        month = today.month - offset
        while month <= 0:
            month += 12
            year -= 1
        months.append(timezone.datetime(year, month, 1).date())
    return months


def _academic_year_month_keys(academic_year):
    """Return calendar months covered by the selected academic year."""
    if academic_year is None:
        return _last_12_month_keys()
    current = academic_year.start_date.replace(day=1)
    last = academic_year.end_date.replace(day=1)
    months = []
    while current <= last:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def _monthly_count(qs, date_field):
    rows = (
        qs.annotate(month=TruncMonth(date_field))
        .values("month")
        .annotate(total=Count("id"))
    )
    return {row["month"].date().replace(day=1): row["total"] for row in rows if row["month"]}


def _monthly_sum(qs, date_field, value_field):
    rows = (
        qs.annotate(month=TruncMonth(date_field))
        .values("month")
        .annotate(total=Sum(value_field))
    )
    return {row["month"].date().replace(day=1): _money(row["total"]) for row in rows if row["month"]}


def _week_scope(request=None):
    today = timezone.localdate()
    week_start = today - timedelta(days=today.weekday())
    if request is not None:
        raw_week_start = (request.GET.get("week_start") or "").strip()
        if raw_week_start:
            try:
                parsed = datetime.strptime(raw_week_start, "%Y-%m-%d").date()
                week_start = parsed - timedelta(days=parsed.weekday())
            except ValueError:
                pass
    week_end = week_start + timedelta(days=7)
    week_start_dt = timezone.make_aware(datetime.combine(week_start, time.min))
    week_end_dt = timezone.make_aware(datetime.combine(week_end, time.min))
    today_start_dt = timezone.make_aware(datetime.combine(today, time.min))
    today_end_dt = today_start_dt + timedelta(days=1)
    return today, week_start, week_end, week_start_dt, week_end_dt, today_start_dt, today_end_dt


def _event_row(event):
    start = timezone.localtime(event.start_datetime)
    end = timezone.localtime(event.end_datetime)
    teacher_name = event.teacher.get_full_name() or event.teacher.username if event.teacher_id else "Non assigne"
    return {
        "id": event.id,
        "title": event.ec.title if event.ec_id else event.title,
        "class_name": event.academic_class.display_name,
        "branch_name": event.branch.name,
        "teacher_name": teacher_name,
        "location": event.location or ("En ligne" if event.is_online else "Salle non precisee"),
        "date": start.date(),
        "start": start,
        "end": end,
        "time_range": f"{start:%H:%M} - {end:%H:%M}",
        "status": event.status,
        "status_label": event.get_status_display(),
        "has_lesson_log": bool(getattr(event, "lesson_log_count", 0)),
        "weekday_index": start.date().weekday(),
        "slot_label": start.strftime("%H:%M"),
    }


def _event_status(event):
    """Return a schedule status from either an ORM event or a serialized row."""
    return event.get("status") if isinstance(event, dict) else event.status


def _build_calendar_grid(events, week_start):
    days = []
    labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"]
    today = timezone.localdate()
    for offset, label in enumerate(labels):
        day = week_start + timedelta(days=offset)
        days.append({"label": label, "date": day, "is_today": day == today})

    event_rows = [_event_row(event) for event in events if timezone.localtime(event.start_datetime).date().weekday() < 6]
    standard_slots = ["08:00", "10:00", "14:00", "16:00"]
    all_slots = sorted({event["slot_label"] for event in event_rows})
    slot_labels = standard_slots + [slot for slot in all_slots if slot not in standard_slots]
    slots = []
    for slot_label in slot_labels:
        cells = []
        for offset, day in enumerate(days):
            cell_events = [
                event
                for event in event_rows
                if event["weekday_index"] == offset and event["slot_label"] == slot_label
            ]
            cells.append({"day_date": day["date"], "events": cell_events})
        slots.append({"label": slot_label, "cells": cells})
    return {"days": days, "slots": slots, "week_start": week_start}


def _build_schedule(request, branches, base, *, academic_year=None):
    branch_ids = base["branch_filter"]["id__in"]
    today, week_start, week_end, week_start_dt, week_end_dt, today_start_dt, today_end_dt = _week_scope(request)
    now = timezone.now()
    selected_class_id = (request.GET.get("class_id") or "").strip()
    class_filters = {"academic_year": academic_year} if academic_year is not None else {}
    class_options = list(
        scoped(AcademicClass).filter(
            is_active=True,
            is_archived=False,
            branch_id__in=branch_ids,
            **class_filters,
        )
        .select_related("branch", "programme", "academic_year")
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
        .order_by("branch__name", "level", "programme__title", "id")
    )
    selected_class = None
    if selected_class_id.isdigit():
        selected_class = next((item for item in class_options if item.id == int(selected_class_id)), None)
    if selected_class is None and len(branch_ids) == 1 and class_options:
        selected_class = class_options[0]

    event_filters = {"academic_year": academic_year} if academic_year is not None else {}
    weekly_events_qs = (
        scoped(AcademicScheduleEvent).filter(
            branch_id__in=branch_ids,
            is_active=True,
            start_datetime__gte=week_start_dt,
            start_datetime__lt=week_end_dt,
            **event_filters,
        )
        .select_related("academic_class", "branch", "teacher", "ec", "academic_year")
        .annotate(lesson_log_count=Count("lesson_logs"))
        .order_by("start_datetime", "id")
    )
    if selected_class is not None:
        weekly_events_qs = weekly_events_qs.filter(academic_class=selected_class)
    today_events_qs = weekly_events_qs.filter(start_datetime__gte=today_start_dt, start_datetime__lt=today_end_dt)
    past_course_events = weekly_events_qs.filter(
        event_type=AcademicScheduleEvent.EVENT_TYPE_COURSE,
        start_datetime__lt=now,
    ).exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
    missing_lesson_logs_qs = past_course_events.filter(lesson_logs__isnull=True)
    lesson_log_filters = {"academic_class__academic_year": academic_year} if academic_year is not None else {}
    lesson_logs_qs = scoped(LessonLog).filter(
        branch_id__in=branch_ids,
        date__gte=week_start,
        date__lt=week_end,
        **lesson_log_filters,
    )
    teacher_attendance_filters = {"schedule_event__academic_year": academic_year} if academic_year is not None else {}
    teacher_attendance_qs = scoped(TeacherAttendance).filter(
        branch_id__in=branch_ids,
        date__gte=week_start,
        date__lt=week_end,
        **teacher_attendance_filters,
    )
    student_attendance_filters = {"academic_class__academic_year": academic_year} if academic_year is not None else {}
    student_attendance_qs = scoped(StudentAttendance).filter(
        branch_id__in=branch_ids,
        date__gte=week_start,
        date__lt=week_end,
        **student_attendance_filters,
    )
    roll_sheet_filters = {"academic_class__academic_year": academic_year} if academic_year is not None else {}
    roll_sheets_qs = scoped(AttendanceRollSheet).filter(
        branch_id__in=branch_ids,
        date__gte=week_start,
        date__lt=week_end,
        **roll_sheet_filters,
    )
    weekly_events = list(weekly_events_qs)
    class_schedule = None
    is_week_in_academic_year = (
        academic_year is None
        or not (week_end <= academic_year.start_date or week_start > academic_year.end_date)
    )
    if selected_class is not None and is_week_in_academic_year:
        class_schedule = get_class_week_schedule_with_weekly_slots(selected_class, week_start)
        weekly_events = class_schedule.get("events") or []
    total_events = len(weekly_events)
    completed_events = sum(1 for event in weekly_events if _event_status(event) == AcademicScheduleEvent.STATUS_COMPLETED)
    cancelled_events = sum(1 for event in weekly_events if _event_status(event) == AcademicScheduleEvent.STATUS_CANCELLED)
    postponed_events = sum(1 for event in weekly_events if _event_status(event) == AcademicScheduleEvent.STATUS_POSTPONED)
    ongoing_events = sum(1 for event in weekly_events if _event_status(event) == AcademicScheduleEvent.STATUS_ONGOING)
    planned_events = sum(1 for event in weekly_events if _event_status(event) == AcademicScheduleEvent.STATUS_PLANNED)
    past_by_branch = dict(
        past_course_events.values("branch_id").annotate(total=Count("id")).values_list("branch_id", "total")
    )
    missing_by_branch = dict(
        missing_lesson_logs_qs.values("branch_id").annotate(total=Count("id")).values_list("branch_id", "total")
    )
    teacher_absences_by_branch = dict(
        teacher_attendance_qs.filter(status=TeacherAttendance.STATUS_ABSENT)
        .values("branch_id")
        .annotate(total=Count("id"))
        .values_list("branch_id", "total")
    )
    lesson_log_stats = lesson_logs_qs.aggregate(
        total=Count("id"),
        done=Count("id", filter=Q(status=LessonLog.STATUS_DONE)),
    )
    teacher_attendance_stats = teacher_attendance_qs.aggregate(
        absent=Count("id", filter=Q(status=TeacherAttendance.STATUS_ABSENT)),
        late=Count("id", filter=Q(status=TeacherAttendance.STATUS_LATE)),
    )
    student_attendance_stats = student_attendance_qs.aggregate(
        absent=Count("id", filter=Q(status=StudentAttendance.STATUS_ABSENT)),
        late=Count("id", filter=Q(status=StudentAttendance.STATUS_LATE)),
    )
    roll_sheet_stats = roll_sheets_qs.aggregate(
        total=Count("id"),
        validated=Count("id", filter=Q(status=AttendanceRollSheet.STATUS_VALIDATED)),
    )
    past_course_count = sum(past_by_branch.values())
    lesson_done_count = lesson_log_stats["done"]
    missing_lesson_logs_count = sum(missing_by_branch.values())
    event_status_rows = [
        {"label": "Planifies", "count": planned_events, "tone": "blue"},
        {"label": "En cours", "count": ongoing_events, "tone": "emerald"},
        {"label": "Termines", "count": completed_events, "tone": "slate"},
        {"label": "Reportes", "count": postponed_events, "tone": "amber"},
        {"label": "Annules", "count": cancelled_events, "tone": "rose"},
    ]
    weekday_labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    weekday_rows = []
    today_events_count = 0
    for offset, label in enumerate(weekday_labels):
        day = week_start + timedelta(days=offset)
        count = sum(
            1
            for event in weekly_events
            if (event.get("start_datetime") if isinstance(event, dict) else timezone.localtime(event.start_datetime)).date() == day
        )
        if day == today:
            today_events_count = count
        weekday_rows.append({"label": label, "date": day, "count": count, "percent": _percent(count, total_events)})
    teacher_load = {}
    for event in weekly_events:
        if isinstance(event, dict):
            teacher_name = event.get("teacher_name") or "Non assigne"
            duration_minutes = event.get("duration_minutes") or 0
        else:
            teacher_name = event.teacher.get_full_name() or event.teacher.username if event.teacher_id else "Non assigne"
            duration_minutes = event.duration_minutes
        item = teacher_load.setdefault(teacher_name, {"teacher_name": teacher_name, "count": 0, "minutes": 0})
        item["count"] += 1
        item["minutes"] += duration_minutes
    teacher_load_rows = sorted(teacher_load.values(), key=lambda item: (item["minutes"], item["count"]), reverse=True)[:6]
    for item in teacher_load_rows:
        item["hours"] = round(item["minutes"] / 60, 1)

    branch_rows = []
    for branch in branches:
        branch_events = [
            event
            for event in weekly_events
            if (event.get("branch_name") if isinstance(event, dict) else event.branch_id) == (branch.name if isinstance(event, dict) else branch.id)
        ]
        branch_past_count = past_by_branch.get(branch.id, 0)
        branch_missing_count = missing_by_branch.get(branch.id, 0)
        branch_teacher_absent = teacher_absences_by_branch.get(branch.id, 0)
        branch_cancelled = sum(1 for event in branch_events if _event_status(event) == AcademicScheduleEvent.STATUS_CANCELLED)
        risk_score = branch_missing_count * 8 + branch_teacher_absent * 10 + branch_cancelled * 5
        branch_rows.append(
            {
                "branch": branch,
                "events": len(branch_events),
                "today_events": sum(
                    1
                    for event in branch_events
                    if (event.get("start_datetime") if isinstance(event, dict) else timezone.localtime(event.start_datetime)).date() == today
                ),
                "missing_lesson_logs": branch_missing_count,
                "coverage_rate": _percent(max(branch_past_count - branch_missing_count, 0), branch_past_count),
                "teacher_absences": branch_teacher_absent,
                "cancelled": branch_cancelled,
                "risk_score": risk_score,
            }
        )
    branch_rows = sorted(branch_rows, key=lambda item: (item["risk_score"], item["events"]), reverse=True)
    upcoming_events = list(
        scoped(AcademicScheduleEvent).filter(
            branch_id__in=branch_ids,
            is_active=True,
            start_datetime__gte=now,
            **event_filters,
        )
        .exclude(status=AcademicScheduleEvent.STATUS_CANCELLED)
        .select_related("academic_class", "branch", "teacher", "ec", "academic_year")
        .annotate(lesson_log_count=Count("lesson_logs"))
        .order_by("start_datetime", "id")[:8]
    )
    weekly_slot_count = scoped(WeeklyScheduleSlot).filter(
        branch_id__in=branch_ids,
        is_active=True,
        **event_filters,
    ).count()
    return {
        "today": today,
        "week_start": week_start,
        "week_end": week_end - timedelta(days=1),
        "prev_week_start": week_start - timedelta(days=7),
        "next_week_start": week_start + timedelta(days=7),
        "calendar": class_schedule or _build_calendar_grid(weekly_events, week_start),
        "class_options": class_options,
        "selected_class": selected_class,
        "selected_class_id": str(selected_class.id) if selected_class else "",
        "requires_class_selection": selected_class is None,
        "week_is_in_selected_academic_year": is_week_in_academic_year,
        "total_events": total_events,
        "today_events_count": today_events_count if selected_class is not None else today_events_qs.count(),
        "planned_events": planned_events,
        "ongoing_events": ongoing_events,
        "completed_events": completed_events,
        "cancelled_events": cancelled_events,
        "postponed_events": postponed_events,
        "weekly_slot_count": weekly_slot_count,
        "lesson_logs_count": lesson_log_stats["total"],
        "lesson_done_count": lesson_done_count,
        "missing_lesson_logs_count": missing_lesson_logs_count,
        "lesson_log_coverage_rate": _percent(max(past_course_count - missing_lesson_logs_count, 0), past_course_count),
        "teacher_absences": teacher_attendance_stats["absent"],
        "teacher_lates": teacher_attendance_stats["late"],
        "student_absences": student_attendance_stats["absent"],
        "student_lates": student_attendance_stats["late"],
        "roll_sheets_total": roll_sheet_stats["total"],
        "roll_sheets_validated": roll_sheet_stats["validated"],
        "roll_validation_rate": _percent(roll_sheet_stats["validated"], roll_sheet_stats["total"]),
        "event_status_rows": event_status_rows,
        "weekday_rows": weekday_rows,
        "branch_rows": branch_rows[:8],
        "teacher_load_rows": teacher_load_rows,
        "today_events": [_event_row(event) for event in today_events_qs[:8]],
        "upcoming_events": [_event_row(event) for event in upcoming_events],
        "missing_lesson_rows": [_event_row(event) for event in missing_lesson_logs_qs.select_related("academic_class", "branch", "teacher", "ec")[:8]],
    }


def _build_analytics(base, branch_summaries, *, academic_year=None):
    total_classes = base["classes"].count()
    total_enrollments = base["enrollments"].count()
    avg_fill = int(total_enrollments / total_classes) if total_classes else 0
    sensitive = sorted(branch_summaries, key=lambda item: item["open_alert_count"], reverse=True)[:4]
    months = _academic_year_month_keys(academic_year) if academic_year is not None else _last_12_month_keys()
    labels = [month.strftime("%b %Y") for month in months]
    candidature_counts = _monthly_count(base["candidatures"], "submitted_at")
    payment_revenue = _monthly_sum(base["payments"], "paid_at", "amount")
    payment_counts = _monthly_count(base["payments"], "paid_at")
    risk_values = [
        base["pending_payments"].count(),
        base["student_cases"].exclude(status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE}).count(),
        base["attendance_alerts"].count(),
        base["year_decisions"].exclude(
            workflow_status__in={StudentYearDecision.WORKFLOW_APPLIED, StudentYearDecision.WORKFLOW_REJECTED}
        ).count(),
    ]
    total_candidatures = base["candidatures"].count()
    accepted_candidatures = base["candidatures"].filter(status__in={"accepted", "accepted_with_reserve"}).count()
    rejected_candidatures = base["candidatures"].filter(status="rejected").count()
    to_complete_candidatures = base["candidatures"].filter(status="to_complete").count()
    active_inscriptions = base["inscriptions"].count()
    validated_payments = base["payments"].count()
    pending_payments = base["pending_payments"].count()
    pending_payment_amount = _money(base["pending_payments"].aggregate(total=Sum("amount"))["total"])
    revenue_total = _money(base["payments"].aggregate(total=Sum("amount"))["total"])
    average_payment = int(revenue_total / validated_payments) if validated_payments else 0
    risk_labels = ["Finance", "Suivi etudiant", "Assiduite", "Workflow"]
    risk_tones = ["amber", "rose", "orange", "blue"]
    risk_total = sum(risk_values)
    risk_breakdown = [
        {
            "label": label,
            "value": value,
            "percent": _percent(value, risk_total),
            "tone": tone,
        }
        for label, value, tone in zip(risk_labels, risk_values, risk_tones)
    ]
    monthly_candidatures = [candidature_counts.get(month, 0) for month in months]
    monthly_revenue = [payment_revenue.get(month, 0) for month in months]
    monthly_payments = [payment_counts.get(month, 0) for month in months]
    monthly_table = [
        {
            "label": labels[index],
            "candidatures": monthly_candidatures[index],
            "payments": monthly_payments[index],
            "revenue": monthly_revenue[index],
        }
        for index in range(max(len(months) - 6, 0), len(months))
    ]
    candidature_status_rows = [
        {
            "label": "Acceptees",
            "count": accepted_candidatures,
            "percent": _percent(accepted_candidatures, total_candidatures),
            "tone": "emerald",
        },
        {
            "label": "A completer",
            "count": to_complete_candidatures,
            "percent": _percent(to_complete_candidatures, total_candidatures),
            "tone": "amber",
        },
        {
            "label": "Refusees",
            "count": rejected_candidatures,
            "percent": _percent(rejected_candidatures, total_candidatures),
            "tone": "rose",
        },
    ]
    workflow_status_rows = [
        {
            "label": "Brouillon",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_DRAFT).count(),
            "tone": "slate",
        },
        {
            "label": "Pedagogie validee",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_ACADEMIC_VALIDATED).count(),
            "tone": "blue",
        },
        {
            "label": "Finance validee",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_FINANCE_VALIDATED).count(),
            "tone": "orange",
        },
        {
            "label": "Appliquees",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_APPLIED).count(),
            "tone": "emerald",
        },
        {
            "label": "Rejetees",
            "count": base["year_decisions"].filter(workflow_status=StudentYearDecision.WORKFLOW_REJECTED).count(),
            "tone": "rose",
        },
    ]
    top_programmes = list(
        base["candidatures"]
        .values("programme__title")
        .annotate(total=Count("id"))
        .order_by("-total", "programme__title")[:5]
    )
    overloaded_classes = list(
        base["classes"]
        .select_related("branch", "programme")
        .annotate(active_students=Count("enrollments", filter=Q(enrollments__is_active=True)))
        .filter(active_students__gt=0)
        .order_by("-active_students", "branch__name", "level")[:6]
    )
    pending_payment_counts = dict(
        base["pending_payments"]
        .values("inscription__candidature__branch_id")
        .annotate(total=Count("id"))
        .values_list("inscription__candidature__branch_id", "total")
    )
    for item in branch_summaries:
        item["analytics_pending_payment_count"] = pending_payment_counts.get(item["branch"].id, 0)
        item["analytics_risk_score"] = (
            item["open_alert_count"] * 10
            + item["analytics_pending_payment_count"] * 3
            + item["pending_expense_count"] * 2
            # A School-only view deliberately has no campus-ledger balance:
            # unknown is not a negative financial position.
            + (12 if item["balance_total"] is not None and item["balance_total"] < 0 else 0)
        )
    branch_health_rows = sorted(
        branch_summaries,
        key=lambda item: (item["analytics_risk_score"], item["student_count"]),
        reverse=True,
    )[:6]
    branch_comparison_rows = sorted(
        branch_summaries,
        key=lambda item: item["branch"].name.casefold(),
    )
    return {
        "class_fill_rate": min(avg_fill * 2, 100),
        "average_students_per_class": avg_fill,
        "total_enrollments": total_enrollments,
        "classes_total": total_classes,
        "classes_normal": max(total_classes - sum(1 for item in branch_summaries if item["open_alert_count"] > 0), 0),
        "classes_attention": sum(1 for item in branch_summaries if item["open_alert_count"] > 0),
        "classes_overloaded": sum(1 for item in branch_summaries if item["student_count"] and item["class_count"] and item["student_count"] / item["class_count"] > 55),
        "classes_empty": base["classes"].annotate(
            active_count=Count("enrollments", filter=Q(enrollments__is_active=True))
        ).filter(active_count=0).count(),
        "sensitive_branches": sensitive,
        "branch_health_rows": branch_health_rows,
        "branch_comparison_rows": branch_comparison_rows,
        "overloaded_classes": overloaded_classes,
        "total_candidatures": total_candidatures,
        "accepted_candidatures": accepted_candidatures,
        "rejected_candidatures": rejected_candidatures,
        "to_complete_candidatures": to_complete_candidatures,
        "admission_conversion_rate": _percent(accepted_candidatures, total_candidatures),
        "inscription_conversion_rate": _percent(active_inscriptions, accepted_candidatures),
        "payment_conversion_rate": _percent(validated_payments, active_inscriptions),
        "active_inscriptions": active_inscriptions,
        "validated_payments": validated_payments,
        "pending_payments": pending_payments,
        "pending_payment_amount": pending_payment_amount,
        "average_payment": average_payment,
        "candidature_status_rows": candidature_status_rows,
        "workflow_status_rows": workflow_status_rows,
        "top_programmes": top_programmes,
        "risk_breakdown": risk_breakdown,
        "risk_total": risk_total,
        "monthly_table": monthly_table,
        "monthly_labels": labels,
        "monthly_labels_json": json.dumps(labels),
        "monthly_candidatures_json": json.dumps(monthly_candidatures),
        "monthly_revenue_json": json.dumps(monthly_revenue),
        "monthly_payments_json": json.dumps(monthly_payments),
        "risk_labels_json": json.dumps(risk_labels),
        "risk_values_json": json.dumps(risk_values),
    }


def _build_rh(base, branches):
    branch_ids = [branch.id for branch in branches]
    staff_queryset = (
        scoped(Profile).filter(user_type="staff")
        .filter(staff_branch_filter(branch_ids))
        .select_related("user__institutional_profile__school", "branch")
    )
    staff_by_position = list(
        staff_queryset
        .values("position")
        .annotate(total=Count("id"))
        .order_by("-total")[:5]
    )
    return {
        "active_staff": base["staff"].count(),
        "branches_with_manager": sum(1 for branch in branches if branch.manager_id),
        "branches_without_manager": sum(1 for branch in branches if not branch.manager_id),
        "positions": staff_by_position,
        "staff_rows": list(staff_queryset.order_by("branch__name", "position", "user__last_name")[:24]),
        "recruitment_drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=recruitment",
    }


def build_dg_staff_workspace(request):
    """Return the server-scoped, paginated RH workspace for the DG.

    The dashboard context remains the authoritative annexe scope.  Section
    filters can only narrow that scope; they can never introduce another
    annexe into a DG result set.
    """

    dg_context = resolve_dg_context(request, accept_legacy_branch_param=False)
    branch_ids = dg_context.scoped_branch_ids
    query = (request.GET.get("q") or "").strip()[:120]
    position = (request.GET.get("position") or "").strip()
    employment_status = (request.GET.get("employment_status") or "").strip()
    account_status = (request.GET.get("account_status") or "").strip()
    requested_branch_id = (request.GET.get("staff_branch_id") or "").strip()

    staff_queryset = (
        scoped(Profile).filter(user_type="staff")
        .filter(staff_branch_filter(branch_ids))
        .select_related("user__institutional_profile__school", "branch")
    )
    if query:
        staff_queryset = staff_queryset.filter(
            Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
            | Q(user__username__icontains=query)
            | Q(user__email__icontains=query)
            | Q(employee_code__icontains=query)
            | Q(position__icontains=query)
            | Q(phone__icontains=query)
            | Q(branch__name__icontains=query)
        )
    valid_positions = {value for value, _label in Profile.POSITION_CHOICES}
    if position in valid_positions:
        staff_queryset = staff_queryset.filter(position=position)
    else:
        position = ""
    valid_employment_statuses = {value for value, _label in Profile.EMPLOYMENT_STATUS_CHOICES}
    if employment_status in valid_employment_statuses:
        staff_queryset = staff_queryset.filter(employment_status=employment_status)
    else:
        employment_status = ""
    if account_status == "active":
        staff_queryset = staff_queryset.filter(user__is_active=True)
    elif account_status == "inactive":
        staff_queryset = staff_queryset.filter(user__is_active=False)
    else:
        account_status = ""
    if requested_branch_id.isdigit() and int(requested_branch_id) in branch_ids:
        staff_queryset = staff_queryset.filter(branch_id=int(requested_branch_id))
    else:
        requested_branch_id = ""

    staff_queryset = staff_queryset.order_by("branch__name", "position", "user__last_name", "user__first_name")
    staff_page = Paginator(staff_queryset, 20).get_page(request.GET.get("page"))
    from accounts.position_registry import POSITION_REGISTRY

    from .forms import DG_RECRUITMENT_POSITION_CHOICES
    position_labels = dict(DG_RECRUITMENT_POSITION_CHOICES)
    table_rows = []
    for profile in staff_page.object_list:
        account_active = bool(profile.user.is_active)
        account_label = "Actif" if account_active else "Désactivé"
        table_rows.append(
            {
                "id": f"dg-staff-{profile.id}",
                "label": profile.user.get_full_name() or profile.user.username,
                "cells": [
                    {
                        "value": profile.user.get_full_name() or profile.user.username,
                        "secondary": profile.employee_code or profile.user.email or profile.user.username,
                        "strong": True,
                    },
                    {"value": profile.user.email or "—"},
                    {"value": position_labels.get(getattr(getattr(profile.user, "institutional_profile", None), "position", profile.position), profile.institutional_position_label)},
                    {"value": getattr(getattr(profile.user, "institutional_profile", None), "school", None) or "Toutes les écoles"},
                    {"value": profile.branch.name if profile.branch_id else "Tous les campus du périmètre"},
                    {"value": getattr(getattr(profile.user, "institutional_profile", None), "scope_label", "Non défini")},
                    {"value": account_label, "tone": "success" if account_active else "danger"},
                    {"value": profile.user.last_login or "Jamais"},
                ],
                "actions": [
                    {
                        "label": "Fiche",
                        "icon": "panel-right-open",
                        "get_url": f"{reverse('accounts_portal:dg_drawer')}?kind=staff&id={profile.id}",
                        "target": "#executive-drawer-content",
                        "swap": "innerHTML",
                        "open_overlay": "executive-drawer",
                    }
                ],
            }
        )

    base_params = request.GET.copy()
    for key in ("page", "q", "position", "employment_status", "account_status", "staff_branch_id"):
        base_params.pop(key, None)
    base_params["academic_year_id"] = str(dg_context.academic_year.id) if dg_context.academic_year else ""
    base_params["scope_branch_id"] = dg_context.selected_branch_id
    base_params["scope_school_id"] = dg_context.selected_school_id
    base_params["period"] = request.GET.get("period") or "month"
    section_url = reverse("accounts_portal:dg_section", kwargs={"section": "rh"})

    def page_url(page_number):
        params = base_params.copy()
        params.update(
            {
                "q": query,
                "position": position,
                "employment_status": employment_status,
                "account_status": account_status,
                "staff_branch_id": requested_branch_id,
                "page": page_number,
            }
        )
        return f"{section_url}?{params.urlencode()}"

    active_filters = []
    if query:
        active_filters.append(f"Recherche : {query}")
    if requested_branch_id:
        branch = next((item for item in dg_context.scoped_branches if item.id == int(requested_branch_id)), None)
        if branch:
            active_filters.append(f"Campus : {branch.name}")
    if position:
        active_filters.append(f"Fonction : {position_labels.get(position, position)}")
    if employment_status:
        active_filters.append(f"Statut : {employment_labels[employment_status]}")
    if account_status:
        active_filters.append(f"Compte : {'Actif' if account_status == 'active' else 'Désactivé'}")

    return {
        "staff_filter_action": section_url,
        "staff_filter_reset_url": f"{section_url}?{base_params.urlencode()}",
        "staff_filter_hidden_fields": [
            {"name": "academic_year_id", "value": base_params["academic_year_id"]},
            {"name": "scope_branch_id", "value": base_params["scope_branch_id"]},
            {"name": "scope_school_id", "value": base_params["scope_school_id"]},
            {"name": "period", "value": base_params["period"]},
        ],
        "staff_filters": [
            {
                "name": "q",
                "label": "Recherche",
                "type": "search",
                "value": query,
                "placeholder": "Nom, matricule, fonction, email ou téléphone",
                "clearable": True,
            },
            {
                "name": "staff_branch_id",
                "label": "Campus",
                "options": [{"value": "", "label": "Tous les campus", "selected": not requested_branch_id}]
                + [
                    {"value": str(branch.id), "label": branch.name, "selected": str(branch.id) == requested_branch_id}
                    for branch in dg_context.scoped_branches
                ],
            },
            {
                "name": "position",
                "label": "Fonction",
                "options": [{"value": "", "label": "Toutes les fonctions", "selected": not position}]
                + [
                    {"value": value, "label": label, "selected": value == position}
                    for value, label in position_labels.items()
                ],
            },
            {
                "name": "employment_status",
                "label": "Statut RH",
                "options": [{"value": "", "label": "Tous les statuts", "selected": not employment_status}]
                + [
                    {"value": value, "label": label, "selected": value == employment_status}
                    for value, label in Profile.EMPLOYMENT_STATUS_CHOICES
                ],
            },
            {
                "name": "account_status",
                "label": "État du compte",
                "options": [
                    {"value": "", "label": "Tous les comptes", "selected": not account_status},
                    {"value": "active", "label": "Actif", "selected": account_status == "active"},
                    {"value": "inactive", "label": "Désactivé", "selected": account_status == "inactive"},
                ],
            },
        ],
        "staff_active_filters": active_filters,
        "staff_headers": ["Personnel", "Email", "Fonction", "École", "Campus", "Périmètre", "Compte", "Dernière connexion"],
        "staff_rows": table_rows,
        "staff_result_count": staff_page.paginator.count,
        "staff_page": staff_page.number,
        "staff_page_count": staff_page.paginator.num_pages,
        "staff_previous_url": page_url(staff_page.previous_page_number()) if staff_page.has_previous() else "",
        "staff_next_url": page_url(staff_page.next_page_number()) if staff_page.has_next() else "",
    }


def _build_executive_summary(base, branch_summaries, finance, analytics, schedule, workflow, rh):
    total_students = base["students"].count()
    total_classes = base["classes"].count()
    open_alerts = base["attendance_alerts"].count()
    total_candidatures = analytics["total_candidatures"]
    accepted_candidatures = analytics["accepted_candidatures"]
    pending_candidatures = base["candidatures"].filter(status__in={"submitted", "under_review", "to_complete"}).count()
    active_inscriptions = analytics["active_inscriptions"]
    pending_payments = analytics["pending_payments"]
    pending_payment_amount = analytics["pending_payment_amount"]
    validated_payments = analytics["validated_payments"]
    finance_balance = finance["balance"]
    total_events = schedule["total_events"]
    completed_events = schedule["completed_events"]
    missing_lesson_logs = schedule["missing_lesson_logs_count"]
    teacher_absences = schedule["teacher_absences"]
    student_absences = schedule["student_absences"]
    workflow_blocked = workflow["blocked_count"]
    branches_without_manager = rh["branches_without_manager"]
    operational_flags = [
        {"label": "Alertes", "value": open_alerts, "tone": "rose" if open_alerts else "emerald"},
        {"label": "Paiements attente", "value": pending_payments, "tone": "amber" if pending_payments else "emerald"},
        {"label": "Cahiers manquants", "value": missing_lesson_logs, "tone": "rose" if missing_lesson_logs else "emerald"},
        {"label": "Dossiers bloques", "value": workflow_blocked, "tone": "rose" if workflow_blocked else "emerald"},
        {"label": "Managers a affecter", "value": branches_without_manager, "tone": "amber" if branches_without_manager else "emerald"},
    ]
    executive_cards = [
        {
            "label": "Conversion admissions",
            "value": f"{_percent(accepted_candidatures, total_candidatures)}%",
            "detail": f"{accepted_candidatures} acceptees / {total_candidatures}",
            "tone": "blue",
            "icon": "fa-user-check",
        },
        {
            "label": "Inscriptions actives",
            "value": active_inscriptions,
            "detail": f"{pending_candidatures} candidatures a traiter",
            "tone": "emerald",
            "icon": "fa-id-card",
        },
        {
            "label": "Solde consolide",
            "value": finance_balance,
            "detail": f"{finance['revenue']} revenus / {finance['expenses']} depenses",
            "tone": "rose" if finance_balance < 0 else "slate",
            "icon": "fa-scale-balanced",
        },
        {
            "label": "Paiements en attente",
            "value": pending_payments,
            "detail": f"{pending_payment_amount} FCFA",
            "tone": "amber" if pending_payments else "emerald",
            "icon": "fa-clock",
        },
        {
            "label": "Cours semaine",
            "value": total_events,
            "detail": f"{completed_events} termines, {missing_lesson_logs} cahiers manquants",
            "tone": "cyan",
            "icon": "fa-calendar-days",
        },
        {
            "label": "Assiduite",
            "value": student_absences + teacher_absences,
            "detail": f"{student_absences} abs. etudiants / {teacher_absences} abs. profs",
            "tone": "orange" if student_absences or teacher_absences else "emerald",
            "icon": "fa-user-clock",
        },
        {
            "label": "Workflow passages",
            "value": workflow_blocked,
            "detail": f"{workflow['total']} decisions en base",
            "tone": "rose" if workflow_blocked else "emerald",
            "icon": "fa-arrows-rotate",
        },
        {
            "label": "Couverture RH",
            "value": rh["active_staff"],
            "detail": f"{branches_without_manager} campus sans gestionnaire",
            "tone": "violet",
            "icon": "fa-user-group",
        },
    ]
    known_balance_branches = [
        item for item in branch_summaries if item["balance_total"] is not None
    ]
    top_balance_branches = sorted(
        known_balance_branches, key=lambda item: item["balance_total"]
    )[:5]
    top_risk_branches = sorted(
        branch_summaries,
        key=lambda item: (
            item["open_alert_count"],
            item["pending_expense_count"],
            item.get("analytics_pending_payment_count", 0),
            -(item["balance_total"] or 0),
        ),
        reverse=True,
    )[:5]
    action_center = [
        {
            "label": "Traiter les alertes",
            "detail": f"{open_alerts} alertes ouvertes",
            "section": "alerts",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=alert",
            "icon": "fa-triangle-exclamation",
            "tone": "rose" if open_alerts else "emerald",
            "count": open_alerts,
        },
        {
            "label": "Ouvrir le suivi finance",
            "detail": f"{pending_payment_amount} FCFA en attente",
            "section": "finance",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=finance",
            "icon": "fa-money-bill-transfer",
            "tone": "amber" if pending_payments else "emerald",
            "count": pending_payments,
        },
        {
            "label": "Suivre les passages",
            "detail": f"{workflow_blocked} dossiers a arbitrer",
            "section": "workflows",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=workflow&step=blocked",
            "icon": "fa-arrows-rotate",
            "tone": "rose" if workflow_blocked else "blue",
            "count": workflow_blocked,
        },
        {
            "label": "Verifier le planning",
            "detail": f"{missing_lesson_logs} cahiers manquants",
            "section": "schedule",
            "drawer_url": "",
            "icon": "fa-calendar-check",
            "tone": "amber" if missing_lesson_logs else "emerald",
            "count": missing_lesson_logs,
        },
        {
            "label": "Affecter les managers",
            "detail": f"{branches_without_manager} campus sans gestionnaire",
            "section": "rh",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=rh",
            "icon": "fa-building-user",
            "tone": "amber" if branches_without_manager else "emerald",
            "count": branches_without_manager,
        },
        {
            "label": "Analyser les campus",
            "detail": f"{len(top_risk_branches)} campus à surveiller",
            "section": "analytics",
            "drawer_url": reverse("accounts_portal:dg_drawer") + "?kind=analytics",
            "icon": "fa-chart-line",
            "tone": "blue",
            "count": len(top_risk_branches),
        },
    ]
    return {
        "total_students": total_students,
        "total_classes": total_classes,
        "validated_payments": validated_payments,
        "pending_candidatures": pending_candidatures,
        "operational_flags": operational_flags,
        "executive_cards": executive_cards,
        "top_balance_branches": top_balance_branches,
        "top_risk_branches": top_risk_branches,
        "action_center": action_center,
    }


def build_dg_shell_context(request, base_context_builder):
    """Build only the context required to render the DG shell.

    The first page response contains a UI Core loading state; its workspace is
    then loaded through the section endpoint.  Computing every finance, RH,
    schedule and analytics aggregate before returning that loading state caused
    a full duplicate dashboard calculation.
    """
    period, period_label, period_days, period_start = _parse_period_scope(request)
    user_position = get_user_position(request.user)
    dg_context = resolve_dg_context(request)
    branch_ids = [branch.id for branch in dg_context.scoped_branches]
    base = get_dg_base_querysets(branch_ids, academic_year=dg_context.academic_year)
    blocked_workflow_count = base["year_decisions"].exclude(
        workflow_status__in={
            StudentYearDecision.WORKFLOW_APPLIED,
            StudentYearDecision.WORKFLOW_REJECTED,
        }
    ).count()

    context = base_context_builder(
        request,
        page_title="Dashboard Directeur General",
        module_cards=["Pilotage multi-campus"],
    )
    context.update(
        {
            "dashboard_kind": "Direction generale",
            "executive_display_name": (
                "Directrice Generale Adjointe"
                if user_position == "deputy_executive_director"
                else "Directeur General"
            ),
            "executive_display_short": "DGA" if user_position == "deputy_executive_director" else "DG",
            "generated_at": timezone.now(),
            # This filter currently scopes the admissions watch window only.
            # Finance and academic KPIs remain explicitly labelled by academic
            # year until their domain-specific period contract is delivered.
            "dashboard_period": period,
            "dashboard_period_label": period_label,
            "dashboard_period_scope_label": f"Veille admissions : {period_label}",
            "dashboard_period_days": period_days,
            "dashboard_period_start": period_start,
            "all_branches": dg_context.all_branches,
            "selected_branch": dg_context.selected_branch,
            "selected_branch_id": dg_context.selected_branch_id,
            "academic_years": dg_context.academic_years,
            "selected_academic_year": dg_context.academic_year,
            "selected_academic_year_id": str(dg_context.academic_year.id) if dg_context.academic_year else "",
            "dashboard_mode": dg_context.mode,
            "dashboard_scope_label": dg_context.scope_label,
            "total_branches": len(dg_context.scoped_branches),
            "total_students": base["students"].count(),
            "total_classes": base["classes"].count(),
            "total_active_inscriptions": base["inscriptions"].count(),
            "open_alerts": base["attendance_alerts"].count(),
            "pending_payments": base["pending_payments"].count(),
            "workflow": {"blocked_count": blocked_workflow_count},
        }
    )
    context.update(dg_context.template_context())
    return context


def build_dg_overview_context(request, base_context_builder):
    """Build the DG cockpit from targeted selectors only.

    The overview intentionally avoids schedule, analytics and RH detail
    builders.  Those domain-specific calculations stay lazy behind their own
    sections while the cockpit still exposes the executive signals needed to
    decide where to go next.
    """

    period, period_label, period_days, period_start = _parse_period_scope(request)
    user_position = get_user_position(request.user)
    dg_context = resolve_dg_context(request)
    branches = dg_context.scoped_branches
    branch_ids = [branch.id for branch in branches]
    academic_year = dg_context.academic_year
    base = get_dg_base_querysets(branch_ids, academic_year=academic_year)
    branch_summaries = _build_branch_summaries(branches, base, academic_year=academic_year)
    blocked_workflow_count = base["year_decisions"].exclude(
        workflow_status__in={
            StudentYearDecision.WORKFLOW_APPLIED,
            StudentYearDecision.WORKFLOW_REJECTED,
        }
    ).count()
    finance = _build_cockpit_finance(base)
    executive_attention = _build_executive_attention(
        branches,
        base,
        blocked_workflow_count=blocked_workflow_count,
    )
    recent_activity = _build_recent_activity(base, dg_context=dg_context, latest_payments=finance["latest_payments"])
    critical_alerts = base["attendance_alerts"].filter(count__gte=5).count() + base["student_cases"].filter(
        priority=StudentCase.PRIORITY_CRITIQUE,
    ).exclude(status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE}).count()
    overview_tones = {
        "green": "success",
        "orange": "warning",
        "red": "danger",
        "blue": "info",
        "gray": "neutral",
    }
    overview_branch_rows = [
        {
            "id": f"dg-overview-branch-{item['branch'].id}",
            "label": item["branch"].name,
            "cells": [
                {"value": item["branch"].name, "strong": True},
                {"value": item.get("manager_name") or "Non assigné"},
                {"value": item.get("student_count", 0), "amount": True},
                {"value": item.get("active_inscription_count", 0), "amount": True},
                {"value": item.get("open_alert_count", 0), "amount": True},
                {
                    "value": item.get("performance_label") or "À suivre",
                    "tone": overview_tones.get(item.get("performance_tone"), "neutral"),
                },
            ],
            "actions": [
                {
                    "label": "Détail",
                    "icon": "panel-right-open",
                    "get_url": item["drawer_url"],
                    "target": "#executive-drawer-content",
                    "swap": "innerHTML",
                    "open_overlay": "executive-drawer",
                },
            ],
        }
        for item in branch_summaries
    ]

    context = base_context_builder(
        request,
        page_title="Dashboard Directeur Général",
        module_cards=["Cockpit exécutif"],
    )
    context.update(
        {
            "dashboard_kind": "Direction générale",
            "executive_display_name": (
                "Directrice Générale Adjointe"
                if user_position == "deputy_executive_director"
                else "Directeur Général"
            ),
            "executive_display_short": "DGA" if user_position == "deputy_executive_director" else "DG",
            "generated_at": timezone.now(),
            "dashboard_period": period,
            "dashboard_period_label": period_label,
            "dashboard_period_scope_label": f"Veille admissions : {period_label}",
            "dashboard_period_days": period_days,
            "dashboard_period_start": period_start,
            "all_branches": dg_context.all_branches,
            "selected_branch": dg_context.selected_branch,
            "selected_branch_id": dg_context.selected_branch_id,
            "academic_years": dg_context.academic_years,
            "selected_academic_year": academic_year,
            "selected_academic_year_id": str(academic_year.id) if academic_year else "",
            "dashboard_mode": dg_context.mode,
            "dashboard_scope_label": dg_context.scope_label,
            "total_branches": len(branches),
            "total_students": base["students"].count(),
            "total_classes": sum(item["class_count"] for item in branch_summaries),
            "total_active_inscriptions": sum(item["active_inscription_count"] for item in branch_summaries),
            "open_alerts": sum(item["open_alert_count"] for item in branch_summaries),
            "critical_alerts": critical_alerts,
            "workflow": {"blocked_count": blocked_workflow_count},
            "finance": finance,
            "branch_summaries": branch_summaries,
            "executive_attention": executive_attention,
            "recent_activity": recent_activity,
            "overview_branch_headers": [
                "Campus",
                "Responsable",
                "Étudiants",
                "Inscriptions",
                "Alertes",
                "Vigilance",
            ],
            "overview_branch_rows": overview_branch_rows,
            "overview_branch_count": len(overview_branch_rows),
            "empty_list": [],
        }
    )
    from .school_reports import summary_context
    context.update(dg_context.template_context())
    context.update(summary_context(dg_context))
    return context


def build_dg_dashboard_context(request, base_context_builder):
    period, period_label, period_days, period_start = _parse_period_scope(request)
    user_position = get_user_position(request.user)
    is_deputy = user_position == "deputy_executive_director"
    dg_context = resolve_dg_context(request)
    all_branches = dg_context.all_branches
    branches = dg_context.scoped_branches
    selected_branch = dg_context.selected_branch
    selected_branch_id = dg_context.selected_branch_id
    academic_year = dg_context.academic_year
    branch_ids = [branch.id for branch in branches]
    today_start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    today_end = today_start + timedelta(days=1)
    base = get_dg_base_querysets(branch_ids, academic_year=academic_year)
    branch_summaries = _build_branch_summaries(branches, base, academic_year=academic_year)
    alerts = _build_alerts(branches, base)
    workflow = _build_workflow(base)
    finance = _build_finance(base, branch_summaries)
    analytics = _build_analytics(base, branch_summaries, academic_year=academic_year)
    schedule = _build_schedule(request, branches, base, academic_year=academic_year)
    rh = _build_rh(base, branches)
    executive_summary = _build_executive_summary(base, branch_summaries, finance, analytics, schedule, workflow, rh)
    overview_tones = {
        "green": "success",
        "orange": "warning",
        "red": "danger",
        "blue": "info",
    }
    overview_branch_rows = [
        {
            "id": f"dg-overview-branch-{item['branch'].id}",
            "label": item["branch"].name,
            "cells": [
                {"value": item["branch"].name, "strong": True},
                {"value": item.get("manager_name") or "Non assigné"},
                {"value": item.get("student_count", 0), "amount": True},
                {
                    "value": item["balance_total"] if item["balance_total"] is not None else "Non calculable par école",
                    "amount": item["balance_total"] is not None,
                },
                {
                    "value": item.get("performance_label") or "À suivre",
                    "tone": overview_tones.get(item.get("performance_tone"), "neutral"),
                },
            ],
            "actions": [
                {
                    "label": "Ouvrir",
                    "icon": "panel-right-open",
                    "get_url": item["drawer_url"],
                    "target": "#executive-drawer-content",
                    "swap": "innerHTML",
                    "open_overlay": "executive-drawer",
                },
            ],
        }
        for item in branch_summaries
    ]

    context = base_context_builder(
        request,
        page_title="Dashboard Directeur General",
        module_cards=[
            "Pilotage multi-campus",
            "Monitoring live",
            "Alertes et risques",
            "RH strategique",
        ],
    )
    context.update(
        {
            "dashboard_kind": "Direction generale",
            "executive_display_name": "Directrice Generale Adjointe" if is_deputy else "Directeur General",
            "executive_display_short": "DGA" if is_deputy else "DG",
            "executive_display_subtitle": "Direction generale adjointe" if is_deputy else "PDG / Fondateur",
            "generated_at": timezone.now(),
            "dashboard_period": period,
            "dashboard_period_label": period_label,
            "dashboard_period_scope_label": f"Veille admissions : {period_label}",
            "dashboard_period_days": period_days,
            "dashboard_period_start": period_start,
            "all_branches": all_branches,
            "selected_branch": selected_branch,
            "selected_branch_id": selected_branch_id,
            "academic_years": dg_context.academic_years,
            "selected_academic_year": academic_year,
            "selected_academic_year_id": str(academic_year.id) if academic_year else "",
            "dashboard_mode": dg_context.mode,
            "dashboard_scope_label": dg_context.scope_label,
            "total_branches": len(branches),
            "total_students": base["students"].count(),
            "total_classes": base["classes"].count(),
            "total_active_inscriptions": base["inscriptions"].count(),
            "new_candidatures_30d": get_recent_candidatures_count(
                branch_ids,
                days=period_days,
                academic_year=academic_year,
            ),
            "open_alerts": len(alerts),
            "critical_alerts": sum(1 for alert in alerts if alert.tone == "red"),
            "total_staff": base["staff"].count(),
            "branch_summaries": branch_summaries,
            "priority_alerts": alerts,
            "workflow": workflow,
            "finance": finance,
            "analytics": analytics,
            "schedule": schedule,
            "rh": rh,
            "executive_summary": executive_summary,
            "overview_branch_headers": [
                "Campus",
                "Responsable",
                "Étudiants",
                "Solde",
                "Vigilance",
            ],
            "overview_branch_rows": overview_branch_rows,
            "overview_branch_count": len(overview_branch_rows),
            "realtime": {
                "today_inscriptions": base["candidatures"].filter(
                    submitted_at__gte=today_start,
                    submitted_at__lt=today_end,
                ).count(),
                "today_payments": base["payments"].filter(
                    paid_at__gte=today_start,
                    paid_at__lt=today_end,
                ).count(),
                "today_courses": schedule["today_events_count"],
                "last_updated_at": timezone.now(),
            },
            "empty_list": [],
        }
    )
    return context


def _build_dg_targeted_section_context(request, base_context_builder):
    """Return the shell and querysets needed by one DG workspace only."""
    context = build_dg_shell_context(request, base_context_builder)
    branches = resolve_dg_context(request).scoped_branches
    base = get_dg_base_querysets(
        [branch.id for branch in branches],
        academic_year=context.get("selected_academic_year"),
    )
    return context, branches, base


def build_dg_finance_section_context(request, base_context_builder):
    """Build the Finance workspace without rebuilding unrelated DG domains."""

    context, _branches, base = _build_dg_targeted_section_context(request, base_context_builder)
    finance = _build_finance(base, [])
    context.update(
        {
            "dg_section": "finance",
            "finance": finance,
            "finance_payment_headers": ["Référence / étudiant", "Campus", "Montant", "Date"],
            "finance_payment_rows": [
                {
                    "id": f"dg-finance-payment-{payment.id}",
                    "label": payment.reference or payment.receipt_number or str(payment.id),
                    "cells": [
                        {
                            "value": payment.reference or payment.receipt_number or f"Paiement #{payment.id}",
                            "secondary": payment.inscription.candidature.full_name,
                            "strong": True,
                        },
                        {"value": payment.inscription.candidature.branch.name},
                        {"value": f"{payment.amount} FCFA", "amount": True},
                        {"value": payment.paid_at.strftime("%d/%m/%Y")},
                    ],
                    "actions": [_dg_drawer_action("payment", payment.id)],
                }
                for payment in finance["latest_payments"]
            ],
        }
    )
    return context


def build_dg_section_context(request, section, base_context_builder):
    if section == "finance":
        return build_dg_finance_section_context(request, base_context_builder)
    if section in {"alerts", "analytics", "realtime", "schedule"}:
        context, branches, base = _build_dg_targeted_section_context(request, base_context_builder)
        academic_year = context.get("selected_academic_year")
        if section == "schedule":
            context["schedule"] = _build_schedule(
                request,
                branches,
                base,
                academic_year=academic_year,
            )
        elif section == "alerts":
            student_cases = base["student_cases"].exclude(
                status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE}
            )
            attendance_count = context["open_alerts"]
            case_count = student_cases.count()
            context.update(
                {
                    "priority_alerts": _build_alerts(branches, base),
                    "critical_alerts": base["attendance_alerts"].filter(count__gte=5).count()
                    + student_cases.filter(priority=StudentCase.PRIORITY_CRITIQUE).count(),
                    "analytics": {
                        "risk_breakdown": [
                            {"label": "Finance", "value": base["pending_payments"].count()},
                            {"label": "Suivi étudiant", "value": case_count},
                            {"label": "Assiduité", "value": attendance_count},
                        ]
                    },
                }
            )
        elif section == "analytics":
            branch_summaries = _build_branch_summaries(
                branches,
                base,
                academic_year=academic_year,
            )
            context.update(
                {
                    "branch_summaries": branch_summaries,
                    "analytics": _build_analytics(
                        base,
                        branch_summaries,
                        academic_year=academic_year,
                    ),
                }
            )
        elif section == "realtime":
            schedule = _build_schedule(
                request,
                branches,
                base,
                academic_year=academic_year,
            )
            today_start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
            today_end = today_start + timedelta(days=1)
            context.update(
                {
                    "schedule": schedule,
                    "branch_summaries": [{"branch": branch} for branch in branches],
                    "realtime": {
                        "today_inscriptions": base["candidatures"].filter(
                            submitted_at__gte=today_start,
                            submitted_at__lt=today_end,
                        ).count(),
                        "today_payments": base["payments"].filter(
                            paid_at__gte=today_start,
                            paid_at__lt=today_end,
                        ).count(),
                        "today_courses": schedule["today_events_count"],
                        "last_updated_at": timezone.now(),
                    },
                }
            )
    else:
        context = build_dg_dashboard_context(request, base_context_builder)
    context["dg_section"] = section
    if section == "finance_reports":
        context["finance_report_headers"] = ["Campus", "Revenus", "Dépenses", "Solde", "Inscriptions", "Alertes"]
        report_context = resolve_dg_context(request)
        report_base = get_dg_base_querysets(
            report_context.scoped_branch_ids,
            academic_year=report_context.academic_year,
        )
        context["report_activity"] = _build_recent_activity(
            report_base,
            dg_context=report_context,
        )
        context["finance_report_rows"] = [
            {
                "id": f"dg-finance-report-{item['branch'].id}",
                "label": item["branch"].name,
                "cells": [
                    {"value": item["branch"].name, "secondary": item.get("manager_name") or "Responsable non assigné", "strong": True},
                    {"value": f"{item['revenue_total']} FCFA", "amount": True},
                    {"value": f"{item['expense_total']} FCFA", "amount": True},
                    {"value": f"{item['balance_total']} FCFA", "amount": True},
                    {"value": item["active_inscription_count"], "amount": True},
                    {"value": item["open_alert_count"], "tone": "warning" if item["open_alert_count"] else "success"},
                ],
            }
            for item in context["branch_summaries"]
        ]
    if section == "alerts":
        context["alert_table_headers"] = ["Alerte", "Campus", "Niveau", "Statut", "Ancienneté"]
        context["alert_table_rows"] = [
            {
                "id": f"dg-alert-{alert.key}",
                "label": alert.description,
                "cells": [
                    {"value": alert.description, "secondary": alert.type, "strong": True},
                    {"value": alert.branch_name},
                    {
                        "value": alert.severity,
                        "tone": "danger" if alert.tone == "red" else "warning" if alert.tone == "orange" else "info",
                    },
                    {"value": alert.status},
                    {"value": alert.age},
                ],
                "actions": [
                    {
                        "label": "Ouvrir",
                        "icon": "panel-right-open",
                        "get_url": alert.drawer_url,
                        "target": "#executive-drawer-content",
                        "swap": "innerHTML",
                        "open_overlay": "executive-drawer",
                    }
                ],
            }
            for alert in context["priority_alerts"]
        ]
    if section == "analytics":
        analytics = context["analytics"]
        context.update(
            {
                "analytics_monthly_headers": ["Mois", "Candidatures", "Paiements", "Revenus"],
                "analytics_monthly_rows": [
                    {
                        "id": f"dg-analytics-month-{index}",
                        "label": row["label"],
                        "cells": [
                            {"value": row["label"], "strong": True},
                            {"value": row["candidatures"], "amount": True},
                            {"value": row["payments"], "amount": True},
                            {"value": f"{row['revenue']} FCFA", "amount": True},
                        ],
                    }
                    for index, row in enumerate(analytics["monthly_table"])
                ],
                "analytics_branch_headers": ["Campus", "Étudiants", "Alertes", "Score de vigilance"],
                "analytics_branch_rows": [
                    {
                        "id": f"dg-analytics-branch-{item['branch'].id}",
                        "label": item["branch"].name,
                        "cells": [
                            {"value": item["branch"].name, "secondary": item.get("manager_name") or "Responsable non assigné", "strong": True},
                            {"value": item["student_count"], "amount": True},
                            {"value": item["open_alert_count"], "amount": True},
                            {"value": item["analytics_risk_score"], "tone": "warning" if item["analytics_risk_score"] else "success"},
                        ],
                    }
                    for item in analytics["branch_health_rows"]
                ],
                "analytics_monthly_datasets": [
                    {"label": "Candidatures", "data": [row["candidatures"] for row in analytics["monthly_table"]], "backgroundColor": "#2563eb"},
                    {"label": "Paiements validés", "data": [row["payments"] for row in analytics["monthly_table"]], "backgroundColor": "#16a34a"},
                ],
                "analytics_monthly_labels": [row["label"] for row in analytics["monthly_table"]],
                "analytics_admission_labels": [row["label"] for row in analytics["candidature_status_rows"]],
                "analytics_admission_datasets": [
                    {
                        "label": "Candidatures",
                        "data": [row["count"] for row in analytics["candidature_status_rows"]],
                        "backgroundColor": ["#16a34a", "#f59e0b", "#ef4444"],
                    }
                ],
            }
        )
    if section == "realtime":
        context["realtime_activity_headers"] = ["Évènement", "Origine", "Date"]
        context["realtime_activity_rows"] = [
            {
                "id": f"dg-realtime-{index}",
                "label": event["title"],
                "cells": [
                    {"value": event["title"], "secondary": event["description"], "strong": True},
                    {"value": "Paiements" if event["section"] == "finance" else "Journal institutionnel"},
                    {"value": event["date"]},
                ],
            }
            for index, event in enumerate(
                _build_recent_activity(
                    get_dg_base_querysets(
                        [item["branch"].id for item in context["branch_summaries"]],
                        academic_year=context["selected_academic_year"],
                    ),
                    dg_context=resolve_dg_context(request),
                )
            )
        ]
    if section == "exports":
        export_url = reverse("accounts_portal:dg_export")
        exports = (
            ("Campus", "Indicateurs consolidés par campus", "branches"),
            ("Finance", "Revenus, dépenses et solde par campus", "finance"),
            ("Alertes", "Alertes prioritaires du périmètre", "alerts"),
            ("Étudiants", "Étudiants et inscriptions du contexte", "students"),
            ("Encaissements", "Paiements validés du contexte", "payments"),
            ("Personnel", "Personnel et affectations", "staff"),
            ("Audit", "Journal des opérations institutionnelles", "audit"),
        )
        context["export_headers"] = ["Jeu de données", "Contenu"]
        context["export_rows"] = [
            {
                "id": f"dg-export-{kind}",
                "label": label,
                "cells": [
                    {"value": label, "strong": True},
                    {"value": description},
                ],
                "actions": [
                    {"label": "CSV", "icon": "file-text", "href": f"{export_url}?kind={kind}&format=csv"},
                    {"label": "Excel", "icon": "file-spreadsheet", "href": f"{export_url}?kind={kind}&format=xlsx"},
                ],
            }
            for label, description, kind in exports
        ]
    if section == "exports":
        from urllib.parse import urlencode
        navigation = resolve_dg_context(request)
        scope = urlencode({"scope_school_id": navigation.selected_school_id,
            "scope_branch_id": navigation.selected_branch_id,
            "academic_year_id": navigation.academic_year.pk if navigation.academic_year else ""})
        for row in context["export_rows"]:
            for action in row["actions"]:
                action["href"] += "&" + scope
        context["export_rows"].insert(0, {
            "id": "dg-export-school-summary", "label": "Synthèse par école",
            "cells": [{"value": "Synthèse par école", "strong": True},
                {"value": "Effectifs, candidatures, inscriptions, encaissements et impayés"}],
            "actions": [{"label": label, "icon": "download", "href":
                f'{export_url}?kind=school_summary&format={output_format}&{scope}'}
                for label, output_format in (("Excel", "xlsx"), ("PDF", "pdf"))],
        })
        context["export_rows"].append({"id": "dg-export-school-bulletins", "label": "Bulletins publiés",
            "cells": [{"value": "Bulletins publiés", "strong": True},
                {"value": "PDF officiels de l’école, du campus et de l’année sélectionnés"}],
            "actions": [{"label": "PDF (ZIP)", "icon": "download", "href":
                f'{export_url}?kind=school_bulletins&format=zip&{scope}'}]})
    return context


def build_dg_reenrollment_context(request, base_context_builder):
    """Read-only, scope-safe pilotage for the shared re-enrollment engine."""
    from portal.services.reenrollment_service import get_reenrollment_dashboard_context

    dg_context = resolve_dg_context(request, accept_legacy_branch_param=False)
    raw_branch_id = (request.GET.get("filter_branch_id") or "").strip()
    selected_branch_id = (
        int(raw_branch_id)
        if raw_branch_id.isdigit() and int(raw_branch_id) in dg_context.scoped_branch_ids
        else None
    )
    scoped_branch_ids = [selected_branch_id] if selected_branch_id else list(dg_context.scoped_branch_ids)
    class_scope = scoped(AcademicClass).select_related("academic_year", "programme", "branch").filter(
        branch_id__in=scoped_branch_ids,
        is_archived=False,
    )
    source_year_id = (request.GET.get("source_year") or "").strip()
    target_year_id = (request.GET.get("target_year") or "").strip()
    source_class_id = (request.GET.get("source_class") or "").strip()
    target_class_id = (request.GET.get("target_class") or "").strip()
    programme_id = (request.GET.get("programme") or "").strip()
    source_class = class_scope.filter(pk=source_class_id).first() if source_class_id.isdigit() else None
    target_class = class_scope.filter(pk=target_class_id, is_active=True).first() if target_class_id.isdigit() else None
    source_year = AcademicYear.objects.filter(pk=source_year_id).first() if source_year_id.isdigit() else None
    target_year = AcademicYear.objects.filter(pk=target_year_id).first() if target_year_id.isdigit() else None
    if source_class is not None:
        source_year = source_class.academic_year
    if target_class is not None:
        target_year = target_class.academic_year
    programme_class = class_scope.filter(programme_id=programme_id).select_related("programme").first() if programme_id.isdigit() else None
    programme = programme_class.programme if programme_class is not None else None

    context = base_context_builder(
        request,
        page_title="Pilotage des réinscriptions",
        module_cards=[],
    )
    context.update(
        get_reenrollment_dashboard_context(
            branch=None,
            branch_ids=scoped_branch_ids,
            source_year=source_year,
            source_class=source_class,
            target_year=target_year,
            target_class=target_class,
            programme=programme,
            decision_value=(request.GET.get("decision") or "").strip(),
            workflow_status=(request.GET.get("workflow_status") or "").strip(),
            finance_state=(request.GET.get("finance_state") or "").strip(),
            search=(request.GET.get("q") or "").strip()[:120],
            actor=request.user,
            surface="executive",
            workspace_target="#executive-workspace",
        )
    )
    context.update(
        {
            "dg_section": "reenrollments",
            "all_branches": dg_context.all_branches,
            "selected_branch": dg_context.selected_branch,
            "selected_branch_id": dg_context.selected_branch_id,
            "academic_years": dg_context.academic_years,
            "selected_academic_year": dg_context.academic_year,
            "dashboard_mode": dg_context.mode,
            "dashboard_scope_label": dg_context.scope_label,
            "reenrollment_branch_options": [
                {
                    "id": branch.id,
                    "name": branch.name,
                    "selected": branch.id == selected_branch_id,
                }
                for branch in dg_context.scoped_branches
            ],
            "reenrollment_filter_branch_id": selected_branch_id or "",
        }
    )
    context.update(
        {
            "reenrollment_filter_action": reverse("accounts_portal:dg_section", kwargs={"section": "reenrollments"}),
            "reenrollment_filter_reset_url": f"{reverse('accounts_portal:dg_section', kwargs={'section': 'reenrollments'})}?domain=etudiants",
            "reenrollment_filter_hidden_fields": [{"name": "domain", "value": "etudiants"}],
            "reenrollment_filters": [
                {"name": "q", "label": "Recherche", "type": "search", "value": (request.GET.get("q") or "").strip(), "placeholder": "Nom ou matricule", "clearable": True},
                {"name": "filter_branch_id", "label": "Campus", "options": [{"value": "", "label": "Tous les campus", "selected": not selected_branch_id}] + [{"value": str(item["id"]), "label": item["name"], "selected": item["selected"]} for item in context["reenrollment_branch_options"]]},
                {"name": "source_year", "label": "Année source", "options": [{"value": "", "label": "Toutes", "selected": source_year is None}] + [{"value": str(year.id), "label": year.name, "selected": source_year is not None and year.id == source_year.id} for year in dg_context.academic_years]},
                {"name": "target_year", "label": "Année cible", "options": [{"value": "", "label": "Toutes", "selected": target_year is None}] + [{"value": str(year.id), "label": year.name, "selected": target_year is not None and year.id == target_year.id} for year in dg_context.academic_years]},
                {"name": "source_class", "label": "Classe source", "options": [{"value": "", "label": "Toutes", "selected": source_class is None}] + [{"value": str(item.id), "label": f"{item.display_name} · {item.branch.name}", "selected": source_class is not None and item.id == source_class.id} for item in context.get("classes", [])]},
                {"name": "programme", "label": "Formation", "options": [{"value": "", "label": "Toutes", "selected": programme is None}] + [{"value": str(item_id), "label": title, "selected": programme is not None and item_id == programme.id} for item_id, title in context.get("programme_choices", [])]},
                {"name": "target_class", "label": "Classe cible", "options": [{"value": "", "label": "Toutes", "selected": target_class is None}] + [{"value": str(item.id), "label": f"{item.display_name} · {item.branch.name}", "selected": target_class is not None and item.id == target_class.id} for item in context.get("target_classes", [])]},
                {"name": "finance_state", "label": "État financier", "options": [{"value": "", "label": "Tous", "selected": not context.get("finance_state")}, {"value": "not_started", "label": "Non démarré", "selected": context.get("finance_state") == "not_started"}, {"value": "ready", "label": "Prêt", "selected": context.get("finance_state") == "ready"}, {"value": "awaiting_payment", "label": "Paiement attendu", "selected": context.get("finance_state") == "awaiting_payment"}, {"value": "partial_payment", "label": "Paiement partiel", "selected": context.get("finance_state") == "partial_payment"}, {"value": "active", "label": "Actif", "selected": context.get("finance_state") == "active"}]},
            ],
            "reenrollment_table_headers": ["Étudiant", "Campus", "Source", "Destination", "Décision", "État"],
            "reenrollment_table_rows": [
                {
                    "id": f"dg-reenrollment-{decision.id}",
                    "label": decision.student.full_name,
                    "cells": [
                        {"value": decision.student.full_name, "secondary": decision.student.matricule, "strong": True},
                        {"value": decision.source_enrollment.branch.name},
                        {"value": f"{decision.source_academic_year.name} · {decision.source_class.display_name}"},
                        {"value": f"{decision.target_academic_year.name} · {decision.target_class.display_name}" if decision.target_class else "À compléter", "tone": "warning" if not decision.target_class else "neutral"},
                        {"value": decision.get_decision_display()},
                        {"value": "Actif" if decision.target_enrollment else "Paiement attendu" if decision.target_inscription else decision.get_workflow_status_display(), "tone": "success" if decision.target_enrollment else "warning" if decision.target_inscription else "neutral"},
                    ],
                }
                for decision in context["decisions"]
            ],
        }
    )
    return context


def build_dg_drawer_context(request, *, kind_override=None):
    # ``branch_id`` in a drawer identifies the object to open; it must never
    # silently replace the persistent dashboard scope.
    dg_context = resolve_dg_context(request, accept_legacy_branch_param=False)
    academic_year = dg_context.academic_year
    kind = (kind_override or request.GET.get("kind") or "overview").strip().lower()
    item_id = (request.GET.get("id") or "").strip()
    # Older DG list rows used the generic ``id`` convention.  A campus drawer
    # is the one exception: its canonical parameter is ``branch_id``.  Keep
    # the old links functional while all newly generated links use the explicit
    # parameter below.
    branch_id = (request.GET.get("branch_id") or "").strip()
    if kind == "branch" and not branch_id:
        branch_id = item_id
    student_id = (request.GET.get("student_id") or item_id).strip()
    payment_id = (request.GET.get("payment_id") or item_id).strip()
    staff_id = (request.GET.get("staff_id") or item_id).strip()
    event_id = (request.GET.get("event_id") or item_id).strip()
    step = (request.GET.get("step") or "").strip()
    branch = None
    if branch_id.isdigit():
        branch = get_active_branches().filter(id=int(branch_id)).first()
        if branch is None or not dg_context.contains_branch_id(branch.id):
            raise DgScopeViolation("Ce campus est hors du contexte DG actif.")

    drawer_branches = [branch] if branch else dg_context.scoped_branches
    drawer_branch_ids = [item.id for item in drawer_branches]
    drawer_base = get_dg_base_querysets(drawer_branch_ids, academic_year=academic_year)
    year_date_filters = {}
    if academic_year is not None:
        academic_year_start, academic_year_end = get_academic_year_datetime_bounds(academic_year)
        year_date_filters = {
            "created_at__gte": academic_year_start,
            "created_at__lt": academic_year_end,
        }

    scoped_alerts = scoped(AttendanceAlert).filter(branch_id__in=drawer_branch_ids)
    if academic_year is not None:
        scoped_alerts = scoped_alerts.filter(
            triggered_at__gte=academic_year_start,
            triggered_at__lt=academic_year_end,
        )
    scoped_cases = scoped(StudentCase).filter(branch_id__in=drawer_branch_ids, **year_date_filters)
    scoped_payments = scoped(Payment).filter(
        inscription__candidature__branch_id__in=drawer_branch_ids,
    )
    if academic_year is not None:
        scoped_payments = scoped_payments.filter(
            inscription__candidature__academic_year=academic_year.name,
        )
    scoped_staff = (
        scoped(Profile).filter(user_type="staff")
        .filter(staff_branch_filter(drawer_branch_ids))
    )
    scoped_events = scoped(AcademicScheduleEvent).filter(
        branch_id__in=drawer_branch_ids,
        is_active=True,
    )
    if academic_year is not None:
        scoped_events = scoped_events.filter(academic_year=academic_year)

    alert = None
    case = None
    student = None
    student_enrollment = None
    student_payments = []
    payment = None
    staff_profile = None
    schedule_event = None
    alert_rows = []
    case_rows = []
    if item_id.isdigit():
        if kind == "alert":
            alert = scoped_alerts.select_related("branch", "student", "student__user").filter(id=int(item_id)).first()
            if alert is None:
                raise DgScopeViolation("Cette alerte est introuvable dans le contexte DG actif.")
        elif kind == "case":
            case = scoped_cases.select_related("branch", "student", "student__user").filter(id=int(item_id)).first()
            if case is None:
                raise DgScopeViolation("Ce dossier etudiant est introuvable dans le contexte DG actif.")
    if kind == "student" and student_id.isdigit():
        student = (
            scoped(Student).select_related(
                "user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
                "inscription__candidature__programme",
                "current_academic_enrollment",
                "current_academic_enrollment__academic_class",
                "current_academic_enrollment__branch",
            )
            .filter(id=int(student_id), id__in=drawer_base["students"].values("id"))
            .first()
        )
        if student is None:
            raise DgScopeViolation("Cet etudiant est introuvable dans le contexte DG actif.")
        student_enrollment_queryset = scoped(AcademicEnrollment).select_related(
            "academic_class", "academic_year", "programme", "branch", "inscription"
        ).filter(student=student.user, branch_id__in=drawer_branch_ids)
        if academic_year is not None:
            student_enrollment_queryset = student_enrollment_queryset.filter(academic_year=academic_year)
        student_enrollment = student_enrollment_queryset.order_by("-created_at").first()
        if student_enrollment is None:
            raise DgScopeViolation("L'inscription academique est introuvable dans le contexte DG actif.")
        student_payments = list(
            scoped_payments.filter(inscription=student_enrollment.inscription)
            .order_by("-paid_at", "-id")[:6]
        )
    if kind == "payment" and payment_id.isdigit():
        payment = (
            scoped(Payment).select_related(
                "agent",
                "agent__user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
                "inscription__candidature__programme",
                "inscription__candidature__programme__school",
                "inscription__academic_class",
                "cash_session",
            )
            .filter(id=int(payment_id), id__in=scoped_payments.values("id"))
            .first()
        )
        if payment is None:
            raise DgScopeViolation("Ce paiement est introuvable dans le contexte DG actif.")
    if kind == "staff" and staff_id.isdigit():
        staff_profile = scoped_staff.select_related("user", "branch").filter(id=int(staff_id)).first()
        if staff_profile is None:
            raise DgScopeViolation("Ce membre du personnel est introuvable dans le contexte DG actif.")
    if kind == "schedule" and event_id.isdigit():
        schedule_event = (
            scoped_events.select_related("academic_class", "branch", "teacher", "ec", "academic_year")
            .filter(id=int(event_id))
            .first()
        )
        if schedule_event is None:
            raise DgScopeViolation("Cet evenement est introuvable dans le contexte DG actif.")
    if kind == "alert" and alert is None:
        alert_qs = scoped_alerts.filter(is_resolved=False)
        alert_rows = list(
            alert_qs
            .select_related("branch", "student", "student__user")
            .order_by("-triggered_at")[:12]
        )
    if kind == "case" and case is None:
        case_qs = scoped_cases.exclude(status__in={StudentCase.STATUS_RESOLU, StudentCase.STATUS_ESCALADE})
        case_rows = list(
            case_qs
            .select_related("branch", "student", "student__user")
            .order_by("-created_at")[:12]
        )
    workflow_rows = []
    if kind == "workflow":
        workflow_rows = list(
            drawer_base["year_decisions"].exclude(
                workflow_status__in={StudentYearDecision.WORKFLOW_APPLIED, StudentYearDecision.WORKFLOW_REJECTED}
            )
            .select_related("student", "student__user", "source_enrollment__branch", "source_class")
            .order_by("created_at")[:12]
        )
    drawer_branch_summaries = (
        _build_branch_summaries(
            drawer_branches,
            drawer_base,
            academic_year=academic_year,
            include_details=branch is not None,
        )
        if drawer_branch_ids
        else []
    )
    drawer_finance = _build_finance(drawer_base, drawer_branch_summaries) if drawer_branch_ids else {}
    drawer_analytics = _build_analytics(
        drawer_base,
        drawer_branch_summaries,
        academic_year=academic_year,
    ) if drawer_branch_ids else {}
    drawer_rh = _build_rh(drawer_base, drawer_branches) if drawer_branch_ids else {}
    drawer_schedule = _build_schedule(
        request,
        drawer_branches,
        drawer_base,
        academic_year=academic_year,
    ) if drawer_branch_ids else {}
    student_rows = []
    payment_rows = []
    staff_rows = []
    audit_rows = []
    staff_audit_rows = []
    staff_security_events = []
    if kind in {"students", "student", "branch"} and drawer_branch_ids:
        student_rows = list(
            drawer_base["students"]
            .select_related(
                "user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
                "inscription__candidature__programme",
                "current_academic_enrollment",
                "current_academic_enrollment__academic_class",
            )
            .order_by("inscription__candidature__last_name", "inscription__candidature__first_name")[:20]
        )
    if kind in {"payments", "payment", "finance", "branch"} and drawer_branch_ids:
        payment_rows = list(
            scoped_payments
            .select_related(
                "agent",
                "agent__user",
                "inscription",
                "inscription__candidature",
                "inscription__candidature__branch",
            )
            .order_by("-paid_at", "-id")[:20]
        )
    if kind in {"staff", "rh", "branch"} and drawer_branch_ids:
        staff_rows = list(
            scoped_staff
            .select_related("user", "branch")
            .order_by("branch__name", "position", "user__last_name")[:20]
        )
    if kind in {"audit", "branch"}:
        audit_qs = scoped(SupportAuditLog).select_related("actor", "branch").order_by("-created_at")
        if drawer_branch_ids:
            audit_qs = audit_qs.filter(Q(branch_id__in=drawer_branch_ids) | Q(branch__isnull=True))
        if academic_year is not None:
            academic_year_start, academic_year_end = get_academic_year_datetime_bounds(academic_year)
            audit_qs = audit_qs.filter(
                created_at__gte=academic_year_start,
                created_at__lt=academic_year_end,
            )
        audit_rows = list(audit_qs[:20])
    if staff_profile is not None:
        staff_audit_rows = list(
            scoped(SupportAuditLog).filter(target_user=staff_profile.user)
            .select_related("actor", "branch")
            .filter(Q(branch_id__in=drawer_branch_ids) | Q(branch__isnull=True))
            .order_by("-created_at", "-id")[:12]
        )
        staff_security_events = list(
            AccountSecurityEvent.objects.filter(user=staff_profile.user)
            .select_related("actor")
            .order_by("-created_at", "-id")[:8]
        )
    branch_finance = None
    branch_summary = None
    branch_schools = []
    branch_today_courses = []
    branch_staff_count = 0
    if branch:
        branch_summary = drawer_branch_summaries[0] if drawer_branch_summaries else None
        revenue, expenses, balance = get_branch_finance(branch, academic_year=academic_year)
        branch_finance = {"revenue": revenue, "expenses": expenses, "balance": balance}
        branch_schools = list(
            scoped(SchoolBranch).filter(branch=branch, is_active=True, school__is_active=True)
            .select_related("school").order_by("school__order", "school__code")
        )
        today_start = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
        today_end = today_start + timedelta(days=1)
        branch_today_courses = list(
            scoped_events.filter(
                event_type__in={AcademicScheduleEvent.EVENT_TYPE_COURSE, AcademicScheduleEvent.EVENT_TYPE_PRACTICAL},
                start_datetime__gte=today_start,
                start_datetime__lt=today_end,
            ).select_related("academic_class", "ec", "teacher").order_by("start_datetime")[:6]
        )
        branch_staff_count = scoped_staff.count()
    from portal.dg.rh_service import can_dg_manage_staff, can_physically_delete_staff

    staff_manageable = bool(staff_profile and can_dg_manage_staff(actor=request.user, profile=staff_profile))
    staff_can_delete = bool(staff_manageable and can_physically_delete_staff(actor=request.user, profile=staff_profile))
    staff_can_invite = bool(
        staff_manageable and staff_profile.user.is_active
        and staff_profile.employment_status == "active"
        and staff_profile.user.email and not staff_profile.user.has_usable_password()
    )
    return {
        "drawer_kind": kind,
        "drawer_branch": branch,
        "drawer_alert": alert,
        "drawer_case": case,
        "drawer_student": student,
        "drawer_student_enrollment": student_enrollment,
        "drawer_student_payments": student_payments,
        "drawer_payment": payment,
        "drawer_staff_profile": staff_profile,
        "drawer_staff_manageable": staff_manageable,
        "drawer_staff_can_delete": staff_can_delete,
        "drawer_staff_can_invite": staff_can_invite,
        "drawer_schedule_event": schedule_event,
        "drawer_alert_rows": alert_rows,
        "drawer_case_rows": case_rows,
        "drawer_student_rows": student_rows,
        "drawer_payment_rows": payment_rows,
        "drawer_staff_rows": staff_rows,
        "drawer_staff_audit_rows": staff_audit_rows,
        "drawer_staff_security_events": staff_security_events,
        "drawer_audit_rows": audit_rows,
        "drawer_item_id": item_id,
        "drawer_step": step,
        "drawer_workflow_rows": workflow_rows,
        "drawer_branch_finance": branch_finance,
        "drawer_branch_summary": branch_summary,
        "drawer_branch_schools": branch_schools,
        "drawer_branch_today_courses": branch_today_courses,
        "drawer_branch_staff_count": branch_staff_count,
        "drawer_branch_summaries": drawer_branch_summaries,
        "drawer_finance": drawer_finance,
        "drawer_analytics": drawer_analytics,
        "drawer_rh": drawer_rh,
        "drawer_schedule": drawer_schedule,
        "generated_at": timezone.now(),
    }


# Back-office list workspaces -------------------------------------------------
#
# These builders intentionally stay independent from ``build_dg_dashboard_context``.
# A list of payments must not calculate charts, schedule health and every other DG
# aggregate before it can answer a paginated search request.
DG_BACKOFFICE_LIST_SECTIONS = frozenset(
    {
        "branch_list",
        "branch_comparison",
        "branch_managers",
        "branch_activity",
        "payments",
        "expenses",
        "receivables",
        "cash_movements",
        "closures",
        "bank_transfers",
        "finance_reports",
        "academic_overview",
        "classes",
        "evaluations",
        "results",
        "progression",
        "workflows",
        "diplomas",
        "students_overview",
        "students",
        "enrollments",
        "reenrollments",
        "student_cases",
        "staff_overview",
        "recruitment",
        "assignments",
        "staff_contracts",
        "staff_access",
        "staff_history",
        "documents",
        "audit",
        "exports",
    }
)


def is_dg_backoffice_list_section(section: str) -> bool:
    return section in DG_BACKOFFICE_LIST_SECTIONS


def _dg_list_base_context(request, base_context_builder, *, title: str):
    """Return the lightweight context shared by every server-side DG list."""

    dg_context = resolve_dg_context(request, accept_legacy_branch_param=False)
    context = base_context_builder(request, page_title=title, module_cards=[])
    context.update(
        {
            "all_branches": dg_context.all_branches,
            "selected_branch": dg_context.selected_branch,
            "selected_branch_id": dg_context.selected_branch_id,
            "academic_years": dg_context.academic_years,
            "selected_academic_year": dg_context.academic_year,
            "selected_academic_year_id": str(dg_context.academic_year.id) if dg_context.academic_year else "",
            "dashboard_mode": dg_context.mode,
            "dashboard_scope_label": dg_context.scope_label,
        }
    )
    return context, dg_context


def _dg_list_scope_params(request, dg_context, *, section: str):
    """Keep all list, filter and pagination links reproducible from the URL."""

    params = request.GET.copy()
    for key in ("page", "_subsection", "_workspace_request"):
        params.pop(key, None)
    params["domain"] = domain_for_section(section).key
    if dg_context.academic_year is not None:
        params["academic_year_id"] = str(dg_context.academic_year.id)
    else:
        params.pop("academic_year_id", None)
    params["scope_branch_id"] = dg_context.selected_branch_id
    params["scope_school_id"] = dg_context.selected_school_id
    return params


def _dg_list_pagination(request, queryset, dg_context, *, section: str, page_size=20):
    page = Paginator(queryset, page_size).get_page(request.GET.get("page"))
    base_params = _dg_list_scope_params(request, dg_context, section=section)
    endpoint = reverse("accounts_portal:dg_section", kwargs={"section": section})

    def page_url(number):
        params = base_params.copy()
        params["page"] = number
        return f"{endpoint}?{params.urlencode()}"

    return page, endpoint, base_params, page_url


def _dg_filter_branch_id(request, dg_context, *, key="filter_branch_id"):
    raw_id = (request.GET.get(key) or "").strip()
    if raw_id.isdigit() and int(raw_id) in dg_context.scoped_branch_ids:
        return int(raw_id)
    return None


def _dg_parse_filter_date(raw_value):
    try:
        return datetime.strptime(str(raw_value or ""), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _dg_financial_audit_entries(dg_context, *, branch_id=None):
    """Return finance audit entries whose academic scope can be proven.

    A financial audit row is generic by design.  Payment rows are therefore
    resolved through their canonical Payment record before a School filter is
    applied; campus-only ledgers remain visible only in campus/global views.
    """
    queryset = FinancialAuditLog.objects.select_related("branch", "performed_by").filter(
        branch_id__in=dg_context.scoped_branch_ids,
    )
    payment_ids = None
    if dg_context.academic_year:
        # The dossier's academic year is authoritative.  A payment may be
        # validated before the calendar start date, so filtering audit-row
        # creation timestamps would incorrectly hide it.
        payment_ids = scoped(Payment).filter(
            inscription__candidature__academic_year=dg_context.academic_year.name,
            inscription__candidature__branch_id__in=dg_context.scoped_branch_ids,
        ).values("pk")
        queryset = queryset.filter(
            target_model="payments.payment", target_id__in=payment_ids,
        )
    if branch_id:
        queryset = queryset.filter(branch_id=branch_id)
    if dg_context.selected_school and payment_ids is None:
        payment_ids = scoped(Payment).filter(
            inscription__candidature__branch_id__in=dg_context.scoped_branch_ids,
        ).values("pk")
        queryset = queryset.filter(target_model="payments.payment", target_id__in=payment_ids)
    return queryset.order_by("-created_at", "-id")


def _dg_security_audit_entries(dg_context, *, branch_id=None):
    """Return authentication and session events in the selected institutional scope."""
    queryset = AccountSecurityEvent.objects.select_related(
        "user", "actor", "user__profile", "user__institutional_profile",
        "actor__profile", "actor__institutional_profile",
    )
    # Security events are operational, not academic records.  They must stay
    # visible during pre-year preparation instead of disappearing before the
    # selected academic calendar officially opens.
    if branch_id:
        queryset = queryset.filter(
            Q(user__profile__branch_id=branch_id) | Q(actor__profile__branch_id=branch_id)
        )
    elif dg_context.selected_school:
        queryset = queryset.filter(
            Q(user__institutional_profile__school=dg_context.selected_school)
            | Q(actor__institutional_profile__school=dg_context.selected_school)
        )
    return queryset.order_by("-created_at", "-id")


def _dg_branch_filter_options(dg_context, selected_id, *, all_label="Tous les campus"):
    return [{"value": "", "label": all_label, "selected": selected_id is None}] + [
        {
            "value": str(branch.id),
            "label": branch.name,
            "selected": branch.id == selected_id,
        }
        for branch in dg_context.scoped_branches
    ]


def _dg_list_result(
    request,
    dg_context,
    *,
    section,
    title,
    eyebrow,
    subtitle,
    headers,
    rows,
    queryset,
    filters,
    active_filters,
    empty_title,
    empty_message,
):
    page, endpoint, base_params, page_url = _dg_list_pagination(
        request, queryset, dg_context, section=section
    )
    filter_names = {item["name"] for item in filters}
    reset_params = base_params.copy()
    for filter_name in filter_names:
        reset_params.pop(filter_name, None)
    return {
        "backoffice_title": title,
        "backoffice_eyebrow": eyebrow,
        "backoffice_subtitle": subtitle,
        "backoffice_headers": headers,
        "backoffice_rows": [rows(item) for item in page.object_list],
        "backoffice_result_count": page.paginator.count,
        "backoffice_page": page.number,
        "backoffice_page_count": page.paginator.num_pages,
        "backoffice_previous_url": page_url(page.previous_page_number()) if page.has_previous() else "",
        "backoffice_next_url": page_url(page.next_page_number()) if page.has_next() else "",
        "backoffice_filter_action": endpoint,
        "backoffice_filter_reset_url": f"{endpoint}?{reset_params.urlencode()}",
        "backoffice_filter_hidden_fields": [
            {
                "name": key,
                "value": value,
            }
            for key, value in base_params.items()
            if key not in filter_names
        ],
        "backoffice_filters": filters,
        "backoffice_active_filters": active_filters,
        "backoffice_empty_title": empty_title,
        "backoffice_empty_message": empty_message,
        "backoffice_class_admin": section == "classes",
    }


def _dg_drawer_action(kind, object_id):
    parameter = "branch_id" if kind == "branch" else "id"
    return {
        "label": "Fiche",
        "icon": "panel-right-open",
        "get_url": f"{reverse('accounts_portal:dg_drawer')}?kind={kind}&{parameter}={object_id}",
        "target": "#executive-drawer-content",
        "swap": "innerHTML",
        "open_overlay": "executive-drawer",
    }


def _dg_programme_filter_options(dg_context, selected_id):
    programme_ids = (
        scoped(AcademicClass).filter(
            branch_id__in=dg_context.scoped_branch_ids,
            academic_year=dg_context.academic_year,
        )
        .values_list("programme_id", flat=True)
        .distinct()
    ) if dg_context.academic_year else scoped(AcademicClass).filter(
        branch_id__in=dg_context.scoped_branch_ids,
    ).values_list("programme_id", flat=True).distinct()
    return [{"value": "", "label": "Tous les programmes", "selected": not selected_id}] + [
        {
            "value": str(programme.id),
            "label": programme.title,
            "selected": programme.id == selected_id,
        }
        for programme in scoped(Programme).filter(id__in=programme_ids).order_by("title")
    ]


def _build_dg_branch_list(request, dg_context, *, section="branch_list"):
    query = (request.GET.get("q") or "").strip()[:120]
    is_comparison = section == "branch_comparison"
    # The annex directory is an institutional catalogue, not an operational
    # dataset.  It must therefore remain exhaustive even while the DG has an
    # annexe selected for the surrounding academic or financial workspaces.
    # Only the administrative list includes inactive annexes for reactivation.
    branches = scoped(Branch) if section == "branch_list" else get_active_branches()
    if query:
        branches = branches.filter(
            Q(name__icontains=query)
            | Q(code__icontains=query)
            | Q(city__icontains=query)
            | Q(manager__first_name__icontains=query)
            | Q(manager__last_name__icontains=query)
    )
    branches = branches.order_by("name")
    listed_branches = list(branches)
    base = get_dg_base_querysets(
        [branch.id for branch in listed_branches],
        academic_year=dg_context.academic_year,
    )
    summary_by_branch_id = {
        item["branch"].id: item
        for item in _build_branch_summaries(
            listed_branches,
            base,
            academic_year=dg_context.academic_year,
        )
    }

    def row(branch):
        summary = summary_by_branch_id.get(branch.id, {})
        if is_comparison:
            return {
                "id": f"dg-branch-{branch.id}",
                "label": branch.name,
                "cells": [
                    {"value": branch.name, "secondary": f"{branch.code} · {branch.city}", "strong": True},
                    {"value": summary.get("student_count", 0), "amount": True},
                    {"value": summary.get("class_count", 0), "amount": True},
                    {
                        "value": summary.get("candidature_count", 0),
                        "secondary": f"{summary.get('accepted_candidature_count', 0)} acceptée(s) · {summary.get('admission_conversion_rate', 0)}%",
                        "amount": True,
                    },
                    {"value": summary.get("active_inscription_count", 0), "amount": True},
                    {"value": f"{summary.get('revenue_total', 0)} FCFA", "amount": True},
                    {
                        "value": f"{summary['expense_total']} FCFA" if summary.get("expense_total") is not None else "Non ventilé par école",
                        "amount": summary.get("expense_total") is not None,
                    },
                    {
                        "value": f"{summary['balance_total']} FCFA" if summary.get("balance_total") is not None else "Non calculable par école",
                        "amount": summary.get("balance_total") is not None,
                        "tone": "success" if summary.get("balance_total") is not None and summary["balance_total"] >= 0 else ("danger" if summary.get("balance_total") is not None else "neutral"),
                    },
                    {
                        "value": summary.get("open_alert_count", 0),
                        "tone": "warning" if summary.get("open_alert_count", 0) else "success",
                    },
                    {
                        "value": summary.get("performance_label", "À suivre"),
                        "tone": summary.get("performance_tone", "neutral"),
                    },
                ],
                "actions": [_dg_drawer_action("branch", branch.id)],
            }
        return {
            "id": f"dg-branch-{branch.id}",
            "label": branch.name,
            "cells": [
                {"value": branch.name, "secondary": f"{branch.code} · {branch.city}", "strong": True},
                {
                    "value": (
                        summary.get("branch_manager_name")
                        if section == "branch_managers"
                        else summary.get("manager_name") or "Non assigné"
                    )
                },
                {"value": summary.get("student_count", 0), "amount": True},
                {"value": summary.get("class_count", 0), "amount": True},
                {"value": "Active" if branch.is_active else "Inactive", "tone": "success" if branch.is_active else "neutral"},
            ],
            "actions": [
                _dg_drawer_action("branch", branch.id),
                {
                    "label": "Modifier",
                    "icon": "pencil",
                    "get_url": f"{reverse('accounts_portal:dg_modal')}?modal=branch_admin&branch_id={branch.id}",
                    "target": "#executive-modal-content",
                    "swap": "innerHTML",
                    "open_overlay": "executive-modal",
                },
            ] if section in {"annexes", "branch_list"} else [_dg_drawer_action("branch", branch.id)],
        }

    result = _dg_list_result(
        request,
        dg_context,
        section=section,
        title={
            "branch_comparison": "Comparaison des campus",
            "branch_managers": "Gestionnaires de campus",
        }.get(section, "Liste des campus"),
        eyebrow="Pilotage institutionnel",
        subtitle=(
            "Comparaison consolidée par campus, fondée sur les inscriptions académiques de l’année sélectionnée."
            if is_comparison
            else "Recherchez un campus, ouvrez sa fiche et conservez son contexte dans les autres domaines."
        ),
        headers=(
            ["Campus", "Étudiants", "Classes", "Candidatures", "Inscriptions", "Revenus", "Dépenses", "Solde", "Alertes", "Vigilance"]
            if is_comparison
            else [
                "Campus",
                "Gestionnaire" if section == "branch_managers" else "Responsable académique",
                "Étudiants",
                "Classes",
                "Statut",
            ]
        ),
        rows=row,
        queryset=branches,
        filters=[
            {"name": "q", "label": "Recherche", "type": "search", "value": query, "placeholder": "Nom, code, ville ou responsable", "clearable": True},
        ],
        active_filters=[f"Recherche : {query}"] if query else [],
        empty_title="Aucun campus trouvé",
        empty_message="Modifiez la recherche ou le contexte institutionnel.",
    )
    result["backoffice_branch_admin"] = section in {"annexes", "branch_list"}
    return result


def _build_dg_students_list(request, dg_context, *, section="students"):
    query = (request.GET.get("q") or "").strip()[:120]
    branch_id = _dg_filter_branch_id(request, dg_context)
    programme_id = int(request.GET["programme_id"]) if (request.GET.get("programme_id") or "").isdigit() else None
    class_id = int(request.GET["academic_class_id"]) if (request.GET.get("academic_class_id") or "").isdigit() else None
    status = (request.GET.get("status") or "").strip()
    enrollment_queryset = scoped(AcademicEnrollment).select_related(
        "academic_class", "academic_year", "programme", "branch"
    ).filter(branch_id__in=dg_context.scoped_branch_ids)
    if dg_context.academic_year:
        enrollment_queryset = enrollment_queryset.filter(academic_year=dg_context.academic_year)

    if branch_id:
        enrollment_queryset = enrollment_queryset.filter(branch_id=branch_id)
    if programme_id:
        enrollment_queryset = enrollment_queryset.filter(programme_id=programme_id)
    if class_id:
        enrollment_queryset = enrollment_queryset.filter(academic_class_id=class_id)
    queryset = scoped(Student).filter(user_id__in=enrollment_queryset.values("student_id")).select_related(
        "user",
        "inscription",
        "inscription__candidature",
        "inscription__candidature__branch",
        "inscription__candidature__programme",
        "current_academic_enrollment",
        "current_academic_enrollment__academic_class",
    ).prefetch_related(
        Prefetch(
            "user__academic_enrollments",
            queryset=enrollment_queryset,
            to_attr="dg_context_enrollments",
        )
    )
    if query:
        queryset = queryset.filter(
            Q(matricule__icontains=query)
            | Q(inscription__candidature__first_name__icontains=query)
            | Q(inscription__candidature__last_name__icontains=query)
            | Q(user__first_name__icontains=query)
            | Q(user__last_name__icontains=query)
        )
    if status == "active":
        queryset = queryset.filter(is_active=True)
    elif status == "inactive":
        queryset = queryset.filter(is_active=False)
    else:
        status = ""
    queryset = queryset.distinct().order_by("inscription__candidature__last_name", "inscription__candidature__first_name")

    available_classes = scoped(AcademicClass).filter(
        branch_id__in=dg_context.scoped_branch_ids,
        is_active=True,
        is_archived=False,
    )
    if dg_context.academic_year:
        available_classes = available_classes.filter(academic_year=dg_context.academic_year)

    def row(student):
        enrollment = next(iter(getattr(student.user, "dg_context_enrollments", [])), None)
        academic_class = enrollment.academic_class if enrollment else student.inscription.academic_class
        programme = enrollment.programme if enrollment else student.inscription.candidature.programme
        branch = enrollment.branch if enrollment else student.inscription.candidature.branch
        return {
            "id": f"dg-student-{student.id}",
            "label": student.full_name,
            "cells": [
                {"value": student.full_name, "secondary": student.matricule, "strong": True},
                {"value": programme.title},
                {"value": academic_class.display_name if academic_class else "Non affecté"},
                {"value": branch.name},
                {"value": "Actif" if student.is_active else "Inactif", "tone": "success" if student.is_active else "neutral"},
            ],
            "actions": [_dg_drawer_action("student", student.id)],
        }

    active_filters = []
    if query:
        active_filters.append(f"Recherche : {query}")
    if branch_id:
        active_filters.append("Campus sélectionné")
    if programme_id:
        active_filters.append("Programme sélectionné")
    if class_id:
        active_filters.append("Classe sélectionnée")
    if status:
        active_filters.append("Statut : actif" if status == "active" else "Statut : inactif")
    return _dg_list_result(
        request,
        dg_context,
        section=section,
        title="Étudiants",
        eyebrow="Parcours étudiant",
        subtitle="Recherche par nom ou matricule, filtres de scoping et accès à la fiche consolidée.",
        headers=["Étudiant", "Programme", "Classe", "Campus", "Statut"],
        rows=row,
        queryset=queryset,
        filters=[
            {"name": "q", "label": "Recherche", "type": "search", "value": query, "placeholder": "Nom ou matricule", "clearable": True},
            {"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)},
            {"name": "programme_id", "label": "Programme", "options": _dg_programme_filter_options(dg_context, programme_id)},
            {"name": "academic_class_id", "label": "Classe", "options": [{"value": "", "label": "Toutes les classes", "selected": not class_id}] + [{"value": str(item.id), "label": item.display_name, "selected": item.id == class_id} for item in available_classes.order_by("name")]},
            {"name": "status", "label": "Statut", "options": [{"value": "", "label": "Tous", "selected": not status}, {"value": "active", "label": "Actif", "selected": status == "active"}, {"value": "inactive", "label": "Inactif", "selected": status == "inactive"}]},
        ],
        active_filters=active_filters,
        empty_title="Aucun étudiant trouvé",
        empty_message="Aucun étudiant ne correspond aux critères sélectionnés.",
    )


def _build_dg_classes_list(request, dg_context, *, section="classes"):
    query = (request.GET.get("q") or "").strip()[:120]
    branch_id = _dg_filter_branch_id(request, dg_context)
    programme_id = int(request.GET["programme_id"]) if (request.GET.get("programme_id") or "").isdigit() else None
    queryset = scoped(AcademicClass).select_related("branch", "academic_year", "programme").annotate(
        student_count=Count("enrollments", filter=Q(enrollments__is_active=True), distinct=True)
    ).filter(branch_id__in=dg_context.scoped_branch_ids, is_active=True, is_archived=False)
    if dg_context.academic_year:
        queryset = queryset.filter(academic_year=dg_context.academic_year)
    if query:
        queryset = queryset.filter(Q(name__icontains=query) | Q(level__icontains=query) | Q(programme__title__icontains=query))
    if branch_id:
        queryset = queryset.filter(branch_id=branch_id)
    if programme_id:
        queryset = queryset.filter(programme_id=programme_id)
    queryset = queryset.order_by("branch__name", "programme__title", "level", "name")

    def row(academic_class):
        return {
            "id": f"dg-class-{academic_class.id}",
            "label": academic_class.display_name,
            "cells": [
                {"value": academic_class.display_name, "secondary": academic_class.level, "strong": True},
                {"value": academic_class.programme.title},
                {"value": academic_class.branch.name},
                {"value": academic_class.academic_year.name},
                {"value": academic_class.student_count, "amount": True},
            ],
            "actions": [_dg_drawer_action("academic_class", academic_class.id)],
        }

    active_filters = []
    if query:
        active_filters.append(f"Recherche : {query}")
    if branch_id:
        active_filters.append("Campus sélectionné")
    if programme_id:
        active_filters.append("Programme sélectionné")
    return _dg_list_result(
        request,
        dg_context,
        section=section,
        title="Classes",
        eyebrow="Pilotage académique",
        subtitle="Classes actives de l’année et du périmètre institutionnel sélectionnés.",
        headers=["Classe", "Programme", "Campus", "Année", "Effectif"],
        rows=row,
        queryset=queryset,
        filters=[
            {"name": "q", "label": "Recherche", "type": "search", "value": query, "placeholder": "Classe, niveau ou programme", "clearable": True},
            {"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)},
            {"name": "programme_id", "label": "Programme", "options": _dg_programme_filter_options(dg_context, programme_id)},
        ],
        active_filters=active_filters,
        empty_title="Aucune classe trouvée",
        empty_message="Aucune classe active ne correspond à ce contexte.",
    )


def _build_dg_payments_list(request, dg_context):
    query = (request.GET.get("q") or "").strip()[:120]
    branch_id = _dg_filter_branch_id(request, dg_context)
    status = (request.GET.get("status") or "").strip()
    method = (request.GET.get("method") or "").strip()
    date_from = _dg_parse_filter_date(request.GET.get("date_from"))
    date_to = _dg_parse_filter_date(request.GET.get("date_to"))
    base = get_dg_base_querysets(
        dg_context.scoped_branch_ids,
        academic_year=dg_context.academic_year,
    )
    queryset = base["all_payments"].select_related(
        "agent",
        "agent__user",
        "inscription",
        "inscription__candidature",
        "inscription__candidature__branch",
        "inscription__candidature__programme",
    )
    if query:
        queryset = queryset.filter(
            Q(reference__icontains=query)
            | Q(receipt_number__icontains=query)
            | Q(inscription__candidature__first_name__icontains=query)
            | Q(inscription__candidature__last_name__icontains=query)
        )
    if branch_id:
        queryset = queryset.filter(inscription__candidature__branch_id=branch_id)
    if date_from:
        queryset = queryset.filter(paid_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(paid_at__date__lte=date_to)
    valid_statuses = {value for value, _label in Payment.STATUS_CHOICES}
    if status in valid_statuses:
        queryset = queryset.filter(status=status)
    else:
        status = ""
    valid_methods = {value for value, _label in Payment.METHOD_CHOICES}
    if method in valid_methods:
        queryset = queryset.filter(method=method)
    else:
        method = ""
    queryset = queryset.order_by("-paid_at", "-id")

    def row(payment):
        candidate = payment.inscription.candidature
        return {
            "id": f"dg-payment-{payment.id}",
            "label": payment.reference or payment.receipt_number or str(payment.id),
            "cells": [
                {"value": payment.reference or payment.receipt_number or f"Paiement #{payment.id}", "secondary": candidate.full_name, "strong": True},
                {"value": candidate.branch.name},
                {"value": payment.get_method_display()},
                {"value": f"{payment.amount} FCFA", "amount": True},
                {"value": payment.get_status_display(), "tone": {Payment.STATUS_VALIDATED: "success", Payment.STATUS_PENDING: "warning", Payment.STATUS_CANCELLED: "danger"}.get(payment.status, "neutral")},
                {"value": payment.paid_at.strftime("%d/%m/%Y")},
            ],
            "actions": [_dg_drawer_action("payment", payment.id)],
        }

    active_filters = []
    if query:
        active_filters.append(f"Recherche : {query}")
    if branch_id:
        active_filters.append("Campus sélectionné")
    if status:
        active_filters.append(f"Statut : {dict(Payment.STATUS_CHOICES)[status]}")
    if method:
        active_filters.append(f"Mode : {dict(Payment.METHOD_CHOICES)[method]}")
    if date_from:
        active_filters.append(f"Depuis le {date_from:%d/%m/%Y}")
    if date_to:
        active_filters.append(f"Jusqu’au {date_to:%d/%m/%Y}")
    return _dg_list_result(
        request,
        dg_context,
        section="payments",
        title="Encaissements",
        eyebrow="Finance",
        subtitle="Opérations de paiement réelles, filtrées côté serveur par année et campus.",
        headers=["Référence / payeur", "Campus", "Mode", "Montant", "Statut", "Date"],
        rows=row,
        queryset=queryset,
        filters=[
            {"name": "q", "label": "Recherche", "type": "search", "value": query, "placeholder": "Référence, reçu ou étudiant", "clearable": True},
            {"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)},
            {"name": "method", "label": "Mode", "options": [{"value": "", "label": "Tous les modes", "selected": not method}] + [{"value": value, "label": label, "selected": value == method} for value, label in Payment.METHOD_CHOICES]},
            {"name": "status", "label": "Statut", "options": [{"value": "", "label": "Tous les statuts", "selected": not status}] + [{"value": value, "label": label, "selected": value == status} for value, label in Payment.STATUS_CHOICES]},
            {"name": "date_from", "label": "Du", "type": "date", "value": date_from.isoformat() if date_from else ""},
            {"name": "date_to", "label": "Au", "type": "date", "value": date_to.isoformat() if date_to else ""},
        ],
        active_filters=active_filters,
        empty_title="Aucun encaissement trouvé",
        empty_message="Aucun paiement ne correspond aux critères sélectionnés.",
    )


def _build_dg_expenses_list(request, dg_context):
    query = (request.GET.get("q") or "").strip()[:120]
    branch_id = _dg_filter_branch_id(request, dg_context)
    status = (request.GET.get("status") or "").strip()
    category = (request.GET.get("category") or "").strip()
    date_from = _dg_parse_filter_date(request.GET.get("date_from"))
    date_to = _dg_parse_filter_date(request.GET.get("date_to"))
    queryset = scoped(BranchExpense).select_related("branch", "created_by", "approved_by", "paid_by").filter(
        branch_id__in=dg_context.scoped_branch_ids
    )
    if dg_context.academic_year:
        queryset = queryset.filter(
            expense_date__gte=dg_context.academic_year.start_date,
            expense_date__lte=dg_context.academic_year.end_date,
        )
    if query:
        queryset = queryset.filter(Q(reference__icontains=query) | Q(title__icontains=query) | Q(supplier__icontains=query))
    if branch_id:
        queryset = queryset.filter(branch_id=branch_id)
    if date_from:
        queryset = queryset.filter(expense_date__gte=date_from)
    if date_to:
        queryset = queryset.filter(expense_date__lte=date_to)
    if status in {value for value, _label in BranchExpense.STATUS_CHOICES}:
        queryset = queryset.filter(status=status)
    else:
        status = ""
    if category in {value for value, _label in BranchExpense.CATEGORY_CHOICES}:
        queryset = queryset.filter(category=category)
    else:
        category = ""
    queryset = queryset.order_by("-expense_date", "-id")

    def row(expense):
        return {
            "id": f"dg-expense-{expense.id}",
            "label": expense.title,
            "cells": [
                {"value": expense.title, "secondary": expense.reference or expense.supplier or "Sans référence", "strong": True},
                {"value": expense.get_category_display()},
                {"value": expense.branch.name},
                {"value": f"{expense.amount} FCFA", "amount": True},
                {"value": expense.get_status_display(), "tone": {"paid": "success", "approved": "info", "submitted": "warning", "rejected": "danger"}.get(expense.status, "neutral")},
                {"value": expense.expense_date.strftime("%d/%m/%Y")},
            ],
            "actions": [_dg_drawer_action("expense", expense.id)],
        }

    active_filters = []
    if query:
        active_filters.append(f"Recherche : {query}")
    if branch_id:
        active_filters.append("Campus sélectionné")
    if category:
        active_filters.append(f"Catégorie : {dict(BranchExpense.CATEGORY_CHOICES)[category]}")
    if status:
        active_filters.append(f"Statut : {dict(BranchExpense.STATUS_CHOICES)[status]}")
    if date_from:
        active_filters.append(f"Depuis le {date_from:%d/%m/%Y}")
    if date_to:
        active_filters.append(f"Jusqu’au {date_to:%d/%m/%Y}")
    return _dg_list_result(
        request,
        dg_context,
        section="expenses",
        title="Dépenses",
        eyebrow="Finance",
        subtitle="Dépenses enregistrées dans les campus sélectionnés, justificatif visible depuis la fiche lorsqu’il existe.",
        headers=["Libellé", "Catégorie", "Campus", "Montant", "Statut", "Date"],
        rows=row,
        queryset=queryset,
        filters=[
            {"name": "q", "label": "Recherche", "type": "search", "value": query, "placeholder": "Référence, libellé ou bénéficiaire", "clearable": True},
            {"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)},
            {"name": "category", "label": "Catégorie", "options": [{"value": "", "label": "Toutes les catégories", "selected": not category}] + [{"value": value, "label": label, "selected": value == category} for value, label in BranchExpense.CATEGORY_CHOICES]},
            {"name": "status", "label": "Statut", "options": [{"value": "", "label": "Tous les statuts", "selected": not status}] + [{"value": value, "label": label, "selected": value == status} for value, label in BranchExpense.STATUS_CHOICES]},
            {"name": "date_from", "label": "Du", "type": "date", "value": date_from.isoformat() if date_from else ""},
            {"name": "date_to", "label": "Au", "type": "date", "value": date_to.isoformat() if date_to else ""},
        ],
        active_filters=active_filters,
        empty_title="Aucune dépense trouvée",
        empty_message="Aucune dépense ne correspond aux critères sélectionnés.",
    )


def _build_dg_inscriptions_list(request, dg_context, *, section="enrollments", receivables=False):
    query = (request.GET.get("q") or "").strip()[:120]
    branch_id = _dg_filter_branch_id(request, dg_context)
    status = (request.GET.get("status") or "").strip()
    queryset = scoped(Inscription).select_related(
        "candidature",
        "candidature__branch",
        "candidature__programme",
        "academic_class",
    ).filter(candidature__branch_id__in=dg_context.scoped_branch_ids, is_archived=False)
    if dg_context.academic_year:
        queryset = queryset.filter(candidature__academic_year=dg_context.academic_year.name)
    if receivables:
        queryset = queryset.filter(amount_paid__lt=F("amount_due"))
    if query:
        queryset = queryset.filter(
            Q(public_token__icontains=query)
            | Q(candidature__first_name__icontains=query)
            | Q(candidature__last_name__icontains=query)
        )
    if branch_id:
        queryset = queryset.filter(candidature__branch_id=branch_id)
    if status in {value for value, _label in Inscription.STATUS_CHOICES}:
        queryset = queryset.filter(status=status)
    else:
        status = ""
    queryset = queryset.order_by("-created_at")

    def row(inscription):
        candidate = inscription.candidature
        outstanding = max(inscription.amount_due - inscription.amount_paid, 0)
        return {
            "id": f"dg-inscription-{inscription.id}",
            "label": candidate.full_name,
            "cells": [
                {"value": candidate.full_name, "secondary": str(inscription.reference)[:12], "strong": True},
                {"value": candidate.programme.title},
                {"value": candidate.branch.name},
                {"value": f"{outstanding} FCFA", "amount": True},
                {"value": inscription.get_status_display(), "tone": "success" if inscription.status == Inscription.STATUS_ACTIVE else "warning"},
            ],
            "actions": [_dg_drawer_action("inscription", inscription.id)],
        }

    active_filters = []
    if query:
        active_filters.append(f"Recherche : {query}")
    if branch_id:
        active_filters.append("Campus sélectionné")
    if status:
        active_filters.append(f"Statut : {dict(Inscription.STATUS_CHOICES)[status]}")
    return _dg_list_result(
        request,
        dg_context,
        section=section,
        title="Créances" if receivables else "Inscriptions",
        eyebrow="Finance" if receivables else "Parcours étudiant",
        subtitle="Soldes administratifs calculés uniquement à partir des montants dus et payés enregistrés." if receivables else "Inscriptions réelles du périmètre DG, accessibles avec leur dossier.",
        headers=["Étudiant", "Programme", "Campus", "Reste dû", "Statut"],
        rows=row,
        queryset=queryset,
        filters=[
            {"name": "q", "label": "Recherche", "type": "search", "value": query, "placeholder": "Nom ou référence", "clearable": True},
            {"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)},
            {"name": "status", "label": "Statut", "options": [{"value": "", "label": "Tous les statuts", "selected": not status}] + [{"value": value, "label": label, "selected": value == status} for value, label in Inscription.STATUS_CHOICES]},
        ],
        active_filters=active_filters,
        empty_title="Aucun dossier trouvé",
        empty_message="Aucune inscription ne correspond aux critères sélectionnés.",
    )


def _build_dg_model_list(request, dg_context, *, section, title, eyebrow, subtitle, queryset, headers, row, filters=None, active_filters=None, empty_title="Aucune donnée", empty_message="Aucune donnée réelle n’est disponible dans ce contexte."):
    return _dg_list_result(
        request,
        dg_context,
        section=section,
        title=title,
        eyebrow=eyebrow,
        subtitle=subtitle,
        headers=headers,
        rows=row,
        queryset=queryset,
        filters=filters or [],
        active_filters=active_filters or [],
        empty_title=empty_title,
        empty_message=empty_message,
    )


def build_dg_backoffice_list_context(request, section, base_context_builder):
    """Build one real, scoped and paginated DG back-office workspace."""

    context, dg_context = _dg_list_base_context(request, base_context_builder, title="Back-office Direction générale")
    if section in {"annexes", "branch_list", "branch_comparison", "branch_managers"}:
        context.update(_build_dg_branch_list(request, dg_context, section=section))
    elif section in {"students", "students_overview"}:
        context.update(_build_dg_students_list(request, dg_context, section=section))
    elif section in {"classes", "academic_overview"}:
        context.update(_build_dg_classes_list(request, dg_context, section=section))
    elif section == "payments":
        context.update(_build_dg_payments_list(request, dg_context))
    elif section == "expenses":
        context.update(_build_dg_expenses_list(request, dg_context))
    elif section == "receivables":
        context.update(_build_dg_inscriptions_list(request, dg_context, section=section, receivables=True))
    elif section == "enrollments":
        context.update(_build_dg_inscriptions_list(request, dg_context, section=section))
    elif section in {"progression", "workflows"}:
        branch_id = _dg_filter_branch_id(request, dg_context)
        status = (request.GET.get("status") or "").strip()
        queryset = scoped(StudentYearDecision).select_related(
            "student",
            "student__user",
            "source_enrollment__branch",
            "source_academic_year",
            "source_class",
            "target_academic_year",
            "target_class",
        ).filter(source_enrollment__branch_id__in=dg_context.scoped_branch_ids)
        if dg_context.academic_year:
            queryset = queryset.filter(source_academic_year=dg_context.academic_year)
        if branch_id:
            queryset = queryset.filter(source_enrollment__branch_id=branch_id)
        if status in {value for value, _label in StudentYearDecision.WORKFLOW_STATUS_CHOICES}:
            queryset = queryset.filter(workflow_status=status)
        else:
            status = ""
        context.update(_build_dg_model_list(
            request,
            dg_context,
            section=section,
            title="Progression et passages",
            eyebrow="Académique",
            subtitle="Décisions annuelles consultées dans leur année source, sans action pédagogique quotidienne du DG.",
            queryset=queryset.order_by("-created_at", "-id"),
            headers=["Étudiant", "Campus", "Classe source", "Décision", "État"],
            row=lambda item: {
                "id": f"dg-progression-{item.id}",
                "label": item.student.full_name,
                "cells": [
                    {"value": item.student.full_name, "secondary": item.student.matricule, "strong": True},
                    {"value": item.source_enrollment.branch.name},
                    {"value": item.source_class.display_name},
                    {"value": item.get_decision_display()},
                    {
                        "value": item.get_workflow_status_display(),
                        "tone": "success" if item.workflow_status == StudentYearDecision.WORKFLOW_APPLIED else "warning" if item.workflow_status != StudentYearDecision.WORKFLOW_REJECTED else "danger",
                    },
                ],
            },
            filters=[
                {"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)},
                {"name": "status", "label": "État", "options": [{"value": "", "label": "Tous les états", "selected": not status}] + [{"value": value, "label": label, "selected": value == status} for value, label in StudentYearDecision.WORKFLOW_STATUS_CHOICES]},
            ],
            active_filters=["Campus sélectionné"] if branch_id else ([f"État : {dict(StudentYearDecision.WORKFLOW_STATUS_CHOICES)[status]}"] if status else []),
            empty_title="Aucune décision annuelle",
            empty_message="Aucune décision de progression ne correspond au contexte académique sélectionné.",
        ))
    else:
        # The remaining workspaces are all connected to persisted entities.  They
        # deliberately use the same list contract and never fabricate a chart or
        # a synthetic row when the underlying workflow has no record yet.
        branch_id = _dg_filter_branch_id(request, dg_context)
        if section == "cash_movements":
            queryset = scoped(BranchCashMovement).select_related("branch").filter(branch_id__in=dg_context.scoped_branch_ids)
            if dg_context.academic_year:
                queryset = queryset.filter(movement_date__gte=dg_context.academic_year.start_date, movement_date__lte=dg_context.academic_year.end_date)
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            context.update(_build_dg_model_list(
                request, dg_context, section=section, title="Caisses", eyebrow="Finance", subtitle="Mouvements de caisse réellement comptabilisés.", queryset=queryset.order_by("-movement_date", "-id"), headers=["Libellé", "Campus", "Type", "Source", "Montant", "Date"],
                row=lambda item: {"id": f"dg-cash-{item.id}", "label": item.label, "cells": [{"value": item.label, "secondary": item.reference, "strong": True}, {"value": item.branch.name}, {"value": item.get_movement_type_display(), "tone": "success" if item.movement_type == BranchCashMovement.TYPE_IN else "warning"}, {"value": item.get_source_display()}, {"value": f"{item.amount} FCFA", "amount": True}, {"value": item.movement_date.strftime("%d/%m/%Y")}], "actions": [_dg_drawer_action("cash_movement", item.id)]},
                filters=[{"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)}], active_filters=["Campus sélectionné"] if branch_id else [], empty_title="Aucun mouvement de caisse", empty_message="Aucun mouvement n’est enregistré pour cette période."))
        elif section == "assignments":
            query = (request.GET.get("q") or "").strip()[:120]
            status = (request.GET.get("status") or "").strip()
            scope_type = (request.GET.get("scope_type") or "").strip()
            queryset = scoped(DirectorTeacherAssignment).select_related(
                "branch", "teacher", "academic_class", "semester", "ue", "ec"
            ).filter(branch_id__in=dg_context.scoped_branch_ids)
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            if query:
                queryset = queryset.filter(
                    Q(teacher__first_name__icontains=query)
                    | Q(teacher__last_name__icontains=query)
                    | Q(teacher__username__icontains=query)
                    | Q(academic_class__name__icontains=query)
                    | Q(semester__academic_class__name__icontains=query)
                    | Q(ue__title__icontains=query)
                    | Q(ec__title__icontains=query)
                )
            valid_statuses = {value for value, _label in DirectorTeacherAssignment.STATUS_CHOICES}
            if status in valid_statuses:
                queryset = queryset.filter(status=status)
            else:
                status = ""
            valid_scope_types = {value for value, _label in DirectorTeacherAssignment.SCOPE_CHOICES}
            if scope_type in valid_scope_types:
                queryset = queryset.filter(scope_type=scope_type)
            else:
                scope_type = ""

            def assignment_target(item):
                if item.ec_id:
                    return item.ec.title
                if item.ue_id:
                    return item.ue.title
                if item.semester_id:
                    return str(item.semester)
                return item.academic_class.display_name if item.academic_class_id else "Non renseigné"

            active_filters = []
            if query:
                active_filters.append(f"Recherche : {query}")
            if branch_id:
                active_filters.append("Campus sélectionné")
            if status:
                active_filters.append(f"Statut : {dict(DirectorTeacherAssignment.STATUS_CHOICES)[status]}")
            if scope_type:
                active_filters.append(f"Portée : {dict(DirectorTeacherAssignment.SCOPE_CHOICES)[scope_type]}")
            context.update(_build_dg_model_list(
                request,
                dg_context,
                section=section,
                title="Affectations",
                eyebrow="Personnel",
                subtitle="Affectations enseignantes réellement enregistrées, contrôlées par campus.",
                queryset=queryset.order_by("teacher__last_name", "teacher__first_name", "-created_at"),
                headers=["Enseignant", "Portée", "Cible", "Campus", "Heures", "Statut"],
                row=lambda item: {
                    "id": f"dg-assignment-{item.id}",
                    "label": item.teacher.get_full_name() or item.teacher.username,
                    "cells": [
                        {"value": item.teacher.get_full_name() or item.teacher.username, "secondary": item.teacher.username, "strong": True},
                        {"value": item.get_scope_type_display()},
                        {"value": assignment_target(item)},
                        {"value": item.branch.name},
                        {"value": item.planned_hours if item.planned_hours is not None else "—", "amount": item.planned_hours is not None},
                        {"value": item.get_status_display(), "tone": "success" if item.status == DirectorTeacherAssignment.STATUS_ACTIVE else "warning"},
                    ],
                    "actions": [_dg_drawer_action("teacher_assignment", item.id)],
                },
                filters=[
                    {"name": "q", "label": "Recherche", "type": "search", "value": query, "placeholder": "Enseignant, classe, UE ou EC", "clearable": True},
                    {"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)},
                    {"name": "scope_type", "label": "Portée", "options": [{"value": "", "label": "Toutes", "selected": not scope_type}] + [{"value": value, "label": label, "selected": value == scope_type} for value, label in DirectorTeacherAssignment.SCOPE_CHOICES]},
                    {"name": "status", "label": "Statut", "options": [{"value": "", "label": "Tous", "selected": not status}] + [{"value": value, "label": label, "selected": value == status} for value, label in DirectorTeacherAssignment.STATUS_CHOICES]},
                ],
                active_filters=active_filters,
                empty_title="Aucune affectation",
                empty_message="Aucune affectation enseignante ne correspond au contexte sélectionné.",
            ))
        elif section == "closures":
            queryset = scoped(BranchMonthlyClosure).select_related("branch", "validated_by").filter(branch_id__in=dg_context.scoped_branch_ids)
            if dg_context.academic_year:
                queryset = queryset.filter(period_month__gte=dg_context.academic_year.start_date, period_month__lte=dg_context.academic_year.end_date)
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            context.update(_build_dg_model_list(
                request, dg_context, section=section, title="Clôtures mensuelles", eyebrow="Finance", subtitle="Archives de clôture conservées, sans suppression des données sources.", queryset=queryset.order_by("-period_month", "-id"), headers=["Période", "Campus", "Entrées", "Sorties", "Résultat", "Statut"],
                row=lambda item: {"id": f"dg-closure-{item.id}", "label": str(item), "cells": [{"value": item.period_month.strftime("%m/%Y"), "strong": True}, {"value": item.branch.name}, {"value": f"{item.total_entries} FCFA", "amount": True}, {"value": f"{item.total_exits} FCFA", "amount": True}, {"value": f"{item.result_amount} FCFA", "amount": True}, {"value": item.get_status_display(), "tone": "success" if item.status == BranchMonthlyClosure.STATUS_CLOSED else "warning"}], "actions": [_dg_drawer_action("closure", item.id)]},
                filters=[{"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)}], active_filters=["Campus sélectionné"] if branch_id else [], empty_title="Aucune clôture", empty_message="Aucune clôture mensuelle n’est disponible dans ce contexte."))
        elif section == "bank_transfers":
            queryset = scoped(BranchBankTransfer).select_related("branch", "closure").filter(branch_id__in=dg_context.scoped_branch_ids)
            if dg_context.academic_year:
                queryset = queryset.filter(transfer_date__gte=dg_context.academic_year.start_date, transfer_date__lte=dg_context.academic_year.end_date)
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            context.update(_build_dg_model_list(
                request, dg_context, section=section, title="Versements bancaires", eyebrow="Finance", subtitle="Versements déclarés avec banque, référence et justificatif lorsque fourni.", queryset=queryset.order_by("-transfer_date", "-id"), headers=["Référence", "Banque", "Campus", "Montant", "Date"],
                row=lambda item: {"id": f"dg-transfer-{item.id}", "label": item.reference, "cells": [{"value": item.reference, "strong": True}, {"value": item.bank_name}, {"value": item.branch.name}, {"value": f"{item.amount} FCFA", "amount": True}, {"value": item.transfer_date.strftime("%d/%m/%Y")}], "actions": [_dg_drawer_action("bank_transfer", item.id)]},
                filters=[{"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)}], active_filters=["Campus sélectionné"] if branch_id else [], empty_title="Aucun versement bancaire", empty_message="Aucun versement n’est enregistré dans ce contexte."))
        elif section in {"evaluations", "results"}:
            queryset = scoped(EvaluationCampaign).select_related("branch", "academic_year", "calendar_entry").filter(branch_id__in=dg_context.scoped_branch_ids)
            if dg_context.academic_year:
                queryset = queryset.filter(academic_year=dg_context.academic_year)
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            context.update(_build_dg_model_list(
                request, dg_context, section=section, title="Évaluations" if section == "evaluations" else "Résultats", eyebrow="Académique", subtitle="Campagnes et états réels des évaluations du périmètre.", queryset=queryset.order_by("-created_at"), headers=["Campagne", "Campus", "Année", "Type", "Statut"],
                row=lambda item: {"id": f"dg-campaign-{item.id}", "label": item.title, "cells": [{"value": item.title, "strong": True}, {"value": item.branch.name}, {"value": item.academic_year.name}, {"value": item.get_kind_display()}, {"value": item.get_status_display(), "tone": "success" if item.status in {EvaluationCampaign.STATUS_RESULTS_PUBLISHED, EvaluationCampaign.STATUS_CLOSED} else "warning"}], "actions": [_dg_drawer_action("evaluation_campaign", item.id)]},
                filters=[{"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)}], active_filters=["Campus sélectionné"] if branch_id else [], empty_title="Aucune campagne d’évaluation", empty_message="Aucune campagne n’est disponible dans ce contexte."))
        elif section == "diplomas":
            queryset = scoped(AcademicDiplomaAward).select_related("student", "student__inscription__candidature", "branch", "programme", "academic_class").filter(branch_id__in=dg_context.scoped_branch_ids)
            if dg_context.academic_year:
                queryset = queryset.filter(academic_year=dg_context.academic_year)
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            context.update(_build_dg_model_list(
                request, dg_context, section=section, title="Diplômes", eyebrow="Académique", subtitle="Dossiers de diplômes générés, prêts ou délivrés par l’établissement.", queryset=queryset.order_by("-created_at"), headers=["Étudiant", "Programme", "Campus", "Référence", "Statut"],
                row=lambda item: {"id": f"dg-diploma-{item.id}", "label": item.student.full_name, "cells": [{"value": item.student.full_name, "strong": True}, {"value": item.programme.title}, {"value": item.branch.name}, {"value": item.reference or "À générer"}, {"value": item.get_status_display(), "tone": "success" if item.status == AcademicDiplomaAward.STATUS_DELIVERED else "warning"}], "actions": [_dg_drawer_action("diploma", item.id)]},
                filters=[{"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)}], active_filters=["Campus sélectionné"] if branch_id else [], empty_title="Aucun diplôme", empty_message="Aucun dossier de diplôme n’est disponible dans ce contexte."))
        elif section == "documents":
            queryset = scoped(AdministrativeDocument).select_related("branch", "created_by").filter(branch_id__in=dg_context.scoped_branch_ids)
            if dg_context.academic_year:
                start, end = get_academic_year_datetime_bounds(dg_context.academic_year)
                queryset = queryset.filter(created_at__gte=start, created_at__lt=end)
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            context.update(_build_dg_model_list(
                request, dg_context, section=section, title="Documents & décisions", eyebrow="Gouvernance", subtitle="Documents administratifs réellement publiés ou en préparation.", queryset=queryset.order_by("-created_at"), headers=["Document", "Type", "Campus", "Statut", "Créé le"],
                row=lambda item: {"id": f"dg-document-{item.id}", "label": item.title, "cells": [{"value": item.title, "secondary": item.reference, "strong": True}, {"value": item.get_doc_type_display()}, {"value": item.branch.name}, {"value": item.get_status_display(), "tone": "success" if item.status == AdministrativeDocument.STATUS_PUBLISHED else "warning"}, {"value": item.created_at.strftime("%d/%m/%Y")}], "actions": [_dg_drawer_action("document", item.id)]},
                filters=[{"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)}], active_filters=["Campus sélectionné"] if branch_id else [], empty_title="Aucun document", empty_message="Aucun document administratif n’est disponible dans ce contexte."))
        elif section == "audit":
            queryset = _scope_support_audit_logs(
                SupportAuditLog.objects.select_related("actor", "target_user", "branch", "school", "academic_year"),
                dg_context,
            )
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            entries = [
                {
                    "kind": "support",
                    "created_at": item.created_at,
                    "action": item.get_action_type_display(),
                    "target": item.target_label or "—",
                    "branch": item.branch,
                    "actor": item.actor,
                    "details": item.details,
                }
                for item in queryset
            ]
            financial_logs = list(_dg_financial_audit_entries(dg_context, branch_id=branch_id))
            payment_ids = [
                item.target_id
                for item in financial_logs
                if item.target_model == "payments.payment"
            ]
            payment_references = {
                payment.pk: payment.public_reference
                for payment in Payment.objects.filter(pk__in=payment_ids)
            }
            for item in financial_logs:
                entries.append(
                    {
                        "kind": "financial",
                        "created_at": item.created_at,
                        "action": "Paiement validé" if item.action_type == "payment_validated" else item.action_type,
                        "target": payment_references.get(item.target_id, f"Opération #{item.target_id}"),
                        "branch": item.branch,
                        "actor": item.performed_by,
                        "details": "Traçabilité financière",
                    }
                )
            for item in _dg_security_audit_entries(dg_context, branch_id=branch_id):
                actor = item.actor or item.user
                profile = getattr(item.user, "profile", None) or getattr(item.actor, "profile", None)
                entries.append(
                    {
                        "kind": "security",
                        "created_at": item.created_at,
                        "action": item.get_event_type_display(),
                        "target": item.user.get_full_name() or item.user.username if item.user else "Compte inconnu",
                        "branch": getattr(profile, "branch", None),
                        "actor": actor,
                        "details": item.reason or "Traçabilité de connexion et de session",
                    }
                )
            entries.sort(key=lambda item: (item["created_at"], item["kind"]), reverse=True)
            context.update(_build_dg_model_list(
                request, dg_context, section=section, title="Audit & contrôle", eyebrow="Gouvernance", subtitle="Journal des opérations institutionnelles et financières réellement tracées dans le périmètre sélectionné.", queryset=entries, headers=["Action", "Cible", "Campus", "Acteur", "Date"],
                row=lambda item: {"id": f"dg-audit-{item['kind']}-{item['created_at'].timestamp()}", "label": item["action"], "cells": [{"value": item["action"], "secondary": item["details"], "strong": True}, {"value": item["target"]}, {"value": item["branch"].name if item["branch"] else "Direction générale"}, {"value": (item["actor"].get_full_name() or item["actor"].username) if item["actor"] else "Système"}, {"value": item["created_at"].strftime("%d/%m/%Y %H:%M")}], "actions": []},
                filters=[{"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)}], active_filters=["Campus sélectionné"] if branch_id else [], empty_title="Aucun événement audité", empty_message="Aucun événement ne correspond au contexte et à la période sélectionnés."))
        else:
            queryset = _scope_support_audit_logs(
                scoped(SupportAuditLog).select_related("actor", "target_user", "branch", "school", "academic_year"),
                dg_context,
            )
            if branch_id:
                queryset = queryset.filter(branch_id=branch_id)
            title = {"branch_activity": "Activité des campus", "staff_history": "Historique du personnel"}.get(section, "Journal d’activité")
            context.update(_build_dg_model_list(
                request, dg_context, section=section, title=title, eyebrow="Gouvernance", subtitle="Journal d’événements réellement audités dans le périmètre sélectionné.", queryset=queryset.order_by("-created_at", "-id"), headers=["Action", "Cible", "Campus", "Acteur", "Date"],
                row=lambda item: {"id": f"dg-audit-{item.id}", "label": item.get_action_type_display(), "cells": [{"value": item.get_action_type_display(), "secondary": item.details, "strong": True}, {"value": item.target_label or "—"}, {"value": item.branch.name if item.branch_id else "Direction générale"}, {"value": item.actor.get_full_name() or item.actor.username}, {"value": item.created_at.strftime("%d/%m/%Y %H:%M")}], "actions": [_dg_drawer_action("audit", item.id)]},
                filters=[{"name": "filter_branch_id", "label": "Campus", "options": _dg_branch_filter_options(dg_context, branch_id)}], active_filters=["Campus sélectionné"] if branch_id else [], empty_title="Aucun événement audité", empty_message="Aucun événement ne correspond au contexte et à la période sélectionnés."))
    return context


DG_GENERIC_DRAWER_KINDS = frozenset(
    {
        "academic_class",
        "expense",
        "inscription",
        "cash_movement",
        "closure",
        "bank_transfer",
        "evaluation_campaign",
        "diploma",
        "document",
        "teacher_assignment",
    }
)


def is_dg_generic_drawer_kind(kind: str) -> bool:
    return kind in DG_GENERIC_DRAWER_KINDS


def build_dg_generic_drawer_context(request):
    """Read one supporting back-office record without widening the DG scope."""

    dg_context = resolve_dg_context(request, accept_legacy_branch_param=False)
    kind = (request.GET.get("kind") or "").strip().lower()
    raw_id = (request.GET.get("id") or "").strip()
    if kind not in DG_GENERIC_DRAWER_KINDS or not raw_id.isdigit():
        raise DgScopeViolation("Objet de consultation DG invalide.")
    object_id = int(raw_id)
    branch_ids = dg_context.scoped_branch_ids
    academic_year = dg_context.academic_year

    entity = None
    title = "Détail"
    subtitle = ""
    fields = []
    attachment = None
    if kind == "academic_class":
        queryset = scoped(AcademicClass).select_related("branch", "academic_year", "programme").annotate(
            student_count=Count("enrollments", filter=Q(enrollments__is_active=True), distinct=True)
        ).filter(id=object_id, branch_id__in=branch_ids)
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)
        entity = queryset.first()
        if entity:
            title = entity.display_name
            subtitle = "Fiche classe"
            fields = [
                ("Programme", entity.programme.title),
                ("Campus", entity.branch.name),
                ("Année académique", entity.academic_year.name),
                ("Niveau", entity.level),
                ("Effectif actif", entity.student_count),
            ]
            context_actions = [
                {"label": "Modifier la classe", "url": f"{reverse('accounts_portal:dg_academic_class_editor')}?class_id={entity.pk}", "style": "primary"},
                {"label": "Supprimer la classe", "url": reverse("accounts_portal:dg_academic_class_archive"), "class_id": entity.pk, "style": "danger"},
            ]
    elif kind == "expense":
        queryset = scoped(BranchExpense).select_related("branch", "created_by", "approved_by", "paid_by").filter(
            id=object_id, branch_id__in=branch_ids
        )
        if academic_year:
            queryset = queryset.filter(expense_date__gte=academic_year.start_date, expense_date__lte=academic_year.end_date)
        entity = queryset.first()
        if entity:
            title = entity.title
            subtitle = "Dépense de campus"
            fields = [
                ("Référence", entity.reference or "Non renseignée"),
                ("Catégorie", entity.get_category_display()),
                ("Campus", entity.branch.name),
                ("Bénéficiaire", entity.supplier or "Non renseigné"),
                ("Montant", f"{entity.amount} FCFA"),
                ("Statut", entity.get_status_display()),
                ("Date", entity.expense_date.strftime("%d/%m/%Y")),
                ("Commentaire", entity.notes or "Aucun commentaire"),
            ]
            attachment = entity.receipt if entity.receipt else None
    elif kind == "inscription":
        queryset = scoped(Inscription).select_related(
            "candidature", "candidature__branch", "candidature__programme", "academic_class"
        ).filter(id=object_id, candidature__branch_id__in=branch_ids)
        if academic_year:
            queryset = queryset.filter(candidature__academic_year=academic_year.name)
        entity = queryset.first()
        if entity:
            candidate = entity.candidature
            title = candidate.full_name
            subtitle = "Dossier d’inscription"
            fields = [
                ("Référence", str(entity.reference)),
                ("Programme", candidate.programme.title),
                ("Campus", candidate.branch.name),
                ("Classe", entity.academic_class.display_name if entity.academic_class else "Non affectée"),
                ("Montant dû", f"{entity.amount_due} FCFA"),
                ("Montant payé", f"{entity.amount_paid} FCFA"),
                ("Reste dû", f"{max(entity.amount_due - entity.amount_paid, 0)} FCFA"),
                ("Statut", entity.get_status_display()),
            ]
    elif kind == "cash_movement":
        queryset = scoped(BranchCashMovement).select_related("branch", "created_by", "expense").filter(
            id=object_id, branch_id__in=branch_ids
        )
        if academic_year:
            queryset = queryset.filter(movement_date__gte=academic_year.start_date, movement_date__lte=academic_year.end_date)
        entity = queryset.first()
        if entity:
            title = entity.label
            subtitle = "Mouvement de caisse"
            fields = [
                ("Campus", entity.branch.name),
                ("Type", entity.get_movement_type_display()),
                ("Source", entity.get_source_display()),
                ("Montant", f"{entity.amount} FCFA"),
                ("Référence", entity.reference or "Non renseignée"),
                ("Date", entity.movement_date.strftime("%d/%m/%Y")),
                ("Notes", entity.notes or "Aucune note"),
            ]
            attachment = entity.receipt_pdf if entity.receipt_pdf else None
    elif kind == "closure":
        queryset = scoped(BranchMonthlyClosure).select_related("branch", "validated_by").filter(
            id=object_id, branch_id__in=branch_ids
        )
        if academic_year:
            queryset = queryset.filter(period_month__gte=academic_year.start_date, period_month__lte=academic_year.end_date)
        entity = queryset.first()
        if entity:
            title = f"Clôture {entity.period_month:%m/%Y}"
            subtitle = entity.branch.name
            fields = [
                ("Statut", entity.get_status_display()),
                ("Total entrées", f"{entity.total_entries} FCFA"),
                ("Total sorties", f"{entity.total_exits} FCFA"),
                ("Résultat", f"{entity.result_amount} FCFA"),
                ("Versement bancaire", f"{entity.bank_transfer_amount} FCFA"),
                ("Caisse théorique", f"{entity.theoretical_cash_balance} FCFA"),
                ("Comptage physique", f"{entity.physical_cash_count} FCFA" if entity.physical_cash_count is not None else "Non renseigné"),
                ("Écart de caisse", f"{entity.cash_difference} FCFA"),
                ("Justification de l'écart", entity.difference_justification or "Aucune"),
                ("Validée par", entity.validated_by.get_full_name() if entity.validated_by else "Non validée"),
                ("Notes", entity.notes or "Aucune note"),
            ]
    elif kind == "bank_transfer":
        queryset = scoped(BranchBankTransfer).select_related("branch", "closure", "created_by").filter(
            id=object_id, branch_id__in=branch_ids
        )
        if academic_year:
            queryset = queryset.filter(transfer_date__gte=academic_year.start_date, transfer_date__lte=academic_year.end_date)
        entity = queryset.first()
        if entity:
            title = entity.reference
            subtitle = "Versement bancaire"
            fields = [
                ("Banque", entity.bank_name),
                ("Campus", entity.branch.name),
                ("Montant", f"{entity.amount} FCFA"),
                ("Date", entity.transfer_date.strftime("%d/%m/%Y")),
                ("Statut", entity.get_status_display()),
                ("Solde avant versement", f"{entity.cash_balance_before} FCFA"),
                ("Solde après versement", f"{entity.cash_balance_after} FCFA"),
                ("Clôture associée", str(entity.closure) if entity.closure_id else "Aucune"),
                ("Commentaire", entity.comment or "Aucun commentaire"),
            ]
            attachment = entity.proof if entity.proof else None
    elif kind == "evaluation_campaign":
        queryset = scoped(EvaluationCampaign).select_related("branch", "academic_year", "calendar_entry").filter(
            id=object_id, branch_id__in=branch_ids
        )
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)
        entity = queryset.first()
        if entity:
            title = entity.title
            subtitle = "Campagne d’évaluation"
            fields = [
                ("Campus", entity.branch.name),
                ("Année", entity.academic_year.name),
                ("Type", entity.get_kind_display()),
                ("Semestre", entity.semester_number or "Tous semestres"),
                ("Statut", entity.get_status_display()),
                ("Calendrier", str(entity.calendar_entry)),
            ]
    elif kind == "diploma":
        queryset = scoped(AcademicDiplomaAward).select_related(
            "student", "student__inscription__candidature", "branch", "programme", "academic_class", "diploma"
        ).filter(id=object_id, branch_id__in=branch_ids)
        if academic_year:
            queryset = queryset.filter(academic_year=academic_year)
        entity = queryset.first()
        if entity:
            title = entity.student.full_name
            subtitle = "Dossier de diplôme"
            fields = [
                ("Référence", entity.reference or "À générer"),
                ("Programme", entity.programme.title),
                ("Diplôme", entity.diploma.name),
                ("Campus", entity.branch.name),
                ("Classe", entity.academic_class.display_name),
                ("Moyenne finale", entity.final_average if entity.final_average is not None else "Non calculée"),
                ("Statut", entity.get_status_display()),
            ]
            attachment = entity.pdf_file if entity.pdf_file else None
    elif kind == "document":
        entity = scoped(AdministrativeDocument).select_related("branch", "created_by").filter(
            id=object_id, branch_id__in=branch_ids
        ).first()
        if entity:
            title = entity.title
            subtitle = "Document administratif"
            fields = [
                ("Référence", entity.reference or "Non renseignée"),
                ("Type", entity.get_doc_type_display()),
                ("Campus", entity.branch.name),
                ("Statut", entity.get_status_display()),
                ("Destinataires", entity.recipients or "Non renseignés"),
                ("Créé le", entity.created_at.strftime("%d/%m/%Y %H:%M")),
                ("Contenu", entity.body),
            ]

    elif kind == "teacher_assignment":
        entity = scoped(DirectorTeacherAssignment).select_related(
            "branch", "teacher", "academic_class", "semester", "ue", "ec"
        ).filter(id=object_id, branch_id__in=branch_ids).first()
        if entity:
            if entity.ec_id:
                target = entity.ec.title
            elif entity.ue_id:
                target = entity.ue.title
            elif entity.semester_id:
                target = str(entity.semester)
            else:
                target = entity.academic_class.display_name if entity.academic_class_id else "Non renseignée"
            title = entity.teacher.get_full_name() or entity.teacher.username
            subtitle = "Affectation enseignante"
            fields = [
                ("Campus", entity.branch.name),
                ("Portée", entity.get_scope_type_display()),
                ("Cible", target),
                ("Salle", entity.room_label or "Non renseignée"),
                ("Heures prévues", entity.planned_hours if entity.planned_hours is not None else "Non renseignées"),
                ("Début", entity.starts_on.strftime("%d/%m/%Y") if entity.starts_on else "Non renseigné"),
                ("Fin", entity.ends_on.strftime("%d/%m/%Y") if entity.ends_on else "Non renseignée"),
                ("Statut", entity.get_status_display()),
            ]

    if entity is None:
        raise DgScopeViolation("Cet objet est introuvable dans le contexte DG actif.")
    return {
        "entity_title": title,
        "entity_subtitle": subtitle,
        "entity_fields": fields,
        "entity_attachment": attachment,
        "entity_actions": locals().get("context_actions", []),
    }
