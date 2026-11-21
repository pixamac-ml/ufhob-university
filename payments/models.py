from django.db import models, transaction
from django.utils import timezone
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.contrib.auth import get_user_model

from branches.models import Branch
from accounts.models import FinancialAuditLog, SchoolFinanceManager
from inscriptions.models import Inscription

from payments.services.receipt import generate_receipt_number
from payments.services.qrcode import generate_qr_image
from core.pdf_documents import generate_pdf as generate_esfe_pdf

from students.services.create_student import create_student_after_first_payment
from students.services.email import (
    send_student_credentials_email,
    send_payment_confirmation_email
)
from payments.services.workflows import run_first_payment_validated_workflow

import secrets
import random
from datetime import timedelta

User = get_user_model()


# ==================================================
# PAYMENT AGENT
# ==================================================

class PaymentAgent(models.Model):

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        limit_choices_to={"is_staff": True},
        related_name="payment_agent_profile"
    )

    agent_code = models.CharField(
        max_length=8,
        unique=True,
        editable=False,
        db_index=True
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        related_name="payment_agents",
        db_index=True
    )

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["user__last_name"]

        indexes = [
            models.Index(fields=["branch"]),
            models.Index(fields=["is_active"]),
        ]

    def save(self, *args, **kwargs):

        if not self.agent_code:
            self.agent_code = secrets.token_hex(3).upper()

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.agent_code})"


# ==================================================
# CASH PAYMENT SESSION
# ==================================================

class CashPaymentSession(models.Model):

    inscription = models.ForeignKey(
        Inscription,
        on_delete=models.CASCADE,
        related_name="cash_sessions",
        db_index=True
    )

    agent = models.ForeignKey(
        PaymentAgent,
        on_delete=models.PROTECT,
        related_name="cash_sessions",
        db_index=True
    )

    verification_code = models.CharField(max_length=6)

    expires_at = models.DateTimeField(db_index=True)

    is_used = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

        indexes = [
            models.Index(fields=["expires_at"]),
            models.Index(fields=["is_used"]),
            models.Index(fields=["agent", "created_at"]),
        ]

    def generate_code(self):

        self.verification_code = str(random.randint(100000, 999999))

        self.expires_at = timezone.now() + timedelta(minutes=5)

        self.save(update_fields=["verification_code", "expires_at"])

    def is_valid(self, code):

        return (
            not self.is_used
            and self.verification_code == code
            and timezone.now() <= self.expires_at
        )

    def __str__(self):
        return f"Session cash {self.inscription.reference}"


# ==================================================
# PAYMENT
# ==================================================

class Payment(models.Model):

    METHOD_CASH = "cash"
    METHOD_ORANGE = "orange_money"
    METHOD_BANK = "bank_transfer"

    METHOD_CHOICES = (
        (METHOD_CASH, "Espèces"),
        (METHOD_ORANGE, "Orange Money"),
        (METHOD_BANK, "Virement bancaire"),
    )

    STATUS_PENDING = "pending"
    STATUS_VALIDATED = "validated"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = (
        (STATUS_PENDING, "En attente"),
        (STATUS_VALIDATED, "Validé"),
        (STATUS_CANCELLED, "Annulé"),
    )

    inscription = models.ForeignKey(
        Inscription,
        on_delete=models.CASCADE,
        related_name="payments",
        db_index=True
    )

    agent = models.ForeignKey(
        PaymentAgent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments"
    )

    cash_session = models.ForeignKey(
        CashPaymentSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )

    amount = models.PositiveBigIntegerField()

    method = models.CharField(
        max_length=30,
        choices=METHOD_CHOICES,
        db_index=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True
    )

    reference = models.CharField(
        max_length=100,
        blank=True,
        db_index=True
    )

    receipt_number = models.CharField(
        max_length=50,
        unique=True,
        null=True,
        blank=True
    )

    receipt_pdf = models.FileField(
        upload_to="payments/receipts/",
        null=True,
        blank=True
    )

    paid_at = models.DateTimeField(default=timezone.now, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        ordering = ["-paid_at"]

        indexes = [

            models.Index(fields=["paid_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["method"]),

            # dashboards financiers
            models.Index(fields=["status", "paid_at"]),
            models.Index(fields=["method", "paid_at"]),
            models.Index(fields=["inscription", "status"]),

        ]

    def __str__(self):
        return f"{self.amount} FCFA – {self.inscription.reference}"

    @property
    def public_reference(self):
        """Institutional display reference, independent from the internal key."""
        return f"UFHOB-PAY-{self.paid_at.year}-{self.pk:06d}"

    @property
    def public_receipt_reference(self):
        return f"UFHOB-REC-{self.paid_at.year}-{self.pk:06d}"

    # ==================================================
    # VALIDATION MÉTIER
    # ==================================================

    def clean(self):

        if self.amount <= 0:
            raise ValidationError("Le montant doit être supérieur à zéro.")

        inscription = self.inscription

        if inscription.status in ["cancelled", "expired"]:
            raise ValidationError(
                "Impossible de payer une inscription annulée ou expirée."
            )

        if inscription.status == "completed":
            raise ValidationError(
                "L'inscription est déjà terminée."
            )

        total_paid = (
            inscription.payments
            .filter(status=self.STATUS_VALIDATED)
            .aggregate(total=Sum("amount"))["total"]
            or 0
        )

        if self.status == self.STATUS_VALIDATED:

            future_total = total_paid + self.amount

            # protection surpaiement extrême
            if future_total > inscription.amount_due * 2:
                raise ValidationError(
                    "Montant incohérent détecté."
                )

    # ==================================================
    # PIPELINE MÉTIER
    # ==================================================

    def save(self, *args, **kwargs):

        previous_status = None

        if self.pk:

            previous_status = (
                Payment.objects.only("status")
                .get(pk=self.pk)
                .status
            )

            if previous_status == self.STATUS_VALIDATED:
                raise ValueError(
                    "Un paiement validé ne peut plus être modifié."
                )

        if not self.reference:
            self.reference = f"PAY-{secrets.token_hex(4).upper()}"

        self.full_clean()

        with transaction.atomic():

            inscription = (
                Inscription.objects
                .select_for_update()
                .get(pk=self.inscription_id)
            )

            super().save(*args, **kwargs)

            just_validated = (
                self.status == self.STATUS_VALIDATED
                and previous_status != self.STATUS_VALIDATED
            )

            if not just_validated:
                return

            # ==================================================
            # MISE À JOUR FINANCIÈRE
            # ==================================================

            inscription.update_financial_state()

            # A validated payment changes both the financial state of the
            # dossier and the governance view.  Keep this trace in the
            # existing immutable financial audit log, using the academic
            # context already carried by the payment dossier.
            candidature = inscription.candidature
            programme = candidature.programme
            school = getattr(programme, "school", None)
            FinancialAuditLog.objects.create(
                branch=candidature.branch,
                action_type="payment_validated",
                target_model="payments.payment",
                target_id=self.pk,
                previous_state={"status": previous_status or self.STATUS_PENDING},
                new_state={
                    "status": self.STATUS_VALIDATED,
                    "amount": self.amount,
                    "academic_year": candidature.academic_year,
                    "school_id": school.pk if school else None,
                    "branch_id": candidature.branch_id,
                    "programme_id": programme.pk if programme else None,
                    "inscription_reference": inscription.public_reference,
                    "payment_reference": self.public_reference,
                },
                performed_by=self.agent.user if self.agent_id else None,
            )

            # ==================================================
            # GÉNÉRATION REÇU
            # ==================================================

            if not self.receipt_number:

                self.receipt_number = generate_receipt_number(self)

                cand = candidature
                programme = cand.programme
                school_obj = getattr(programme, "school", None)
                student = getattr(inscription, "student", None)

                pdf_bytes = generate_esfe_pdf("esfe_receipt", {
                    "document_context": inscription,
                    "school_object": school_obj,
                    "branch": cand.branch,
                    "programme_object": programme,
                    "academic_year_object": cand.academic_year,
                    "receipt_number": self.receipt_number,
                    "public_receipt_reference": self.public_receipt_reference,
                    "public_payment_reference": self.public_reference,
                    "date": self.paid_at.strftime("%d %B %Y"),
                    "academic_year": cand.academic_year,
                    "student_name": f"{cand.last_name} {cand.first_name}",
                    "student_matricule": getattr(student, "matricule", ""),
                    "programme": programme.title if programme else "",
                    "school": getattr(school_obj, "code", ""),
                    "school_name": getattr(school_obj, "official_name", ""),
                    "institution": getattr(school_obj, "institution", None),
                    "branch_name": getattr(cand.branch, "name", ""),
                    "level": inscription.academic_level or getattr(getattr(programme, "cycle", None), "name", ""),
                    "cycle_name": getattr(getattr(programme, "cycle", None), "name", ""),
                    "agent_name": self.agent.user.get_full_name() if self.agent_id else "",
                    "items": [
                        {
                            "label": "Versement sur frais d'inscription",
                            "quantity": "1",
                            "unit_price": f"{self.amount:,}".replace(",", " "),
                            "total": f"{self.amount:,} FCFA".replace(",", " "),
                        },
                    ],
                    "total_amount": f"{self.amount:,}".replace(",", " "),
                    "operation_amount": f"{self.amount:,}".replace(",", " "),
                    "amount_paid": f"{inscription.amount_paid:,}".replace(",", " "),
                    "balance_amount": f"{inscription.balance:,}".replace(",", " "),
                    "payment_method": self.get_method_display() if hasattr(self, "get_method_display") else "",
                    "payment_reference": self.reference or "",
                })

                self.receipt_pdf.save(
                    f"receipt-{self.receipt_number}.pdf",
                    ContentFile(pdf_bytes),
                    save=False
                )

                super().save(
                    update_fields=["receipt_number", "receipt_pdf"]
                )

        transaction.on_commit(
            lambda: self._post_commit_actions()
        )

    # ==================================================
    # ACTIONS APRÈS COMMIT
    # ==================================================

    def _post_commit_actions(self):

        result = create_student_after_first_payment(self.inscription)

        if result and result.get("created") and result.get("password"):

            send_student_credentials_email(
                student=result["student"],
                raw_password=result["password"]
            )

        else:

            send_payment_confirmation_email(payment=self)

        run_first_payment_validated_workflow(
            payment=self,
            student_result=result,
        )


class PaymentCorrection(models.Model):
    payment = models.ForeignKey(
        Payment,
        on_delete=models.PROTECT,
        related_name="corrections",
        db_index=True,
    )
    old_amount = models.PositiveBigIntegerField()
    new_amount = models.PositiveBigIntegerField()
    delta_amount = models.BigIntegerField()
    reason = models.TextField()
    corrected_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_corrections",
    )
    corrected_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-corrected_at"]
        indexes = [
            models.Index(fields=["payment", "corrected_at"]),
            models.Index(fields=["corrected_by", "corrected_at"]),
        ]

    def __str__(self):
        return f"Correction paiement #{self.payment_id}: {self.old_amount} -> {self.new_amount}"


class FinancialLog(models.Model):
    ACTION_PAYMENT_CREATED = "payment_created"
    ACTION_PAYMENT_VALIDATED = "payment_validated"
    ACTION_PAYMENT_CANCELLED = "payment_cancelled"
    ACTION_PAYMENT_CORRECTED = "payment_corrected"
    ACTION_EXPENSE = "expense"
    ACTION_EXPORT = "export"
    ACTION_PRINT = "print"
    ACTION_COUPON_APPLIED = "coupon_applied"

    ACTION_CHOICES = (
        (ACTION_PAYMENT_CREATED, "Paiement cree"),
        (ACTION_PAYMENT_VALIDATED, "Paiement valide"),
        (ACTION_PAYMENT_CANCELLED, "Paiement annule"),
        (ACTION_PAYMENT_CORRECTED, "Paiement corrige"),
        (ACTION_EXPENSE, "Depense"),
        (ACTION_EXPORT, "Export"),
        (ACTION_PRINT, "Impression"),
        (ACTION_COUPON_APPLIED, "Coupon applique"),
    )

    branch = models.ForeignKey(
        Branch,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="financial_logs",
        db_index=True,
    )
    # T6 caisse par école : nullable le temps de la répartition
    # (manage.py attribuer_ecole_finance), à rendre obligatoire ensuite.
    school = models.ForeignKey(
        "core.School",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
        db_index=True,
        verbose_name="École",
    )
    payment = models.ForeignKey(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_logs",
    )
    correction = models.ForeignKey(
        PaymentCorrection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_logs",
    )
    action = models.CharField(max_length=40, choices=ACTION_CHOICES, db_index=True)
    old_amount = models.PositiveBigIntegerField(null=True, blank=True)
    new_amount = models.PositiveBigIntegerField(null=True, blank=True)
    delta_amount = models.BigIntegerField(default=0)
    reason = models.TextField(blank=True)
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="financial_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)

    objects = SchoolFinanceManager()
    all_objects = models.Manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["payment", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_action_display()} - {self.created_at:%Y-%m-%d %H:%M}"
