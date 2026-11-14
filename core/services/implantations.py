"""Shared business rules for School <-> Branch implantations.

DG cockpit and superadmin must apply the exact same SchoolBranch semantics:
a link is a historical pair, never deleted by a sync; unselected pairs are
deactivated and selected pairs are created or reactivated.
"""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.models import SchoolBranch


@transaction.atomic
def sync_school_branches(school, selected_branches):
    """Align a school's active implantations with the selected campuses.

    Unselected links are deactivated (history preserved); selected links are
    created or reactivated. Must run inside ``transaction.atomic()``.
    """
    type(school).objects.select_for_update().get(pk=school.pk)
    selected_ids = {branch.pk for branch in selected_branches}
    school.school_branches.exclude(branch_id__in=selected_ids).update(is_active=False)
    for branch_id in selected_ids:
        SchoolBranch.objects.update_or_create(
            school=school,
            branch_id=branch_id,
            defaults={"is_active": True},
        )


@transaction.atomic
def sync_branch_schools(branch, selected_schools):
    """Align a campus' active implantations with the selected schools.

    Mirror of :func:`sync_school_branches` for the campus-side editors.
    """
    type(branch).objects.select_for_update().get(pk=branch.pk)
    selected_ids = {school.pk for school in selected_schools}
    branch.school_branches.exclude(school_id__in=selected_ids).update(is_active=False)
    for school_id in selected_ids:
        SchoolBranch.objects.update_or_create(
            school_id=school_id,
            branch=branch,
            defaults={"is_active": True},
        )


@transaction.atomic
def attach_school_to_branch(school, branch):
    """Create or reactivate one SchoolBranch pair.

    The unique (school, branch) constraint is never violated: an inactive link
    is reactivated instead of duplicated, and an already active link is a
    business error, not a silent no-op.
    """
    link, created = SchoolBranch.objects.select_for_update().get_or_create(
        school=school, branch=branch, defaults={"is_active": True},
    )
    if created:
        return link
    if link.is_active:
        raise ValidationError("Cette école est déjà implantée sur ce campus.")
    link.is_active = True
    link.save(update_fields=["is_active", "updated_at"])
    return link
