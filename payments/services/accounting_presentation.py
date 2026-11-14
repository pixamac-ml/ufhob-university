"""Human-readable accounting context for an already-authorized payment."""

from accounts.models import FinancialAuditLog, SensitiveActionRequest
from payments.models import FinancialLog


def _user_name(user):
    if not user:
        return "Non renseigne"
    return user.get_full_name().strip() or user.username


def build_payment_accounting_snapshot(payment):
    """Return accounting values without duplicating financial calculations in templates."""
    inscription = payment.inscription
    candidature = inscription.candidature
    programme = candidature.programme
    school = getattr(programme, "school", None)
    corrections = list(
        payment.corrections.select_related("corrected_by").order_by("corrected_at", "pk")
    )
    correction_ids = [correction.pk for correction in corrections]
    logs_by_correction = {
        log.correction_id: log
        for log in FinancialLog.objects.filter(correction_id__in=correction_ids)
        .select_related("actor")
        .order_by("created_at", "pk")
    }
    audits = list(
        FinancialAuditLog.objects.filter(
            action_type=SensitiveActionRequest.ACTION_PAYMENT_EDIT,
            target_model="Payment",
            target_id=payment.pk,
        )
        .select_related("sensitive_action_request", "performed_by", "approved_by")
        .order_by("created_at", "pk")
    )

    def audit_for(correction):
        for audit in audits:
            if (
                audit.previous_state.get("amount") == correction.old_amount
                and audit.new_state.get("amount") == correction.new_amount
            ):
                return audit
        return None

    running_total = int(inscription.amount_paid or 0)
    history = []
    for correction in reversed(corrections):
        balance_after = max(int(inscription.amount_due or 0) - running_total, 0)
        total_before = running_total - correction.new_amount + correction.old_amount
        balance_before = max(int(inscription.amount_due or 0) - total_before, 0)
        audit = audit_for(correction)
        sensitive_request = getattr(audit, "sensitive_action_request", None)
        financial_log = logs_by_correction.get(correction.pk)
        history.append({
            "correction": correction,
            "old_amount": correction.old_amount,
            "new_amount": correction.new_amount,
            "delta_amount": correction.delta_amount,
            "balance_before": balance_before,
            "balance_after": balance_after,
            "requested_by": _user_name(getattr(sensitive_request, "requested_by", None) or correction.corrected_by),
            "actor": _user_name(correction.corrected_by or getattr(financial_log, "actor", None)),
            "authorization": (
                f"Autorisation #{sensitive_request.pk} · Coupon DG/DGA"
                if sensitive_request else "Autorisation DG/DGA tracee dans l'audit"
            ),
            "authorization_status": "Appliquee",
            "cash_adjustment_id": (financial_log.metadata or {}).get("adjustment_cash_movement_id") if financial_log else None,
        })
        running_total = total_before
    history.reverse()

    return {
        "student_name": candidature.full_name,
        "programme_name": programme.title if programme else "",
        "school_name": getattr(school, "display_name", "") or getattr(school, "code", "") or "Non renseignee",
        "campus_name": candidature.branch.name if candidature.branch_id else "Non renseigne",
        "academic_year": candidature.academic_year,
        "initial_amount": corrections[0].old_amount if corrections else payment.amount,
        "effective_amount": payment.amount,
        "total_due": inscription.amount_due,
        "total_paid": inscription.amount_paid,
        "balance": inscription.balance,
        "is_adjusted": bool(corrections),
        "corrections": history,
    }
