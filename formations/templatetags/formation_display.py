from django import template

register = template.Library()


@register.filter
def xof(value):
    if value is None:
        return ''
    return f'{int(value):,}'.replace(',', ' ') + ' F CFA'


@register.filter
def cursus_year(value):
    number = int(value)
    return '1re année' if number == 1 else f'{number}e année'


@register.filter
def fcfa(value):
    """Montant brut avec espace comme séparateur de milliers (unité donnée à part)."""
    if value is None:
        return ''
    return f'{int(value):,}'.replace(',', ' ')
