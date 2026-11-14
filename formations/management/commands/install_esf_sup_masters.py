"""UFHOB-only operational entry point; explicit apply after a read-only plan."""

import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from django.db import connection, transaction

from formations.esf_sup_masters import install_masters


class Command(BaseCommand):
    help = "Installe les Masters ESF Sup documentés, sans inventer campus, année ou valeurs EC."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--output", type=Path)

    def handle(self, *args, **options):
        if settings.DATABASES["default"]["NAME"] != "ufhob_db" or connection.vendor != "postgresql":
            raise CommandError("Cette commande opérationnelle est limitée à PostgreSQL ufhob_db.")
        try:
            with transaction.atomic():
                # SELECT FOR UPDATE is used by apply only; dry-run remains
                # nonmutating, while the command verifies the actual database.
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_database()")
                    if cursor.fetchone()[0] != "ufhob_db":
                        raise CommandError("La connexion ne cible pas ufhob_db.")
                result = install_masters(apply=options["apply"])
        except ValidationError as error:
            raise CommandError(str(error)) from error
        rendered = json.dumps(result, ensure_ascii=False, indent=2, default=str)
        if options["output"]:
            options["output"].write_text(rendered + "\n", encoding="utf-8")
        self.stdout.write(rendered)
