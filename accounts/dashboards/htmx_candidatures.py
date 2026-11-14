from accounts.scoping import scoped
import json
from pathlib import Path

from django.db import transaction
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_GET, require_POST

from admissions.models import Candidature, CandidatureDocument
from accounts.services.manager_dashboard_presentation import build_candidature_table_row
from accounts.services.manager_admission_documents import ManagerCandidatureDocumentForm

from accounts.dashboards.htmx_utils import manager_capability_required


def _candidature_row_context(request, candidature):
    return {
        "candidature_row": build_candidature_table_row(
            candidature,
            request.manager_workspace_access.capabilities,
        )
    }


@manager_capability_required("view_admissions")
@require_GET
def candidature_detail(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(
        scoped(Candidature, user=request.user).select_related("programme", "branch"),
        pk=pk,
        branch=request.branch,
        is_deleted=False,
    )
    return _render_candidature_detail(request, candidature)


def _render_candidature_detail(request, candidature, document_form=None):
    documents = candidature.documents.select_related("document_type").all()
    form = document_form if document_form is not None else ManagerCandidatureDocumentForm(candidature=candidature)
    return render(
        request,
        "accounts/dashboard/partials/candidature_modal.html",
        {
            "candidature": candidature,
            "documents": documents,
            "document_form": form,
            "missing_documents": form.fields["document_type"].queryset,
            "manager_capabilities": request.manager_workspace_access.capabilities_context(),
        },
    )


@manager_capability_required("manage_admissions")
@require_POST
def candidature_document_add(request: HttpRequest, pk: int) -> HttpResponse:
    with transaction.atomic():
        candidature = get_object_or_404(
            scoped(Candidature, user=request.user).select_for_update(),
            pk=pk, branch=request.branch, is_deleted=False,
        )
        form = ManagerCandidatureDocumentForm(request.POST, request.FILES, candidature=candidature)
        if not form.is_valid():
            return _render_candidature_detail(request, candidature, form)
        # Receiving a late document must not undo an admission or enrollment decision.
        CandidatureDocument.objects.create(candidature=candidature, **form.cleaned_data)
    response = _render_candidature_detail(request, candidature)
    response["HX-Trigger"] = json.dumps({"showToast": {"message": "Document ajouté.", "type": "success"}})
    return response


@manager_capability_required("manage_admissions")
@require_POST
def candidature_document_validate(request: HttpRequest, pk: int) -> HttpResponse:
    document = get_object_or_404(
        scoped(CandidatureDocument, user=request.user).select_related("candidature"),
        pk=pk, candidature__branch=request.branch, candidature__is_deleted=False,
    )
    if not document.file:
        return HttpResponse("Document indisponible.", status=400)
    document.is_valid = document.is_validated = True
    document.validated_at = timezone.now()
    document.validated_by = request.user
    document.save(update_fields=["is_valid", "is_validated", "validated_at", "validated_by"])
    return _render_candidature_detail(request, document.candidature)


@manager_capability_required("view_admissions")
@require_GET
def candidature_document_download(request: HttpRequest, pk: int) -> FileResponse:
    document = get_object_or_404(
        scoped(CandidatureDocument, user=request.user).select_related("candidature__branch", "document_type"),
        pk=pk,
        candidature__branch=request.branch,
    )
    if not document.file:
        raise Http404("Document indisponible.")
    suffix = Path(document.file.name).suffix.lower() or ".bin"
    label = slugify(document.document_type.name) or f"document-{document.pk}"
    return FileResponse(
        document.file.open("rb"),
        as_attachment=True,
        filename=f"{label}-{document.pk}{suffix}",
    )


@manager_capability_required("manage_admissions")
@require_POST
def candidature_under_review(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(scoped(Candidature, user=request.user), pk=pk, branch=request.branch, is_deleted=False)

    if candidature.status not in ("submitted", "to_complete"):
        return HttpResponse("Seules les candidatures soumises peuvent passer en analyse.", status=400)

    candidature.status = "under_review"
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])

    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        _candidature_row_context(request, candidature),
    )
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "showToast": {
                "message": "Candidature passee en analyse.",
                "type": "info",
            },
        }
    )
    return response


@manager_capability_required("manage_admissions")
@require_POST
def candidature_accept(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(scoped(Candidature, user=request.user), pk=pk, branch=request.branch, is_deleted=False)

    if candidature.status not in ("submitted", "under_review", "to_complete"):
        return HttpResponse("Cette candidature ne peut plus etre acceptee.", status=400)

    candidature.status = "accepted"
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "reviewed_at", "reviewed_by"])
    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        _candidature_row_context(request, candidature),
    )
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "showToast": {"message": "Candidature acceptee. Positionnement academique requis.", "type": "success"},
        }
    )
    # Open the next step after the previous modal's after-request close handler.
    response["HX-Trigger-After-Settle"] = json.dumps({
        "openInscriptionPositioning": {
            "url": reverse("accounts:htmx_inscription_positioning", args=[candidature.id]),
        },
    })
    return response


@manager_capability_required("manage_admissions")
@require_POST
def candidature_reject(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(scoped(Candidature, user=request.user), pk=pk, branch=request.branch, is_deleted=False)

    if candidature.status not in ("submitted", "under_review", "to_complete"):
        return HttpResponse("Cette candidature ne peut plus etre refusee.", status=400)

    candidature.status = "rejected"
    candidature.rejection_reason = (request.POST.get("reason") or "").strip() or "Rejete par le gestionnaire."
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "rejection_reason", "reviewed_at", "reviewed_by"])
    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        _candidature_row_context(request, candidature),
    )
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "showToast": {"message": "Candidature refusee.", "type": "warning"},
        }
    )
    return response


@manager_capability_required("manage_admissions")
@require_POST
def candidature_to_complete(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(scoped(Candidature, user=request.user), pk=pk, branch=request.branch, is_deleted=False)

    if candidature.status not in ("submitted", "under_review", "to_complete"):
        return HttpResponse("Cette candidature ne peut plus etre marquee a completer.", status=400)

    candidature.status = "to_complete"
    candidature.completion_message = (request.POST.get("message") or "").strip() or "Complements demandes par le gestionnaire."
    candidature.reviewed_at = timezone.now()
    candidature.reviewed_by = request.user
    candidature.save(update_fields=["status", "completion_message", "reviewed_at", "reviewed_by"])
    response = render(
        request,
        "accounts/dashboard/partials/manager_candidature_row.html",
        _candidature_row_context(request, candidature),
    )
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "showToast": {"message": "Complement demande au candidat.", "type": "info"},
        }
    )
    return response


@manager_capability_required("delete_candidature")
@require_POST
def candidature_delete(request: HttpRequest, pk: int) -> HttpResponse:
    candidature = get_object_or_404(
        scoped(Candidature, user=request.user).select_related("branch").prefetch_related("documents"),
        pk=pk,
        branch=request.branch,
        is_deleted=False,
    )

    if candidature.status != "rejected":
        return HttpResponse("Seules les candidatures rejetees peuvent etre supprimees.", status=400)

    if hasattr(candidature, "inscription"):
        return HttpResponse("Impossible de supprimer: une inscription est liee a cette candidature.", status=400)

    with transaction.atomic():
        candidature.documents.all().delete()
        candidature.is_deleted = True
        candidature.deleted_at = timezone.now()
        candidature.deleted_by = request.user
        candidature.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    response = HttpResponse("")
    response["HX-Trigger"] = json.dumps(
        {
            "candidatureUpdated": True,
            "candidatureDeleted": {"id": pk},
            "showToast": {
                "message": "Candidature supprimee.",
                "type": "warning",
            },
        }
    )
    return response
