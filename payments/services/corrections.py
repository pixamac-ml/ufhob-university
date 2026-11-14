from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from inscriptions.models import Inscription
from accounts.models import BranchCashMovement
from payments.models import FinancialLog, Payment, PaymentCorrection


def _recalculate_historical_inscription_financial_state(*, inscription):
    """Recalculate only financial fields after an audited payment correction.

    Historical classes can legitimately be closed.  Re-saving the whole
    inscription would re-run academic positioning validation and make a
    financial rectification depend on the current class state.  The payment,
    cash movement and FinancialLog provide the correction audit; this narrow
    update deliberately avoids academic signals such as student assignment.
    """
    total_paid = (
        Payment.objects.filter(
            inscription_id=inscription.pk,
            status=Payment.STATUS_VALIDATED,
        ).aggregate(total=Sum("amount"))["total"]
        or 0
    )
    if total_paid == 0:
        financial_status = Inscription.STATUS_AWAITING_PAYMENT
    elif total_paid < inscription.amount_due:
        financial_status = Inscription.STATUS_PARTIAL
    else:
        financial_status = Inscription.STATUS_ACTIVE

    if (
        inscription.amount_paid != total_paid
        or inscription.status != financial_status
    ):
        Inscription.objects.filter(pk=inscription.pk).update(
            amount_paid=total_paid,
            status=financial_status,
        )
        inscription.amount_paid = total_paid
        inscription.status = financial_status


def _record_payment_correction_cash_adjustment(*, payment, correction, actor=None):
    """Keep the original receipt and record one traceable cash adjustment."""
    inscription = payment.inscription
    candidature = inscription.candidature
    branch = candidature.branch
    payment_reference = payment.reference or f"PAY-{payment.pk}"
    school = getattr(candidature.programme, "school", None)
    school_label = getattr(school, "display_name", "") or getattr(school, "code", "")

    # Some legacy payments predate the cash ledger.  Their source movement is
    # reconstructed at its pre-correction amount, never at the corrected one.
    original_movement, _created = BranchCashMovement.objects.get_or_create(
        branch=branch,
        source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
        source_reference=payment_reference,
        defaults={
            "movement_type": BranchCashMovement.TYPE_IN,
            "amount": correction.old_amount,
            "label": f"Paiement etudiant - {candidature.full_name}",
            "movement_date": payment.paid_at.date(),
            "reference": payment.reference,
            "receipt_number": payment.receipt_number or "",
            "notes": f"Paiement original {payment_reference}.",
            "created_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )

    adjustment_reference = f"{payment_reference}:COR:{correction.pk}"
    adjustment_movement, _created = BranchCashMovement.objects.get_or_create(
        branch=branch,
        source=BranchCashMovement.SOURCE_ADJUSTMENT,
        source_reference=adjustment_reference,
        defaults={
            "movement_type": (
                BranchCashMovement.TYPE_IN
                if correction.delta_amount > 0
                else BranchCashMovement.TYPE_OUT
            ),
            "amount": abs(correction.delta_amount),
            "label": f"Ajustement de paiement - {candidature.full_name}",
            "movement_date": correction.corrected_at.date(),
            "reference": payment.reference,
            "receipt_number": payment.receipt_number or "",
            "notes": (
                f"Paiement : {payment_reference}. "
                f"Ecole : {school_label or 'Non renseignee'}. "
                f"Campus : {branch.name}. Motif : {correction.reason}"
            ),
            "created_by": actor if getattr(actor, "is_authenticated", False) else None,
        },
    )
    return original_movement, adjustment_movement


def correct_validated_payment_amount(*, payment, new_amount, reason, actor=None):
    if payment.status != Payment.STATUS_VALIDATED:
        raise ValidationError("Seul un paiement valide peut etre corrige.")

    if new_amount <= 0:
        raise ValidationError("Le nouveau montant doit etre superieur a zero.")

    reason = (reason or "").strip()
    if not reason:
        raise ValidationError("Le motif de correction est obligatoire.")

    with transaction.atomic():
        locked_payment = (
            Payment.objects
            .select_for_update()
            .select_related("inscription__candidature__branch")
            .get(pk=payment.pk)
        )

        if locked_payment.status != Payment.STATUS_VALIDATED:
            raise ValidationError("Seul un paiement valide peut etre corrige.")

        old_amount = locked_payment.amount
        if old_amount == new_amount:
            raise ValidationError("Le nouveau montant est identique au montant actuel.")
        if new_amount > locked_payment.inscription.amount_due * 2:
            raise ValidationError("Montant incoherent detecte.")

        # Serialise the recalculation with normal payment validation, which
        # also locks the inscription before changing its financial state.
        locked_inscription = Inscription.objects.select_for_update().get(
            pk=locked_payment.inscription_id,
        )
        branch = locked_payment.inscription.candidature.branch
        correction = PaymentCorrection.objects.create(
            payment=locked_payment,
            old_amount=old_amount,
            new_amount=new_amount,
            delta_amount=new_amount - old_amount,
            reason=reason,
            corrected_by=actor if getattr(actor, "is_authenticated", False) else None,
        )

        Payment.objects.filter(pk=locked_payment.pk).update(amount=new_amount)
        locked_payment.amount = new_amount

        _recalculate_historical_inscription_financial_state(
            inscription=locked_inscription,
        )
        original_movement, adjustment_movement = _record_payment_correction_cash_adjustment(
            payment=locked_payment,
            correction=correction,
            actor=actor,
        )

        FinancialLog.objects.create(
            branch=branch,
            payment=locked_payment,
            correction=correction,
            action=FinancialLog.ACTION_PAYMENT_CORRECTED,
            old_amount=old_amount,
            new_amount=new_amount,
            delta_amount=new_amount - old_amount,
            reason=reason,
            actor=actor if getattr(actor, "is_authenticated", False) else None,
            metadata={
                "payment_reference": locked_payment.reference,
                "receipt_number": locked_payment.receipt_number or "",
                "inscription_id": locked_payment.inscription_id,
                "original_cash_movement_id": original_movement.pk,
                "adjustment_cash_movement_id": adjustment_movement.pk,
                "school_id": getattr(locked_payment.inscription.candidature.programme, "school_id", None),
                "branch_id": branch.pk,
                "academic_year": locked_payment.inscription.candidature.academic_year,
            },
        )

    locked_payment.refresh_from_db()
    return correction


def financial_logs_for_payment(payment):
    return (
        FinancialLog.objects
        .filter(payment=payment)
        .select_related("actor", "correction")
        .order_by("-created_at")
    )
