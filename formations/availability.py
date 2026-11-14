"""Single business rule for programme/campus eligibility."""

from django.core.exceptions import ValidationError


def validate_programme_branch(programme, branch_id):
    # Null School is the explicit migration bridge for pre-university records.
    if programme is None or not programme.school_id or not branch_id:
        return
    from core.models import SchoolBranch

    if not SchoolBranch.objects.filter(
        school_id=programme.school_id, branch_id=branch_id,
        is_active=True, school__is_active=True,
    ).exists():
        raise ValidationError({"branch": "Ce programme ne peut pas être proposé sur ce campus : son école n'y est pas active."})


def validate_offering_change(instance, *, programme_field="programme", branch_field="branch"):
    """Validate new/reassigned records while retaining closed-campus history."""
    programme_id = getattr(instance, f"{programme_field}_id")
    branch_id = getattr(instance, f"{branch_field}_id")
    if not programme_id or not branch_id:
        return
    if not instance._state.adding:
        old = type(instance).objects.filter(pk=instance.pk).values_list(
            f"{programme_field}_id", f"{branch_field}_id"
        ).first()
        if old == (programme_id, branch_id):
            return
    programme = getattr(instance, programme_field)
    validate_programme_branch(programme, branch_id)
    from accounts.scoping import require_object_scope

    require_object_scope(programme)
