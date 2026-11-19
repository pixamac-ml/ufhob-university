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
        response = self.client.get('/universite/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'ESFé Sup')
        self.assertRedirects(self.client.get('/ecoles/ESFÉ/'), '/formations/', fetch_redirect_response=False)
        for item in self.source['programmes']:
            p = Programme.objects.get(pk=item['id'])
            self.assertRedirects(self.client.get(p.get_absolute_url()), '/formations/', fetch_redirect_response=False)
            self.assertFalse(p.admissions_open)
            self.assertEqual(list(p.years.order_by('year_number').values_list('year_number', flat=True)), [1, 2])
            self.assertEqual(p.years.get(year_number=1).fees.count(), 3)
            self.assertEqual(p.years.get(year_number=2).fees.count(), 3)
        for p in self.others:
            p.refresh_from_db()
            self.assertEqual(p.description, 'Texte existant')
            response = self.client.get(p.get_absolute_url())
            if p.school.code == 'ESMED':
                self.assertRedirects(response, '/formations/', fetch_redirect_response=False)
                continue
            self.assertEqual(response.status_code,200)
            self.assertEqual(p.years.get(year_number=1).fees.get().amount, 123456)
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
