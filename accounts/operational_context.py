"""Campus selection for school staff whose workflows require a physical campus."""

from dataclasses import replace

from django.core.exceptions import PermissionDenied


def resolve_operational_context(request, context):
    campus_workflows = {
        "it_support", "academic_supervisor", "director_of_studies", "secretary",
        "annex_manager", "branch_manager", "finance_manager", "payment_agent", "admissions",
    }
    if not context.is_valid or context.scope != "SCHOOL" or context.position not in campus_workflows:
        return context
    from branches.models import Branch

    campuses = list(Branch.objects.filter(is_active=True, school_branches__school=context.school,
        school_branches__is_active=True).order_by("name"))
    request.operational_campuses = campuses
    raw = request.GET.get("context_branch_id") if "context_branch_id" in request.GET else request.POST.get("context_branch_id")
    session_key = f"school_operational_campus_{context.school.pk}"
    selected_id = raw if raw is not None else request.session.get(session_key)
    selected = next((campus for campus in campuses if str(campus.pk) == str(selected_id)), None)
    if selected_id is not None and selected is None:
        raise PermissionDenied("Ce campus n'est pas autorisé pour votre école.")
    selected = selected or next(iter(campuses), None)
    if selected is None:
        return context
    request.session[session_key] = selected.pk
    request.authorization_access_context = context
    return replace(context, branch=selected, scope="SCHOOL_BRANCH")
