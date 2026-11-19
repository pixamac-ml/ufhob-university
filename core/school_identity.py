"""Logo et description institutionnelle des écoles FATEC et ESGA.

Le champ ``School.logo`` reste prioritaire lorsqu'il est renseigné dans l'admin ;
sinon le logo statique est résolu par le code de l'école. Les descriptions sont
des PROPOSITIONS à faire valider par la direction ; elles sont écrites en base
par ``manage.py charger_identite_ecoles``.
"""

from django.templatetags.static import static


SCHOOL_IDENTITY = {
    "FATEC": {
        "logo": "images/institution/fatec-logo.svg",
        "logo_white": "images/institution/fatec-logo-blanc.svg",
        "description": (
            "La Faculté des Technologies Appliquées Cheick Modibo Diarra (FATEC) forme aux métiers "
            "du numérique : informatique de gestion, génie logiciel, réseaux et télécommunications, "
            "audiovisuel multimédia. Ses parcours DUT, Licence et Master associent bases théoriques "
            "et mises en pratique. Les cours sont proposés en présentiel ou en ligne."
        ),
    },
    "ESGA": {
        "logo": "images/institution/esga-logo.svg",
        "logo_white": "images/institution/esga-logo-blanc.svg",
        "description": (
            "L'École Supérieure de Gestion Alassane Dramane Ouattara (ESGA) forme aux métiers de la "
            "gestion : finance et comptabilité, gestion des entreprises et administration, ressources "
            "humaines, marketing et communication. Ses parcours DUT, Licence et Master préparent à "
            "comprendre, organiser et piloter les activités des organisations. Les cours sont "
            "proposés en présentiel ou en ligne."
        ),
    },
}


def school_logo_url(school, variant="color"):
    """Logo de l'école : champ du modèle, sinon fichier statique par code, sinon vide."""
    if school is None:
        return ""
    logo = getattr(school, "logo", None)
    if logo:
        try:
            return logo.url
        except ValueError:
            pass
    identity = SCHOOL_IDENTITY.get((getattr(school, "code", "") or "").upper())
    if identity:
        return static(identity["logo_white" if variant == "white" else "logo"])
    return ""
