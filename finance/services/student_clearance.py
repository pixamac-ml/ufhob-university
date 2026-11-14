"""Canonical financial clearance for protected student academic services.

The current billing schema has no semester-specific instalment calendar.  We
therefore deliberately use the authoritative enrolment contract (`amount_due`)
and validated payments; callers must not guess six monthly amounts in views.
"""
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Sum

from payments.models import Payment


@dataclass(frozen=True)
class FinancialClearance:
    required_amount: Decimal
    paid_amount: Decimal
    outstanding_amount: Decimal
    is_cleared: bool
    academic_period: str
    enrollment: object | None

    @property
    def period(self):
        """Backward-compatible label for older callers."""
        return self.academic_period


def get_financial_clearance(student, enrollment, semester):
    if not enrollment or not getattr(enrollment, "inscription_id", None):
        return FinancialClearance(Decimal("0"), Decimal("0"), Decimal("0"), False, "Inscription inconnue", enrollment)
    required = Decimal(getattr(enrollment.inscription, "amount_due", 0) or 0)
    paid = Decimal(Payment.objects.filter(
        inscription=enrollment.inscription, status=Payment.STATUS_VALIDATED
    ).aggregate(total=Sum("amount"))["total"] or 0)
    outstanding = max(required - paid, Decimal("0"))
    return FinancialClearance(required, paid, outstanding, outstanding == 0, f"Semestre {semester.number}", enrollment)
