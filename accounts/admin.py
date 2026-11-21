from django.contrib import admin

from accounts.models import (
    AccountingDocumentSequence,
    BranchBankTransfer,
    BranchCashMovement,
    BranchCashRegisterSession,
    BranchExpense,
    BranchMonthlyClosure,
    Donation,
    FinancialAuditLog,
    PayrollEntry,
    PaymentSignatureSession,
    Profile,
    SensitiveActionRequest,
    TeacherHonorariumEntry,
)


class SchoolFinanceAdminMixin:
    """T6 : l'admin d'un superutilisateur voit toutes les écoles.

    Le manager par défaut des modèles de caisse filtre par l'école du contexte
    d'accès ; un superutilisateur rattaché à une école ne doit pas perdre la
    vue complète dans l'admin (listes, fiches, autocomplétion).
    """

    def get_queryset(self, request):
        manager = getattr(self.model, "all_objects", None)
        if manager is None or not getattr(request.user, "is_superuser", False):
            return super().get_queryset(request)
        queryset = manager.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            queryset = queryset.order_by(*ordering)
        return queryset


@admin.register(PaymentSignatureSession)
class PaymentSignatureSessionAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("id", "payment_type", "beneficiary", "branch", "school", "amount", "status", "expires_at", "signed_at", "completed_at")
    list_filter = ("branch", "school", "payment_type", "status")
    search_fields = ("beneficiary__username", "beneficiary__email", "token_hash")
    readonly_fields = ("token_hash", "signature_sha256", "signature_data", "created_at", "updated_at")
    autocomplete_fields = ("branch", "school", "beneficiary", "payroll_entry", "honorarium_entry", "created_by", "approved_by", "cash_movement")


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "position", "branch", "user_type", "salary_base", "teacher_hourly_rate", "employment_status", "is_public", "updated_at")
    list_filter = ("role", "position", "branch", "user_type", "employment_status", "is_public")
    search_fields = ("user__username", "user__first_name", "user__last_name", "user__email")
    autocomplete_fields = ("user", "branch")


@admin.register(PayrollEntry)
class PayrollEntryAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("employee", "branch", "school", "period_month", "base_salary", "paid_amount", "status", "paid_at")
    list_filter = ("branch", "school", "status", "period_month")
    search_fields = ("employee__username", "employee__first_name", "employee__last_name", "employee__email")
    autocomplete_fields = ("employee", "branch", "created_by", "updated_by")


@admin.register(BranchExpense)
class BranchExpenseAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("title", "branch", "school", "category", "amount", "expense_date", "status", "paid_at")
    list_filter = ("branch", "school", "category", "status", "expense_date")
    search_fields = ("title", "supplier", "reference")
    autocomplete_fields = ("branch", "school", "created_by", "approved_by", "paid_by")


@admin.register(BranchCashMovement)
class BranchCashMovementAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("reference", "receipt_number", "label", "branch", "school", "movement_type", "source", "amount", "movement_date", "created_by")
    list_filter = ("branch", "school", "movement_type", "source", "movement_date")
    search_fields = ("label", "reference", "source_reference", "receipt_number", "notes")
    autocomplete_fields = ("branch", "school", "expense", "created_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # The ledger is append-only. Corrections are done by a counter-entry
        # through the financial workflows, never by editing the source row.
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(BranchCashRegisterSession)
class BranchCashRegisterSessionAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = (
        "branch", "school", "session_date", "status", "system_opening_balance",
        "expected_amount", "counted_amount", "difference_amount", "closed_at",
    )
    list_filter = ("branch", "school", "status", "session_date")
    search_fields = ("branch__name", "branch__code", "opening_notes", "closing_notes")
    autocomplete_fields = ("branch", "school", "opened_by", "closed_by")
    readonly_fields = (
        "branch", "session_date", "opening_amount", "system_opening_balance",
        "expected_amount", "counted_amount", "difference_amount", "status",
        "opening_notes", "closing_notes", "opened_by", "closed_by", "opened_at",
        "closed_at", "created_at", "updated_at",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AccountingDocumentSequence)
class AccountingDocumentSequenceAdmin(admin.ModelAdmin):
    list_display = ("branch", "school", "document_type", "year", "last_number", "updated_at")
    list_filter = ("branch", "school", "document_type", "year")
    search_fields = ("branch__name", "branch__code")


@admin.register(TeacherHonorariumEntry)
class TeacherHonorariumEntryAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("teacher", "branch", "school", "period_month", "hourly_rate", "validated_hours", "paid_amount", "status", "paid_at")
    list_filter = ("branch", "school", "status", "period_month")
    search_fields = ("teacher__username", "teacher__first_name", "teacher__last_name", "teacher__email")
    autocomplete_fields = ("teacher", "branch", "created_by", "updated_by")


@admin.register(BranchMonthlyClosure)
class BranchMonthlyClosureAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("branch", "school", "period_month", "status", "result_amount", "bank_transfer_amount", "closed_at")
    list_filter = ("branch", "school", "status", "period_month")
    search_fields = ("branch__name", "branch__code", "notes")
    autocomplete_fields = ("branch", "school", "created_by", "validated_by")


@admin.register(BranchBankTransfer)
class BranchBankTransferAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("branch", "school", "bank_name", "reference", "transfer_date", "amount", "created_by")
    list_filter = ("branch", "school", "transfer_date")
    search_fields = ("bank_name", "reference", "comment")
    autocomplete_fields = ("branch", "school", "closure", "created_by")


@admin.register(Donation)
class DonationAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("donor_name", "amount", "branch", "school", "date", "motif", "payment_method", "receipt_number", "created_by")
    list_filter = ("branch", "school", "motif", "payment_method", "date")
    search_fields = ("donor_name", "description", "receipt_number")
    autocomplete_fields = ("branch", "school", "cash_movement", "created_by")


@admin.register(SensitiveActionRequest)
class SensitiveActionRequestAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("action_type", "target_model", "target_id", "branch", "school", "requested_by", "status", "created_at", "expires_at")
    list_filter = ("branch", "school", "action_type", "status")
    search_fields = ("target_model", "reason")
    autocomplete_fields = ("branch", "school", "requested_by", "approved_by")
    readonly_fields = ("otp_code_hash", "otp_display_code", "created_at", "resolved_at")


@admin.register(FinancialAuditLog)
class FinancialAuditLogAdmin(SchoolFinanceAdminMixin, admin.ModelAdmin):
    list_display = ("action_type", "target_model", "target_id", "branch", "school", "performed_by", "approved_by", "created_at")
    list_filter = ("branch", "school", "action_type")
    search_fields = ("target_model",)
    autocomplete_fields = ("branch", "school", "performed_by", "approved_by", "sensitive_action_request")
    readonly_fields = ("created_at",)


from accounts.models import InstitutionalProfile


@admin.register(InstitutionalProfile)
class InstitutionalProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "position", "scope", "school", "branch")
    list_filter = ("position", "access_scope", "school", "branch")
    search_fields = ("user__username", "user__first_name", "user__last_name", "employee_code")
    autocomplete_fields = ("user", "school", "branch")
    list_select_related = ("user", "school", "branch")

    def has_change_permission(self, request, obj=None):
        from accounts.access import get_user_scope

        return super().has_change_permission(request, obj) and get_user_scope(request.user)["is_global"]

    def has_add_permission(self, request):
        from accounts.access import get_user_scope

        return super().has_add_permission(request) and get_user_scope(request.user)["is_global"]

    def has_delete_permission(self, request, obj=None):
        from accounts.access import get_user_scope

        return super().has_delete_permission(request, obj) and get_user_scope(request.user)["is_global"]
