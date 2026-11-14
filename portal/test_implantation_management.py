"""Regression checks for the DG and Superadmin SchoolBranch editors."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from branches.models import Branch
from core.models import SchoolBranch
from core.test_ufhob_phase2 import UFHOBPhase2Tests
from portal.dg.forms import DgBranchForm
from admissions.views import _build_school_campus_cards


@override_settings(AXES_ENABLED=False)
class ImplantationManagementTests(TestCase):
    make_user = staticmethod(UFHOBPhase2Tests.make_user)

    @classmethod
    def setUpTestData(cls):
        UFHOBPhase2Tests.setUpTestData.__func__(cls)
        cls.admin = get_user_model().objects.create_superuser('implantation-admin', password='test')

    def setUp(self):
        self.client.force_login(self.global_user)

    def campus_data(self, **extra):
        return dict(name='Campus recette', code='RECETTE', slug='recette', city='Test',
                    is_active='on', accepts_online_registration='on', **extra)

    def test_global_campus_without_school(self):
        response = self.client.post(reverse('accounts_portal:dg_branch_save'), self.campus_data())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Branch.objects.get(code='RECETTE').school_branches.exists())

    def test_context_school_is_preserved_even_if_omitted(self):
        url = reverse('accounts_portal:dg_branch_save')
        response = self.client.post(f'{url}?scope_school_id={self.schools[0].pk}&academic_year_id={self.year.pk}', self.campus_data())
        self.assertEqual(response.status_code, 200)
        self.assertTrue(SchoolBranch.objects.filter(school=self.schools[0], branch__code='RECETTE', is_active=True).exists())
        self.assertNotIn('scope_school_id', response.json()['context_params'])

    def test_multi_school_sync_preserves_history_and_reactivates(self):
        url = reverse('accounts_portal:dg_branch_save')
        data = self.campus_data(schools=[s.pk for s in self.schools])
        self.assertEqual(self.client.post(url, data).status_code, 200)
        campus = Branch.objects.get(code='RECETTE')
        original = dict(campus.school_branches.values_list('school_id', 'pk'))
        data.update(branch_id=campus.pk, schools=[self.schools[0].pk])
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertEqual(campus.school_branches.filter(is_active=True).count(), 1)
        data['schools'] = list(original)
        self.assertEqual(self.client.post(url, data).status_code, 200)
        self.assertEqual(dict(campus.school_branches.values_list('school_id', 'pk')), original)
        self.assertEqual(campus.school_branches.filter(is_active=True).count(), 3)

    def test_invalid_school_rejected_without_creating_campus(self):
        response = self.client.post(reverse('accounts_portal:dg_branch_save'), self.campus_data(schools=['999999']))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Branch.objects.filter(code='RECETTE').exists())

    def test_form_rolls_back_campus_if_sync_fails(self):
        form = DgBranchForm(self.campus_data(schools=[self.schools[0].pk]))
        self.assertTrue(form.is_valid(), form.errors)
        with patch('core.services.implantations.sync_branch_schools', side_effect=RuntimeError('failure')):
            with self.assertRaises(RuntimeError):
                form.save()
        self.assertFalse(Branch.objects.filter(code='RECETTE').exists())

    def test_global_attach_form_and_forged_school(self):
        url = reverse('accounts_portal:dg_implantation_editor')
        self.assertContains(self.client.get(url), 'name="school"')
        self.assertEqual(self.client.post(url, {'school': '999999', 'branch': self.b.pk}).status_code, 404)
        self.assertEqual(self.client.post(url, {'school': 'invalid', 'branch': self.b.pk}).status_code, 400)
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        self.assertEqual(self.client.post(url, {'school': self.schools[1].pk, 'branch': self.b.pk, 'is_active': 'on'}).status_code, 200)

    def test_inactive_pair_selectable_on_shared_campus_and_reactivated(self):
        school = self.schools[1]
        link = SchoolBranch.objects.create(school=school, branch=self.b, is_active=False)
        url = reverse('accounts_portal:dg_implantation_editor')
        response = self.client.get(url, {'school_id': school.pk})
        self.assertIn(self.b, response.context['form'].fields['branch'].queryset)
        data = {'school_id': school.pk, 'branch': self.b.pk, 'is_active': 'on'}
        self.assertEqual(self.client.post(url, data).status_code, 200)
        link.refresh_from_db()
        self.assertTrue(link.is_active)
        self.assertEqual(self.client.post(url, data).status_code, 400)
        self.assertEqual(SchoolBranch.objects.filter(school=school, branch=self.b).count(), 1)

    def test_school_editor_syncs_multiple_campuses(self):
        school = self.schools[1]
        response = self.client.post(reverse('accounts_portal:dg_school_editor'), {
            'school_id': school.pk, 'code': school.code, 'short_name': school.short_name,
            'order': 0, 'is_active': 'on', 'branches': [self.a.pk, self.b.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(school.school_branches.filter(is_active=True).count(), 2)

    def test_funnel_only_uses_active_pairs_for_each_school(self):
        self.assertEqual({row['id'] for row in _build_school_campus_cards(self.schools[0])}, {self.a.pk, self.b.pk})
        self.assertEqual({row['id'] for row in _build_school_campus_cards(self.schools[1])}, {self.a.pk})
        SchoolBranch.objects.filter(school=self.schools[0], branch=self.b).update(is_active=False)
        self.assertEqual({row['id'] for row in _build_school_campus_cards(self.schools[0])}, {self.a.pk})

    def test_superadmin_campus_uses_same_sync(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('superadmin:branch_create'), self.campus_data(schools=[s.pk for s in self.schools]))
        self.assertEqual(response.status_code, 302)
        campus = Branch.objects.get(code='RECETTE')
        self.assertEqual(campus.school_branches.filter(is_active=True).count(), 3)
        response = self.client.post(reverse('superadmin:branch_edit', args=[campus.pk]), self.campus_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(campus.school_branches.count(), 3)
        self.assertFalse(campus.school_branches.filter(is_active=True).exists())

    def test_superadmin_school_and_explicit_reactivation(self):
        self.client.force_login(self.admin)
        school = self.schools[1]
        response = self.client.post(reverse('superadmin:public_school_edit', args=[school.pk]), {
            'code': school.code, 'short_name': school.short_name, 'order': 0,
            'is_active': 'on', 'branches': [self.a.pk, self.b.pk],
        })
        self.assertEqual(response.status_code, 302)
        link = SchoolBranch.objects.get(school=school, branch=self.b)
        link.is_active = False
        link.save()
        url = reverse('superadmin:school_implantation_editor', args=[school.pk])
        self.assertContains(self.client.get(url), 'Campus existant')
        data = {'branch': self.b.pk, 'is_active': 'on', 'local_code': 'TEST'}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        link.refresh_from_db()
        self.assertTrue(link.is_active)
        self.assertEqual(link.local_code, 'TEST')
        self.assertEqual(self.client.post(url, data).status_code, 400)

    def test_superadmin_permission_and_invalid_identifier(self):
        self.assertEqual(self.client.post(reverse('superadmin:branch_create'), self.campus_data()).status_code, 302)
        self.assertFalse(Branch.objects.filter(code='RECETTE').exists())
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(reverse('superadmin:branch_create'), self.campus_data(schools=['999999'])).status_code, 400)
        self.assertFalse(Branch.objects.filter(code='RECETTE').exists())

    def test_superadmin_creates_school_with_multiple_campuses_and_rejects_duplicate(self):
        self.client.force_login(self.admin)
        url = reverse('superadmin:public_school_create')
        data = {'code': 'recette', 'short_name': 'Recette', 'order': 0,
                'is_active': 'on', 'branches': [self.a.pk, self.b.pk]}
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(SchoolBranch.objects.filter(school__code='RECETTE', is_active=True).count(), 2)
        self.assertContains(self.client.post(url, data), 'Ce code est déjà utilisé')

    def test_global_school_field_cannot_escape_selected_scope(self):
        url = reverse('accounts_portal:dg_implantation_editor')
        response = self.client.post(f'{url}?scope_school_id={self.schools[0].pk}', {
            'school': self.schools[1].pk, 'branch': self.b.pk, 'is_active': 'on',
        })
        self.assertEqual(response.status_code, 404)
