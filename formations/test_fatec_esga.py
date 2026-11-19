import json
from io import StringIO
from django.test import TestCase, override_settings
from django.core.management import call_command
from core.models import Institution,School,SchoolBranch
from branches.models import Branch
from formations.models import Programme,Fee
from formations.fatec_esga import DOMAINS,ALIASES


@override_settings(ALLOWED_HOSTS=['testserver'],SECURE_SSL_REDIRECT=False)
class FatecEsgaCatalogueTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        institution=Institution.objects.create(name='UFHOB test',phone='test',email='',address='',city='')
        branch=Branch.objects.create(name='Campus de test',slug='campus-test',code='TST')
        for code in ['FATEC','ESGA','ESMED']:
            school=School.objects.create(institution=institution,code=code,short_name=code)
            SchoolBranch.objects.create(school=school,branch=branch)
        call_command('charger_catalogue_fatec_esga',stdout=StringIO(),stderr=StringIO())

    def test_command_idempotence_and_dry_run(self):
        ids=list(Programme.objects.values_list('pk',flat=True))
        output=StringIO();call_command('charger_catalogue_fatec_esga',stdout=output,stderr=StringIO())
        self.assertIn('créations=0',output.getvalue());self.assertIn('mises à jour=0',output.getvalue())
        self.assertEqual(ids,list(Programme.objects.values_list('pk',flat=True)))
        call_command('charger_catalogue_fatec_esga',dry_run=True,stdout=StringIO(),stderr=StringIO())
        self.assertEqual(Programme.objects.public().filter(school__code__in=['FATEC','ESGA']).count(),24)
        self.assertEqual(Programme.objects.filter(campaign_published=True).count(),8)

    def test_twenty_four_pages_content_fees_documents_scope(self):
        for code,title,base,alias in DOMAINS:
            for level in ['DUT','Licence','Master']:
                p=Programme.objects.get(slug=base+'-'+level.lower())
                self.assertEqual(p.school.code,code);self.assertEqual(p.title,f'{level} — {title}')
                self.assertEqual(p.cycle.name,level);self.assertEqual(p.diploma_awarded.name,level)
                self.assertEqual(p.duration_years,3 if level=='Licence' else 2)
                r=self.client.get(p.get_absolute_url());self.assertEqual(r.status_code,200)
                self.assertContains(r,'Candidater à cette formation');self.assertContains(r,'Demande manuscrite timbrée')
                self.assertContains(r,'costume complet');self.assertContains(r,'chaussures fermées')
                text=r.content.decode().replace('\u00a0',' ').replace('\u202f',' ')
                for amount in (['750 000 FCFA','850 000 FCFA'] if level=='Master' else ['375 000 FCFA' if level=='DUT' else '600 000 FCFA']):self.assertIn(amount,text)
                for forbidden in ['CAMES',"Diplôme reconnu par l'État",'univ-fhb-mali.org']:
                    self.assertNotIn(forbidden,text)
                self.assertEqual(p.required_documents.count(),4)
                admission=self.client.get('/admissions/',{'formation':p.slug})
                self.assertEqual(json.loads(admission.context['initial_form_json'])['formation_slug'],p.slug)

    def test_legacy_redirects_and_admissions_preserve_tracking(self):
        for alias,target_slug in ALIASES.items():
            target=Programme.objects.get(slug=target_slug)
            for school in ['fatec','esga']:
                r=self.client.get(f'/formations/{school}/{alias}/?utm_source=facebook')
                self.assertEqual(r.status_code,301);self.assertEqual(r.url,target.get_absolute_url()+'?utm_source=facebook')
            r=self.client.get('/admissions/',{'formation':alias,'utm_source':'facebook','utm_campaign':'mission1'})
            state=json.loads(r.context['initial_form_json']);self.assertEqual(state['formation_slug'],target_slug)
            self.assertEqual(state['school_code'],target.school.code)
            self.assertEqual(r.context['campaign_tracking']['utm_source'],'facebook')

    def test_home_eight_licences_and_grouped_catalogues(self):
        r=self.client.get('/');self.assertEqual(len(r.context['formations_home']),8)
        for p in r.context['formations_home']:self.assertEqual(p.cycle.name,'Licence')
        for url in ['/ecoles/fatec/','/ecoles/esga/','/formations/']:
            r=self.client.get(url);self.assertEqual(r.status_code,200)
            self.assertContains(r,'DUT');self.assertContains(r,'Licence');self.assertContains(r,'Master')

    def test_existing_campaign_row_and_application_survive(self):
        from admissions.models import Candidature
        from django.core import serializers
        canonical=Programme.objects.get(slug='marketing-communication-licence')
        source=Programme.objects.create(title='Marketing et Communication',slug='marketing-communication',school=School.objects.get(code='FATEC'),filiere=canonical.filiere,description='Texte source validé.',short_description='Accroche source',career_opportunities='Chargé de communication',campaign_published=True)
        candidature=Candidature.objects.create(programme=source,branch=Branch.objects.first(),academic_year='2026-2027',first_name='Test',last_name='Historique',birth_date='2000-01-01',email='historique@example.invalid')
        candidature.refresh_from_db()
        before=serializers.serialize('json',[candidature])
        call_command('charger_catalogue_fatec_esga',stdout=StringIO(),stderr=StringIO())
        source.refresh_from_db();candidature.refresh_from_db()
        self.assertFalse(source.is_public);self.assertFalse(source.campaign_published)
        self.assertEqual(source.school.code,'FATEC')
        self.assertEqual(before,serializers.serialize('json',[candidature]))
        canonical.refresh_from_db();self.assertIn('Texte source validé.',canonical.description)
