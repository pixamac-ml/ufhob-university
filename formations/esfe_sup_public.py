"""Persist the authorized public copy and institutional fees; never used by views."""
import json
from pathlib import Path
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from formations.models import Programme, Fee, CompetenceBlock, CompetenceItem
from formations.esf_sup_masters import find_school, programme_key, normalize

SOURCE = Path(settings.BASE_DIR) / 'docs/esfe_sup_public_content.json'


@transaction.atomic
def install_public_content(*, apply=False):
    source = json.loads(SOURCE.read_text(encoding='utf-8'))
    if len(source['programmes']) != 7 or {item['id'] for item in source['programmes']} != set(range(51, 58)):
        raise ValidationError('Les sept Masters institutionnels #51–57 sont requis.')
    school = find_school(lock=apply)
    if school.pk != source['school_id'] or school.short_name != 'ESFé Sup':
        raise ValidationError('École canonique ESFé Sup #4 requise.')
    result = {'apply': apply, 'fees_created': 0, 'fees_updated': 0,
              'programmes_updated': 0, 'school_updated': 0,
              'competence_blocks_created': 0, 'competence_items_created': 0,
              'competence_items_updated': 0, 'totals': {}}
    fields = [key for key, value in source['school'].items() if getattr(school, key) != value]
    result['school_updated'] = int(bool(fields))
    if apply and fields:
        for field in fields:
            setattr(school, field, source['school'][field])
        school.save(update_fields=fields + ['updated_at'])
    for item in source['programmes']:
        programme = Programme.objects.select_related('cycle', 'diploma_awarded').get(pk=item['id'])
        if (programme.school_id != school.pk or normalize(programme.cycle.name) != 'master'
                or normalize(programme.diploma_awarded.name) != 'master'
                or programme_key(programme.title) != normalize(item['formation'])):
            raise ValidationError(f"Identité académique divergente : #{programme.pk}.")
        keys = ('short_description', 'description', 'learning_outcomes', 'career_opportunities', 'program_structure')
        fields = [key for key in keys if getattr(programme, key) != item[key]]
        result['programmes_updated'] += int(bool(fields))
        if apply and fields:
            for field in fields:
                setattr(programme, field, item[field])
            programme.save(update_fields=fields + ['updated_at'])
        result['totals'][item['formation']] = {}
        for year_source in item['years']:
            year = programme.years.get(year_number=year_source['year_number'])
            fees = list(year.fees.all())
            canonical = {normalize(f['label']) for f in year_source['fees']}
            if any(normalize(f.label) not in canonical for f in fees):
                raise ValidationError(f'Frais supplémentaires non documentés : ProgrammeYear #{year.pk}.')
            for fee_source in year_source['fees']:
                matches = [f for f in fees if normalize(f.label) == normalize(fee_source['label'])]
                if len(matches) > 1:
                    raise ValidationError(f'Doublon tarifaire : ProgrammeYear #{year.pk}.')
                fee = matches[0] if matches else None
                if fee is None:
                    result['fees_created'] += 1
                    if apply:
                        Fee.objects.create(programme_year=year, **fee_source)
                elif any(getattr(fee, key) != value for key, value in fee_source.items()):
                    result['fees_updated'] += 1
                    if apply:
                        for key, value in fee_source.items():
                            setattr(fee, key, value)
                        fee.full_clean()
                        fee.save(update_fields=list(fee_source))
            result['totals'][item['formation']][year.year_number] = sum(f['amount'] for f in year_source['fees'])
        blocks = list(programme.competence_blocks.filter(title='Compétences développées'))
        if len(blocks) > 1:
            raise ValidationError(f'Blocs de compétences multiples : #{programme.pk}.')
        block = blocks[0] if blocks else None
        if block is None:
            result['competence_blocks_created'] += 1
            if apply:
                block = CompetenceBlock.objects.create(programme=programme, title='Compétences développées', order=0)
        for order, title in enumerate(item['skills']):
            matches = list(block.items.filter(title=title)) if block else []
            if len(matches) > 1:
                raise ValidationError('Compétence en doublon.')
            if not matches:
                result['competence_items_created'] += 1
                if apply:
                    CompetenceItem.objects.create(block=block, title=title, order=order)
            elif matches[0].order != order:
                result['competence_items_updated'] += 1
                if apply:
                    matches[0].order = order
                    matches[0].save(update_fields=['order'])
    return result
