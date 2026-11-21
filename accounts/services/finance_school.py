"""T6 — caisse par école : déduire l'école d'un enregistrement financier.

Un seul résolveur sert à deux moments :
- à la création (signal pre_save, voir ``accounts/signals_finance_school.py``) ;
- à la répartition de l'existant (``manage.py attribuer_ecole_finance``).

Ordre de priorité : l'enregistrement métier lié (paiement, salarié,
dépense, clôture…) > l'école de la navigation courante (requête) > l'école
du compte qui agit. Rien n'est inventé : si aucune source n'est sûre, le
résultat est ``None`` et la ligne reste à répartir à la main.
"""

from __future__ import annotations

import re

FINANCE_SCHOOL_MODELS = (
    "accounts.SensitiveActionRequest",
    "accounts.FinancialAuditLog",
    "accounts.PayrollEntry",
    "accounts.BranchExpense",
    "accounts.BranchCashMovement",
    "accounts.BranchCashRegisterSession",
    "accounts.BranchWallet",
    "accounts.AccountingDocumentSequence",
    "accounts.TeacherHonorariumEntry",
    "accounts.PaymentSignatureSession",
    "accounts.BranchMonthlyClosure",
    "accounts.BranchBankTransfer",
    "accounts.Donation",
    "payments.FinancialLog",
)


def _school_id_of_user(user):
    if user is None or not getattr(user, "pk", None):
        return None
    from accounts.models import InstitutionalProfile

    return (
        InstitutionalProfile.objects.filter(user_id=user.pk)
        .values_list("school_id", flat=True)
        .first()
    )


def _school_id_of_inscription_id(inscription_id):
    if not inscription_id:
        return None
    from inscriptions.models import Inscription

    return (
        Inscription.objects.filter(pk=inscription_id)
        .values_list("candidature__programme__school_id", flat=True)
        .first()
    )


def _school_id_of_payment(payment):
    if payment is None:
        return None
    return _school_id_of_inscription_id(getattr(payment, "inscription_id", None))


def context_school_id():
    """École sélectionnée dans le contexte de la requête en cours, s'il y en a un."""
    from accounts.scoping import _request_context

    context = _request_context.get()
    school = getattr(context, "school", None) if context is not None else None
    return getattr(school, "pk", None)


def _related_school_id(instance, field):
    if not getattr(instance, f"{field}_id", None):
        return None
    related = getattr(instance, field, None)
    return getattr(related, "school_id", None)


def _movement_reference_school_id(movement):
    """École d'un mouvement de caisse d'après sa référence source."""
    from accounts.models import (
        BranchBankTransfer,
        BranchCashMovement,
        BranchExpense,
        Donation,
        PayrollEntry,
        TeacherHonorariumEntry,
    )

    ref = (movement.source_reference or "").strip()
    source = movement.source
    if movement.expense_id:
        school_id = _related_school_id(movement, "expense")
        if school_id:
            return school_id
    if not ref:
        return None
    if source == BranchCashMovement.SOURCE_STUDENT_PAYMENT:
        from payments.models import Payment

        payment = None
        match = re.fullmatch(r"PAY-(\d+)", ref)
        if match:
            payment = Payment.objects.filter(pk=int(match.group(1))).first()
        if payment is None:
            payment = Payment.objects.filter(reference=ref).first()
        return _school_id_of_payment(payment)
    if source == BranchCashMovement.SOURCE_SHOP:
        from shop.models import ShopPayment

        match = re.fullmatch(r"shop_payment:(\d+)", ref)
        qs = ShopPayment.objects.filter(pk=int(match.group(1))) if match else ShopPayment.objects.filter(reference=ref)
        inscription_id = qs.values_list("order__inscription_id", flat=True).first()
        return _school_id_of_inscription_id(inscription_id)
    simple = {
        BranchCashMovement.SOURCE_DONATION: (r"donation:(\d+)", Donation),
        BranchCashMovement.SOURCE_BANK_TRANSFER: (r"bank_transfer:(\d+)", BranchBankTransfer),
        BranchCashMovement.SOURCE_EXPENSE: (r"expense:(\d+)", BranchExpense),
        BranchCashMovement.SOURCE_PAYROLL: (r"PAYROLL-(\d+)(?:-\d+)?", PayrollEntry),
        BranchCashMovement.SOURCE_HONORARIUM: (r"HON-(\d+)(?:-\d+)?", TeacherHonorariumEntry),
    }
    if source in simple:
        pattern, model = simple[source]
        match = re.fullmatch(pattern, ref)
        qs = model._base_manager.filter(pk=int(match.group(1))) if match else None
        if qs is None and model is BranchExpense:
            qs = BranchExpense._base_manager.filter(reference=ref)
        if qs is not None:
            return qs.values_list("school_id", flat=True).first()
    return None


def _target_school_id(instance):
    """Pour les demandes sensibles / journaux : école de l'objet visé."""
    from django.apps import apps

    label = (getattr(instance, "target_model", "") or "").strip()
    target_id = getattr(instance, "target_id", None)
    if not label or not target_id:
        return None
    try:
        model = apps.get_model(label) if "." in label else apps.get_model("accounts", label)
    except (LookupError, ValueError):
        return None
    try:
        target = model._base_manager.filter(pk=target_id).first()
    except (ValueError, TypeError):
        return None
    if target is None:
        return None
    if hasattr(target, "school_id") and model._meta.label_lower != "core.school":
        return target.school_id
    if model._meta.label_lower == "payments.payment":
        return _school_id_of_payment(target)
    return None


def record_school_id(instance):
    """École déduite de l'enregistrement lui-même (sans contexte ni acteur)."""
    label = instance._meta.label_lower
    if label == "accounts.branchcashmovement":
        return _movement_reference_school_id(instance)
    if label == "accounts.payrollentry":
        return _school_id_of_user(instance.employee) if instance.employee_id else None
    # Honoraires : un enseignant peut servir deux écoles ; l'école vient du
    # contexte de la gestionnaire, son école de rattachement n'est qu'un repli.
    if label == "accounts.paymentsignaturesession":
        return (
            _related_school_id(instance, "payroll_entry")
            or _related_school_id(instance, "honorarium_entry")
            or _related_school_id(instance, "cash_movement")
        )
    if label == "accounts.donation":
        return _related_school_id(instance, "cash_movement")
    if label == "accounts.branchbanktransfer":
        return _related_school_id(instance, "closure")
    if label == "accounts.financialauditlog":
        return _related_school_id(instance, "sensitive_action_request") or _target_school_id(instance)
    if label == "accounts.sensitiveactionrequest":
        return _target_school_id(instance)
    if label == "payments.financiallog":
        if instance.payment_id:
            return _school_id_of_payment(instance.payment)
        return _school_id_of_inscription_id(getattr(instance, "inscription_id", None))
    return None


ACTOR_FIELDS = {
    "accounts.sensitiveactionrequest": ("requested_by",),
    "accounts.financialauditlog": ("performed_by",),
    "accounts.payrollentry": ("created_by",),
    "accounts.branchexpense": ("created_by",),
    "accounts.branchcashmovement": ("created_by",),
    "accounts.branchcashregistersession": ("opened_by",),
    "accounts.branchwallet": ("created_by",),
    "accounts.teacherhonorariumentry": ("created_by",),
    "accounts.paymentsignaturesession": ("created_by",),
    "accounts.branchmonthlyclosure": ("created_by",),
    "accounts.branchbanktransfer": ("created_by",),
    "accounts.donation": ("created_by",),
    "payments.financiallog": ("actor",),
}

# L'école portée par le compte d'un acteur n'est fiable que s'il exerce dans
# le campus de l'enregistrement (une gestionnaire d'école, par ex.).
def _actor_school_id(instance):
    for field in ACTOR_FIELDS.get(instance._meta.label_lower, ()):
        user = getattr(instance, field, None) if getattr(instance, f"{field}_id", None) else None
        school_id = _school_id_of_user(user)
        if school_id and _school_on_branch(school_id, instance.branch_id):
            return school_id
    return None


def _school_on_branch(school_id, branch_id):
    if not school_id:
        return False
    if not branch_id:
        return True
    from core.models import SchoolBranch

    return SchoolBranch.objects.filter(school_id=school_id, branch_id=branch_id).exists()


def resolve_finance_school_id(instance, *, use_context=True, use_actor=True):
    """École à écrire sur ``instance`` ; ``None`` si rien de sûr."""
    if getattr(instance, "school_id", None):
        return instance.school_id
    school_id = record_school_id(instance)
    if school_id and _school_on_branch(school_id, getattr(instance, "branch_id", None)):
        return school_id
    if use_context:
        school_id = context_school_id()
        if school_id and _school_on_branch(school_id, getattr(instance, "branch_id", None)):
            return school_id
    if use_actor:
        school_id = _actor_school_id(instance)
        if school_id:
            return school_id
    if instance._meta.label_lower == "accounts.teacherhonorariumentry" and instance.teacher_id:
        school_id = _school_id_of_user(instance.teacher)
        if _school_on_branch(school_id, instance.branch_id):
            return school_id
    return None
