import json
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.html import conditional_escape
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from accounts.forms import (
    BranchBankTransferForm,
    BranchBankTransferProofForm,
    BranchExpenseForm,
    BranchMonthlyClosureForm,
    DonationForm,
)
from accounts.models import BranchBankTransfer, BranchCashMovement, BranchExpense, BranchMonthlyClosure, Donation
from accounts.services.accounting_documents import (
    create_cash_movement,
    ensure_expense_reference,
)
from accounts.services.financial_integrity import assert_financial_period_open
from accounts.services.manager_intelligence import (
    branch_financial_orphan_report,
    create_validated_bank_transfer,
    get_branch_cash_period_snapshot,
    get_branch_cash_balance,
    lock_branch_cash_balance,
    sync_donation_cash_movement,
)
from accounts.services.wallets import (
    configured_wallet_for_category,
    consume_wallet_for_cash_movement,
    wallet_balance,
)

from accounts.dashboards.htmx_utils import (
    manager_closure_redirect_response,
    manager_required,
    manager_section_notice_redirect_response,
    manager_section_redirect_response,
)


@manager_required
@require_POST
def expense_create(request: HttpRequest) -> HttpResponse:
    form = BranchExpenseForm(request.POST, request.FILES)
    if not form.is_valid():
        response = render(
            request,
            "accounts/dashboard/partials/manager_expense_form.html",
            {"expense_form": form},
        )
        response.status_code = 400
        return response

    try:
        assert_financial_period_open(request.branch, form.cleaned_data["expense_date"])
    except ValidationError as exc:
        return HttpResponse(" ".join(exc.messages), status=400)
    expense = form.save(commit=False)
    expense.branch = request.branch
    expense.created_by = request.user
    expense.status = BranchExpense.STATUS_SUBMITTED
    expense.save()
    ensure_expense_reference(expense)
    return manager_section_redirect_response("depenses")


@manager_required
@require_POST
def expense_approve(request: HttpRequest, pk: int) -> HttpResponse:
    expense = get_object_or_404(BranchExpense, pk=pk, branch=request.branch)
    if not expense.can_be_approved:
        return HttpResponse("Cette depense ne peut pas etre approuvee.", status=400)
    expense.status = BranchExpense.STATUS_APPROVED
    expense.approved_by = request.user
    expense.approved_at = timezone.now()
    expense.save(update_fields=["status", "approved_by", "approved_at", "updated_at"])
    return manager_section_redirect_response("depenses")


@manager_required
@require_POST
def expense_reject(request: HttpRequest, pk: int) -> HttpResponse:
    expense = get_object_or_404(BranchExpense, pk=pk, branch=request.branch)
    if expense.status == BranchExpense.STATUS_PAID:
        return HttpResponse("Une depense deja payee ne peut pas etre rejetee.", status=400)
    expense.status = BranchExpense.STATUS_REJECTED
    expense.save(update_fields=["status", "updated_at"])
    return manager_section_redirect_response("depenses")


@manager_required
@require_POST
def expense_pay(request: HttpRequest, pk: int) -> HttpResponse:
    with transaction.atomic():
        _locked_branch, available_cash = lock_branch_cash_balance(request.branch)
        expense = get_object_or_404(
            BranchExpense.objects.select_for_update(),
            pk=pk,
            branch=request.branch,
        )
        try:
            assert_financial_period_open(request.branch, expense.expense_date)
        except ValidationError as exc:
            return HttpResponse(" ".join(exc.messages), status=400)
        if not expense.can_be_paid:
            return HttpResponse("Cette depense doit etre approuvee avant paiement.", status=400)
        if expense.amount > available_cash:
            return HttpResponse(
                (
                    "<div class='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>"
                    f"Caisse insuffisante pour payer cette depense. Disponible: {available_cash} FCFA."
                    "</div>"
                ),
                status=400,
            )
        expense_wallet = configured_wallet_for_category(request.branch, "expense")
        if expense_wallet and expense.amount > wallet_balance(expense_wallet):
            return HttpResponse(
                (
                    "<div class='rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700'>"
                    f"La mini-caisse Dépenses est insuffisante. Disponible : {wallet_balance(expense_wallet)} FCFA."
                    "</div>"
                ),
                status=400,
            )
        expense.status = BranchExpense.STATUS_PAID
        expense.paid_by = request.user
        expense.paid_at = timezone.now()
        expense.save(update_fields=["status", "paid_by", "paid_at", "updated_at"])
        ensure_expense_reference(expense)
        cash_movement = create_cash_movement(
            branch=request.branch,
            movement_type=BranchCashMovement.TYPE_OUT,
            source=BranchCashMovement.SOURCE_EXPENSE,
            amount=expense.amount,
            label=expense.title,
            movement_date=expense.expense_date,
            expense=expense,
            source_reference=expense.reference,
            notes=expense.notes,
            created_by=request.user,
        )
        if expense_wallet:
            consume_wallet_for_cash_movement(
                wallet=expense_wallet,
                cash_movement=cash_movement,
                actor=request.user,
                label="Paiement de dépense",
                notes=expense.reference,
            )
    response = manager_section_redirect_response("depenses")
    response["HX-Trigger"] = json.dumps({"cashBalanceUpdated": True, "dashboardStatsUpdated": True})
    return response


@manager_required
@require_POST
def monthly_closure_create(request: HttpRequest) -> HttpResponse:
    closure_form = BranchMonthlyClosureForm(request.POST)
    available_cash_balance = get_branch_cash_balance(request.branch)
    if not closure_form.is_valid():
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "available_cash_balance": available_cash_balance,
                "transfer_form": BranchBankTransferForm(initial={"transfer_date": timezone.localdate()}, available_cash_balance=available_cash_balance),
                "closure_error": "Verifiez les champs du formulaire de cloture.",
            },
        )
        response.status_code = 400
        return response

    period_month = closure_form.cleaned_data["period_month"].replace(day=1)

    orphan_report = branch_financial_orphan_report(request.branch, period_month)
    if any(orphan_report.values()):
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "transfer_form": BranchBankTransferForm(initial={"transfer_date": timezone.localdate()}, available_cash_balance=available_cash_balance),
                "available_cash_balance": available_cash_balance,
                "closure_error": _format_financial_orphan_message(orphan_report),
                "report_closure_blockers": [_format_financial_orphan_message(orphan_report)],
            },
        )
        response.status_code = 400
        return response

    existing_closure = BranchMonthlyClosure.objects.filter(
        branch=request.branch, period_month=period_month,
    ).first()
    if existing_closure and existing_closure.status != BranchMonthlyClosure.STATUS_DRAFT:
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "transfer_form": BranchBankTransferForm(initial={"transfer_date": timezone.localdate()}, available_cash_balance=get_branch_cash_balance(request.branch)),
                "available_cash_balance": get_branch_cash_balance(request.branch),
                "closure_error": "Cette periode est deja validee ou cloturee. Elle ne peut plus etre modifiee.",
            },
        )
        response.status_code = 400
        return response

    snapshot = get_branch_cash_period_snapshot(request.branch, period_month)
    physical_count = closure_form.cleaned_data["physical_cash_count"]
    difference = physical_count - snapshot["theoretical_cash_balance"]
    justification = (closure_form.cleaned_data.get("difference_justification") or "").strip()
    if difference and not justification:
        closure_form.add_error(
            "difference_justification",
            "Une justification est obligatoire lorsqu'un écart de caisse est constaté.",
        )
        response = render(
            request,
            "accounts/dashboard/partials/monthly_closure_form.html",
            {
                "closure_form": closure_form,
                "transfer_form": BranchBankTransferForm(initial={"transfer_date": timezone.localdate()}, available_cash_balance=available_cash_balance),
                "available_cash_balance": available_cash_balance,
                "closure_error": "Le comptage physique doit être expliqué lorsqu'il diffère du solde théorique.",
            },
        )
        response.status_code = 400
        return response

    with transaction.atomic():
        locked_branch, _balance = lock_branch_cash_balance(request.branch)
        snapshot = get_branch_cash_period_snapshot(locked_branch, period_month)
        difference = physical_count - snapshot["theoretical_cash_balance"]
        closure, created = BranchMonthlyClosure.objects.select_for_update().get_or_create(
            branch=locked_branch,
            period_month=period_month,
            defaults={"created_by": request.user},
        )
        if not created and closure.status != BranchMonthlyClosure.STATUS_DRAFT:
            return HttpResponse("Cette période est déjà validée ou clôturée.", status=400)
        for field, value in snapshot.items():
            setattr(closure, field, value)
        closure.physical_cash_count = physical_count
        closure.cash_difference = difference
        closure.difference_justification = justification
        closure.notes = closure_form.cleaned_data.get("notes", "")
        closure.counted_by = request.user
        closure.counted_at = timezone.now()
        closure.status = BranchMonthlyClosure.STATUS_DRAFT
        closure.save()

    return manager_closure_redirect_response(period_month)


@manager_required
@require_POST
def bank_transfer_create(request: HttpRequest) -> HttpResponse:
    form = BranchBankTransferForm(request.POST, request.FILES)
    if not form.is_valid():
        return _bank_transfer_error_response(request,
            "Versement bancaire invalide : vérifiez les champs obligatoires.",
            status=400,
        )
    try:
        from core.models import Institution

        institution = Institution.objects.filter(is_active=True).only("country").first()
        transfer, created = create_validated_bank_transfer(
            branch=request.branch,
            actor=request.user,
            bank_name=form.cleaned_data["bank_name"],
            bank_country=institution.country if institution and institution.country else "Mali",
            transfer_date=form.cleaned_data["transfer_date"],
            amount=form.cleaned_data["amount"],
            proof=form.cleaned_data.get("proof"),
            comment=form.cleaned_data.get("comment", ""),
            idempotency_key=form.cleaned_data.get("request_token", ""),
        )
    except ValidationError as exc:
        return _bank_transfer_error_response(request, " ".join(exc.messages), status=400)
    if not _is_htmx(request):
        messages.success(
            request,
            f"Versement bancaire enregistré sous la référence {transfer.reference}.",
        )
        return redirect(_manager_closure_url())
    # The closure subcontent opts into this canonical HTMX refresh.  Returning
    # no fragment here preserves the form until the server-rendered refresh
    # replaces the whole closure region with the new table and balance.
    response = HttpResponse("")
    response["HX-Reswap"] = "none"
    response["HX-Trigger"] = json.dumps({
        "ui:toast": {"message": (f"Versement bancaire {transfer.reference} enregistré." if created else f"Versement {transfer.reference} déjà enregistré."), "tone": "success" if created else "info"},
        "ui:invalidate": {"topics": ["cash", "closures"]},
        "cashBalanceUpdated": True,
        "dashboardStatsUpdated": True,
    })
    return response


@manager_required
@require_POST
def bank_transfer_proof_upload(request: HttpRequest, pk: int) -> HttpResponse:
    """Attach the bank-issued proof without altering a validated cash operation."""

    transfer = get_object_or_404(
        BranchBankTransfer.objects,
        pk=pk,
        branch=request.branch,
    )
    if transfer.status != BranchBankTransfer.STATUS_VALIDATED:
        return _bank_transfer_error_response(
            request,
            "Le justificatif ne peut être ajouté que sur un versement validé.",
            status=400,
            target=f"#bank-transfer-proof-feedback-{transfer.pk}",
        )
    if transfer.proof:
        return _bank_transfer_error_response(
            request,
            "Un justificatif bancaire est déjà conservé pour ce versement.",
            status=400,
            target=f"#bank-transfer-proof-feedback-{transfer.pk}",
        )
    form = BranchBankTransferProofForm(request.POST, request.FILES, instance=transfer)
    if not form.is_valid():
        return _bank_transfer_error_response(
            request,
            "Ajoutez un justificatif bancaire PDF ou image valide.",
            status=400,
            target=f"#bank-transfer-proof-feedback-{transfer.pk}",
        )
    with transaction.atomic():
        transfer = BranchBankTransfer.objects.select_for_update().get(pk=transfer.pk)
        if transfer.proof:
            return _bank_transfer_error_response(
                request,
                "Un justificatif bancaire est déjà conservé pour ce versement.",
                status=400,
                target=f"#bank-transfer-proof-feedback-{transfer.pk}",
            )
        transfer.proof = form.cleaned_data["proof"]
        transfer.proof_uploaded_by = request.user
        transfer.proof_uploaded_at = timezone.now()
        transfer.save(update_fields=["proof", "proof_uploaded_by", "proof_uploaded_at", "updated_at"])
    if not _is_htmx(request):
        messages.success(request, f"Justificatif bancaire ajouté pour {transfer.reference}.")
        return redirect(_manager_closure_url())
    response = HttpResponse("")
    response["HX-Reswap"] = "none"
    response["HX-Trigger"] = json.dumps({
        "ui:toast": {"message": f"Justificatif bancaire ajouté pour {transfer.reference}.", "tone": "success"},
        "ui:invalidate": {"topics": ["closures"]},
    })
    return response


def _is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request", "").lower() == "true"


def _manager_closure_url() -> str:
    return f"{reverse('accounts:manager_dashboard')}?section=cloture&view=archives"


def _bank_transfer_error_response(request: HttpRequest, message: str, *, status: int, target="#bank-transfer-feedback") -> HttpResponse:
    if not _is_htmx(request):
        messages.error(request, message)
        return redirect(_manager_closure_url())
    return _bank_transfer_feedback_response(message, status=status, target=target)


def _bank_transfer_feedback_response(message: str, *, status: int, target="#bank-transfer-feedback") -> HttpResponse:
    """Display a local error without replacing the active closure workspace."""
    response = HttpResponse(
        (
            f'<p id="{conditional_escape(target.removeprefix("#"))}" class="rounded-ui-card border border-ui-danger/30 '
            'bg-ui-danger-soft px-3 py-2 text-sm text-ui-danger" role="alert">'
            f"{conditional_escape(message)}"
            "</p>"
        ),
        status=status,
    )
    response["HX-Retarget"] = target
    response["HX-Reswap"] = "outerHTML"
    response["HX-Trigger"] = json.dumps({
        "ui:toast": {"message": message, "tone": "danger"},
    })
    return response


@manager_required
@require_POST
def monthly_closure_validate(request: HttpRequest, pk: int) -> HttpResponse:
    closure = get_object_or_404(BranchMonthlyClosure, pk=pk, branch=request.branch)
    if closure.status != BranchMonthlyClosure.STATUS_DRAFT:
        return manager_section_notice_redirect_response("cloture", "cloture_non_brouillon")
    orphan_report = branch_financial_orphan_report(request.branch, closure.period_month)
    if any(orphan_report.values()):
        return HttpResponse(_format_financial_orphan_message(orphan_report), status=400)
    if closure.physical_cash_count is None:
        return HttpResponse("Clôture impossible : le comptage physique est obligatoire.", status=400)
    if closure.cash_difference and not closure.difference_justification.strip():
        return HttpResponse("Clôture impossible : justifiez l'écart de caisse.", status=400)
    current_snapshot = get_branch_cash_period_snapshot(request.branch, closure.period_month)
    if current_snapshot["theoretical_cash_balance"] < 0:
        return HttpResponse("Cloture impossible: la caisse de l'annexe est negative.", status=400)
    if current_snapshot["theoretical_cash_balance"] != closure.theoretical_cash_balance:
        return HttpResponse(
            "Clôture impossible : le grand livre a changé depuis le comptage. Préparez à nouveau la clôture.",
            status=400,
        )

    closure.status = BranchMonthlyClosure.STATUS_VALIDATED
    closure.validated_by = request.user
    closure.validated_at = timezone.now()
    closure.save(update_fields=["status", "validated_by", "validated_at", "updated_at"])

    return manager_closure_redirect_response(closure.period_month)


@manager_required
@require_POST
def monthly_closure_close(request: HttpRequest, pk: int) -> HttpResponse:
    closure = get_object_or_404(BranchMonthlyClosure, pk=pk, branch=request.branch)
    if closure.status != BranchMonthlyClosure.STATUS_VALIDATED:
        return manager_section_notice_redirect_response("cloture", "cloture_non_validee")
    orphan_report = branch_financial_orphan_report(request.branch, closure.period_month)
    if any(orphan_report.values()):
        return HttpResponse(_format_financial_orphan_message(orphan_report), status=400)
    if closure.theoretical_cash_balance < 0:
        return HttpResponse("Cloture impossible: la caisse de l'annexe est negative.", status=400)

    closure.status = BranchMonthlyClosure.STATUS_CLOSED
    closure.closed_at = timezone.now()
    closure.save(update_fields=["status", "closed_at", "updated_at"])

    return manager_closure_redirect_response(closure.period_month)


@manager_required
@require_POST
def donation_create(request: HttpRequest) -> HttpResponse:
    form = DonationForm(request.POST)
    if not form.is_valid():
        return render(
            request,
            "accounts/dashboard/partials/donation_form.html",
            {"donation_form": form},
        )

    with transaction.atomic():
        donation = form.save(commit=False)
        donation.branch = request.branch
        donation.created_by = request.user
        donation.save()
        sync_donation_cash_movement(donation, user=request.user)

    response = render(
        request,
        "accounts/dashboard/partials/donation_row.html",
        {"donation": donation},
    )
    response["HX-Trigger"] = json.dumps({
        "cashBalanceUpdated": True, "dashboardStatsUpdated": True,
        "showToast": {"message": f"Don de {donation.donor_name} enregistre ({donation.amount:,} FCFA).", "type": "success"},
    })
    return response


def _format_financial_orphan_message(orphan_report: dict[str, list]) -> str:
    labels = {
        "payments": "paiement(s) etudiant valide(s) sans mouvement de caisse",
        "shop_payments": "paiement(s) boutique valide(s) sans mouvement de caisse",
        "donations": "don(s) sans mouvement de caisse",
        "expenses": "depense(s) payee(s) sans mouvement de caisse",
        "payroll_entries": "fiche(s) de paie payee(s) ou partielle(s) sans mouvement de caisse",
        "honorarium_entries": "honoraire(s) enseignant(s) paye(s) ou partiel(s) sans mouvement de caisse",
        "bank_transfers": "versement(s) bancaire(s) sans mouvement de sortie",
    }
    pieces = [
        f"{len(items)} {labels[key]}"
        for key, items in orphan_report.items()
        if items
    ]
    return "Cloture bloquee : " + "; ".join(pieces) + "."
