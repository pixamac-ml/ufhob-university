"""Contexte institutionnel persistant du tableau de bord DG.

Le DG n'est pas limite a l'annexe de son profil : il peut passer d'une vue
consolidee a une annexe, tout en conservant l'annee academique choisie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from django.core.exceptions import ValidationError
from core.models import School, SchoolBranch

from academics.models import AcademicYear

from .selectors import get_active_branches


SESSION_KEY = "dg_dashboard_context"
MODE_GLOBAL = "global"
MODE_BRANCH = "branch"
MODE_SCHOOL = "school"
MODE_SCHOOL_BRANCH = "school_branch"


@dataclass(frozen=True)
class DgDashboardContext:
    academic_year: AcademicYear | None
    academic_years: list[AcademicYear]
    all_branches: list
    selected_branch: object | None
    mode: str
    selected_school: object | None = None
    all_schools: list = field(default_factory=list)
    school_branch_pairs: list = field(default_factory=list)

    @property
    def selected_school_id(self):
        return str(self.selected_school.id) if self.selected_school else ""

    @property
    def available_branches(self):
        if not self.selected_school:
            return self.all_branches
        ids = {branch for school, branch in self.school_branch_pairs if school == self.selected_school.id}
        return [branch for branch in self.all_branches if branch.id in ids]

    @property
    def available_schools(self):
        if not self.selected_branch:
            return self.all_schools
        ids = {school for school, branch in self.school_branch_pairs if branch == self.selected_branch.id}
        return [school for school in self.all_schools if school.id in ids]

    def template_context(self):
        return {
            "academic_years": self.academic_years,
            "selected_academic_year": self.academic_year,
            "selected_academic_year_id": str(self.academic_year.id) if self.academic_year else "",
            "selected_branch_id": self.selected_branch_id,
            "selected_branch": self.selected_branch,
            "dashboard_mode": self.mode,
            "selected_school": self.selected_school,
            "selected_school_id": self.selected_school_id,
            "available_schools": self.available_schools,
            "available_branches": self.available_branches,
            "dashboard_scope_label": self.scope_label,
        }

    @property
    def selected_branch_id(self) -> str:
        return str(self.selected_branch.id) if self.selected_branch else ""

    @property
    def scoped_branches(self) -> list:
        return [self.selected_branch] if self.selected_branch else self.available_branches

    @property
    def scoped_branch_ids(self) -> list[int]:
        return [branch.id for branch in self.scoped_branches]

    def contains_branch_id(self, branch_id) -> bool:
        try:
            return int(branch_id) in self.scoped_branch_ids
        except (TypeError, ValueError):
            return False

    @property
    def scope_label(self) -> str:
        if self.selected_school:
            campus = self.selected_branch.name if self.selected_branch else "Tous les campus"
            return f"{self.selected_school.display_name} — {campus}"
        if self.selected_branch:
            return f"Toutes les écoles — {self.selected_branch.name}"
        return "Université — Toutes les écoles — Tous les campus"


def _resolve_academic_year(*, academic_years, raw_year_id, saved_context):
    requested_id = raw_year_id if raw_year_id is not None else saved_context.get("academic_year_id")
    if str(requested_id or "").isdigit():
        selected = next((year for year in academic_years if year.id == int(requested_id)), None)
        if selected:
            return selected
    return next((year for year in academic_years if year.is_active), None) or (academic_years[0] if academic_years else None)


def _resolve_branch(*, branches, raw_branch_id, saved_context):
    requested_id = raw_branch_id if raw_branch_id is not None else saved_context.get("branch_id")
    if str(requested_id or "").isdigit():
        return next((branch for branch in branches if branch.id == int(requested_id)), None)
    return None


def resolve_dg_context(request, *, accept_legacy_branch_param=True) -> DgDashboardContext:
    """Validate then persist the DG's academic year and global/branch scope.

    Query parameters take precedence over the saved context.  IDs are accepted
    only when they resolve to an existing academic year or active branch;
    arbitrary client values therefore cannot widen or corrupt the scope.
    """

    cached = getattr(request, "_dg_navigation_context", None)
    if cached is not None:
        return cached
    academic_years = list(AcademicYear.objects.order_by("-start_date", "-id"))
    all_branches = list(get_active_branches())
    all_schools = list(School.objects.filter(is_active=True).order_by("order", "code"))
    pairs = list(SchoolBranch.objects.filter(is_active=True, school__is_active=True, branch__is_active=True).values_list("school_id", "branch_id"))
    saved_context = request.session.get(SESSION_KEY, {})

    raw_year_id = (
        request.GET.get("academic_year_id")
        if "academic_year_id" in request.GET
        else request.POST.get("academic_year_id") if "academic_year_id" in request.POST else None
    )
    if "scope_branch_id" in request.GET or "scope_branch_id" in request.POST:
        raw_branch_id = request.GET.get("scope_branch_id") if "scope_branch_id" in request.GET else request.POST.get("scope_branch_id")
    elif accept_legacy_branch_param and "branch_id" in request.GET:
        # Kept for bookmarked dashboard URLs. Drawers use ``branch_id`` for
        # their target object and deliberately disable this legacy behaviour.
        raw_branch_id = request.GET.get("branch_id")
    else:
        raw_branch_id = None
    academic_year = _resolve_academic_year(
        academic_years=academic_years,
        raw_year_id=raw_year_id,
        saved_context=saved_context,
    )
    selected_branch = _resolve_branch(
        branches=all_branches,
        raw_branch_id=raw_branch_id,
        saved_context=saved_context,
    )
    if raw_branch_id is None and saved_context.get("branch_id") and selected_branch is None:
        raise ValidationError("Le campus mémorisé n'est plus actif. Sélectionnez un nouveau contexte.")
    raw_school_id = request.GET.get("scope_school_id") if "scope_school_id" in request.GET else request.POST.get("scope_school_id")
    requested_school = raw_school_id if raw_school_id is not None else saved_context.get("school_id")
    selected_school = next((school for school in all_schools if str(school.id) == str(requested_school)), None)
    if requested_school and selected_school is None:
        raise ValidationError("École inconnue ou inactive. Sélectionnez un contexte valide.")
    # Explicit scope parameters must never silently broaden a saved context.
    # The old branch_id bookmark fallback remains compatible for legacy URLs.
    if raw_branch_id and selected_branch is None and ("scope_branch_id" in request.GET or "scope_branch_id" in request.POST or selected_school):
        raise ValidationError("Campus inconnu ou inactif.")
    if selected_school and selected_branch and (selected_school.id, selected_branch.id) not in pairs:
        raise ValidationError("Cette école n'est pas implantée sur ce campus.")
    mode = (MODE_SCHOOL_BRANCH if selected_branch else MODE_SCHOOL) if selected_school else (MODE_BRANCH if selected_branch else MODE_GLOBAL)

    persisted = {
        "academic_year_id": academic_year.id if academic_year else None,
        "branch_id": selected_branch.id if selected_branch else None,
        "mode": mode,
    }
    if selected_school:
        persisted["school_id"] = selected_school.id
    if saved_context != persisted:
        request.session.pop("dg_calendar_edit_scope", None)
        request.session[SESSION_KEY] = persisted

    resolved = DgDashboardContext(
        academic_year=academic_year,
        academic_years=academic_years,
        all_branches=all_branches,
        selected_branch=selected_branch,
        mode=mode,
        selected_school=selected_school,
        all_schools=all_schools,
        school_branch_pairs=pairs,
    )
    request._dg_navigation_context = resolved
    return resolved
