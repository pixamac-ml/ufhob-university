"""T6-b — écrire l'école à chaque création d'un enregistrement financier.

Branché sur pre_save pour tous les modèles de FINANCE_SCHOOL_MODELS : on ne
remplace jamais une école donnée explicitement, on ne touche pas aux mises à
jour (la répartition de l'existant passe par attribuer_ecole_finance).
"""

from django.apps import apps
from django.db.models.signals import pre_save

from accounts.services.finance_school import FINANCE_SCHOOL_MODELS, resolve_finance_school_id

# Les séquences de numérotation sont choisies explicitement par le service
# qui numérote (étape c) : pas de déduction implicite ici.
_SKIP = {"accounts.accountingdocumentsequence"}


def _fill_school_on_create(sender, instance, raw=False, **kwargs):
    if raw or not instance._state.adding or instance.school_id:
        return
    school_id = resolve_finance_school_id(instance)
    if school_id:
        instance.school_id = school_id


def connect():
    for label in FINANCE_SCHOOL_MODELS:
        model = apps.get_model(label)
        if model._meta.label_lower in _SKIP:
            continue
        pre_save.connect(
            _fill_school_on_create,
            sender=model,
            dispatch_uid=f"t6_finance_school_{model._meta.label_lower}",
        )
