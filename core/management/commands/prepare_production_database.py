from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.services.business_data_reset import assert_migrations_current, assert_safe_local_development_database
from core.services.production_database_reset import (
    build_production_reset_plan,
    delete_collected_media,
    execute_production_reset,
    validate_execute_plan,
)


def _postgres_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    candidate = Path(r"C:\Program Files\PostgreSQL\18\bin") / f"{name}.exe"
    return str(candidate) if candidate.exists() else None


def _create_verified_backup(*, identity: dict[str, str], backup_dir: Path) -> Path:
    pg_dump = _postgres_binary("pg_dump")
    pg_restore = _postgres_binary("pg_restore")
    if not pg_dump or not pg_restore:
        raise CommandError("pg_dump et pg_restore sont requis avant toute exécution.")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = backup_dir / f"backup-pre-production-reset-{timestamp}.dump"
    environment = os.environ.copy()
    password = identity.get("password")
    if password:
        environment["PGPASSWORD"] = password
    command = [
        pg_dump,
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--host", identity["host"],
        "--port", identity["port"],
        "--username", identity["user"],
        "--file", str(path),
        identity["name"],
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False, env=environment)
    if completed.returncode:
        raise CommandError("Sauvegarde PostgreSQL échouée : " + completed.stderr.strip())
    if not path.is_file() or path.stat().st_size == 0:
        raise CommandError("Sauvegarde absente ou vide : " + str(path))
    verified = subprocess.run([pg_restore, "--list", str(path)], capture_output=True, text=True, check=False)
    if verified.returncode:
        raise CommandError("Sauvegarde PostgreSQL illisible : " + verified.stderr.strip())
    return path


class Command(BaseCommand):
    help = "Prépare une base UFHOB de démonstration pour le chargement des données réelles."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Affiche le plan sans écrire (mode par défaut).")
        parser.add_argument("--execute", action="store_true", help="Exécute le plan après sauvegarde vérifiée.")
        parser.add_argument(
            "--confirm-production-reset",
            action="store_true",
            help="Confirmation explicite obligatoire avec --execute.",
        )
        parser.add_argument("--keep-user", action="append", default=[], metavar="USERNAME")
        parser.add_argument("--backup-file", type=Path, help="Dump complet déjà créé avant le dry-run.")
        parser.add_argument("--media-backup", type=Path, help="Archive ZIP média vérifiée avant suppression.")
        parser.add_argument("--keep-class", action="append", default=[], type=int, metavar="ID")
        memo = parser.add_mutually_exclusive_group()
        memo.add_argument("--remove-memoires", action="store_true", help="Supprime explicitement les mémoires et consultations demo.")
        memo.add_argument("--keep-memoires", action="store_true", help="Conserve explicitement les mémoires existants.")
        parser.add_argument(
            "--backup-dir",
            type=Path,
            default=Path("backups"),
            help="Répertoire de la sauvegarde PostgreSQL horodatée.",
        )

    def _print_plan(self, plan, identity):
        self.stdout.write(self.style.WARNING(
            f"Base ciblée : {identity['name']} sur {identity['host']}:{identity['port']} ({identity['engine']})"
        ))
        self.stdout.write("\nUSERS — candidats bootstrap (aucun n'est choisi automatiquement) :")
        for item in plan.candidate_users:
            if item["is_superuser"] or item["position"] == "executive_director":
                self.stdout.write(
                    "  - {username} | {email} | position={position} | superuser={is_superuser} | campus={campus}".format(**item)
                )
        self.stdout.write("\nRÉFÉRENTIEL À CONSERVER :")
        for label, rows in plan.structural_keep.items():
            self.stdout.write(f"  - {label}: {len(rows)}")
            for row in rows:
                self.stdout.write("      " + str(row))
        self.stdout.write("\nRÉFÉRENTIEL LEGACY À SUPPRIMER :")
        for label, rows in plan.structural_remove.items():
            self.stdout.write(f"  - {label}: {len(rows)}")
            for row in rows:
                self.stdout.write("      " + str(row))
        self.stdout.write("\nOPÉRATIONNEL À SUPPRIMER :")
        for label, count in plan.delete_counts.items():
            self.stdout.write(f"  - {label}: {count}")
        self.stdout.write(f"  - Fichiers métier candidats: {len(plan.media_files)}")
        self.stdout.write("\nCLASSES OPÉRATIONNELLES À SUPPRIMER :")
        for item in plan.operational_classes:
            self.stdout.write("  - " + str(item))
        if plan.media_files:
            self.stdout.write("\nFICHIERS MÉTIER CANDIDATS À SUPPRIMER :")
            for _storage, name in plan.media_files:
                self.stdout.write("  - " + name)
        if plan.structural_unknown:
            self.stdout.write(self.style.ERROR("\nUNKNOWN / PROTECTED — exécution bloquée :"))
            for label, rows in plan.structural_unknown.items():
                self.stdout.write(f"  - {label}: {rows}")
        self.stdout.write("\nComptes explicitement protégés : " + (", ".join(plan.protected_usernames) or "aucun"))

    def handle(self, *args, **options):
        if options["dry_run"] and options["execute"]:
            raise CommandError("Choisissez --dry-run ou --execute, pas les deux.")
        identity = assert_safe_local_development_database()
        if identity["name"] != "ufhob_db":
            raise CommandError("Reset refusé : seule la base ufhob_db est autorisée.")
        assert_migrations_current()
        from django.db import connection

        config = connection.settings_dict
        backup_identity = {
            **identity,
            "user": str(config.get("USER") or ""),
            "password": str(config.get("PASSWORD") or ""),
        }
        plan = build_production_reset_plan(
            preserve_usernames=options["keep_user"],
            keep_class_ids=options["keep_class"],
            memoire_disposition=("remove" if options["remove_memoires"] else "keep" if options["keep_memoires"] else "unknown"),
        )
        self._print_plan(plan, identity)

        if not options["execute"]:
            self.stdout.write(self.style.SUCCESS("\nDRY RUN : aucune donnée ni fichier n'a été modifié."))
            return
        if not options["confirm_production_reset"]:
            raise CommandError("--confirm-production-reset est obligatoire avec --execute.")

        # Validate every non-destructive precondition before a backup or write.
        validate_execute_plan(plan)
        from core.management.commands.reset_business_data import _validate_backup
        backup = options["backup_file"]
        if backup:
            backup = backup.resolve()
            _validate_backup(backup, identity["name"])
        else:
            backup = _create_verified_backup(identity=backup_identity, backup_dir=options["backup_dir"].resolve())
        media_backup = options["media_backup"]
        if not media_backup or not media_backup.is_file():
            raise CommandError("Archive média obligatoire : --media-backup.")
        with zipfile.ZipFile(media_backup) as archive:
            if not archive.namelist() or archive.testzip():
                raise CommandError("Archive média vide ou corrompue.")
        self.stdout.write(self.style.SUCCESS(
            f"Sauvegarde vérifiée : {backup} ({backup.stat().st_size} octets)"
        ))
        deleted = execute_production_reset(plan)
        media_deleted, media_failures = delete_collected_media(plan.media_files)
        self.stdout.write(self.style.SUCCESS("Reset UFHOB terminé."))
        for label, count in deleted.items():
            self.stdout.write(f"  - {label}: {count}")
        self.stdout.write(f"  - Fichiers supprimés: {media_deleted}")
        if media_failures:
            self.stderr.write(self.style.WARNING("Fichiers non supprimés : " + "; ".join(media_failures)))
