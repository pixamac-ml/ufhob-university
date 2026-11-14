from django.core.exceptions import ValidationError
from django.db import transaction

from academics.services.academic_positioning import validate_academic_class_for_candidature
from academics.services.academic_years import resolve_academic_year_reference
from inscriptions.models import Inscription


def create_inscription_from_candidature(
    *,
    candidature,
    amount_due,
    academic_class=None,
    status=Inscription.STATUS_CREATED,
    actor=None,
):
    """
    Creation officielle d'une inscription a partir d'une candidature.

    PRINCIPES :

    - La candidature doit etre acceptee
    - Une seule inscription possible par candidature
    - Le montant est copie et fige
    - La classe academique doit etre positionnee explicitement
    - Transaction atomique pour eviter les duplications
    """

    if not candidature:
        raise ValidationError("Candidature requise.")

    if candidature.status not in {"accepted", "accepted_with_reserve"}:
        raise ValidationError(
            "Impossible de creer une inscription : candidature non acceptee."
        )

    if amount_due <= 0:
        raise ValidationError(
            "Le montant du doit etre superieur a zero."
        )

    validation = validate_academic_class_for_candidature(
        candidature=candidature,
        academic_class=academic_class,
    )
    if not validation["ok"]:
        raise ValidationError(validation["message"])

    with transaction.atomic():
        candidature_locked = (
            type(candidature)
            .objects
            .select_for_update()
            .get(pk=candidature.pk)
        )

        if hasattr(candidature_locked, "inscription"):
            return candidature_locked.inscription

        inscription = Inscription.objects.create(
            candidature=candidature_locked,
            amount_due=amount_due,
            status=status,
            academic_class=academic_class,
            academic_level=getattr(academic_class, "level", ""),
        )

        # The academic record is the source of truth for this audit context.
        # Keeping it on the event preserves the historical School/Branch/Year
        # even if staff assignments or the student's later enrolment changes.
        if actor is not None and getattr(actor, "is_authenticated", False):
            from portal.models import SupportAuditLog

            year = resolve_academic_year_reference(candidature_locked.academic_year).get("academic_year")
            programme = candidature_locked.programme
            SupportAuditLog.objects.create(
                actor=actor,
                branch=candidature_locked.branch,
                school=getattr(programme, "school", None),
                academic_year=year,
                action_type=SupportAuditLog.ACTION_INSCRIPTION_CREATED,
                target_label=f"{inscription.public_reference} · {candidature_locked.full_name}",
                details=f"Programme : {programme.title}. Statut initial : {inscription.get_status_display()}.",
            )

        return inscription
