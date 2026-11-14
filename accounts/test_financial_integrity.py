from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from branches.models import Branch
from accounts.models import (
    BranchCashMovement,
    BranchCashRegisterSession,
    BranchBankTransfer,
    BranchMonthlyClosure,
    BranchWallet,
)
from accounts.services.accounting_documents import create_cash_movement
from accounts.services.financial_integrity import (
    close_cash_register_session,
    open_cash_register_session,
)
from accounts.services.wallets import (
    allocate_from_principal,
    branch_unallocated_cash,
    return_to_principal,
    transfer_between_wallets,
    wallet_balance,
)
from accounts.services.manager_intelligence import create_validated_bank_transfer, get_branch_cash_balance


User = get_user_model()


class FinancialIntegrityTests(TestCase):
    def setUp(self):
        self.branch = Branch.objects.create(
            name="Annexe integrite", code="INT", slug="annexe-integrite"
        )
        self.actor = User.objects.create_user(username="financial-integrity", password="pass1234")

    @patch("accounts.services.accounting_documents.finalize_cash_movement_document", side_effect=lambda movement: movement)
    def test_source_reference_is_idempotent(self, _finalize):
        first = create_cash_movement(
            branch=self.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference="payment:integrity:1",
            amount=25000,
            label="Paiement test",
            created_by=self.actor,
        )
        repeated = create_cash_movement(
            branch=self.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_STUDENT_PAYMENT,
            source_reference="payment:integrity:1",
            amount=25000,
            label="Paiement test",
            created_by=self.actor,
        )

        self.assertEqual(first.pk, repeated.pk)
        self.assertEqual(BranchCashMovement.objects.count(), 1)

    @patch("accounts.services.accounting_documents.finalize_cash_movement_document", side_effect=lambda movement: movement)
    def test_finalized_month_refuses_new_ledger_entry(self, _finalize):
        today = timezone.localdate()
        BranchMonthlyClosure.objects.create(
            branch=self.branch,
            period_month=today.replace(day=1),
            status=BranchMonthlyClosure.STATUS_CLOSED,
        )

        with self.assertRaises(ValidationError):
            create_cash_movement(
                branch=self.branch,
                movement_type=BranchCashMovement.TYPE_IN,
                source=BranchCashMovement.SOURCE_MANUAL,
                amount=1000,
                label="Ecriture tardive",
                movement_date=today,
                created_by=self.actor,
            )

    def test_daily_cash_register_preserves_the_observed_difference(self):
        BranchCashMovement.objects.create(
            branch=self.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_MANUAL,
            amount=10000,
            label="Fonds test",
            created_by=self.actor,
        )
        session, created = open_cash_register_session(
            branch=self.branch,
            actor=self.actor,
            opening_amount=10000,
        )
        self.assertTrue(created)
        self.assertEqual(session.status, BranchCashRegisterSession.STATUS_OPEN)

        session = close_cash_register_session(
            branch=self.branch,
            actor=self.actor,
            counted_amount=9500,
            notes="Billet manquant signale.",
        )
        self.assertEqual(session.status, BranchCashRegisterSession.STATUS_CLOSED)
        self.assertEqual(session.difference_amount, -500)

    def test_daily_cash_register_requires_reason_for_a_difference(self):
        BranchCashMovement.objects.create(
            branch=self.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_MANUAL,
            amount=10000,
            label="Fonds test",
            created_by=self.actor,
        )
        open_cash_register_session(branch=self.branch, actor=self.actor, opening_amount=10000)
        with self.assertRaises(ValidationError):
            close_cash_register_session(
                branch=self.branch,
                actor=self.actor,
                counted_amount=9500,
            )

    @patch("accounts.services.accounting_documents.finalize_cash_movement_document", side_effect=lambda movement: movement)
    def test_bank_transfer_is_idempotent_and_reduces_physical_cash(self, _finalize):
        BranchCashMovement.objects.create(
            branch=self.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_MANUAL,
            amount=10000,
            label="Fonds test",
            created_by=self.actor,
        )
        transfer, created = create_validated_bank_transfer(
            branch=self.branch,
            actor=self.actor,
            bank_name="Banque Test",
            bank_country="Mali",
            reference="BORD-001",
            transfer_date=timezone.localdate(),
            amount=7000,
        )
        repeated, created_again = create_validated_bank_transfer(
            branch=self.branch,
            actor=self.actor,
            bank_name="Banque Test",
            bank_country="Mali",
            reference="BORD-001",
            transfer_date=timezone.localdate(),
            amount=7000,
        )
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(transfer.pk, repeated.pk)
        self.assertEqual(transfer.status, BranchBankTransfer.STATUS_VALIDATED)
        self.assertEqual(transfer.cash_balance_before, 10000)
        self.assertEqual(transfer.cash_balance_after, 3000)
        self.assertEqual(get_branch_cash_balance(self.branch), 3000)
        self.assertEqual(
            BranchCashMovement.objects.filter(
                branch=self.branch,
                source=BranchCashMovement.SOURCE_BANK_TRANSFER,
            ).count(),
            1,
        )

    def test_wallet_allocation_transfer_and_return_do_not_change_total_cash(self):
        BranchCashMovement.objects.create(
            branch=self.branch,
            movement_type=BranchCashMovement.TYPE_IN,
            source=BranchCashMovement.SOURCE_MANUAL,
            amount=100000,
            label="Encaissement de depart",
            created_by=self.actor,
        )
        salaries = BranchWallet.objects.create(
            branch=self.branch, name="Salaires", wallet_type=BranchWallet.TYPE_DISBURSEMENT,
            category="salary", created_by=self.actor,
        )
        honoraria = BranchWallet.objects.create(
            branch=self.branch, name="Honoraires", wallet_type=BranchWallet.TYPE_DISBURSEMENT,
            category="honorarium", created_by=self.actor,
        )

        allocate_from_principal(wallet=salaries, amount=60000, actor=self.actor)
        self.assertEqual(wallet_balance(salaries), 60000)
        self.assertEqual(branch_unallocated_cash(self.branch), 40000)

        transfer_between_wallets(source=salaries, target=honoraria, amount=15000, actor=self.actor)
        self.assertEqual(wallet_balance(salaries), 45000)
        self.assertEqual(wallet_balance(honoraria), 15000)
        self.assertEqual(branch_unallocated_cash(self.branch), 40000)

        return_to_principal(wallet=honoraria, amount=5000, actor=self.actor)
        self.assertEqual(wallet_balance(honoraria), 10000)
        self.assertEqual(branch_unallocated_cash(self.branch), 45000)
        self.assertEqual(get_branch_cash_balance(self.branch), 100000)
