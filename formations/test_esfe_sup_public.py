import json
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from formations.esfe_sup_public import SOURCE, install_public_content
from formations.models import Programme, ProgrammeYear, Fee, Cycle, Diploma, Filiere
from core.models import Institution, School, SchoolBranch
from branches.models import Branch
from academics.models import AcademicClass, AcademicYear, Semester, UE, EC


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class ESFePublicContentTests(TestCase):
    def setUp(self):
        self.source = json.loads(SOURCE.read_text(encoding='utf-8'))
        institution = Institution.objects.create(name='Université test', short_name='UFHOB', address='Test', city='Test', phone='000', email='test@example.test')
        self.school = School.objects.create(pk=4, institution=institution, code='ESFÉ', short_name='ESFé Sup')
        self.campus = Branch.objects.create(code='MBG', name='Moribabougou', slug='moribabougou')
        SchoolBranch.objects.create(school=self.school, branch=self.campus)
        cycle = Cycle.objects.create(name='Master', min_duration_years=2, max_duration_years=2)
        diploma = Diploma.objects.create(name='Master', level='superieur')
        filiere = Filiere.objects.create(name='Sciences de la Santé')
        for item in self.source['programmes']:
            p = Programme.objects.create(pk=item['id'], title='Master — '+item['formation'], school=self.school,
                cycle=cycle, diploma_awarded=diploma, filiere=filiere, duration_years=2,
                short_description='Avant', description='Avant', is_public=True, admissions_open=False)
            # IDs and creation dates intentionally oppose the displayed order.
            ProgrammeYear.objects.create(programme=p, year_number=2)
            ProgrammeYear.objects.create(programme=p, year_number=1)
        self.others = []
        for code in ('ESMED', 'ESGA', 'FATEC'):
            school = School.objects.create(institution=institution, code=code, short_name=code)
            p = Programme.objects.create(title='Programme '+code, school=school, cycle=cycle,
                diploma_awarded=diploma, filiere=filiere, duration_years=2, description='Texte existant', short_description='Résumé existant')
            year = ProgrammeYear.objects.create(programme=p, year_number=1)
            Fee.objects.create(programme_year=year, label='Frais existants', amount=123456, due_month='Octobre')
            self.others.append(p)

    def test_fees_exact_totals_dry_run_and_idempotence(self):
        before = Fee.objects.count()
        plan = install_public_content()
        self.assertEqual(plan['fees_created'], 42)
        self.assertEqual(Fee.objects.count(), before)
        result = install_public_content(apply=True)
        self.assertEqual(result['fees_created'], 42)
        self.assertEqual(Programme.objects.filter(school=self.school).count(), 7)
        self.assertEqual(ProgrammeYear.objects.filter(programme__school=self.school).count(), 14)
        for item in self.source['programmes']:
            p = Programme.objects.get(pk=item['id'])
            for n in (1, 2):
                fees = {f.label: f.amount for f in p.years.get(year_number=n).fees.all()}
                expected = {'Inscription':600000,'Janvier':300000,'Mars':300000} if p.pk >= 55 and n == 2 else {'Inscription':410000,'Janvier':200000,'Mars':200000}
                self.assertEqual(fees, expected)
                self.assertEqual(sum(fees.values()), 1200000 if p.pk >= 55 and n == 2 else 810000)
            self.assertTrue(p.description and p.learning_outcomes and p.career_opportunities)
            self.assertEqual(p.competence_blocks.get().items.count(), 3)
        repeat = install_public_content(apply=True)
        self.assertTrue(all(value == 0 for key,value in repeat.items() if key.endswith(('created','updated'))))
        for model in (AcademicYear, AcademicClass, Semester, UE, EC):
            self.assertFalse(model.objects.exists())

    def test_public_pages_order_amounts_and_other_schools(self):
        install_public_content(apply=True)
        for url in ('/universite/', '/ecoles/ESFÉ/'):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'ESFé Sup')
        school_page = self.client.get('/ecoles/ESFÉ/')
        self.assertContains(school_page, 'Moribabougou')
        self.assertNotContains(school_page, 'src=""')
        self.assertEqual(len(school_page.context['programmes']), 7)
        self.assertFalse(school_page.context['school_can_apply'])
        for item in self.source['programmes']:
            p = Programme.objects.get(pk=item['id'])
            response = self.client.get(p.get_absolute_url())
            self.assertEqual(response.status_code, 200)
            html = response.content.decode()
            self.assertLess(html.index('1re année'), html.index('2e année'))
            self.assertLess(html.index('data-cursus-year="1"'), html.index('data-cursus-year="2"'))
            self.assertEqual([x['year'].year_number for x in response.context['years_with_totals']], [1,2])
            self.assertEqual([[f.label for f in x['fees']] for x in response.context['years_with_totals']], [['Inscription','Janvier','Mars']]*2)
            for term in ('Objectifs', 'Compétences développées', 'Débouchés', 'Frais de formation', '410 000 F CFA', '200 000 F CFA', '810 000 F CFA', 'Moribabougou'):
                self.assertContains(response, term)
            if p.pk >= 55:
                for amount in ('600 000 F CFA','300 000 F CFA','1 200 000 F CFA'):
                    self.assertContains(response, amount)
            self.assertContains(response, '<h1', html=False)
            self.assertContains(response, p.title)
            self.assertFalse(response.context['can_apply'])
        for p in self.others:
            p.refresh_from_db()
            self.assertEqual(p.description, 'Texte existant')
            response = self.client.get(p.get_absolute_url())
            self.assertEqual(response.status_code,200)
            self.assertContains(response, '123 456 F CFA')
            self.assertNotContains(response,'810 000 F CFA')
            self.assertNotContains(response,'1 200 000 F CFA')
        self.assertEqual(Fee.objects.exclude(programme_year__programme__school=self.school).count(), 3)

    def test_unexpected_existing_fee_stops_without_deleting(self):
        year = ProgrammeYear.objects.get(programme_id=51, year_number=1)
        fee = Fee.objects.create(programme_year=year,label='Autre échéance',amount=2500,due_month='Juin')
        with self.assertRaises(ValidationError):
            install_public_content(apply=True)
        self.assertTrue(Fee.objects.filter(pk=fee.pk).exists())
        self.assertEqual(Programme.objects.get(pk=51).description, 'Avant')
        self.school.refresh_from_db()
        self.assertEqual(self.school.description, '')
