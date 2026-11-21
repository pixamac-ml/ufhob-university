"""Recette T6 — le filtre par défaut des modèles de caisse ne masque rien
hors d'un contexte d'école, et ne fuit pas d'une requête / d'un thread à l'autre."""

import threading
from dataclasses import replace
from datetime import date
from io import StringIO

from django.core.management import call_command
from django.urls import reverse

from accounts.access_context import build_access_context
from accounts.models import BranchCashMovement, BranchExpense, InstitutionalProfile
from accounts.scoping import _request_context, access_scope
from accounts.services.manager_intelligence import get_branch_cash_balance
from accounts.test_caisse_par_ecole import CaisseParEcoleBase


class FiltreDefautCaisseTests(CaisseParEcoleBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.dg = cls.make_user("t6r-dg", "executive_director")
        with access_scope(build_access_context(cls.gest_esga)):
            cls.mv_esga = BranchCashMovement.objects.create(
                branch=cls.a, movement_type=BranchCashMovement.TYPE_IN, amount=70000, label="Recette ESGA")
        with access_scope(build_access_context(cls.gest_fatec)):
            cls.mv_fatec = BranchCashMovement.objects.create(
                branch=cls.a, movement_type=BranchCashMovement.TYPE_IN, amount=30000, label="Recette FATEC")
        cls.mv_legacy = BranchCashMovement.objects.create(
            branch=cls.a, movement_type=BranchCashMovement.TYPE_IN, amount=1000, label="Ancien",
            created_by=cls.global_user)
        BranchCashMovement.all_objects.filter(pk=cls.mv_legacy.pk).update(school=None)

    # (a) ---------------------------------------------------------------
    def test_a_commande_utilise_all_objects_meme_sous_contexte_d_ecole(self):
        expense = BranchExpense.objects.create(branch=self.a, title="Ancienne FATEC", amount=500,
                                               created_by=self.gest_fatec)
        BranchExpense.all_objects.filter(pk=expense.pk).update(school=None)
        out = StringIO()
        # Même lancée « au nom » d'une gestionnaire ESGA, la commande voit tout.
        with access_scope(build_access_context(self.gest_esga)):
            call_command("attribuer_ecole_finance", "--apply", stdout=out)
        expense.refresh_from_db()
        self.assertEqual(expense.school, self.fatec)
        self.assertIn("BranchCashMovement: ", out.getvalue())
        self.assertIn(str(self.mv_legacy.pk), out.getvalue())  # listée, non devinée
        self.assertIsNone(_request_context.get())

    def test_a_commande_sans_utilisateur_connecte(self):
        self.assertIsNone(_request_context.get())
        out = StringIO()
        call_command("attribuer_ecole_finance", stdout=out)
        self.assertIn("SIMULATION", out.getvalue())
        self.assertIn("1 restante(s)", out.getvalue().split("accounts.BranchCashMovement")[1].splitlines()[0])

    # (b) ---------------------------------------------------------------
    def test_b_hors_requete_tout_est_visible(self):
        self.assertIsNone(_request_context.get())
        self.assertEqual(BranchCashMovement.objects.filter(branch=self.a).count(), 3)
        self.assertEqual(get_branch_cash_balance(self.a), 101000)

    def test_b_thread_sans_requete_voit_tout_meme_lance_depuis_une_requete(self):
        seen = {}

        def worker():
            seen["ctx"] = _request_context.get()
            # SQLite mémoire + transaction de test : on inspecte la requête
            # construite par le thread au lieu de l'exécuter.
            seen["sql"] = str(BranchCashMovement.objects.filter(branch=self.a).query).split(" WHERE ")[1]

        with access_scope(build_access_context(self.gest_esga)):
            self.assertEqual(BranchCashMovement.objects.filter(branch=self.a).count(), 1)
            thread = threading.Thread(target=worker)
            thread.start()
            thread.join()
        self.assertIsNone(seen["ctx"])
        self.assertNotIn("school_id", seen["sql"])
        with access_scope(build_access_context(self.gest_esga)):
            where = str(BranchCashMovement.objects.filter(branch=self.a).query).split(" WHERE ")[1]
            self.assertIn("school_id", where)

    # (c) ---------------------------------------------------------------
    def test_c_admin_superutilisateur_voit_tout(self):
        admin_user = self.make_user("t6r-root", "annex_manager", self.a, self.esga, "SCHOOL_BRANCH")
        admin_user.is_superuser = admin_user.is_staff = True
        admin_user.save(update_fields=["is_superuser", "is_staff"])
        self.client.force_login(admin_user)
        response = self.client.get(reverse("admin:accounts_branchcashmovement_changelist"))
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        for label in ("Recette ESGA", "Recette FATEC", "Ancien"):
            self.assertIn(label, body)
        detail = self.client.get(reverse("admin:accounts_branchcashmovement_change", args=[self.mv_fatec.pk]))
        self.assertEqual(detail.status_code, 200)
        # Recette 3 : colonne et filtre « École » dans l'admin.
        filtered = self.client.get(reverse("admin:accounts_branchcashmovement_changelist"),
                                   {"school__id__exact": self.fatec.pk})
        self.assertContains(filtered, "Recette FATEC")
        self.assertNotContains(filtered, "Recette ESGA")
        self.assertContains(filtered, "column-school")

    # (d) ---------------------------------------------------------------
    def test_d_dg_voit_tout_le_campus_et_chaque_ecole_quand_il_filtre(self):
        dg_context = build_access_context(self.dg)
        self.assertIsNone(dg_context.school)
        with access_scope(dg_context):
            self.assertEqual(get_branch_cash_balance(self.a), 101000)
        with access_scope(replace(dg_context, school=self.esga)):
            self.assertEqual(get_branch_cash_balance(self.a), 70000)
        with access_scope(replace(dg_context, school=self.fatec)):
            self.assertEqual(get_branch_cash_balance(self.a), 30000)

    # (e) ---------------------------------------------------------------
    def test_e_contexte_reinitialise_apres_chaque_requete(self):
        self.client.force_login(self.gest_esga)
        self.client.post(reverse("accounts:htmx_manager_expense_approve", args=[999999]), HTTP_HX_REQUEST="true")
        self.assertIsNone(_request_context.get())
        self.assertEqual(BranchCashMovement.objects.filter(branch=self.a).count(), 3)
        self.client.logout()
        self.client.force_login(self.gest_fatec)
        with access_scope(build_access_context(self.gest_fatec)):
            self.assertEqual(list(BranchCashMovement.objects.filter(branch=self.a)), [self.mv_fatec])
        self.assertIsNone(_request_context.get())

    def test_e_contexte_restaure_meme_en_cas_d_exception(self):
        with self.assertRaises(RuntimeError):
            with access_scope(build_access_context(self.gest_esga)):
                raise RuntimeError("boom")
        self.assertIsNone(_request_context.get())
        self.assertEqual(InstitutionalProfile.objects.filter(user=self.gest_esga).count(), 1)
