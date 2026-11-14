from accounts.scoping import scoped
import json

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.models import BranchCashMovement, SensitiveActionRequest
from payments.models import FinancialLog, Payment

from accounts.services.accounting_documents import create_cash_movement
from accounts.services.financial_integrity import assert_financial_period_open
from accounts.services.manager_dashboard_presentation import build_payment_table_row
from accounts.services.manager_intelligence import payment_cash_reference
from accounts.services.sensitive_actions import (
    SensitiveActionError,
    confirm_sensitive_action,
    request_sensitive_action,
)
from payments.services.corrections import correct_validated_payment_amount, financial_logs_for_payment
from payments.services.accounting_presentation import build_payment_accounting_snapshot

from accounts.dashboards.htmx_utils import manager_finance_required


def _payment_modal_context(request, payment, **extra):
    context = {
        "payment": payment,
        "financial_logs": financial_logs_for_payment(payment)[:20],
        "corrections": payment.corrections.select_related("corrected_by").all()[:10],
        "accounting": build_payment_accounting_snapshot(payment),
        "manager_capabilities": request.manager_workspace_access.capabilities_context(),
    }
    context.update(extra)
    return context


@manager_finance_required("view_payments")
@require_GET
def payment_detail(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        scoped(Payment, user=request.user).select_related(
            "inscription__candidature",
            "inscription__candidature__programme",
            "inscription__candidature__programme__school",
            "agent__user",
            "cash_session",
            "cash_session__agent__user",
        ),
        pk=pk,
        inscription__candidature__branch=request.branch,
    )
    pending_request = SensitiveActionRequest.objects.filter(
        action_type=SensitiveActionRequest.ACTION_PAYMENT_EDIT,
        target_model="Payment",
        target_id=payment.pk,
        branch=request.branch,
        requested_by=request.user,
        status=SensitiveActionRequest.STATUS_PENDING,
        expires_at__gt=timezone.now(),
    ).order_by("-created_at").first()
    return render(
        request,
        "accounts/dashboard/partials/payment_modal.html",
        _payment_modal_context(
            request,
            payment,
            pending_request=pending_request,
            otp_request_id=pending_request.pk if pending_request else None,
        ),
    )


@manager_finance_required("correct_payment")
@require_POST
def payment_correct(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        scoped(Payment, user=request.user).select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__branch",
            "inscription__candidature__programme__school",
        ),
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_VALIDATED,
    )
    action = (request.POST.get("action") or "request_authorization").strip()
    raw_amount = (request.POST.get("new_amount") or "").strip()
    reason = (request.POST.get("reason") or "").strip()

    if action != "request_authorization":
        return HttpResponse("Action de correction invalide.", status=400)

    try:
        new_amount = int(raw_amount)
    except (TypeError, ValueError):
        new_amount = 0

    if new_amount <= 0:
        response = render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            _payment_modal_context(
                request,
                payment,
                correction_error="Saisissez une nouvelle valeur valide.",
                correction_new_amount=raw_amount,
                correction_reason=reason,
            ),
        )
        response.status_code = 400
        return response

    if new_amount == payment.amount:
        response = render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            _payment_modal_context(
                request,
                payment,
                correction_error="La nouvelle valeur doit etre differente de l'ancienne.",
                correction_new_amount=raw_amount,
                correction_reason=reason,
            ),
        )
        response.status_code = 400
        return response

    if not reason:
        response = render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            _payment_modal_context(
                request,
                payment,
                correction_error="Le motif de correction est obligatoire.",
                correction_new_amount=raw_amount,
            ),
        )
        response.status_code = 400
        return response

    try:
        otp_request = request_sensitive_action(
            branch=request.branch,
            action_type=SensitiveActionRequest.ACTION_PAYMENT_EDIT,
            target_model="Payment",
            target_id=payment.pk,
            previous_state={"amount": int(payment.amount)},
            requested_state={
                "amount": new_amount,
                "delta": new_amount - int(payment.amount),
            },
            requested_by=request.user,
            reason=reason,
        )
    except SensitiveActionError as exc:
        response = render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            _payment_modal_context(
                request,
                payment,
                correction_error=str(exc),
                correction_new_amount=raw_amount,
                correction_reason=reason,
            ),
        )
        response.status_code = 400
        return response

    response = render(
        request,
        "accounts/dashboard/partials/payment_modal.html",
        _payment_modal_context(
            request,
            payment,
            pending_request=otp_request,
            otp_request_id=otp_request.pk,
            correction_new_amount=raw_amount,
            correction_reason=reason,
        ),
    )
    response["HX-Trigger"] = json.dumps({
        "showToast": {
            "message": "Votre demande a ete transmise a la Direction Generale.",
            "type": "info",
        },
    })
    return response


@manager_finance_required("correct_payment")
@require_POST
def payment_correct_confirm_otp(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        scoped(Payment, user=request.user).select_related(
            "inscription",
            "inscription__candidature",
            "inscription__candidature__branch",
            "inscription__candidature__programme__school",
        ),
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_VALIDATED,
    )
    action = (request.POST.get("action") or "apply_correction").strip()
    otp_request_id = request.POST.get("otp_request_id")
    otp_code = (request.POST.get("otp_code") or "").strip()
    confirmation = (request.POST.get("confirmation") or "").strip().upper()

    def _render_missing_request(message):
        return render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            _payment_modal_context(request, payment, correction_error=message),
        )

    matching_requests = SensitiveActionRequest.objects.filter(
        branch=request.branch,
        action_type=SensitiveActionRequest.ACTION_PAYMENT_EDIT,
        target_model="Payment",
        target_id=payment.pk,
        requested_by=request.user,
    )
    if otp_request_id:
        pending_request = matching_requests.filter(pk=otp_request_id).first()
    else:
        # Legacy modal clients without an id resolve the latest live request;
        # cancelled or consumed history cannot shadow a newer pending request.
        pending_request = matching_requests.filter(
            status=SensitiveActionRequest.STATUS_PENDING,
            expires_at__gt=timezone.now(),
        ).order_by("-created_at", "-pk").first()
    if pending_request is None:
        return _render_missing_request("Demande d'autorisation introuvable ou inactive.")

    def _render_otp_error(message):
        active_request = pending_request.status == SensitiveActionRequest.STATUS_PENDING
        return render(
            request,
            "accounts/dashboard/partials/payment_modal.html",
            _payment_modal_context(
                request,
                payment,
                pending_request=pending_request if active_request else None,
                otp_request_id=pending_request.pk,
                otp_error=message if active_request else None,
                correction_error=message if not active_request else None,
            ),
        )

    if pending_request.status == SensitiveActionRequest.STATUS_CANCELLED:
        return _render_otp_error("Cette demande a ete annulee. Demandez une nouvelle autorisation.")
    if pending_request.status == SensitiveActionRequest.STATUS_APPROVED:
        return _render_otp_error("Cette demande a deja ete utilisee.")
    if pending_request.status == SensitiveActionRequest.STATUS_EXPIRED or pending_request.expires_at <= timezone.now():
        if pending_request.status == SensitiveActionRequest.STATUS_PENDING:
            pending_request.status = SensitiveActionRequest.STATUS_EXPIRED
            pending_request.resolved_at = timezone.now()
            pending_request.otp_display_code = ""
            pending_request.save(update_fields=["status", "resolved_at", "otp_display_code"])
        return _render_otp_error("Ce code a expire. Demandez une nouvelle autorisation.")

    if action != "apply_correction":
        return _render_otp_error("Action de correction invalide.")

    if not otp_code:
        return _render_otp_error("Saisissez le code d'autorisation.")

    if confirmation != "CORRIGER":
        return _render_otp_error("Tapez CORRIGER pour appliquer la correction.")

    def _apply(otp_request):
        new_amount = otp_request.requested_state.get("amount")
        expected_old_amount = otp_request.previous_state.get("amount")
        payment.refresh_from_db(fields=["amount"])
        if expected_old_amount is None or int(payment.amount) != int(expected_old_amount):
            raise ValidationError(
                "Le paiement a change depuis la demande. Creez une nouvelle demande d'autorisation."
            )
        correct_validated_payment_amount(
            payment=payment,
            new_amount=new_amount,
            reason=otp_request.reason,
            actor=otp_request.requested_by,
        )
        payment.refresh_from_db()
        return {"amount": payment.amount}

    try:
        confirm_sensitive_action(
            request_id=pending_request.pk,
            code=otp_code,
            approver=request.user,
            apply_callback=_apply,
            allow_requester_code_holder=True,
        )
    except (SensitiveActionError, ValidationError, SensitiveActionRequest.DoesNotExist) as exc:
        message = " ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
        if message == "Code de validation incorrect.":
            message = "Code d'autorisation incorrect."
        elif message == "Le code n'a pas ete entre a temps. Veuillez recommencer la demande.":
            message = "Ce code a expire. Demandez une nouvelle autorisation."
        payment.refresh_from_db()
        pending_request.refresh_from_db()
        return _render_otp_error(message)

    payment.refresh_from_db()
    response = render(
        request,
        "accounts/dashboard/partials/payment_modal.html",
        _payment_modal_context(
            request,
            payment,
            correction_success="Correction effectuee et caisse synchronisee.",
            correction_old_amount=pending_request.previous_state.get("amount"),
            correction_new_amount=pending_request.requested_state.get("amount"),
            correction_delta=pending_request.requested_state.get("delta"),
        ),
    )
    response["HX-Trigger"] = json.dumps({
        "paymentUpdated": True, "cashBalanceUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": "Paiement corrige avec tracabilite.", "type": "success"},
    })
    return response


@manager_finance_required("validate_payment")
@require_POST
def payment_validate(request: HttpRequest, pk: int) -> HttpResponse:
    try:
        assert_financial_period_open(request.branch, timezone.localdate())
    except ValidationError as exc:
        return HttpResponse(" ".join(exc.messages), status=400)
    with transaction.atomic():
        payment = get_object_or_404(
            scoped(Payment, user=request.user).select_for_update().select_related(
                "inscription__candidature"
            ),
            pk=pk,
            inscription__candidature__branch=request.branch,
            status=Payment.STATUS_PENDING,
        )
        payment.status = Payment.STATUS_VALIDATED
        payment.paid_at = timezone.now()
        payment.save()
        existing_movement = BranchCashMovement.objects.filter(
            branch=request.branch,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference=payment_cash_reference(payment),
        ).first()
        if not existing_movement:
            create_cash_movement(
                branch=request.branch,
                source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
                source_reference=payment_cash_reference(payment),
                movement_type=BranchCashMovement.TYPE_IN,
                amount=payment.amount,
                label=f"Paiement etudiant - {payment.inscription.candidature.full_name}",
                movement_date=payment.paid_at.date(),
                notes=f"Synchronisation automatique paiement #{payment.pk}.",
                created_by=request.user,
            )
        FinancialLog.objects.create(
            branch=request.branch,
            payment=payment,
            action=FinancialLog.ACTION_PAYMENT_VALIDATED,
            new_amount=payment.amount,
            reason="Validation du paiement par la gestionnaire.",
            actor=request.user,
            metadata={"payment_reference": payment.reference, "inscription_id": payment.inscription_id},
        )
    payment.refresh_from_db()
    response = render(
        request,
        "accounts/dashboard/partials/manager_payment_row.html",
        {
            "payment_row": build_payment_table_row(
                payment,
                request.manager_workspace_access.capabilities,
            )
        },
    )
    response["HX-Trigger"] = json.dumps({
        "paymentUpdated": True, "cashBalanceUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": "Paiement valide et caisse creditee.", "type": "success"},
    })
    return response


@manager_finance_required("cancel_payment")
@require_POST
def payment_cancel(request: HttpRequest, pk: int) -> HttpResponse:
    payment = get_object_or_404(
        scoped(Payment, user=request.user),
        pk=pk,
        inscription__candidature__branch=request.branch,
        status=Payment.STATUS_PENDING,
    )
    payment.status = Payment.STATUS_CANCELLED
    payment.save()
    payment.inscription.update_financial_state()
    FinancialLog.objects.create(
        branch=request.branch,
        payment=payment,
        action=FinancialLog.ACTION_PAYMENT_CANCELLED,
        old_amount=payment.amount,
        delta_amount=-payment.amount,
        reason="Annulation du paiement en attente par la gestionnaire.",
        actor=request.user,
        metadata={"payment_reference": payment.reference, "inscription_id": payment.inscription_id},
    )
    payment.refresh_from_db()
    response = render(
        request,
        "accounts/dashboard/partials/manager_payment_row.html",
        {
            "payment_row": build_payment_table_row(
                payment,
                request.manager_workspace_access.capabilities,
            )
        },
    )
    response["HX-Trigger"] = json.dumps({
        "paymentUpdated": True, "cashBalanceUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": "Paiement annule.", "type": "warning"},
    })
    return response
