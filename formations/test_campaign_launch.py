"""Current campaign contract: eight Licences, canonical aliases, shared templates."""
from io import StringIO
import json
from django.test import TestCase
from django.core.management import call_command
from formations.fatec_esga import ALIASES
from formations.models import Programme


class CampaignCompatibilityTests(TestCase):
    def setUp(self):
        call_command('preparer_catalogue_fatec_esga', stdout=StringIO())
        call_command('charger_catalogue_fatec_esga', stdout=StringIO())

    def test_campaign_uses_canonical_licences(self):
        self.assertEqual(Programme.objects.filter(campaign_published=True).count(),8)
        for alias,slug in ALIASES.items():
            response=self.client.get('/admissions/',{'formation':alias,'utm_source':'facebook'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(json.loads(response.context['initial_form_json'])['formation_slug'],slug)

    def test_shared_templates_and_no_public_uncertainty_notice(self):
        for programme in Programme.objects.all():
            response=self.client.get(programme.get_absolute_url())
            self.assertTemplateUsed(response,'formations/detail.html')
            self.assertNotContains(response,'annualité')
            self.assertNotContains(response,'à confirmer')
