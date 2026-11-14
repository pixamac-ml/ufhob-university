import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError, ObjectDoesNotExist
from django.db import connection, transaction
from formations.esfe_sup_public import install_public_content


class Command(BaseCommand):
    help = 'Persiste les contenus et tarifs documentés des sept Masters ESFé Sup.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--output', type=Path)

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql' or connection.settings_dict['NAME'] != 'ufhob_db':
            raise CommandError('Commande limitée à PostgreSQL ufhob_db.')
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute('SELECT current_database()')
                    if cursor.fetchone()[0] != 'ufhob_db':
                        raise CommandError('Mauvaise base connectée.')
                result = install_public_content(apply=options['apply'])
        except (ValidationError, ObjectDoesNotExist) as error:
            raise CommandError(str(error)) from error
        rendered = json.dumps(result, ensure_ascii=False, indent=2)
        if options['output']:
            options['output'].write_text(rendered+'\n', encoding='utf-8')
        self.stdout.write(rendered)
