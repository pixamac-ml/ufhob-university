"""T6 — caisse par école : écriture de l'école, répartition, isolation."""

from datetime import date
from io import StringIO

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.access_context import build_access_context
from accounts.models import BranchCashMovement, BranchExpense, Donation, PayrollEntry
from accounts.scoping import access_scope
from core import test_ufhob_phase2 as fixtures
from inscriptions.models import Inscription
from payments.models import Payment
from payments.services.workflows import sync_payment_finance_history


@override_settings(
    AUTH_POLICY_V2_ENABLED=False,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
)
class CaisseParEcoleBase(TestCase):
    make_user = staticmethod(fixtures.UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        fixtures.UFHOBPhase2Tests.setUpTestData.__func__(cls)
        cls.esmed, cls.esga, cls.fatec = cls.schools
        cls.gest_esga = cls.make_user("t6-gest-esga", "annex_manager", cls.a, cls.esga, "SCHOOL_BRANCH")
        cls.gest_fatec = cls.make_user("t6-gest-fatec", "annex_manager", cls.a, cls.fatec, "SCHOOL_BRANCH")
        cls.employe_fatec = cls.make_user("t6-employe-fatec", "secretary", cls.a, cls.fatec, "SCHOOL_BRANCH")

    @classmethod
    def inscription(cls, programme, key):
        candidature = fixtures.Candidature.objects.create(
            programme=programme, branch=cls.a, academic_year=cls.year.name, birth_date=date(2000, 1, 1),
            first_name="T6", last_name=key, email=f"t6.{key}@example.invalid", gender="female",
            phone="000", birth_place="Bamako", status="accepted",
        )
        return Inscription.objects.create(candidature=candidature, amount_due=100000, amount_paid=0)

    def movement(self, **kwargs):
        values = {"branch": self.a, "movement_type": BranchCashMovement.TYPE_IN, "amount": 1000, "label": "Test"}
        values.update(kwargs)
        return BranchCashMovement.objects.create(**values)


class EcritureEcoleTests(CaisseParEcoleBase):
    def test_paiement_etudiant_va_dans_la_caisse_de_son_ecole(self):
        ins = self.inscription(self.programmes[2], "fatec")
        payment = Payment.objects.create(
            inscription=ins, amount=25000, method=Payment.METHOD_CASH,
            status=Payment.STATUS_VALIDATED, paid_at=timezone.now(), reference="T6-PAY-FATEC",
        )
        movement = sync_payment_finance_history(payment=payment)
        self.assertEqual(movement.school, self.fatec)

    def test_depense_sous_contexte_gestionnaire(self):
        with access_scope(build_access_context(self.gest_esga)):
            expense = BranchExpense.objects.create(branch=self.a, title="Craies", amount=5000)
        self.assertEqual(expense.school, self.esga)

    def test_acteur_gestionnaire_sans_contexte(self):
        expense = BranchExpense.objects.create(branch=self.a, title="Encre", amount=3000, created_by=self.gest_fatec)
        self.assertEqual(expense.school, self.fatec)

    def test_paie_suit_l_ecole_du_salarie(self):
        entry = PayrollEntry.objects.create(
            branch=self.a, employee=self.employe_fatec, period_month=date(2026, 11, 1), created_by=self.gest_esga,
        )
        self.assertEqual(entry.school, self.fatec)

    def test_mouvement_de_don_suit_la_depense_ou_le_don(self):
        with access_scope(build_access_context(self.gest_fatec)):
            donation = Donation.objects.create(branch=self.a, donor_name="ONG", amount=10000)
        self.assertEqual(donation.school, self.fatec)
        movement = self.movement(source=BranchCashMovement.SOURCE_DONATION, source_reference=f"donation:{donation.pk}")
        self.assertEqual(movement.school, self.fatec)

    def test_ecole_explicite_conservee_et_ecole_hors_campus_ignoree(self):
        movement = self.movement(school=self.esga, created_by=self.gest_fatec)
        self.assertEqual(movement.school, self.esga)
        outsider = self.make_user("t6-gest-b", "annex_manager", self.b, self.esmed, "SCHOOL_BRANCH")
        lone = BranchExpense.objects.create(branch=self.a, title="Sans école", amount=100, created_by=outsider)
        # ESMED existe aussi sur le campus A : l'école de l'acteur reste valable.
        self.assertEqual(lone.school, self.esmed)
        unknown = self.movement(created_by=self.global_user)
        self.assertIsNone(unknown.school)


class AttribuerEcoleFinanceTests(CaisseParEcoleBase):
    def _legacy(self):
        """Lignes « d'avant » : école effacée comme avant la migration."""
        ins = self.inscription(self.programmes[1], "esga-legacy")
        payment = Payment.objects.create(
            inscription=ins, amount=40000, method=Payment.METHOD_CASH,
            status=Payment.STATUS_VALIDATED, paid_at=timezone.now(), reference="T6-LEGACY-ESGA",
        )
        pay_mv = self.movement(source=BranchCashMovement.SOURCE_STUDENT_PAYMENT, source_reference=payment.reference)
        expense = BranchExpense.objects.create(branch=self.a, title="Ancienne", amount=900, created_by=self.gest_fatec)
        exp_mv = self.movement(movement_type=BranchCashMovement.TYPE_OUT, source=BranchCashMovement.SOURCE_EXPENSE,
                               source_reference=f"expense:{expense.pk}")
        mono = self.movement(branch=self.b)  # campus B : ESMED seule
        orphan = self.movement(created_by=self.global_user)
        rows = [pay_mv, expense, exp_mv, mono, orphan]
        for row in rows:
            type(row).objects.filter(pk=row.pk).update(school=None)
        return rows

    def test_simulation_n_ecrit_rien_puis_apply_repartit(self):
        pay_mv, expense, exp_mv, mono, orphan = self._legacy()
        out = StringIO()
        call_command("attribuer_ecole_finance", "--dry-run", stdout=out)
        self.assertIn("SIMULATION", out.getvalue())
        self.assertFalse(BranchCashMovement.objects.filter(school__isnull=False, pk__in=[pay_mv.pk, mono.pk]).exists())
        out = StringIO()
        call_command("attribuer_ecole_finance", "--apply", stdout=out)
        for row in (pay_mv, expense, exp_mv, mono, orphan):
            row.refresh_from_db()
        self.assertEqual(pay_mv.school, self.esga)
        self.assertEqual(expense.school, self.fatec)
        self.assertEqual(exp_mv.school, self.fatec)
        self.assertEqual(mono.school, self.esmed)
        self.assertIsNone(orphan.school)
        self.assertIn(str(orphan.pk), out.getvalue())

    def test_sans_acteur_laisse_la_depense_a_repartir(self):
        _pay, expense, *_ = self._legacy()
        call_command("attribuer_ecole_finance", "--apply", "--sans-acteur", stdout=StringIO())
        expense.refresh_from_db()
        self.assertIsNone(expense.school)


class IsolationCaisseEcoleTests(CaisseParEcoleBase):
    """ESGA et FATEC sur le même campus A : deux caisses ; le DG voit tout."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from accounts.models import BranchMonthlyClosure

        cls.dg = cls.make_user("t6-dg", "executive_director")
        with access_scope(build_access_context(cls.gest_esga)):
            cls.mv_esga = BranchCashMovement.objects.create(
                branch=cls.a, movement_type=BranchCashMovement.TYPE_IN, amount=70000, label="Recette ESGA")
            cls.exp_esga = BranchExpense.objects.create(branch=cls.a, title="Dépense ESGA", amount=5000)
            cls.clo_esga = BranchMonthlyClosure.objects.create(branch=cls.a, period_month=date(2026, 11, 1))
        with access_scope(build_access_context(cls.gest_fatec)):
            cls.mv_fatec = BranchCashMovement.objects.create(
                branch=cls.a, movement_type=BranchCashMovement.TYPE_IN, amount=30000, label="Recette FATEC")
            cls.exp_fatec = BranchExpense.objects.create(branch=cls.a, title="Dépense FATEC", amount=8000)
            # Même campus, même mois : chaque école a sa propre clôture.
            cls.clo_fatec = BranchMonthlyClosure.objects.create(branch=cls.a, period_month=date(2026, 11, 1))

    def as_user(self, user):
        return access_scope(build_access_context(user))

    def test_chaque_gestionnaire_ne_voit_que_sa_caisse(self):
        from accounts.models import BranchMonthlyClosure
        from accounts.services.manager_intelligence import get_branch_cash_balance

        self.assertEqual((self.mv_esga.school, self.mv_fatec.school), (self.esga, self.fatec))
        with self.as_user(self.gest_esga):
            self.assertEqual(get_branch_cash_balance(self.a), 70000)
            self.assertEqual(list(BranchExpense.objects.filter(branch=self.a)), [self.exp_esga])
            self.assertEqual(list(BranchMonthlyClosure.objects.filter(branch=self.a)), [self.clo_esga])
            self.assertFalse(BranchExpense.objects.filter(pk=self.exp_fatec.pk).exists())
        with self.as_user(self.gest_fatec):
            self.assertEqual(get_branch_cash_balance(self.a), 30000)
            self.assertEqual(list(BranchExpense.objects.filter(branch=self.a)), [self.exp_fatec])

    def test_dg_voit_toutes_les_ecoles(self):
        from accounts.services.manager_intelligence import get_branch_cash_balance

        with self.as_user(self.dg):
            self.assertEqual(get_branch_cash_balance(self.a), 100000)
            self.assertEqual(BranchExpense.objects.filter(branch=self.a).count(), 2)
        self.assertEqual(BranchCashMovement.all_objects.filter(branch=self.a).count(), 2)

    def test_scoped_et_numerotation_par_ecole(self):
        from accounts.scoping import scoped
        from accounts.services.accounting_documents import ensure_expense_reference

        with self.as_user(self.gest_fatec):
            self.assertEqual(list(scoped(BranchExpense, user=self.gest_fatec)), [self.exp_fatec])
        ref_esga = ensure_expense_reference(self.exp_esga)
        ref_fatec = ensure_expense_reference(self.exp_fatec)
        self.assertIn("-ESGA-", ref_esga)
        self.assertIn("-FATEC-", ref_fatec)
        self.assertTrue(ref_esga.endswith("000001") and ref_fatec.endswith("000001"))

    def test_http_gestionnaire_ne_peut_pas_approuver_la_depense_de_l_autre_ecole(self):
        from django.urls import reverse

        self.client.force_login(self.gest_esga)
        response = self.client.post(
            reverse("accounts:htmx_manager_expense_approve", args=[self.exp_fatec.pk]), HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 404)
        self.exp_fatec.refresh_from_db()
        self.assertEqual(self.exp_fatec.status, BranchExpense.STATUS_SUBMITTED)
        ok = self.client.post(
            reverse("accounts:htmx_manager_expense_approve", args=[self.exp_esga.pk]), HTTP_HX_REQUEST="true",
        )
        self.assertNotEqual(ok.status_code, 404)
        self.exp_esga.refresh_from_db()
        self.assertEqual(self.exp_esga.status, BranchExpense.STATUS_APPROVED)
