"""Contrat du référentiel réel, uniquement sur la base isolée du test runner."""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.urls import reverse

from academics.models import AcademicClass, AcademicEnrollment, AcademicYear
from branches.models import Branch
from core.services.business_data_reset import remaining_business_data, reset_business_data
from core.services.institution_bootstrap import apply_bootstrap_manifest, load_bootstrap_manifest
from formations.models import (
    Cycle, Diploma, Fee, Filiere, Programme, ProgrammeQuickFact,
    ProgrammeRequiredDocument, ProgrammeYear, RequiredDocument,
)
from inscriptions.models import Inscription


MANIFEST = Path(settings.BASE_DIR) / "bootstrap" / "academic_reference.json"
REFERENCE_MODELS = (
    Cycle, Diploma, Filiere, Programme, ProgrammeYear, Fee,
    RequiredDocument, ProgrammeRequiredDocument, ProgrammeQuickFact,
)
EXPECTED = {
    "Cycle primaire": {
        "Employé de Pharmacie": (2, 200000, 9),
        "Agent de Santé Communautaire": (2, 200000, 9),
        "Matrone": (2, 100000, 9),
        "Aide Soignant": (1, 100000, 9),
    },
    "Cycle secondaire": {
        "Infirmier Santé Publique": (3, 310000, 9),
        "Infirmière Santé Maternelle et Infantile": (3, 310000, 9),
        "Technicien de Labo-Pharmacie": (3, 310000, 9),
        "Technicien Santé Communautaire": (3, 310000, 9),
        "Auxiliaire Infirmier": (2, 225000, 9),
        "Auxiliaire Puériculture": (2, 225000, 9),
    },
    "Cycle Licence": {
        "Infirmier d'État": (3, 410000, 9),
        "Sage-Femme": (3, 410000, 9),
        "Biologie Médicale": (3, 410000, 9),
        "Nutrition": (2, 510000, 3),
        "Santé Environnementale": (2, 510000, 3),
    },
    "Cycle Master": {
        "Biologie Médicale": (2, 810000, 3),
        "Gynécologie Obstétrique": (2, 810000, 3),
        "Manager en Santé": (2, 810000, 3),
        "Pédagogie en Santé": (2, 810000, 3),
        "Épidémiologie": (2, None, 0),
        "Nutrition": (2, None, 0),
        "Santé Environnementale": (2, None, 0),
    },
}


class InstitutionalReferenceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))

    def test_exact_cycles_programmes_durations_and_years(self):
        self.assertSetEqual(set(Cycle.objects.values_list("name", flat=True)), set(EXPECTED))
        self.assertEqual(Programme.objects.count(), 22)
        for cycle, programmes in EXPECTED.items():
            self.assertSetEqual(
                set(Programme.objects.filter(cycle__name=cycle).values_list("title", flat=True)),
                set(programmes),
            )
            for title, (duration, _total, _count) in programmes.items():
                with self.subTest(cycle=cycle, title=title):
                    programme = Programme.objects.get(cycle__name=cycle, title=title)
                    self.assertEqual(programme.duration_years, duration)
                    self.assertEqual(list(programme.years.values_list("year_number", flat=True)), list(range(1, duration + 1)))
        licence = Cycle.objects.get(name="Cycle Licence")
        self.assertEqual((licence.min_duration_years, licence.max_duration_years), (2, 3))

    def test_access_conditions_are_per_programme_and_not_cycle_duration(self):
        for programme in Programme.objects.select_related("cycle"):
            expected = (
                "BAC ou diplôme TS ou BT + 3 ans" if programme.cycle.name == "Cycle Licence"
                else "À confirmer par l'établissement" if programme.cycle.name == "Cycle Master"
                else "DEF ou BEPC"
            )
            self.assertEqual(programme.quick_facts.get(label="Conditions d'accès").value, expected)

    def test_annual_finance_totals_and_installments_use_existing_engine(self):
        for cycle, programmes in EXPECTED.items():
            for title, (duration, total, fee_count) in programmes.items():
                programme = Programme.objects.get(cycle__name=cycle, title=title)
                for year in range(1, duration + 1):
                    with self.subTest(cycle=cycle, title=title, year=year):
                        expected_total = None if cycle == "Cycle Master" and year == 2 else total
                        fees = programme.years.get(year_number=year).fees
                        self.assertEqual(programme.get_inscription_amount_for_year(year), expected_total or 0)
                        self.assertEqual(fees.count(), fee_count if expected_total else 0)
                        if expected_total:
                            self.assertEqual(fees.filter(label="Inscription").count(), 1)
                            registration, installment = {
                                100000: (20000, 10000), 200000: (100000, 12500),
                                225000: (85000, 17500), 310000: (110000, 25000),
                                410000: (130000, 35000), 510000: (210000, 150000),
                                810000: (410000, 200000),
                            }[expected_total]
                            self.assertEqual(fees.get(label="Inscription").amount, registration)
                            self.assertSetEqual(set(fees.exclude(label="Inscription").values_list("amount", flat=True)), {installment})
                            if fee_count == 9:
                                self.assertEqual(fees.filter(label__startswith="Mensualité ").count(), 8)
                                self.assertEqual(fees.values("due_month").distinct().count(), 9)
                            else:
                                self.assertSetEqual(set(fees.exclude(label="Inscription").values_list("due_month", flat=True)), {"Janvier", "Mars"})

    def test_document_identity_shared_and_access_dependent_diploma_not_cumulative(self):
        self.assertEqual(RequiredDocument.objects.count(), 5)
        for programme in Programme.objects.all():
            self.assertEqual(programme.required_documents.count(), 5)
        diploma = RequiredDocument.objects.get(name="Copie légalisée du diplôme correspondant au niveau d'accès")
        self.assertIn("uniquement lorsque requis", diploma.description)
        self.assertIn("Ne pas exiger cumulativement", diploma.description)

    def test_bootstrap_is_idempotent_preserves_ids_and_does_not_create_operations(self):
        before = {model: set(model.objects.values_list("pk", flat=True)) for model in REFERENCE_MODELS}
        summary = apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))
        self.assertEqual(summary.created, 0)
        for model, ids in before.items():
            self.assertSetEqual(set(model.objects.values_list("pk", flat=True)), ids)
        for model in (Branch, AcademicClass, AcademicYear, AcademicEnrollment, Inscription):
            self.assertEqual(model.objects.count(), 0)

    def test_deactivation_and_archival_survive_rebootstrap(self):
        programme = Programme.objects.get(cycle__name="Cycle Licence", title="Nutrition")
        programme.is_active = False
        programme.save(update_fields=["is_active"])
        cycle = programme.cycle
        cycle.is_active = False
        cycle.save(update_fields=["is_active"])
        apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))
        programme.refresh_from_db()
        cycle.refresh_from_db()
        self.assertFalse(programme.is_active)
        self.assertFalse(cycle.is_active)
        self.assertFalse(Programme.objects.public().filter(cycle=cycle).exists())
        cycle.is_active = True
        cycle.save(update_fields=["is_active"])
        programme.is_active = True
        programme.save(update_fields=["is_active"])
        self.assertTrue(Programme.objects.public().filter(pk=programme.pk).exists())
        programme.archive()
        apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))
        programme.refresh_from_db()
        self.assertTrue(programme.is_archived)
        self.assertFalse(programme.is_active)

    def test_reset_preserves_reference_ids_fees_and_deactivation_but_removes_operations(self):
        admin = get_user_model().objects.create_superuser(username="reference-admin", password="test-only")
        branch = Branch.objects.create(code="REF", name="Test reset", slug="test-reset")
        year = AcademicYear.objects.create(name="2098-2099", start_date="2098-10-01", end_date="2099-07-31")
        programme = Programme.objects.get(cycle__name="Cycle Licence", title="Nutrition")
        AcademicClass.objects.create(programme=programme, branch=branch, academic_year=year, level="L1")
        programme.is_active = False
        programme.save(update_fields=["is_active"])
        # Une spécialité ajoutée par l'établissement n'a pas besoin d'être
        # codée dans le manifeste pour rester un référentiel permanent.
        Programme.objects.create(
            title="Spécialité ajoutée ultérieurement (test)",
            cycle=Cycle.objects.get(name="Cycle Master"),
            filiere=programme.filiere, diploma_awarded=programme.diploma_awarded,
            duration_years=2, short_description="Test", description="Test",
        )
        before = {model: set(model.objects.values_list("pk", flat=True)) for model in REFERENCE_MODELS}
        reset_business_data(preserve_usernames=[admin.username])
        for model, ids in before.items():
            self.assertSetEqual(set(model.objects.values_list("pk", flat=True)), ids)
        programme.refresh_from_db()
        self.assertFalse(programme.is_active)
        self.assertFalse(AcademicClass.objects.exists())
        self.assertFalse(AcademicYear.objects.exists())
        self.assertEqual(remaining_business_data([admin.pk]), {})

    def test_legacy_cycle_name_is_normalized_without_replacing_identity(self):
        cycle = Cycle.objects.get(name="Cycle Licence")
        Cycle.objects.filter(pk=cycle.pk).update(name="Cycle supérieur Licence")
        apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))
        cycle.refresh_from_db()
        self.assertEqual(cycle.name, "Cycle Licence")
        self.assertEqual(Cycle.objects.count(), 4)

    def test_infirmier_etat_legacy_secondary_assignment_is_corrected(self):
        programme = Programme.objects.get(title="Infirmier d'État")
        for title in ("Infirmier d'État", "Infirmier d’État"):
            with self.subTest(title=title):
                Programme.objects.filter(pk=programme.pk).update(
                    title=title, cycle=Cycle.objects.get(name="Cycle secondaire")
                )
                apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))
                programme.refresh_from_db()
                self.assertEqual(programme.cycle.name, "Cycle Licence")
                self.assertEqual(programme.title, "Infirmier d'État")
                self.assertEqual(Programme.objects.count(), 22)

    def test_ambiguous_cycle_refuses_instead_of_arbitrary_merge(self):
        Cycle.objects.create(name="Licence", min_duration_years=3, max_duration_years=3)
        with self.assertRaisesMessage(CommandError, "Référentiel ambigu"):
            apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))
        self.assertEqual(Cycle.objects.count(), 5)

    def test_conflicting_fee_refuses_and_rolls_back_earlier_updates(self):
        cycle = Cycle.objects.get(name="Cycle primaire")
        Cycle.objects.filter(pk=cycle.pk).update(min_duration_years=9)
        fee = Fee.objects.filter(label="Inscription").first()
        Fee.objects.filter(pk=fee.pk).update(amount=123)
        with self.assertRaisesMessage(CommandError, "Valeur existante contradictoire"):
            apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))
        cycle.refresh_from_db()
        fee.refresh_from_db()
        self.assertEqual(cycle.min_duration_years, 9)
        self.assertEqual(fee.amount, 123)

    def test_extra_legacy_fee_refuses_double_counting(self):
        year = ProgrammeYear.objects.first()
        Fee.objects.create(programme_year=year, label="Ancienne tranche", amount=999, due_month="Mars")
        with self.assertRaisesMessage(CommandError, "Tranches existantes à réconcilier"):
            apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))

    def test_master_featured_years_are_editable_data_and_unpriced_m2_is_not_free(self):
        programme = Programme.objects.get(cycle__name="Cycle Master", title="Biologie Médicale")
        self.assertEqual(programme.quick_facts.get(label="Année actuellement mise en avant").value, "Master 1")
        response = self.client.get(reverse("formations:detail", args=[programme.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["total_programme_cost"])
        self.assertIsNone(response.context["average_year_cost"])
        self.assertNotContains(response, "Tarif à confirmer")
        self.assertContains(response, programme.title)
        # Le rendu n'affiche plus de tarif provisoire ; les frais historiques
        # restent contrôlés sans inventer un total pour un M2 non renseigné.
        self.assertEqual(response.context["years_with_totals"][0]["year_total"], 810000)
        self.assertFalse(response.context["can_apply"])

    def test_later_master_tariffs_can_be_configured_without_bootstrap_erasing_them(self):
        programme = Programme.objects.get(cycle__name="Cycle Master", title="Biologie Médicale")
        year = programme.years.get(year_number=2)
        fee = Fee.objects.create(programme_year=year, label="Tarif confirmé ultérieurement (test)", amount=777, due_month="Janvier")
        apply_bootstrap_manifest(load_bootstrap_manifest(MANIFEST))
        fee.refresh_from_db()
        self.assertEqual(fee.amount, 777)

    def test_primary_detail_and_licence_two_year_total(self):
        primary = Programme.objects.get(title="Matrone")
        response = self.client.get(reverse("formations:detail", args=[primary.slug]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["cycle_type"], "primaire")
        self.assertNotContains(response, "DEF ou BEPC")
        self.assertContains(response, primary.title)
        licence = Programme.objects.get(title="Nutrition", cycle__name="Cycle Licence")
        response = self.client.get(reverse("formations:detail", args=[licence.slug]))
        self.assertEqual(response.context["total_programme_cost"], 1020000)
        self.assertEqual(response.context["average_year_cost"], 510000)


class InstitutionalReferenceInstallationTests(TestCase):
    def test_manifest_rejects_strings_exceeding_postgresql_column_length(self):
        payload = {"version": 1, "objects": [{
            "model": "branches.Branch", "lookup": {"code": "LONG"},
            "fields": {"name": "Test", "slug": "a" * 51},
        }]}
        with self.assertRaisesMessage(CommandError, "Valeur trop longue"):
            apply_bootstrap_manifest(payload)
        self.assertFalse(Branch.objects.exists())

    def test_official_command_installs_on_empty_database_and_dry_run_writes_nothing(self):
        call_command("bootstrap_institution", dry_run=True, verbosity=0)
        self.assertFalse(Cycle.objects.exists())
        self.assertFalse(Branch.objects.exists())
        call_command("bootstrap_institution", verbosity=0)
        self.assertEqual(Cycle.objects.count(), 4)
        self.assertEqual(Programme.objects.count(), 22)
        self.assertEqual(Branch.objects.count(), 14)
        counts = {model: model.objects.count() for model in REFERENCE_MODELS}
        call_command("bootstrap_institution", verbosity=0)
        self.assertEqual(counts, {model: model.objects.count() for model in REFERENCE_MODELS})
        self.assertFalse(AcademicClass.objects.exists())

    def test_manifest_includes_cannot_escape_directory_or_recurse(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            path.write_text('{"version": 1, "objects": [], "includes": ["manifest.json"]}', encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "circulaire"):
                load_bootstrap_manifest(path)
            path.write_text('{"version": 1, "objects": [], "includes": ["../outside.json"]}', encoding="utf-8")
            with self.assertRaisesMessage(CommandError, "dossier du manifeste"):
                load_bootstrap_manifest(path)
