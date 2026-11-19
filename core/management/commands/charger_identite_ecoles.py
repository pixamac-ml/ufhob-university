"""Renseigne la description institutionnelle de FATEC et ESGA (idempotent).

Textes proposés, à faire valider par la direction. Un texte déjà présent
n'est jamais écrasé sans ``--force``. Aucune autre école n'est modifiée.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import School
from core.school_identity import SCHOOL_IDENTITY


class Command(BaseCommand):
    help = "Renseigne la description de FATEC et ESGA (n'écrase pas un texte existant sans --force)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Remplace une description déjà renseignée.")
        parser.add_argument("--dry-run", action="store_true", help="Affiche les changements sans écrire.")

    @transaction.atomic
    def handle(self, *args, force=False, dry_run=False, **options):
        updated = unchanged = kept = 0
        for code, identity in SCHOOL_IDENTITY.items():
            schools = list(School.objects.filter(code__iexact=code))
            if not schools:
                self.stdout.write(self.style.WARNING(f"{code} : école introuvable, ignorée."))
                continue
            for school in schools:
                current = (school.description or "").strip()
                target = identity["description"]
                if current == target:
                    unchanged += 1
                    self.stdout.write(f"{code} : déjà à jour.")
                    continue
                if current and not force:
                    kept += 1
                    self.stdout.write(f"{code} : description existante conservée (utiliser --force pour remplacer).")
                    continue
                updated += 1
                self.stdout.write(f"{code} : description {'à écrire' if dry_run else 'écrite'}.")
                if not dry_run:
                    school.description = target
                    school.save(update_fields=["description", "updated_at"])
        if dry_run:
            transaction.set_rollback(True)
        self.stdout.write(self.style.SUCCESS(
            f"Mises à jour : {updated} ; inchangées : {unchanged} ; conservées : {kept}"
            f"{' (simulation)' if dry_run else ''}."
        ))
