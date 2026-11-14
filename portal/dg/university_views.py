"""University reference management inside the executive DashboardShell."""

from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from core.models import School, SchoolBranch
from academics.models import AcademicClass
from portal.models import SupportAuditLog

from .context import resolve_dg_context
from .scoping import dg_navigation_scope, scoped
from .university_forms import DgAcademicClassForm, DgSchoolBranchForm, DgSchoolForm


@login_required
@require_http_methods(["GET", "POST"])
@dg_navigation_scope
def school_editor(request):
    data = request.POST if request.method == "POST" else request.GET
    school_id = data.get("school_id")
    if school_id and not school_id.isdigit():
        return JsonResponse({"ok": False, "message": "École invalide."}, status=400)
    school = get_object_or_404(scoped(School), pk=school_id) if school_id else None
    form = DgSchoolForm(
        request.POST if request.method == "POST" else None, instance=school,
        navigation=resolve_dg_context(request),
    )
    return _editor_response(request, form, title="Modifier l’école" if school else "Créer une école", school=school)


@login_required
@require_http_methods(["GET", "POST"])
@dg_navigation_scope
def implantation_editor(request):
    data = request.POST if request.method == "POST" else request.GET
    school_id, link_id = data.get("school_id", ""), data.get("link_id", "")
    if (school_id and not school_id.isdigit()) or (link_id and not link_id.isdigit()):
        return JsonResponse({"ok": False, "message": "Implantation invalide."}, status=400)
    link = get_object_or_404(scoped(SchoolBranch), pk=link_id) if link_id else None
    if school_id:
        school = get_object_or_404(scoped(School), pk=school_id)
        if link is not None and link.school_id != school.pk:
            return JsonResponse({"ok": False, "message": "Implantation invalide."}, status=400)
    elif link is not None:
        school = link.school
    elif request.method == "POST" and data.get("school"):
        # Global view: the school comes from the form field.
        if not data["school"].isdigit():
            return JsonResponse({"ok": False, "message": "École invalide."}, status=400)
        school = get_object_or_404(scoped(School), pk=int(data["school"]))
    else:
        school = None
    if link is None and school is not None and request.method == "POST":
        branch_id = data.get("branch", "")
        if branch_id.isdigit():
            existing = SchoolBranch.objects.filter(school=school, branch_id=int(branch_id)).first()
            if existing is not None:
                if existing.is_active:
                    return JsonResponse(
                        {"ok": False, "message": "Cette école est déjà implantée sur ce campus."},
                        status=400,
                    )
                # Reactivate the historical pair instead of duplicating it.
                link = existing
    form = DgSchoolBranchForm(
        request.POST if request.method == "POST" else None, instance=link,
        school=school, navigation=resolve_dg_context(request),
    )
    if "school" in form.fields:
        from django.urls import reverse

        form.fields["school"].widget.attrs["onchange"] = (
            "if(this.value) dgOpenModal('"
            + reverse("accounts_portal:dg_implantation_editor")
            + "?school_id=' + encodeURIComponent(this.value))"
        )
    return _editor_response(request, form, title="Modifier l’implantation" if link else "Rattacher un campus", school=school, link=link)


def _editor_response(request, form, *, title, school, link=None):
    is_school = isinstance(form, DgSchoolForm)
    creating = not form.instance.pk
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                obj = form.save()
                SupportAuditLog.objects.create(
                    actor=request.user, branch=None if is_school else obj.branch,
                    action_type=SupportAuditLog.ACTION_BRANCH_SETTINGS_UPDATED,
                    target_label=str(obj),
                    details=f"Structure universitaire : {title.lower()} depuis le cockpit DG.",
                )
        except IntegrityError:
            form.add_error(None, "Ce code ou ce rattachement existe déjà. Actualisez la structure.")
        else:
            navigation = resolve_dg_context(request)
            # Closing the selected scope must not strand the executive on an
            # invalid saved pair. Return the explicit parent navigation to UI Core.
            context_params = {}
            if is_school and creating:
                context_params = {"scope_school_id": str(obj.pk) if obj.is_active else "", "scope_branch_id": ""}
            if not obj.is_active:
                if is_school and navigation.selected_school_id == str(obj.pk):
                    context_params = {"scope_school_id": "", "scope_branch_id": ""}
                elif not is_school and navigation.selected_school_id == str(obj.school_id) and navigation.selected_branch_id == str(obj.branch_id):
                    context_params = {"scope_branch_id": ""}
            return JsonResponse({"ok": True, "message": "Structure universitaire enregistrée.", "close_modal": True, "topic": "branches", "context_params": context_params})
    return render(request, "portal/dg/modals/university_editor.html", {
        "form": form, "editor_title": title, "school_admin": school,
        "implantation_admin": link, "is_school_editor": is_school,
    }, status=400 if request.method == "POST" else 200)


@login_required
@require_http_methods(["GET", "POST"])
@dg_navigation_scope
def academic_class_editor(request):
    navigation = resolve_dg_context(request)
    raw_class_id = (request.POST.get("class_id") if request.method == "POST" else request.GET.get("class_id")) or ""
    editing_class = None
    if raw_class_id:
        if not raw_class_id.isdigit():
            return JsonResponse({"ok": False, "message": "Classe invalide."}, status=400)
        editing_class = get_object_or_404(
            scoped(AcademicClass).select_related("programme", "programme__school", "branch", "academic_year"),
            pk=int(raw_class_id), branch_id__in=navigation.scoped_branch_ids,
        )
    form = DgAcademicClassForm(
        request.POST if request.method == "POST" else None,
        navigation=navigation,
        instance=editing_class,
    )
    if request.method == "POST" and form.is_valid():
        from portal.services.academic_structure_service import save_academic_class

        data = form.cleaned_data
        try:
            academic_class = save_academic_class(
                branch=data["branch"],
                programme_id=data["programme"].pk,
                class_id=editing_class.pk if editing_class else None,
                academic_year_id=data["academic_year"].pk,
                level=data["level"],
                threshold=data.get("validation_threshold"),
                actor=request.user,
            )
        except Exception as exc:
            form.add_error(None, str(exc))
        else:
            SupportAuditLog.objects.create(
                actor=request.user,
                branch=data["branch"],
                action_type=SupportAuditLog.ACTION_BRANCH_SETTINGS_UPDATED,
                target_label=str(academic_class),
                details="Classe académique créée depuis le cockpit DG.",
            )
            return JsonResponse({
                "ok": True,
                "message": "Classe créée et activée. Les inscriptions peuvent maintenant être positionnées.",
                "close_modal": True,
                "topic": "classes",
            })
    return render(request, "portal/dg/modals/academic_class_editor.html", {
        "form": form,
        "navigation": navigation,
        "editing_class": editing_class,
    }, status=400 if request.method == "POST" else 200)


@login_required
@require_http_methods(["POST"])
@dg_navigation_scope
def academic_class_archive(request):
    raw_id = (request.POST.get("class_id") or "").strip()
    if not raw_id.isdigit():
        return JsonResponse({"ok": False, "message": "Classe invalide."}, status=400)
    navigation = resolve_dg_context(request)
    academic_class = get_object_or_404(
        scoped(AcademicClass).select_related("branch"),
        pk=int(raw_id), branch_id__in=navigation.scoped_branch_ids, is_active=True, is_archived=False,
    )
    from portal.services.academic_structure_service import archive_academic_class

    archive_academic_class(branch=academic_class.branch, class_id=academic_class.pk)
    SupportAuditLog.objects.create(
        actor=request.user, branch=academic_class.branch,
        action_type=SupportAuditLog.ACTION_BRANCH_SETTINGS_UPDATED,
        target_label=str(academic_class), details="Classe académique archivée depuis le cockpit DG.",
    )
    return JsonResponse({"ok": True, "message": "Classe archivée. Son historique académique est conservé.", "close_drawer": True, "topic": "classes"})
