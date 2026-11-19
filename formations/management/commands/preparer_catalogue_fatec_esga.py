"""Strict minimum for the official catalogue on an empty UFHOB database."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from core.models import Institution, School, SchoolBranch
from branches.models import Branch
from formations.campaign_catalogue import SCHOOLS


class Command(BaseCommand):
    help = 'Crée uniquement Institution, FATEC, ESGA et leur implantation Moribabougou si absents.'

    @transaction.atomic
    def handle(self, *args, **options):
        isolated = getattr(settings, 'UFHOB_CATALOGUE_ISOLATED_TEST', False) and connection.settings_dict['NAME'].startswith('test_ufhob_catalogue_')
        # Base de test Django (préfixe test_) : autorisée ; toute autre base que ufhob_db reste interdite.
        test_database = connection.settings_dict['NAME'].startswith('test_')
        if connection.vendor == 'postgresql' and connection.settings_dict['NAME'] != 'ufhob_db' and not (isolated or test_database):
            raise CommandError('Base cible UFHOB invalide.')
        institution = Institution.objects.first()
        if institution is None:
            institution = Institution.objects.create(name='Université Privée Félix Houphouët-Boigny – Mali', short_name='UFHOB-Mali', phone='+223 76 88 24 79', address='', city='', email='')
        branch = Branch.objects.filter(code='MBG').first()
        if branch is None:
            branch, _ = Branch.objects.get_or_create(slug='moribabougou', defaults={'name':'Moribabougou','code':'MBG','city':'Bamako'})
        for code, name in SCHOOLS.items():
            school, created = School.objects.get_or_create(institution=institution, code=code, defaults={'short_name':code,'official_name':name,'is_active':True})
            SchoolBranch.objects.get_or_create(school=school,branch=branch)
            self.stdout.write(f'{code} : {"créée" if created else "conservée"}')
        self.stdout.write('Préparation minimale terminée ; références existantes conservées.')
