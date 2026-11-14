from .scoping import scoped, staff_branch_filter
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Count, Q, Sum
from django.utils import timezone

from academics.models import AcademicClass, AcademicEnrollment
from accounts.models import (
    BranchExpense,
    BranchMonthlyClosure,
    InstitutionalProfile,
    Profile,
)
from admissions.models import Candidature
from branches.models import Branch
from inscriptions.models import Inscription
from payments.models import Payment
from students.models import AttendanceAlert, Student, StudentCase, StudentYearDecision


def get_active_branches():
    return (
        scoped(Branch).filter(is_active=True)
        .select_related("manager")
        .order_by("name")
    )


def get_active_branch_directors_of_studies(branch_ids, *, school=None):
    """Resolve active Directors of Studies from official HR assignments.

    Institutional assignments are authoritative and support all four scopes;
    legacy Profile rows remain only as a fallback for accounts not migrated yet.
    """
    if not branch_ids:
        return []

    coverage = Q(branch_id__in=branch_ids) | Q(access_scope="GLOBAL")
    if school is not None:
        coverage |= Q(school=school, branch__isnull=True)
        coverage |= Q(access_scope="BRANCH", branch_id__in=branch_ids, school__isnull=True)
    institutional = InstitutionalProfile.objects.filter(
        position="director_of_studies", employment_status="active", user__is_active=True,
    ).filter(coverage)
    if school is not None:
        institutional = institutional.filter(Q(school=school) | Q(school__isnull=True))
    institutional = list(institutional.select_related("user", "branch", "school"))
    institutional_user_ids = [item.user_id for item in institutional]

    # Compatibility only: a legacy director without an institutional assignment
    # still keeps its concrete campus responsibility.
    legacy = list(scoped(Profile).filter(
        position="director_of_studies", employment_status="active", user__is_active=True,
        user_type="staff", branch_id__in=branch_ids,
    ).exclude(user_id__in=institutional_user_ids).select_related("user", "branch"))
    return sorted(institutional + legacy, key=lambda item: (
        item.user.last_name, item.user.first_name, item.user.username, item.id
    ))


def get_academic_year_datetime_bounds(academic_year):
    """Return timezone-aware inclusive/exclusive bounds for a DG academic year."""
    return (
        timezone.make_aware(datetime.combine(academic_year.start_date, time.min)),
        timezone.make_aware(datetime.combine(academic_year.end_date + timedelta(days=1), time.min)),
    )


def get_dg_base_querysets(branch_ids, *, academic_year=None):
    """Canonical DG querysets constrained by branches and, when selected, year."""
    branch_filter = {"id__in": branch_ids}
    candidature_filters = {}
    class_filters = {}
    enrollment_filters = {}
    payment_filters = {}
    expense_filters = {}
    closure_filters = {}
    alert_filters = {}
    case_filters = {}
    decision_filters = {}
    if academic_year is not None:
        academic_year_start, academic_year_end = get_academic_year_datetime_bounds(academic_year)
        candidature_filters["academic_year"] = academic_year.name
        class_filters["academic_year"] = academic_year
        enrollment_filters["academic_year"] = academic_year
        # Payment scope inherits ``candidature_filters`` below.  That keeps a
        # payment tied to its academic dossier year rather than only to its
        # transaction timestamp.
        expense_filters.update(
            {
                "expense_date__gte": academic_year.start_date,
                "expense_date__lte": academic_year.end_date,
            }
        )
        closure_filters.update(
            {
                "period_month__gte": academic_year.start_date,
                "period_month__lte": academic_year.end_date,
            }
        )
        alert_filters.update(
            {
                "triggered_at__gte": academic_year_start,
                "triggered_at__lt": academic_year_end,
            }
        )
        case_filters.update(
            {
                "created_at__gte": academic_year_start,
                "created_at__lt": academic_year_end,
            }
        )
        decision_filters["source_enrollment__academic_year"] = academic_year
    student_enrollment_filters = {
        "user__academic_enrollments__branch_id__in": branch_ids,
    }
    if academic_year is not None:
        # Keep branch and year on the same enrollment join.  Separate filters
        # can otherwise match two historical enrollments of the same student.
        student_enrollment_filters[
            "user__academic_enrollments__academic_year"
        ] = academic_year
    student_queryset = scoped(Student).filter(
        is_active=True,
        **student_enrollment_filters,
    )

    payment_scope = scoped(Payment).filter(
        inscription__candidature__branch_id__in=branch_ids,
        **{f"inscription__candidature__{key}": value for key, value in candidature_filters.items()},
        **payment_filters,
    )

    return {
        # AcademicEnrollment is the authoritative yearly student state.  The
        # original administrative inscription remains the identity anchor but
        # must not reconstruct a historical academic year.
        "students": student_queryset.distinct(),
        "classes": scoped(AcademicClass).filter(
            is_active=True,
            is_archived=False,
            branch_id__in=branch_ids,
            **class_filters,
        ),
        "enrollments": scoped(AcademicEnrollment).filter(
            is_active=True,
            branch_id__in=branch_ids,
            **enrollment_filters,
        ),
        "inscriptions": scoped(Inscription).filter(
            status__in={"partial_paid", "active"},
            candidature__branch_id__in=branch_ids,
            **{f"candidature__{key}": value for key, value in candidature_filters.items()},
        ),
        "candidatures": scoped(Candidature).filter(
            is_deleted=False,
            branch_id__in=branch_ids,
            **candidature_filters,
        ),
        "all_payments": payment_scope,
        "payments": payment_scope.filter(status=Payment.STATUS_VALIDATED),
        "pending_payments": payment_scope.filter(status=Payment.STATUS_PENDING),
        "cancelled_payments": payment_scope.filter(status=Payment.STATUS_CANCELLED),
        "expenses": scoped(BranchExpense).filter(branch_id__in=branch_ids, **expense_filters),
        "attendance_alerts": scoped(AttendanceAlert).filter(
            is_resolved=False,
            branch_id__in=branch_ids,
            **alert_filters,
        ),
        "student_cases": scoped(StudentCase).filter(branch_id__in=branch_ids, **case_filters),
        "year_decisions": scoped(StudentYearDecision).filter(
            source_enrollment__branch_id__in=branch_ids,
            **decision_filters,
        ),
        "staff": scoped(Profile).filter(
            user_type="staff",
            employment_status="active",
        ).filter(staff_branch_filter(branch_ids)),
        "monthly_closures": scoped(BranchMonthlyClosure).filter(
            branch_id__in=branch_ids,
            **closure_filters,
        ).select_related("branch", "validated_by"),
        "branch_filter": branch_filter,
    }


def get_recent_candidatures_count(branch_ids, days=30, *, academic_year=None):
    academic_year_filter = {"academic_year": academic_year.name} if academic_year else {}
    return scoped(Candidature).filter(
        submitted_at__gte=timezone.now() - timedelta(days=days),
        branch_id__in=branch_ids,
        is_deleted=False,
        **academic_year_filter,
    ).count()


def get_branch_finance(branch, *, academic_year=None):
    expense_date_filters = {}
    candidature_filters = {}
    if academic_year is not None:
        # A payment belongs to the academic year of its administrative dossier,
        # not to the wall-clock date on which the cashier validates it.  This
        # keeps an early payment for 2026-2027 visible before its first class day.
        candidature_filters["inscription__candidature__academic_year"] = academic_year.name
        expense_date_filters = {
            "expense_date__gte": academic_year.start_date,
            "expense_date__lte": academic_year.end_date,
        }
    revenue = (
        scoped(Payment).filter(
            status=Payment.STATUS_VALIDATED,
            inscription__candidature__branch=branch,
            **candidature_filters,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    expenses = (
        scoped(BranchExpense).filter(
            branch=branch,
            status__in={
                BranchExpense.STATUS_SUBMITTED,
                BranchExpense.STATUS_APPROVED,
                BranchExpense.STATUS_PAID,
            },
            **expense_date_filters,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    return revenue, expenses, revenue - expenses


def get_top_classes_for_branch(branch, limit=5, *, academic_year=None):
    year_filter = {"academic_year": academic_year} if academic_year else {}
    return list(
        scoped(AcademicClass).filter(branch=branch, is_active=True, is_archived=False, **year_filter)
        .annotate(student_count=Count("enrollments", filter=Q(enrollments__is_active=True)))
        .order_by("-student_count", "level", "programme__title")[:limit]
    )


def get_top_programmes_for_branch(branch, limit=3, *, academic_year=None):
    year_filter = {"academic_year": academic_year.name} if academic_year else {}
    return list(
        scoped(Candidature).filter(branch=branch, is_deleted=False, **year_filter)
        .values("programme__title")
        .annotate(total=Count("id"))
        .order_by("-total", "programme__title")[:limit]
    )


def get_latest_payments_for_branch(branch, limit=5, *, academic_year=None):
    candidature_filters = {}
    if academic_year is not None:
        # Match the canonical DG payment scope: dossier academic year, rather
        # than an incidental validation timestamp.
        candidature_filters["inscription__candidature__academic_year"] = academic_year.name
    return list(
        scoped(Payment).filter(
            status=Payment.STATUS_VALIDATED,
            inscription__candidature__branch=branch,
            **candidature_filters,
        )
        .select_related("inscription__candidature")
        .order_by("-paid_at")[:limit]
    )
