"""Durées et frais ESMed validés par la direction (idempotent, sans suppression).

Médecine 7 ans, Pharmacie 7 ans, Chirurgie dentaire 6 ans.
Chaque année : Inscription 1 100 000 FCFA + en cours d'année 1 000 000 FCFA = 2 100 000 FCFA.

- Base vide (production) : crée l'école ESMED et ses 3 programmes s'ils manquent.
- Base existante : met à jour durée, années et montants ; ne touche ni à la
  publication ni aux admissions d'un programme existant.
- Aucune suppression : une année au-delà de la durée est signalée, jamais effacée.
"""
from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Institution, School
from formations.models import Cycle, Diploma, Fee, Filiere, Programme, ProgrammeQuickFact, ProgrammeYear

REGISTRATION = ("Inscription", 1_100_000)
# Libellé historique conservé : il est déjà utilisé par les années existantes.
DURING_YEAR = ("Scolarité", 1_000_000)
DUE_MONTH = "Octobre"

PROGRAMMES = (
    {
        "title": "Médecine", "years": 7, "diploma": "Doctorat en Médecine",
        "description": (
            "<p>Le doctorat en médecine forme des médecins autonomes et éthiques, "
            "experts en diagnostic, traitement et gestion des maladies.</p>"
            "<p>Il intègre la recherche scientifique à la pratique, prépare à l'évolution "
            "technologique, encourage une approche centrée sur le patient et renforce "
            "le leadership dans les systèmes de santé.</p>"
        ),
    },
    {
        "title": "Pharmacie", "years": 7, "diploma": "Doctorat en Pharmacie",
        "description": (
            "<p>Le doctorat en pharmacie forme des professionnels de la santé compétents "
            "en soins pharmaceutiques et en gestion des médicaments.</p>"
            "<p>Il allie théorie et pratique, avec un accent sur la recherche, l'éthique "
            "et l'application clinique. Les diplômés peuvent travailler dans des pharmacies, "
            "hôpitaux, l'industrie pharmaceutique et la recherche.</p>"
        ),
    },
    {
        "title": "Chirurgie dentaire", "years": 6, "diploma": "Doctorat en Chirurgie Dentaire",
        "description": (
            "<p>Le doctorat en chirurgie dentaire prépare des praticiens capables "
            "d'exercer la médecine bucco-dentaire avec autonomie et rigueur clinique.</p>"
            "<p>La formation allie sciences fondamentales, pratiques cliniques et éthique "
            "professionnelle sur six années.</p>"
        ),
    },
)


class Command(BaseCommand):
    help = "Applique les durées et frais ESMed validés (Médecine 7 ans, Pharmacie 7 ans, Chirurgie dentaire 6 ans)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Affiche le bilan sans rien enregistrer.")

    def handle(self, *args, **options):
        self.counts = Counter()
        try:
            with transaction.atomic():
                self._apply()
                if options["dry_run"]:
                    raise _DryRun
        except _DryRun:
            self.stdout.write(self.style.WARNING("--dry-run : aucune modification enregistrée."))
        summary = ", ".join(f"{key} : {value}" for key, value in sorted(self.counts.items())) or "aucun changement"
        self.stdout.write(self.style.SUCCESS(f"Bilan ESMed — {summary}"))

    def _note(self, key, message=None):
        self.counts[key] += 1
        if message:
            self.stdout.write(f"  {message}")

    def _apply(self):
        school = School.objects.filter(code="ESMED").first()
        if school is None:
            institution = Institution.objects.first()
            if institution is None:
                raise CommandError("Aucune institution : lancer d'abord initialiser_catalogue_ufhob.")
            school = School.objects.create(
                institution=institution, code="ESMED", short_name="ESMed", order=1,
                official_name="École des Sciences Médicales Félix Houphouët Boigny",
            )
            self._note("écoles créées", "École ESMED créée")

        cycle, created = Cycle.objects.get_or_create(
            name="Doctorat", defaults={"min_duration_years": 5, "max_duration_years": 7, "theme": "dark"},
        )
        if created:
            self._note("cycles créés")
        if cycle.max_duration_years < 7:
            cycle.max_duration_years = 7
            cycle.save(update_fields=["max_duration_years"])
            self._note("cycles mis à jour", "Cycle Doctorat : durée maximale portée à 7 ans")
        filiere, created = Filiere.objects.get_or_create(name="Sciences de la Santé")
        if created:
            self._note("filières créées")

        for spec in PROGRAMMES:
            self._apply_programme(school, cycle, filiere, spec)

    def _apply_programme(self, school, cycle, filiere, spec):
        title, years = spec["title"], spec["years"]
        programme = Programme.objects.filter(school=school, title=title).first()
        if programme is None:
            diploma, _ = Diploma.objects.get_or_create(name=spec["diploma"], defaults={"level": "superieur"})
            programme = Programme.objects.create(
                title=title, school=school, filiere=filiere, cycle=cycle, diploma_awarded=diploma,
                duration_years=years, short_description=spec["diploma"], description=spec["description"],
            )
            self._note("programmes créés", f"{title} : programme créé")
        elif programme.duration_years != years:
            self._note("durées corrigées", f"{title} : durée {programme.duration_years} → {years} ans")
            programme.duration_years = years
            programme.save(update_fields=["duration_years", "updated_at"])
        if "sur cinq années" in (programme.description or "") and years == 6:
            programme.description = programme.description.replace("sur cinq années", "sur six années")
            programme.save(update_fields=["description", "updated_at"])
            self._note("descriptions corrigées", f"{title} : « cinq années » → « six années »")

        for number in range(1, years + 1):
            year, created = ProgrammeYear.objects.get_or_create(programme=programme, year_number=number)
            if created:
                self._note("années créées", f"{title} : année {number} créée")
            for label, amount in (REGISTRATION, DURING_YEAR):
                fee, created = Fee.objects.get_or_create(
                    programme_year=year, label=label, defaults={"amount": amount, "due_month": DUE_MONTH},
                )
                if created:
                    self._note("frais créés")
                elif fee.amount != amount:
                    self._note("frais corrigés", f"{title} année {number} : {label} {fee.amount} → {amount}")
                    fee.amount = amount
                    fee.save(update_fields=["amount"])
            extra = year.fees.exclude(label__in=(REGISTRATION[0], DURING_YEAR[0]))
            if extra.exists():
                self._note("frais hors décision conservés", f"{title} année {number} : autres frais conservés ({', '.join(extra.values_list('label', flat=True))}) — à vérifier")

        beyond = programme.years.filter(year_number__gt=years)
        if beyond.exists():
            self._note("années au-delà de la durée (conservées)", f"{title} : années {list(beyond.values_list('year_number', flat=True))} conservées, non affichées")

        for label, value in (("Durée", f"{years} ans"), ("Semestres", str(years * 2)), ("Crédits", str(years * 60))):
            fact = ProgrammeQuickFact.objects.filter(programme=programme, label=label).first()
            if fact and fact.value != value:
                self._note("faits rapides corrigés", f"{title} : {label} {fact.value} → {value}")
                fact.value = value
                fact.save(update_fields=["value"])


class _DryRun(Exception):
    pass
