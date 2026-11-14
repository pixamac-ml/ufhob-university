import io
import json
import zipfile
import secrets
from datetime import date, time, timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from academics.models import (
    AcademicBulletin,
    AcademicDiplomaAward,
    AcademicEnrollment,
    AcademicClass,
    AcademicScheduleEvent,
    AcademicYear,
    AcademicDocumentAuditLog,
    OfficialTranscriptRequest,
    ResultAccessAuthorization,
    EC,
    LessonLog,
    Semester,
)
from academics.services.lesson_log_service import (
    create_lesson_log,
    get_class_lesson_logs,
    get_daily_lesson_status,
    get_teacher_lesson_logs,
    update_lesson_log,
)
from accounts.dashboards.helpers import get_user_branch
from branches.models import Branch
from students.models import Student
from academics.permissions import can_manage_bulletins, can_manage_diplomas, can_view_academic_class, can_view_student_academic_report
from accounts.scoping import scoped
from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from academics.services.documents import (
    build_bulletin_context,
    build_diploma_context,
    generate_annual_bulletin,
    generate_semester_bulletin,
    prepare_diploma_award,
    render_bulletin_pdf_bytes,
)
from academics.services.reporting import (
    build_annual_class_report,
    build_student_annual_report,
    build_student_semester_report,
)
from academics.services.workflow import get_semester_permissions

try:
    from weasyprint import HTML
except Exception:  # pragma: no cover
    HTML = None


User = get_user_model()


def _can_validate_lesson_log(user):
    """Validation is a supervisory act, never a teacher self-declaration."""
    if user.is_superuser:
        return True
    profile = getattr(user, "profile", None)
    return getattr(profile, "position", None) in {
        "academic_supervisor",
        "director_of_studies",
    }


def _ensure_pdf_backend():
    if HTML is None:
        return HttpResponse(
            "WeasyPrint n'est pas installe ou ses dependances systeme sont manquantes.",
            status=500,
            content_type="text/plain; charset=utf-8",
        )
    return None


def _resolve_report_student(student_id):
    student = Student.objects.select_related("user", "inscription__candidature__branch").filter(id=student_id).first()
    if student:
        return student
    return get_object_or_404(Student.objects.select_related("user", "inscription__candidature__branch"), user_id=student_id)


def _ensure_can_view_semester_report(request, student_id, semester):
    student = _resolve_report_student(student_id)
    # A report URL carries both a student and a semester.  Permission to view
    # each object separately is not sufficient: they must be linked by the
    # same historical enrollment.  This keeps cross-class and cross-year IDs
    # from ever reaching the PDF/report builder.
    if not AcademicEnrollment.objects.filter(
        student=student.user,
        academic_class=semester.academic_class,
        academic_year=semester.academic_class.academic_year,
    ).exists():
        raise PermissionDenied(
            "Cet etudiant n'est pas inscrit dans la classe et l'annee de ce releve."
        )
    if not can_view_student_academic_report(request.user, student, academic_class=semester.academic_class):
        raise PermissionDenied("Acces refuse a ce releve academique.")
    return student


def _audit(request, action, *, student=None, authorization=None, transcript_request=None, **metadata):
    enrollment = getattr(authorization, "enrollment", None) or getattr(transcript_request, "enrollment", None)
    if enrollment is None and student is not None:
        enrollment = student.user.academic_enrollments.select_related("programme__school", "branch", "academic_year").order_by("-created_at").first()
    from accounts.access import get_user_position
    AcademicDocumentAuditLog.objects.create(
        action=action, actor=request.user if request.user.is_authenticated else None,
        student=student, authorization=authorization, transcript_request=transcript_request,
        metadata=metadata, ip_address=request.META.get("REMOTE_ADDR"),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
        school=getattr(getattr(enrollment, "programme", None), "school", None),
        branch=getattr(enrollment, "branch", None), academic_year=getattr(enrollment, "academic_year", None),
        actor_role=get_user_position(request.user) if request.user.is_authenticated else "",
    )


def _ensure_can_view_class_reports(request, academic_class):
    if not can_view_academic_class(request.user, academic_class):
        raise PermissionDenied("Acces refuse a cette classe.")


def _build_semester_report_context(request, student_id, semester_id):
    semester = get_object_or_404(
        Semester.objects.select_related("academic_class__branch"),
        id=semester_id,
    )
    student = _ensure_can_view_semester_report(request, student_id, semester)
    permissions = get_semester_permissions(semester)
    if not permissions["can_generate_reports"]:
        raise PermissionDenied("Les releves ne sont disponibles qu'apres publication.")
    bulletin = AcademicBulletin.objects.select_related(
        "student__user",
        "enrollment",
        "academic_year",
        "academic_class__branch",
        "branch",
        "semester",
    ).filter(
        student=student,
        semester=semester,
        bulletin_type=AcademicBulletin.TYPE_SEMESTER,
        status=AcademicBulletin.STATUS_PUBLISHED,
    ).first()
    if bulletin is None:
        raise Http404("Le relevé officiel est en cours de génération.")
    return build_bulletin_context(bulletin)


def _build_semester_report_filename(context):
    return f"releve-semestre-s{context['semester'].number}-{context['student_matricule']}.pdf"


def _render_pdf_from_template(request, template_name, context):
    backend_error = _ensure_pdf_backend()
    if backend_error is not None:
        return None, backend_error
    html = render_to_string(template_name, context, request=request)
    return HTML(string=html, base_url=request.build_absolute_uri()).write_pdf(), None


@login_required
@require_POST
def director_result_access_decision_view(request, authorization_id):
    authorization = get_object_or_404(ResultAccessAuthorization.objects.select_related("semester__academic_class", "student"), pk=authorization_id)
    if not can_manage_bulletins(request.user, authorization.semester.academic_class):
        raise PermissionDenied("Autorisation réservée au Directeur des études.")
    decision = request.POST.get("decision")
    authorization.processed_by = request.user
    authorization.processed_at = timezone.now()
    if decision == "approve":
        otp = f"{secrets.randbelow(1_000_000):06d}"
        authorization.status = authorization.STATUS_APPROVED
        authorization.otp_hash = make_password(otp)
        authorization.expires_at = timezone.now() + timedelta(minutes=5)
        authorization.attempts = 0
        authorization.save(update_fields=["processed_by", "processed_at", "status", "otp_hash", "expires_at", "attempts"])
        _audit(request, "results_access_authorized", student=authorization.student, authorization=authorization)
        _audit(request, "results_otp_generated", student=authorization.student, authorization=authorization)
        # Code is deliberately returned only once to the authorised DE UI.
        return JsonResponse({"ok": True, "otp": otp, "expires_at": authorization.expires_at.isoformat()})
    authorization.status = authorization.STATUS_REJECTED
    authorization.save(update_fields=["processed_by", "processed_at", "status"])
    _audit(request, "results_access_rejected", student=authorization.student, authorization=authorization)
    return JsonResponse({"ok": True, "status": authorization.status})


@login_required
@require_POST
def director_mark_transcript_delivered_view(request, transcript_request_id):
    transcript_request = get_object_or_404(OfficialTranscriptRequest.objects.select_related("semester__academic_class", "student"), pk=transcript_request_id)
    if not transcript_request.semester_id or not can_manage_bulletins(request.user, transcript_request.semester.academic_class):
        raise PermissionDenied("Remise réservée au Directeur des études.")
    transcript_request.status = transcript_request.STATUS_DELIVERED
    transcript_request.delivered_by = request.user
    transcript_request.delivered_at = timezone.now()
    transcript_request.save(update_fields=["status", "delivered_by", "delivered_at"])
    _audit(request, "official_transcript_delivered", student=transcript_request.student, transcript_request=transcript_request)
    return JsonResponse({"ok": True, "status": transcript_request.status})


def _notify_transcript_status(transcript_request, actor):
    """Inform the student without ever exposing a document URL or token."""
    messages = {
        OfficialTranscriptRequest.STATUS_PROCESSING: "Votre demande de relevé officiel est en traitement.",
        OfficialTranscriptRequest.STATUS_AVAILABLE: "Votre relevé officiel est disponible auprès du service académique.",
        OfficialTranscriptRequest.STATUS_DELIVERED: "Votre relevé officiel a été remis.",
    }
    body = messages.get(transcript_request.status)
    if body:
        NotificationBus.notify(
            recipient=transcript_request.student.user, actor=actor,
            event_type=f"official_transcript_{transcript_request.status}",
            title="Suivi de votre relevé officiel", body=body, source_app="academics",
            priority=NotificationMessage.PRIORITY_HIGH,
            legacy_source="official_transcript_request",
            legacy_object_id=str(transcript_request.pk),
        )


def _transcript_action_response(request, transcript_request):
    if request.headers.get("HX-Request") == "true":
        response = render(request, "academics/partials/transcript_request_row.html", {"request_item": transcript_request})
        response["HX-Trigger"] = json.dumps({"ufhob:toast": {"level": "success", "message": "Statut du relevé mis à jour."}})
        return response
    return JsonResponse({"ok": True, "status": transcript_request.status})


def _get_managed_transcript_request(request, transcript_request_id):
    transcript_request = get_object_or_404(
        scoped(OfficialTranscriptRequest, user=request.user).select_related(
            "student__user", "enrollment__programme__school", "enrollment__branch",
            "enrollment__academic_class", "academic_year", "semester", "bulletin",
        ), pk=transcript_request_id,
    )
    if not transcript_request.semester_id or not can_manage_bulletins(request.user, transcript_request.semester.academic_class):
        raise PermissionDenied("Accès réservé au personnel académique autorisé.")
    return transcript_request


@login_required
def director_transcript_requests_view(request):
    """Scoped operational queue; URL filters can only narrow the user's scope."""
    from accounts.access import get_user_position
    if not request.user.is_superuser and get_user_position(request.user) not in {
        "super_admin", "executive_director", "deputy_executive_director",
        "director_of_studies", "academic_supervisor",
    }:
        raise PermissionDenied("Accès réservé au personnel académique autorisé.")
    candidates = scoped(OfficialTranscriptRequest, user=request.user).select_related(
        "student__user", "enrollment__programme__school", "enrollment__branch",
        "enrollment__academic_class", "academic_year", "semester", "bulletin",
    )
    candidates = [item for item in candidates if item.semester_id and can_manage_bulletins(request.user, item.semester.academic_class)]
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip().casefold()
    requested_filters = {
        "school": request.GET.get("school", "").strip(),
        "branch": request.GET.get("branch", "").strip(),
        "programme": request.GET.get("programme", "").strip(),
        "academic_class": request.GET.get("academic_class", "").strip(),
        "semester": request.GET.get("semester", "").strip(),
        "academic_year": request.GET.get("academic_year", "").strip(),
    }
    def matches(item):
        enrollment = item.enrollment
        return (
            (not status or item.status == status)
            and (not query or query in item.student.full_name.casefold() or query in getattr(item.student, "matricule", "").casefold())
            and (not requested_filters["school"] or str(enrollment.programme.school_id) == requested_filters["school"])
            and (not requested_filters["branch"] or str(enrollment.branch_id) == requested_filters["branch"])
            and (not requested_filters["programme"] or str(enrollment.programme_id) == requested_filters["programme"])
            and (not requested_filters["academic_class"] or str(enrollment.academic_class_id) == requested_filters["academic_class"])
            and (not requested_filters["semester"] or str(item.semester_id) == requested_filters["semester"])
            and (not requested_filters["academic_year"] or str(item.academic_year_id) == requested_filters["academic_year"])
        )
    return render(request, "academics/director_transcript_requests.html", {
        "transcript_requests": [item for item in candidates if matches(item)],
        "status_choices": OfficialTranscriptRequest.STATUS_CHOICES,
    })


@login_required
@require_POST
def director_take_transcript_request_view(request, transcript_request_id):
    transcript_request = _get_managed_transcript_request(request, transcript_request_id)
    if transcript_request.status != transcript_request.STATUS_REQUESTED:
        return HttpResponse("Cette demande n'est plus en attente.", status=409)
    transcript_request.status = transcript_request.STATUS_PROCESSING
    transcript_request.processing_by = request.user
    transcript_request.processed_at = timezone.now()
    transcript_request.save(update_fields=["status", "processing_by", "processed_at"])
    _audit(request, "official_transcript_processing", student=transcript_request.student, transcript_request=transcript_request)
    _notify_transcript_status(transcript_request, request.user)
    return _transcript_action_response(request, transcript_request)


@login_required
@require_POST
def director_generate_transcript_view(request, transcript_request_id):
    transcript_request = _get_managed_transcript_request(request, transcript_request_id)
    if transcript_request.status != transcript_request.STATUS_PROCESSING:
        return HttpResponse("La demande doit être en traitement avant génération.", status=409)
    bulletin = generate_semester_bulletin(
        enrollment=transcript_request.enrollment, semester=transcript_request.semester,
        actor=request.user, publish=True,
    )
    transcript_request.bulletin = bulletin
    transcript_request.save(update_fields=["bulletin"])
    _audit(request, "official_transcript_generated", student=transcript_request.student,
           transcript_request=transcript_request, bulletin_id=bulletin.id)
    return _transcript_action_response(request, transcript_request)


@login_required
@require_POST
def director_mark_transcript_available_view(request, transcript_request_id):
    transcript_request = _get_managed_transcript_request(request, transcript_request_id)
    if transcript_request.status != transcript_request.STATUS_PROCESSING or not transcript_request.bulletin_id:
        return HttpResponse("Générez le relevé avant de le déclarer disponible.", status=409)
    transcript_request.status = transcript_request.STATUS_AVAILABLE
    transcript_request.available_at = timezone.now()
    transcript_request.save(update_fields=["status", "available_at"])
    _audit(request, "official_transcript_available", student=transcript_request.student, transcript_request=transcript_request)
    _notify_transcript_status(transcript_request, request.user)
    return _transcript_action_response(request, transcript_request)


@login_required
@require_POST
def director_mark_transcript_delivered_view(request, transcript_request_id):
    transcript_request = _get_managed_transcript_request(request, transcript_request_id)
    if transcript_request.status != transcript_request.STATUS_AVAILABLE:
        return HttpResponse("Le relevé doit d'abord être déclaré disponible.", status=409)
    transcript_request.status = transcript_request.STATUS_DELIVERED
    transcript_request.delivered_by = request.user
    transcript_request.delivered_at = timezone.now()
    transcript_request.save(update_fields=["status", "delivered_by", "delivered_at"])
    _audit(request, "official_transcript_delivered", student=transcript_request.student, transcript_request=transcript_request)
    _notify_transcript_status(transcript_request, request.user)
    return _transcript_action_response(request, transcript_request)


def _render_semester_report_pdf(request, student_id, semester_id):
    context = _build_semester_report_context(request, student_id, semester_id)
    bulletin = context["bulletin"]
    if bulletin.pdf_file:
        with bulletin.pdf_file.open("rb") as pdf_file:
            pdf_bytes = pdf_file.read()
    else:
        backend_error = _ensure_pdf_backend()
        if backend_error is not None:
            return None, None, backend_error
        html = render_to_string(
            "academics/reports/bulletin_esfe.html",
            context,
            request=request,
        )
        pdf_bytes = HTML(
            string=html,
            base_url=request.build_absolute_uri(),
        ).write_pdf()
    return pdf_bytes, context, None


def _normalize_selected_student_ids(raw_ids):
    normalized_ids = []
    for value in raw_ids:
        try:
            normalized_ids.append(int(value))
        except (TypeError, ValueError):
            continue
    # Preserve order while deduplicating.
    return list(dict.fromkeys(normalized_ids))


def _get_class_student_ids(semester):
    enrollments = (
        AcademicEnrollment.objects.select_related("student")
        .filter(
            academic_class=semester.academic_class,
            academic_year=semester.academic_class.academic_year,
            is_active=True,
        )
        .order_by(
            "student__student_profile__inscription__candidature__last_name",
            "student__student_profile__inscription__candidature__first_name",
        )
    )
    return [enrollment.student.student_profile.id for enrollment in enrollments]


@login_required
def student_semester_report_view(request, student_id, semester_id):
    # Official transcript layouts are never an owner/student portal feature.
    semester = get_object_or_404(Semester.objects.select_related("academic_class"), id=semester_id)
    if not can_manage_bulletins(request.user, semester.academic_class):
        raise PermissionDenied("Le relevé officiel est réservé au service académique.")
    context = _build_semester_report_context(request, student_id, semester_id)
    return render(request, "academics/reports/bulletin_esfe.html", context)


@login_required
def student_semester_pdf_view(request, student_id, semester_id):
    semester = get_object_or_404(Semester.objects.select_related("academic_class"), id=semester_id)
    if not can_manage_bulletins(request.user, semester.academic_class):
        raise PermissionDenied("Le relevé officiel est réservé au service académique.")
    pdf_bytes, context, backend_error = _render_semester_report_pdf(request, student_id, semester_id)
    if backend_error is not None:
        return backend_error

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{_build_semester_report_filename(context)}"'
    return response


@login_required
def export_selected_reports_view(request, semester_id):
    if request.method != "POST":
        return HttpResponse("Methode non autorisee.", status=405)

    semester = get_object_or_404(
        Semester.objects.select_related("academic_class__branch"),
        id=semester_id,
    )
    _ensure_can_view_class_reports(request, semester.academic_class)
    selected_ids = _normalize_selected_student_ids(request.POST.getlist("selected_students"))
    if not selected_ids:
        return HttpResponse("Aucun etudiant selectionne.", status=400)

    backend_error = _ensure_pdf_backend()
    if backend_error is not None:
        return backend_error

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for student_id in selected_ids:
            pdf_bytes, context, backend_error = _render_semester_report_pdf(request, student_id, semester.id)
            if backend_error is not None:
                return backend_error
            archive.writestr(_build_semester_report_filename(context), pdf_bytes)

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="releves-selection-s{semester.number}.zip"'
    return response


@login_required
def export_class_reports_view(request, semester_id):
    semester = get_object_or_404(
        Semester.objects.select_related("academic_class__branch"),
        id=semester_id,
    )
    _ensure_can_view_class_reports(request, semester.academic_class)
    backend_error = _ensure_pdf_backend()
    if backend_error is not None:
        return backend_error

    student_ids = _get_class_student_ids(semester)
    if not student_ids:
        return HttpResponse("Aucun etudiant disponible pour cette classe.", status=404)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for student_id in student_ids:
            pdf_bytes, context, backend_error = _render_semester_report_pdf(request, student_id, semester.id)
            if backend_error is not None:
                return backend_error
            archive.writestr(_build_semester_report_filename(context), pdf_bytes)

    response = HttpResponse(zip_buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="releves-classe-s{semester.number}.zip"'
    return response


@login_required
def class_reports_overview_view(request, semester_id):
    from core.pdf_documents import get_document_branding_context

    semester = get_object_or_404(
        Semester.objects.select_related("academic_class__programme__school__institution", "academic_class__programme__cycle", "academic_class__academic_year", "academic_class__branch"),
        id=semester_id,
    )
    _ensure_can_view_class_reports(request, semester.academic_class)
    published_bulletins = {
        bulletin.enrollment_id: bulletin
        for bulletin in AcademicBulletin.objects.filter(
            academic_class=semester.academic_class,
            semester=semester,
            bulletin_type=AcademicBulletin.TYPE_SEMESTER,
            status=AcademicBulletin.STATUS_PUBLISHED,
        )
    }
    rows = []
    enrollments = AcademicEnrollment.objects.select_related(
        "student__student_profile",
    ).filter(
        academic_class=semester.academic_class,
        academic_year=semester.academic_class.academic_year,
        is_active=True,
    ).order_by("student__student_profile__matricule", "id")
    for enrollment in enrollments:
        student = enrollment.student.student_profile
        rows.append({
            "student_id": student.id,
            "student_name": student.full_name,
            "student_matricule": student.matricule,
            "bulletin": published_bulletins.get(enrollment.id),
        })

    return render(
        request,
        "academics/reports/class_report_overview.html",
        {
            "semester": semester,
            "academic_class": semester.academic_class,
            "branding": get_document_branding_context(semester.academic_class, request=request),
            "rows": rows,
        },
    )


@login_required
def annual_class_report_view(request, class_id):
    from core.pdf_documents import get_document_branding_context

    academic_class = get_object_or_404(AcademicClass.objects.select_related("programme__school__institution", "programme__cycle", "academic_year", "branch"), pk=class_id)
    _ensure_can_view_class_reports(request, academic_class)
    data = build_annual_class_report(class_id)
    data["branding"] = get_document_branding_context(academic_class, request=request)
    return render(
        request,
        "academics/reports/annual_class_report.html",
        data,
    )


@login_required
def student_annual_report_view(request, student_id):
    student = _resolve_report_student(student_id)
    academic_year_id = (request.GET.get("academic_year_id") or "").strip()
    if academic_year_id and not academic_year_id.isdigit():
        raise Http404("Annee academique invalide.")
    academic_year = (
        get_object_or_404(AcademicYear, pk=int(academic_year_id))
        if academic_year_id
        else None
    )
    # Annual reports are official documents and must never be rendered to a student portal user.
    enrollment = student.user.academic_enrollments.filter(academic_year=academic_year).select_related("academic_class").first() if academic_year else student.user.academic_enrollments.select_related("academic_class").order_by("-created_at").first()
    if not enrollment or not can_manage_bulletins(request.user, enrollment.academic_class):
        raise PermissionDenied("Acces refuse a ce rapport academique.")
    data = build_student_annual_report(
        student_id,
        academic_year_id=academic_year.id if academic_year else None,
    )
    return render(
        request,
        "academics/reports/student_annual_report.html",
        data,
    )


@login_required
def student_year_report_view(request, student_id, academic_year_id):
    student = _resolve_report_student(student_id)
    academic_year = get_object_or_404(AcademicYear, pk=academic_year_id)
    enrollment = student.user.academic_enrollments.filter(academic_year=academic_year).select_related("academic_class").first()
    if not enrollment or not can_manage_bulletins(request.user, enrollment.academic_class):
        raise PermissionDenied("Acces refuse a ce rapport academique.")
    context = build_student_annual_report(student_id, academic_year_id=academic_year_id)
    return render(request, "academics/reports/year_report.html", context)


@login_required
@require_POST
def generate_semester_bulletin_view(request, enrollment_id, semester_id):
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related(
            "student__student_profile",
            "academic_class__branch",
            "academic_year",
            "programme",
            "branch",
        ),
        pk=enrollment_id,
    )
    if not can_manage_bulletins(request.user, enrollment.academic_class):
        raise PermissionDenied("Vous n'etes pas autorise a generer ce bulletin.")
    semester = get_object_or_404(Semester, pk=semester_id, academic_class=enrollment.academic_class)
    bulletin = generate_semester_bulletin(
        enrollment=enrollment,
        semester=semester,
        actor=request.user,
        publish=True,
    )
    return JsonResponse({"ok": True, "bulletin_id": bulletin.pk, "reference": bulletin.reference})


@login_required
@require_POST
def generate_annual_bulletin_view(request, enrollment_id):
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related(
            "student__student_profile",
            "academic_class__branch",
            "academic_year",
            "programme",
            "branch",
        ),
        pk=enrollment_id,
    )
    if not can_manage_bulletins(request.user, enrollment.academic_class):
        raise PermissionDenied("Vous n'etes pas autorise a generer ce bulletin.")
    bulletin = generate_annual_bulletin(enrollment=enrollment, actor=request.user, publish=True)
    return JsonResponse({"ok": True, "bulletin_id": bulletin.pk, "reference": bulletin.reference})


@login_required
def bulletin_detail_view(request, bulletin_id):
    bulletin = get_object_or_404(
        AcademicBulletin.objects.select_related(
            "student__user",
            "enrollment",
            "academic_year",
            "academic_class__branch",
            "branch",
            "semester",
        ),
        pk=bulletin_id,
        status=AcademicBulletin.STATUS_PUBLISHED,
    )
    if not can_manage_bulletins(request.user, bulletin.academic_class):
        raise PermissionDenied("Acces refuse a ce bulletin.")
    return render(request, "academics/reports/bulletin_esfe.html", build_bulletin_context(bulletin, request=request))


@login_required
def bulletin_pdf_view(request, bulletin_id):
    bulletin = get_object_or_404(
        AcademicBulletin.objects.select_related(
            "student__user",
            "enrollment",
            "academic_year",
            "academic_class__branch",
            "branch",
            "semester",
        ),
        pk=bulletin_id,
        status=AcademicBulletin.STATUS_PUBLISHED,
    )
    if not can_manage_bulletins(request.user, bulletin.academic_class):
        raise PermissionDenied("Acces refuse a ce bulletin.")
    _audit(request, "official_transcript_downloaded", student=bulletin.student, bulletin_id=bulletin.id)
    if bulletin.pdf_file:
        response = FileResponse(
            bulletin.pdf_file.open("rb"),
            content_type="application/pdf",
        )
        response["Content-Disposition"] = f'inline; filename="bulletin-{bulletin.reference}.pdf"'
        return response

    try:
        pdf_bytes = render_bulletin_pdf_bytes(bulletin)
    except ValidationError as exc:
        return HttpResponse(" ".join(exc.messages), status=500, content_type="text/plain; charset=utf-8")
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="bulletin-{bulletin.reference}.pdf"'
    return response


@login_required
@require_POST
def prepare_diploma_award_view(request, enrollment_id):
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.select_related(
            "student__student_profile",
            "academic_class__branch",
            "academic_year",
            "programme__diploma_awarded",
            "branch",
        ),
        pk=enrollment_id,
    )
    if not can_manage_diplomas(request.user, enrollment.academic_class):
        raise PermissionDenied("Vous n'etes pas autorise a preparer ce diplome.")
    award = prepare_diploma_award(enrollment=enrollment, actor=request.user)
    return JsonResponse({"ok": True, "diploma_award_id": award.pk, "reference": award.reference})


@login_required
def diploma_award_detail_view(request, award_id):
    award = get_object_or_404(
        AcademicDiplomaAward.objects.select_related(
            "student__user",
            "enrollment",
            "academic_year",
            "academic_class__branch",
            "branch",
            "programme",
            "diploma",
        ),
        pk=award_id,
    )
    if not can_view_student_academic_report(request.user, award.student, academic_class=award.academic_class):
        raise PermissionDenied("Acces refuse a ce diplome.")
    return render(request, "academics/reports/diploma_award.html", build_diploma_context(award, request=request))


@login_required
def diploma_award_pdf_view(request, award_id):
    award = get_object_or_404(
        AcademicDiplomaAward.objects.select_related(
            "student__user",
            "enrollment",
            "academic_year",
            "academic_class__branch",
            "branch",
            "programme",
            "diploma",
        ),
        pk=award_id,
    )
    if not can_view_student_academic_report(request.user, award.student, academic_class=award.academic_class):
        raise PermissionDenied("Acces refuse a ce diplome.")
    context = build_diploma_context(award, request=request)
    pdf_bytes, backend_error = _render_pdf_from_template(request, "academics/reports/diploma_award.html", context)
    if backend_error is not None:
        return backend_error
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="diplome-{award.reference}.pdf"'
    return response


def _parse_json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"Corps JSON invalide: {exc.msg}") from exc


def _resolve_branch(request, payload):
    user_branch = get_user_branch(request.user)
    if user_branch is not None:
        return user_branch
    branch_id = payload.get("branch_id")
    if not branch_id:
        raise ValidationError("branch_id est obligatoire pour cet utilisateur.")
    return get_object_or_404(Branch, pk=branch_id)


def _parse_iso_date(raw_value):
    try:
        return date.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("date doit etre au format YYYY-MM-DD.") from exc


def _parse_time(raw_value, *, field_name):
    try:
        return time.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} doit etre au format HH:MM[:SS].") from exc


def _serialize_lesson_log(lesson_log):
    return {
        "id": lesson_log.id,
        "class_id": lesson_log.academic_class_id,
        "class_name": lesson_log.academic_class.display_name,
        "subject_id": lesson_log.ec_id,
        "subject_title": lesson_log.ec.title,
        "teacher_id": lesson_log.teacher_id,
        "teacher_name": lesson_log.teacher.get_full_name() or lesson_log.teacher.username,
        "date": lesson_log.date.isoformat(),
        "start_time": lesson_log.start_time.strftime("%H:%M"),
        "end_time": lesson_log.end_time.strftime("%H:%M"),
        "status": lesson_log.status,
        "content": lesson_log.content,
        "homework": lesson_log.homework,
        "observations": lesson_log.observations,
        "branch_id": lesson_log.branch_id,
        "schedule_event_id": lesson_log.schedule_event_id,
    }


@login_required
@require_POST
def lesson_log_create_view(request):
    try:
        payload = _parse_json_body(request)
        if payload.get("validated") and not _can_validate_lesson_log(request.user):
            return JsonResponse({"ok": False, "errors": ["Validation réservée au contrôle académique."]}, status=403)
        branch = _resolve_branch(request, payload)
        academic_class = get_object_or_404(AcademicClass.objects.select_related("branch"), pk=payload.get("academic_class_id"))
        ec = get_object_or_404(EC.objects.select_related("ue__semester__academic_class"), pk=payload.get("ec_id"))
        teacher = get_object_or_404(User, pk=payload.get("teacher_id"))
        schedule_event = None
        schedule_event_id = payload.get("schedule_event_id")
        if schedule_event_id:
            schedule_event = get_object_or_404(AcademicScheduleEvent, pk=schedule_event_id)

        lesson_log = create_lesson_log(
            academic_class=academic_class,
            ec=ec,
            teacher=teacher,
            schedule_event=schedule_event,
            date=_parse_iso_date(payload.get("date")),
            start_time=_parse_time(payload.get("start_time"), field_name="start_time"),
            end_time=_parse_time(payload.get("end_time"), field_name="end_time"),
            status=payload.get("status"),
            branch=branch,
            created_by=request.user,
            validated_by=request.user if payload.get("validated") else None,
            content=payload.get("content", ""),
            homework=payload.get("homework", ""),
            observations=payload.get("observations", ""),
        )
        return JsonResponse({"ok": True, "lesson_log": _serialize_lesson_log(lesson_log)}, status=201)
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)


@login_required
@require_POST
def lesson_log_update_view(request, lesson_log_id):
    try:
        payload = _parse_json_body(request)
        if payload.get("validated") and not _can_validate_lesson_log(request.user):
            return JsonResponse({"ok": False, "errors": ["Validation réservée au contrôle académique."]}, status=403)
        lesson_log = get_object_or_404(
            LessonLog.objects.select_related("academic_class__branch", "ec", "teacher", "branch", "schedule_event"),
            pk=lesson_log_id,
        )
        user_branch = get_user_branch(request.user)
        if user_branch and lesson_log.branch_id != user_branch.id:
            return JsonResponse({"ok": False, "errors": ["Acces refuse a cette annexe."]}, status=403)

        changes = {}
        simple_fields = ["status", "content", "homework", "observations"]
        for field in simple_fields:
            if field in payload:
                changes[field] = payload[field]
        if "date" in payload:
            changes["date"] = _parse_iso_date(payload.get("date"))
        if "start_time" in payload:
            changes["start_time"] = _parse_time(payload.get("start_time"), field_name="start_time")
        if "end_time" in payload:
            changes["end_time"] = _parse_time(payload.get("end_time"), field_name="end_time")
        if "validated" in payload and payload.get("validated"):
            changes["validated_by"] = request.user

        lesson_log = update_lesson_log(lesson_log, updated_by=request.user, **changes)
        return JsonResponse({"ok": True, "lesson_log": _serialize_lesson_log(lesson_log)})
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)


@login_required
@require_GET
def class_lesson_logs_view(request, class_id):
    academic_class = get_object_or_404(AcademicClass.objects.select_related("branch"), pk=class_id)
    user_branch = get_user_branch(request.user)
    if user_branch and academic_class.branch_id != user_branch.id:
        return JsonResponse({"ok": False, "errors": ["Acces refuse a cette annexe."]}, status=403)
    logs = get_class_lesson_logs(academic_class)
    return JsonResponse({"ok": True, "lesson_logs": [_serialize_lesson_log(log) for log in logs]})


@login_required
@require_GET
def teacher_lesson_logs_view(request, teacher_id):
    teacher = get_object_or_404(User, pk=teacher_id)
    branch = get_user_branch(request.user)
    logs = get_teacher_lesson_logs(teacher, branch=branch.id if branch else request.GET.get("branch_id"))
    return JsonResponse({"ok": True, "lesson_logs": [_serialize_lesson_log(log) for log in logs]})


@login_required
@require_GET
def daily_lesson_status_view(request):
    try:
        branch = _resolve_branch(request, request.GET)
        status_date = _parse_iso_date(request.GET.get("date"))
        data = get_daily_lesson_status(branch, status_date)
        payload = {
            **data,
            "date": data["date"].isoformat(),
            "lesson_logs": [_serialize_lesson_log(log) for log in data["lesson_logs"]],
        }
        return JsonResponse({"ok": True, "data": payload})
    except ValidationError as exc:
        return JsonResponse({"ok": False, "errors": exc.messages}, status=400)
