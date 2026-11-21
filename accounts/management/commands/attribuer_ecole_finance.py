"""T6-d — répartir l'existant financier par école.

    python manage.py attribuer_ecole_finance --dry-run   (par défaut, n'écrit rien)
    python manage.py attribuer_ecole_finance --apply

Règles (dans l'ordre, rien n'est inventé) :
1. enregistrement lié (paiement → inscription → formation → école, salarié,
   dépense, don, clôture, référence source du mouvement) ;
2. campus qui n'accueille qu'une seule école active → cette école ;
3. école du compte qui a créé la ligne, si elle est présente sur le campus
   (désactivable avec --sans-acteur).
Ne remplit que les lignes sans école. Les clôtures et versements bancaires
validés/clos ne sont pas touchés sans --inclure-clotures (date de bascule).
Les lignes restantes sont listées pour répartition manuelle.
"""

from collections import Counter

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.services.finance_school import (
    _school_on_branch,
    record_school_id,
    resolve_finance_school_id,
)

# Ordre : les sources d'abord, les lignes qui en dépendent ensuite.
ORDER = (
    "accounts.BranchExpense",
    "accounts.PayrollEntry",
    "accounts.TeacherHonorariumEntry",
    "accounts.Donation",
    "accounts.BranchMonthlyClosure",
    "accounts.BranchBankTransfer",
    "accounts.BranchCashMovement",
    "accounts.PaymentSignatureSession",
    "accounts.BranchCashRegisterSession",
    "accounts.BranchWallet",
    "accounts.SensitiveActionRequest",
    "accounts.FinancialAuditLog",
    "payments.FinancialLog",
)
FROZEN_STATUSES = {
    "accounts.branchmonthlyclosure": {"validated", "closed"},
    "accounts.branchbanktransfer": {"validated"},
}


def _single_school_by_branch():
    from core.models import SchoolBranch

    schools = {}
    for branch_id, school_id in SchoolBranch.objects.filter(
        is_active=True, school__is_active=True,
    ).values_list("branch_id", "school_id"):
        schools.setdefault(branch_id, set()).add(school_id)
    return {branch_id: ids.pop() for branch_id, ids in schools.items() if len(ids) == 1}


class Command(BaseCommand):
    help = "Attribue l'école aux enregistrements financiers qui n'en ont pas (T6)."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", help="Simulation (par défaut).")
        mode.add_argument("--apply", action="store_true", help="Écrit les écoles trouvées.")
        parser.add_argument("--sans-acteur", action="store_true", help="N'utilise pas l'école du créateur.")
        parser.add_argument("--inclure-clotures", action="store_true",
                            help="Traite aussi les clôtures et versements déjà validés.")
        parser.add_argument("--limite-liste", type=int, default=20, help="Lignes non attribuées affichées par modèle.")

    def handle(self, *args, **options):
        apply = options["apply"]
        single = _single_school_by_branch()
        total_set = 0
        total_left = 0
        try:
            with transaction.atomic():
                for label in ORDER:
                    set_count, left = self._process(label, single, options, apply)
                    total_set += set_count
                    total_left += left
                if not apply:
                    raise _DryRun
        except _DryRun:
            pass
        mode = "APPLIQUÉ" if apply else "SIMULATION (rien n'est écrit ; relancer avec --apply)"
        self.stdout.write(self.style.SUCCESS(
            f"{mode} — {total_set} ligne(s) attribuée(s), {total_left} à répartir à la main."
        ))

    def _process(self, label, single, options, apply):
        model = apps.get_model(label)
        lower = model._meta.label_lower
        queryset = model._base_manager.filter(school__isnull=True).order_by("pk")
        frozen = FROZEN_STATUSES.get(lower)
        skipped = 0
        if frozen and not options["inclure_clotures"]:
            skipped = queryset.filter(status__in=frozen).count()
            queryset = queryset.exclude(status__in=frozen)
        reasons = Counter()
        left = []
        for obj in queryset.iterator():
            branch_id = getattr(obj, "branch_id", None)
            school_id, reason = record_school_id(obj), "lien"
            if school_id and not _school_on_branch(school_id, branch_id):
                school_id = None
            if not school_id and branch_id in single:
                school_id, reason = single[branch_id], "campus mono-école"
            if not school_id:
                school_id = resolve_finance_school_id(
                    obj, use_context=False, use_actor=not options["sans_acteur"],
                )
                reason = "créateur / rattachement"
            if not school_id:
                left.append(obj.pk)
                continue
            reasons[reason] += 1
            # update() : aucune logique de save()/signal relancée sur l'existant.
            model._base_manager.filter(pk=obj.pk, school__isnull=True).update(school_id=school_id)
        done = sum(reasons.values())
        detail = ", ".join(f"{k} {v}" for k, v in sorted(reasons.items())) or "-"
        line = f"{label}: {done} attribuée(s) ({detail}), {len(left)} restante(s)"
        if skipped:
            line += f", {skipped} clôturée(s)/validée(s) laissée(s) telles quelles"
        self.stdout.write(line)
        if left:
            shown = left[: options["limite_liste"]]
            more = "…" if len(left) > len(shown) else ""
            self.stdout.write(f"  à répartir (id) : {', '.join(map(str, shown))}{more}")
        return done, len(left)


class _DryRun(Exception):
    pass

