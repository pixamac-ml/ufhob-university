"""Catalogue officiel et compatibilité des liens de campagne (aucun ID local)."""
DOMAINS = (
    ('FATEC', 'Informatique de gestion', 'informatique-de-gestion', 'informatique-de-gestion'),
    ('FATEC', 'Génie logiciel', 'genie-logiciel', None),
    ('FATEC', 'Réseaux et Télécommunications', 'reseau-et-telecommunication', 'reseaux-telecommunications'),
    ('FATEC', 'Audiovisuel multimédia', 'audiovisuel-multimedia', None),
    ('ESGA', 'Finance et Comptabilité', 'finance-comptabilite', 'finance-comptabilite'),
    ('ESGA', 'Gestion des entreprises et administration', 'gestion-des-entreprises-et-administration', 'gestion-des-entreprises-et-administration'),
    ('ESGA', 'Gestion des ressources humaines', 'gestion-des-ressources-humaines', 'gestion-des-ressources-humaines'),
    ('ESGA', 'Marketing et Communication', 'marketing-communication', 'marketing-communication'),
)
ALIASES = {alias: base + '-licence' for school, title, base, alias in DOMAINS if alias}
SCOPED_CODES = ('FATEC', 'ESGA')


def canonical_slug(slug):
    return ALIASES.get(slug, slug)


def grouped_programmes(programmes):
    groups = {}
    rank = {'DUT': 0, 'Licence': 1, 'Master': 2}
    for programme in programmes:
        groups.setdefault(programme.filiere.name, []).append(programme)
    return [{'name': name, 'description': items[0].filiere.description, 'programmes': sorted(items, key=lambda p: rank.get(p.cycle.name if p.cycle_id else '', 9))} for name, items in sorted(groups.items())]


def public_catalogue_context():
    import json
    return {'public_contact': {'phones':[{'label':'+223 76 88 24 79','href':'tel:+22376882479'}], 'website':'https://www.ufhob-mali.ml','website_label':'www.ufhob-mali.ml','email':'','address':''},
        'public_social_links': [], 'organization_schema_json':json.dumps({'@context':'https://schema.org','@type':'EducationalOrganization','name':'UFHOB-Mali','url':'https://www.ufhob-mali.ml'})}
