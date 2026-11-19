"""Masque ESFé Sup sur le site public, sans rien supprimer (idempotent, réversible).

- l'école passe `is_public=False` : elle disparaît du menu, des onglets /formations/,
  des cartes de l'accueil, du pied de page, du plan du site et du tunnel d'admission ;
- ses programmes passent `is_public=False` ; leurs anciennes URL redirigent vers /formations/ ;
- l'école reste active en interne (dossiers, étudiants, historique inchangés).

`--reactiver` rétablit la visibilité de l'école et de ses programmes actifs non archivés.
Base vide : aucune école ESFé Sup → rien à faire, la commande le signale.
"""
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from core.models import School
from formations.models import Programme

ESFE_SUP = Q(code__in=("ESFÉ", "ESFE", "ESFE_SUP", "ESFESUP")) | Q(short_name__iexact="ESFé Sup")


class Command(BaseCommand):
    help = "Masque (ou réaffiche avec --reactiver) ESFé Sup sur le site public, sans suppression."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Affiche le bilan sans rien enregistrer.")
        parser.add_argument("--reactiver", action="store_true", help="Réaffiche l'école et ses programmes actifs.")

    def handle(self, *args, **options):
        visible = options["reactiver"]
        schools = list(School.objects.filter(ESFE_SUP))
        if not schools:
            self.stdout.write(self.style.SUCCESS("Aucune école ESFé Sup en base : rien à faire."))
            return
        with transaction.atomic():
            school_changes = [s for s in schools if s.is_public != visible]
            programmes = Programme.objects.filter(school__in=schools)
            if visible:
                programmes = programmes.filter(is_active=True, is_archived=False)
            programme_changes = programmes.exclude(is_public=visible)
            n_programmes = programme_changes.count()
            for school in schools:
                self.stdout.write(f"  École {school.code} ({school.short_name}) : public={school.is_public} → {visible}")
            for title in programme_changes.values_list("title", flat=True):
                self.stdout.write(f"  Programme « {title} » : public → {visible}")
            if options["dry_run"]:
                self.stdout.write(self.style.WARNING("--dry-run : aucune modification enregistrée."))
            else:
                School.objects.filter(pk__in=[s.pk for s in school_changes]).update(is_public=visible)
                programme_changes.update(is_public=visible)
        action = "réaffichée" if visible else "masquée"
        self.stdout.write(self.style.SUCCESS(
            f"ESFé Sup {action} — écoles modifiées : {len(school_changes)}, programmes modifiés : {n_programmes}"
        ))
