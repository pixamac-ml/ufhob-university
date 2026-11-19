"""Masque (ou réaffiche) une école sur le site public, sans rien supprimer (idempotent, réversible).

Même mécanisme que `masquer_esfe_public` :
- l'école passe `is_public=False` : menu, onglets /formations/, accueil, pied de page,
  plan du site et tunnel d'admission ne la proposent plus ;
- ses programmes passent `is_public=False` ; leurs URL publiques redirigent vers /formations/ ;
- l'école reste active en interne ; données, frais et dossiers sont conservés.

Exemples :
    python manage.py masquer_ecole_public --code ESMED --dry-run
    python manage.py masquer_ecole_public --code ESMED
    python manage.py masquer_ecole_public --code ESMED --reactiver
"""
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import School
from formations.models import Programme


class Command(BaseCommand):
    help = "Masque (ou réaffiche avec --reactiver) une école sur le site public, sans suppression."

    def add_arguments(self, parser):
        parser.add_argument("--code", required=True, help="Code de l'école (ex. ESMED).")
        parser.add_argument("--dry-run", action="store_true", help="Affiche le bilan sans rien enregistrer.")
        parser.add_argument("--reactiver", action="store_true", help="Réaffiche l'école et ses programmes actifs.")

    def handle(self, *args, **options):
        code = options["code"].strip()
        if code.upper() in ("FATEC", "ESGA"):
            raise CommandError("FATEC et ESGA font partie de la campagne : masquage refusé.")
        visible = options["reactiver"]
        school = School.objects.filter(code__iexact=code).first()
        if school is None:
            self.stdout.write(self.style.SUCCESS(f"Aucune école {code} en base : rien à faire."))
            return
        with transaction.atomic():
            programmes = Programme.objects.filter(school=school)
            if visible:
                programmes = programmes.filter(is_active=True, is_archived=False)
            changes = programmes.exclude(is_public=visible)
            n_programmes = changes.count()
            school_changed = school.is_public != visible
            self.stdout.write(f"  École {school.code} ({school.short_name}) : public={school.is_public} → {visible}")
            for title in changes.values_list("title", flat=True):
                self.stdout.write(f"  Programme « {title} » : public → {visible}")
            if options["dry_run"]:
                self.stdout.write(self.style.WARNING("--dry-run : aucune modification enregistrée."))
            else:
                if school_changed:
                    School.objects.filter(pk=school.pk).update(is_public=visible)
                changes.update(is_public=visible)
        action = "réaffichée" if visible else "masquée"
        self.stdout.write(self.style.SUCCESS(
            f"{school.short_name} {action} — écoles modifiées : {int(school_changed)}, programmes modifiés : {n_programmes}"
        ))
