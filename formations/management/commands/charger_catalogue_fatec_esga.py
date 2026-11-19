from collections import Counter
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from formations.models import Programme, Filiere, Cycle, Diploma, ProgrammeYear, Fee, RequiredDocument, ProgrammeRequiredDocument, ProgrammeTab, ProgrammeSection
from formations.fatec_esga import DOMAINS
from formations.campaign_catalogue import OFFERS
from core.models import School
from django.conf import settings


class Command(BaseCommand):
    help = 'Complète les 24 programmes FATEC/ESGA sans modifier les autres écoles ni les dossiers opérationnels.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        isolated = getattr(settings, 'UFHOB_CATALOGUE_ISOLATED_TEST', False) and connection.settings_dict['NAME'].startswith('test_ufhob_catalogue_')
        # Base de test Django (préfixe test_) : autorisée ; toute autre base que ufhob_db reste interdite.
        test_database = connection.settings_dict['NAME'].startswith('test_')
        if connection.vendor == 'postgresql' and connection.settings_dict['NAME'] != 'ufhob_db' and not (isolated or test_database):
            raise CommandError('Cible interdite : ufhob_db attendu.')
        self.counts = Counter()
        for code, title, base, alias in DOMAINS:
            try:
                school = School.objects.get(code=code, is_active=True)
            except School.DoesNotExist as exc:
                raise CommandError(f'École active manquante : {code}') from exc
            source = Programme.objects.filter(slug=alias).first() if alias else None
            reference = next((x for x in OFFERS if x[2] == alias), None)
            for level, duration in [('DUT', 2), ('Licence', 3), ('Master', 2)]:
                slug = base + '-' + level.lower()
                programme = Programme.objects.select_for_update().filter(slug=slug).first()
                if programme and programme.school_id != school.pk:
                    raise CommandError(f'{slug} : rattachement inattendu, aucun transfert automatique.')
                filiere = programme.filiere if programme else self.upsert(Filiere, {'name': title}, {})
                # Shared filières used outside this mission must not be renamed.
                if filiere.name != title:
                    if filiere.programmes.exclude(school__code__in=['FATEC', 'ESGA']).exists():
                        filiere = self.upsert(Filiere, {'name': title}, {})
                    else:
                        other = Filiere.objects.filter(name=title).exclude(pk=filiere.pk).first()
                        if other:
                            filiere = other
                        else:
                            self.save(filiere, {'name': title})
                cycle = programme.cycle if programme and programme.cycle_id else self.upsert(Cycle, {'name': level}, {}, create_extra={'min_duration_years': duration, 'max_duration_years': duration})
                if cycle.name != level or not cycle.is_active or not filiere.is_active:
                    raise CommandError(f'{slug} : référentiel incohérent/inactif.')
                diploma = self.upsert(Diploma, {'name': level}, {}, create_extra={'level': 'superieur'})
                if diploma.level != 'superieur':
                    raise CommandError(f'Diplôme partagé {level} incohérent : aucune réécriture automatique.')
                if not programme:
                    programme = Programme(slug=slug, school=school)
                values = dict(title=f'{level} — {title}', filiere=filiere, cycle=cycle, diploma_awarded=diploma,
                    duration_years=duration, delivery_modes='Présentiel ou en ligne', registration_notice='Inscriptions ouvertes — Rentrée académique 2026-2027',
                    is_active=True, is_public=True, admissions_open=True, campaign_published=level == 'Licence')
                if programme.is_archived:
                    raise CommandError(f'{slug} archivé : validation nécessaire avant réactivation.')
                if alias:
                    desc = source.description if source and source.description else reference[4]
                    careers = source.career_opportunities if source and source.career_opportunities else reference[5]
                    intro = source.short_description if source and source.short_description else reference[3]
                    values.update(description=f'{level} — {title}. {desc}', career_opportunities=careers, short_description=f'{level} — {intro}', meta_title=f'{level} — {title} | UFHOB'[:70], meta_description=f'{level} — {intro}'[:160])
                else:
                    additional = {
                        'genie-logiciel': (
                            "Découvrez les méthodes de conception et de développement des logiciels. Apprenez à analyser un besoin, à programmer et à tester des applications fiables. Développez une démarche rigoureuse du travail en équipe sur des projets concrets.",
                            "Développeur d'applications\nDéveloppeur web et mobile\nTesteur logiciel"),
                        'audiovisuel-multimedia': (
                            "Découvrez les techniques de création et de production de contenus audiovisuels et multimédias. Apprenez les bases de la prise de vue, du son, du montage et du graphisme. Développez une approche créative et méthodique de la réalisation de projets.",
                            "Monteur vidéo\nOpérateur de prise de vue\nInfographiste multimédia"),
                    }
                    desc, careers = additional[base]
                    values.update(description=desc, career_opportunities=careers, short_description=desc.split('. ')[0] + '.', meta_title=f'{level} — {title} | UFHOB'[:70], meta_description=desc[:160])
                # A single source of editorial text for grouped catalogue cards.
                domain_description = desc
                if filiere.description != domain_description and filiere.programmes.exclude(school__code__in=['FATEC','ESGA']).exists():
                    raise CommandError(f'Filière partagée hors périmètre : {filiere.name}. Présentation conservée ; validation nécessaire.')
                self.save(filiere, {'description': domain_description})
                self.save(programme, values)
                schedules = [(400000,175000,175000),(450000,200000,200000)] if level == 'Master' else [(175000,100000,100000) if level == 'DUT' else (300000,150000,150000)]
                for year_number, amounts in enumerate(schedules, 1):
                    year = self.upsert(ProgrammeYear, {'programme':programme,'year_number':year_number}, {})
                    for label, amount in zip(['Inscription','Janvier','Mars'], amounts):
                        self.upsert(Fee, {'programme_year':year,'label':label}, {'amount':amount}, create_extra={'due_month':''})
                diploma_requirement = {'DUT':'Baccalauréat ou BT2','Licence':'DUT (ou équivalent)','Master':'Licence ou Maîtrise'}[level]
                names = ['Demande manuscrite timbrée', "Extrait d'acte de naissance ou jugement supplétif", f'Copie légalisée du diplôme requis : {diploma_requirement}', "4 photos d'identité"]
                expected=[]
                for name in names:
                    doc=self.upsert(RequiredDocument, {'name':name}, {}, create_extra={'is_mandatory':True})
                    expected.append(doc.pk)
                    self.upsert(ProgrammeRequiredDocument, {'programme':programme,'document':doc}, {})
                # Only reference requirements are replaced; uploaded candidature documents survive.
                stale=programme.required_documents.exclude(document_id__in=expected)
                self.counts['liens de pièces remplacés']+=stale.count()
                stale.delete()
                tab=self.upsert(ProgrammeTab, {'programme':programme,'slug':'conditions-catalogue'}, {'title':'Conditions pratiques','tab_type':'admission','is_active':True})
                conditions='Échéances payables au plus tard le 05 du mois. Frais non remboursables. Internat facultatif. Tenue exigée : costume complet et chaussures fermées.'
                self.upsert(ProgrammeSection, {'tab':tab,'title':'Conditions'}, {'content':conditions,'section_type':'text'})
                self.stdout.write(f'{slug} : {level}, {school.code}, {duration} ans, échéancier {[sum(x) for x in schedules]} FCFA')
            if source:
                self.save(source, {'is_public':False,'campaign_published':False})
        self.stdout.write('Bilan : '+', '.join(f'{k}={self.counts[k]}' for k in ['créations','mises à jour','inchangés','liens de pièces remplacés']))
        if options['dry_run']:
            transaction.set_rollback(True)
            self.stdout.write('DRY-RUN : aucune modification conservée.')

    def save(self, obj, values):
        new=obj.pk is None
        changed=any(getattr(obj,k)!=v for k,v in values.items())
        for key,value in values.items():setattr(obj,key,value)
        if new or changed:obj.save()
        self.counts['créations' if new else 'mises à jour' if changed else 'inchangés']+=1
        return obj

    def upsert(self, model, lookup, values, create_extra=None):
        obj=model.objects.filter(**lookup).first()
        if obj is None:obj=model(**lookup,**(create_extra or {}))
        return self.save(obj,values)
