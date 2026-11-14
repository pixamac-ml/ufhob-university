import json
from urllib.parse import parse_qs, urlparse
from urllib.parse import quote as urlquote

from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.contrib.auth import update_session_auth_hash
from django.conf import settings
from django.db import connection
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.exceptions import ValidationError
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from django.db.models import Prefetch, Q
from django.views.decorators.http import require_POST
from django.urls import reverse

from academics.forms import PedagogicalAnswerForm, PedagogicalQuestionForm
from academics.models import AcademicEnrollment, AcademicBulletin, AcademicDocumentAuditLog, EC, ECChapter, ECContent, ECGrade, ECResource, ECPedagogicalQuestion, OfficialTranscriptRequest, OnlineClassRecording, ResultAccessAuthorization, Semester, StudentContentProgress
from academics.permissions import can_manage_bulletins
from finance.services.student_clearance import get_financial_clearance
from notifier.models import NotificationMessage
from notifier.services import NotificationBus
from academics.services.course_interaction_service import create_student_answer, create_student_question, student_questions
from academics.services.online_class_service import (
    BigBlueButtonProviderError,
    OnlineClassNotReady,
    get_student_online_session_join_url,
)
from academics.services.recording_service import get_recording_download_url_for_user
from notifier.models import NotificationMessage
from portal.permissions import role_required
from portal.services.certified_dashboard_shell import build_role_dashboard_shell
from portal.services.staff import (
    build_staff_account_context,
    build_staff_messaging_context,
    resolve_staff_dashboard,
)

from .services import (
    get_student_dashboard_base_context,
    get_student_overview_data,
    get_student_courses_context,
    get_student_timetable_context,
    get_student_academic_calendar,
    get_student_teachers,
    is_semester_unlocked_for_enrollment,
)
from .profile_service import (
    accept_internal_rules,
    get_internal_rules_status,
    get_profile_data,
    handle_document_upload,
    update_account_center,
    update_account_password,
    update_account_preferences,
    update_editable_fields,
)
from .widgets.academics import get_academics_widget, get_student_academic_snapshot
from .widgets.finance import get_finance_widget
from shop.services.shop_service import get_required_shop_context


def _selected_academic_year_id(request):
    value = (request.GET.get("academic_year_id") or request.POST.get("academic_year_id") or "").strip()
    return int(value) if value.isdigit() else None


@login_required
@role_required("student")
def online_session_open(request, event_id):
    try:
        join_url = get_student_online_session_join_url(
            student=request.user, event_id=event_id
        )
    except OnlineClassNotReady as exc:
        return HttpResponse(exc.messages[0] if exc.messages else str(exc), status=409)
    except BigBlueButtonProviderError as exc:
        return HttpResponse(exc.messages[0], status=503)
    except ValidationError as exc:
        raise PermissionDenied(exc.messages[0] if exc.messages else str(exc))
    return redirect(join_url)


@login_required
@role_required("student")
def online_recording_download(request, recording_id):
    recording = get_object_or_404(OnlineClassRecording, pk=recording_id)
    try:
        return redirect(get_recording_download_url_for_user(
            user=request.user,
            recording=recording,
            force_download=request.GET.get("download") == "1",
        ))
    except PermissionDenied:
        raise
    except ValidationError as exc:
        return HttpResponse(exc.messages[0] if exc.messages else str(exc), status=409)


@login_required
@role_required("student")
def academic_calendar_pdf(request):
    """Give a student only the published calendar that applies to enrollment."""
    from academics.services.calendar_document_service import render_calendar_pdf_response

    snapshot = get_student_academic_snapshot(
        request.user, academic_year_id=_selected_academic_year_id(request)
    )
    enrollment = snapshot.get("academic_enrollment")
    calendar, _projection = get_student_academic_calendar(enrollment)
    if calendar is None:
        return HttpResponse("Aucun calendrier académique publié n’est disponible.", status=404)
    semester_ids = list(enrollment.academic_class.semesters.values_list("id", flat=True))
    try:
        return render_calendar_pdf_response(
            calendar,
            request=request,
            school=enrollment.programme.school,
            programme=enrollment.programme,
            academic_class=enrollment.academic_class,
            semester_ids=semester_ids,
            public_only=True,
        )
    except Exception as exc:
        return HttpResponse(
            f"Le PDF du calendrier n'a pas pu être généré : {exc}",
            status=500,
            content_type="text/plain; charset=utf-8",
        )


STUDENT_SECTION_TEMPLATES = {
    "overview": "portal/student/partials/overview_student.html",
    "courses": "portal/student/partials/courses_student.html",
    "schedule": "portal/student/partials/calendar_student.html",
    "academics": "portal/student/partials/academics.html",
    "messages": "portal/staff/shared/messaging/workspace.html",
    "teachers": "portal/student/partials/teachers_student.html",
    "shop": "portal/student/partials/shop_orders_student.html",
    "diplomas": "portal/student/partials/diplomas_student.html",
    "settings": "portal/student/partials/settings_student.html",
}

STUDENT_SECTION_META = {
    "overview": ("Vue générale", "Vos cours, votre planning et les actions utiles aujourd'hui."),
    "courses": ("Mes cours", "Une bibliothèque organisée par semestre et unité d'enseignement."),
    "schedule": ("Calendrier", "Votre emploi du temps et vos prochaines échéances."),
    "academics": ("Académique", "Résultats officiels, crédits et parcours en lecture seule."),
    "messages": ("Messagerie", "Vos échanges, notifications et messages institutionnels."),
    "teachers": ("Encadrement", "Vos enseignants et leurs créneaux pédagogiques."),
    "shop": ("Boutique", "Vos commandes et l'accès au catalogue UFHOB."),
    "diplomas": ("Diplômes et documents", "Vos documents académiques réellement disponibles."),
    "settings": ("Profil et paramètres", "Votre profil, la sécurité et les préférences du compte."),
}


def _with_year(url, academic_year_id):
    return f"{url}?academic_year_id={academic_year_id}" if academic_year_id else url


def _student_navigation(active_section, academic_year_id):
    dashboard_url = reverse("portal_student:dashboard")
    rows = [
        ("overview", "Vue générale", "layout-dashboard", "overview_partial"),
        ("courses", "Mes cours", "book-open-check", "courses_partial"),
        ("schedule", "Calendrier", "calendar-days", "timetable_partial"),
        ("academics", "Académique", "graduation-cap", "academics_partial"),
        ("messages", "Messagerie", "messages-square", "messages_partial"),
        ("teachers", "Encadrement", "users-round", "teachers_partial"),
        ("shop", "Boutique", "shopping-bag", "shop_orders_partial"),
        ("diplomas", "Diplômes / Documents", "award", "diplomas_partial"),
        ("settings", "Profil et paramètres", "user-cog", "settings_partial"),
    ]
    items = []
    for key, label, icon, url_name in rows:
        page_url = f"{dashboard_url}?section={key}"
        if academic_year_id:
            page_url = f"{dashboard_url}?section={key}&academic_year_id={academic_year_id}"
        items.append(
            {
                "key": key,
                "label": label,
                "icon": icon,
                "url": page_url,
                "hx_get": _with_year(reverse(f"portal_student:{url_name}"), academic_year_id),
                "hx_target": "#student-workspace",
                "hx_swap": "innerHTML",
                "hx_push_url": page_url,
                "active": key == active_section,
            }
        )
    return [{"label": "Espace étudiant", "items": items}]


def _student_shell_context(request, context, active_section, academic_year_id):
    enrollment = context.get("enrollment")
    academic_class = context.get("academic_class") or getattr(enrollment, "academic_class", None)
    academic_year = context.get("academic_year") or getattr(enrollment, "academic_year", None)
    programme = context.get("academic_programme") or getattr(enrollment, "programme", None)
    school = context.get("academic_school") or getattr(programme, "school", None)
    campus = context.get("academic_branch") or getattr(enrollment, "branch", None)
    labels = [
        getattr(school, "code", ""),
        f"Campus {campus.name}" if campus else "",
        getattr(academic_class, "display_name", "") or getattr(academic_class, "level", ""),
        getattr(programme, "title", ""),
        getattr(academic_year, "name", ""),
    ]
    context_label = " · ".join(label for label in labels if label) or "Affectation académique en attente"
    shell = build_role_dashboard_shell(
        request,
        role="student",
        key="student",
        title="Portail étudiant",
        subtitle="Espace étudiant",
        active_section=active_section,
        groups=_student_navigation(active_section, academic_year_id),
        dashboard_url=reverse("portal_student:dashboard"),
        workspace_template="portal/student/section_workspace.html",
        workspace_target="#student-workspace",
        context_label=context_label,
        page_title="Portail étudiant - UFHOB",
        topbar_template="portal/student/partials/topbar_actions_student.html",
        script_path="",
        stylesheet_path="portal/student/dashboard.css",
        drawer_title="Cours et ressources",
        modal_title="Portail étudiant",
    )
    context.update(shell)
    context["active_section"] = active_section
    context["section_template"] = STUDENT_SECTION_TEMPLATES[active_section]
    context["section_meta"] = {
        "title": STUDENT_SECTION_META[active_section][0],
        "description": STUDENT_SECTION_META[active_section][1],
    }
    return context


def _academic_chapters_available():
    return "academics_ecchapter" in connection.introspection.table_names()


def _content_prefetch():
    return Prefetch(
        "contents",
        queryset=ECContent.objects.filter(
            is_active=True,
            status=ECContent.STATUS_PUBLISHED,
        ).prefetch_related(
            Prefetch(
                "resources",
                queryset=ECResource.objects.filter(
                    is_active=True,
                    status=ECResource.STATUS_READY,
                ).order_by("order", "id"),
            )
        ).order_by("order", "id"),
    )


def _get_video_embed_url(video_url: str) -> str:
    if not video_url:
        return ""
    parsed = urlparse(video_url)
    host = (parsed.netloc or "").lower()

    if "youtube.com" in host:
        query = parse_qs(parsed.query)
        video_id = (query.get("v") or [""])[0]
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"
        if "/embed/" in parsed.path:
            return video_url
    if "youtu.be" in host:
        video_id = parsed.path.strip("/")
        if video_id:
            return f"https://www.youtube.com/embed/{video_id}"
    if "vimeo.com" in host:
        video_id = parsed.path.strip("/")
        if video_id.isdigit():
            return f"https://player.vimeo.com/video/{video_id}"
    return ""


def _content_progress_defaults(content):
    if content.content_type == ECContent.CONTENT_TYPE_TEXT:
        return {"initial_progress": 60, "completion_hint": "Lecture du texte puis validation manuelle."}
    if content.content_type == ECContent.CONTENT_TYPE_PDF:
        return {"initial_progress": 35, "completion_hint": "Consultation du support PDF."}
    if content.content_type in {ECContent.CONTENT_TYPE_DOC, ECContent.CONTENT_TYPE_EXCEL, ECContent.CONTENT_TYPE_PPT}:
        return {"initial_progress": 25, "completion_hint": "Ouverture du document bureautique."}
    if content.content_type == ECContent.CONTENT_TYPE_IMAGE:
        return {"initial_progress": 70, "completion_hint": "Consultation du visuel pedagogique."}
    if content.content_type == ECContent.CONTENT_TYPE_VIDEO:
        return {"initial_progress": 15, "completion_hint": "Progression mise a jour pendant la lecture video."}
    if content.content_type == ECContent.CONTENT_TYPE_AUDIO:
        return {"initial_progress": 10, "completion_hint": "Progression mise a jour pendant l'ecoute audio."}
    return {"initial_progress": 20, "completion_hint": "Consultation du contenu."}


def _get_student_ec_queryset(enrollment):
    if enrollment is None:
        return EC.objects.none()

    queryset = (
        EC.objects.select_related(
            "ue",
            "ue__semester",
            "ue__semester__academic_class",
        )
        .filter(ue__semester__academic_class=enrollment.academic_class)
        .order_by("ue__semester__number", "ue__code", "id")
    )

    if _academic_chapters_available():
        queryset = queryset.prefetch_related(
            Prefetch(
                "chapters",
                queryset=ECChapter.objects.prefetch_related(_content_prefetch()).order_by("order", "id"),
            )
        )

    return queryset


def _prepare_chapter_contents(request, user, chapters):
    content_ids = [
        content.id
        for chapter in chapters
        for content in chapter.contents.all()
    ]
    progress_map = {
        entry.content_id: entry
        for entry in StudentContentProgress.objects.filter(
            student=user,
            content_id__in=content_ids,
        )
    }

    for chapter in chapters:
        chapter.active_contents = list(chapter.contents.all())
        chapter.active_content_count = len(chapter.active_contents)
        chapter.completed_content_count = 0
        chapter.has_accessible_content = False
        for content in chapter.active_contents:
            progress_entry = progress_map.get(content.id)
            content.student_progress_percent = progress_entry.progress_percent if progress_entry else 0
            content.student_is_completed = progress_entry.is_completed if progress_entry else False
            content.student_last_position = progress_entry.last_position if progress_entry else 0
            content.absolute_file_url = request.build_absolute_uri(content.file.url) if content.file else ""
            content.legacy_file_url = content.file.url if content.file else ""
            try:
                content.legacy_file_size_label = _format_resource_size(content.file.size) if content.file else ""
            except (OSError, ValueError):
                content.legacy_file_size_label = ""
            content.available_resources = list(content.resources.all())
            for resource in content.available_resources:
                resource.download_url = reverse("portal_student:course_resource_download", args=[resource.id])
                resource.preview_url = f"{resource.download_url}?disposition=inline"
                resource.size_label = _format_resource_size(resource.size_bytes)
            defaults = _content_progress_defaults(content)
            content.initial_progress_step = defaults["initial_progress"]
            content.completion_hint = defaults["completion_hint"]
            content.embed_video_url = _get_video_embed_url(content.video_url or "")
            content.video_try_direct_player = (
                content.content_type == ECContent.CONTENT_TYPE_VIDEO
                and not content.embed_video_url
                and bool((content.video_url or "").strip())
                and not content.file
            )
            content.preview_as_media = content.content_type in {
                ECContent.CONTENT_TYPE_AUDIO,
                ECContent.CONTENT_TYPE_IMAGE,
            }
            content.document_like = content.content_type in {
                ECContent.CONTENT_TYPE_DOC,
                ECContent.CONTENT_TYPE_EXCEL,
                ECContent.CONTENT_TYPE_PPT,
            }
            content.office_embed_url = ""
            if content.document_like and content.absolute_file_url:
                # Viewer Office Online (permet un rendu "inline" type Udemy).
                # Note: exige que l'URL soit accessible depuis le navigateur (et souvent publiquement).
                content.office_embed_url = (
                    "https://view.officeapps.live.com/op/embed.aspx?src="
                    + urlquote(content.absolute_file_url, safe="")
                )
            content.preview_with_iframe = bool(content.embed_video_url) or content.content_type == ECContent.CONTENT_TYPE_PDF
            content.has_inline_preview = (
                (content.content_type == ECContent.CONTENT_TYPE_VIDEO and bool(content.embed_video_url))
                or (content.document_like and bool(content.office_embed_url))
                or (content.content_type == ECContent.CONTENT_TYPE_AUDIO and bool(content.file))
                or (content.content_type == ECContent.CONTENT_TYPE_IMAGE and bool(content.file))
                or (content.content_type == ECContent.CONTENT_TYPE_PDF and bool(content.file))
                or (content.content_type == ECContent.CONTENT_TYPE_TEXT and bool((content.text_content or "").strip()))
            )
            content.has_accessible_source = bool(content.file or content.video_url or (content.text_content or "").strip())
            content.has_broken_source = not content.has_accessible_source
            content.source_label = {
                ECContent.CONTENT_TYPE_PDF: "Support PDF",
                ECContent.CONTENT_TYPE_VIDEO: "Video",
                ECContent.CONTENT_TYPE_DOC: "Document Word",
                ECContent.CONTENT_TYPE_EXCEL: "Fichier Excel",
                ECContent.CONTENT_TYPE_PPT: "Presentation",
                ECContent.CONTENT_TYPE_IMAGE: "Image",
                ECContent.CONTENT_TYPE_AUDIO: "Audio",
                ECContent.CONTENT_TYPE_TEXT: "Texte",
            }.get(content.content_type, "Contenu")
            if content.content_type == ECContent.CONTENT_TYPE_VIDEO and not content.embed_video_url and content.video_url and not content.file:
                content.preview_notice = ""
            elif content.document_like and content.file and not content.office_embed_url:
                content.preview_notice = "Consultez le document via le lecteur integre ou le telechargement."
            elif content.has_broken_source:
                content.preview_notice = "La ressource source est indisponible ou incomplete."
            else:
                content.preview_notice = ""
            chapter.completed_content_count += 1 if content.student_is_completed else 0
            chapter.has_accessible_content = chapter.has_accessible_content or content.has_accessible_source

    return chapters


def _format_resource_size(size_bytes):
    size = int(size_bytes or 0)
    if size < 1024 * 1024:
        return f"{max(1, round(size / 1024))} Ko"
    return f"{size / (1024 * 1024):.1f} Mo"


def _build_course_player_bundle(chapters, selected_content_id=None):
    flat_nav = []
    for chapter in chapters:
        for content in getattr(chapter, "active_contents", []):
            flat_nav.append(
                {
                    "id": content.id,
                    "title": content.title,
                    "chapter_title": chapter.title,
                    "done": bool(content.student_is_completed),
                }
            )
    initial_id = None
    if selected_content_id in {row["id"] for row in flat_nav}:
        initial_id = selected_content_id
    if initial_id is None:
        for row in flat_nav:
            if not row["done"]:
                initial_id = row["id"]
                break
    if initial_id is None and flat_nav:
        initial_id = flat_nav[0]["id"]
    return {"nav": flat_nav, "initialId": initial_id}


def _diplomas_context(user, academic_year_id):
    snapshot = get_student_academic_snapshot(user, academic_year_id=academic_year_id)
    student = snapshot["student"]
    enrollment = snapshot["academic_enrollment"]
    awards = []
    if student and enrollment:
        awards = student.academic_diploma_awards.select_related(
            "programme", "academic_year", "diploma", "branch"
        ).filter(
            enrollment=enrollment,
            status__in=("ready", "delivered"),
        ).order_by("-awarded_at", "-created_at")
    return {
        "awards": awards,
        "selected_academic_year_id": snapshot["selected_academic_year_id"],
    }


def _shop_orders_context(user):
    from shop.models import ShopOrder, ShopProduct

    orders = ShopOrder.objects.filter(student=user).select_related("branch").prefetch_related(
        "items", "payments"
    ).order_by("-created_at")[:50]
    branch_slug = None
    student_profile = getattr(user, "student_profile", None)
    if student_profile and student_profile.inscription and student_profile.inscription.candidature:
        branch_slug = student_profile.inscription.candidature.branch.slug
    return {
        "orders": orders,
        "branch_slug": branch_slug,
        "product_categories": ShopProduct.CATEGORY_CHOICES,
        "selected_sort": "featured",
    }


def _student_section_context(request, section, academic_year_id):
    user = request.user
    if section == "overview":
        return get_student_overview_data(user, academic_year_id=academic_year_id)
    if section == "courses":
        return get_student_courses_context(user, academic_year_id=academic_year_id)
    if section == "schedule":
        return get_student_timetable_context(user, academic_year_id=academic_year_id)
    if section == "academics":
        return get_academics_widget(user, academic_year_id=academic_year_id)
    if section == "messages":
        target = resolve_staff_dashboard("student")
        context = build_staff_messaging_context(
            request,
            detail_url_name="accounts_portal:staff_notification_detail",
            dash=target.key,
        )
        context.update(
            {
                "staff_dash": target.key,
                "staff_workspace_target": target.workspace_target,
                "staff_modal_target": target.modal_content_target,
                "staff_drawer_target": target.drawer_content_target,
                "messaging_eyebrow": "Communication UFHOB",
                "messaging_title": "Messagerie",
                "messaging_subtitle": "Consultez vos messages et échangez avec les interlocuteurs autorisés de votre annexe.",
            }
        )
        return context
    if section == "teachers":
        snapshot = get_student_academic_snapshot(user, academic_year_id=academic_year_id)
        student = snapshot["student"]
        return {
            "teachers": get_student_teachers(student, academic_year_id=academic_year_id) if student else [],
            "selected_academic_year_id": snapshot["selected_academic_year_id"],
        }
    if section == "shop":
        return _shop_orders_context(user)
    if section == "diplomas":
        return _diplomas_context(user, academic_year_id)
    if section == "settings":
        context = get_profile_data(user, academic_year_id=academic_year_id)
        context.update(
            build_staff_account_context(
                request,
                panel_url_name="accounts_portal:staff_account_panel",
                drawer_content_target="#student-drawer-content",
                panel_query="dash=student",
            )
        )
        panel_url = reverse("accounts_portal:staff_account_panel")
        context["common_account_urls"] = {
            "profile": f"{panel_url}?dash=student&view=profile",
            "edit": f"{panel_url}?dash=student&view=edit",
            "security": f"{panel_url}?dash=student&view=security",
            "preferences": f"{panel_url}?dash=student&view=preferences",
        }
        return context
    raise ValueError(f"Section étudiante inconnue: {section}")


def _render_student_section(request, section):
    academic_year_id = _selected_academic_year_id(request)
    context = get_student_dashboard_base_context(request.user, academic_year_id=academic_year_id)
    context.update(_student_section_context(request, section, academic_year_id))
    context["university_student_context"] = True
    context.update(
        {
            "active_section": section,
            "section_template": STUDENT_SECTION_TEMPLATES[section],
            "dashboard_url": reverse("portal_student:dashboard"),
            "section_meta": {
                "title": STUDENT_SECTION_META[section][0],
                "description": STUDENT_SECTION_META[section][1],
            },
        }
    )
    return render(request, "portal/student/section_workspace.html", context)


@login_required
@role_required("student")
def dashboard(request):
    academic_year_id = _selected_academic_year_id(request)
    active_section = request.GET.get("section", "overview").strip().lower()
    if active_section == "messages":
        from communications.compat import redirect_legacy_messages
        return redirect_legacy_messages(request)
    if active_section not in STUDENT_SECTION_TEMPLATES:
        active_section = "overview"
    context = (
        get_student_overview_data(request.user, academic_year_id=academic_year_id)
        if active_section == "overview"
        else get_student_dashboard_base_context(request.user, academic_year_id=academic_year_id)
    )
    if active_section != "overview":
        context.update(_student_section_context(request, active_section, academic_year_id))
    context["shop_required"] = get_required_shop_context(request.user)
    context["internal_rules"] = get_internal_rules_status(request.user)
    _student_shell_context(request, context, active_section, academic_year_id)
    return render(request, "portal/student/dashboard.html", context)


@login_required
@role_required("student")
def overview_partial(request):
    return _render_student_section(request, "overview")


@login_required
@role_required("student")
def teachers_partial(request):
    return _render_student_section(request, "teachers")


@login_required
@role_required("student")
def internal_rules_modal(request):
    context = get_internal_rules_status(request.user)
    if getattr(request, "htmx", None):
        context["show_popup"] = True
    return render(request, "portal/student/partials/internal_rules_modal.html", context)


@login_required
@role_required("student")
@require_POST
def accept_internal_rules_view(request):
    accept_internal_rules(request.user)
    return HttpResponse("")


@login_required
@role_required("student")
def academics_partial(request):
    return _render_student_section(request, "academics")


def _result_audit(request, action, *, student=None, authorization=None, transcript_request=None, **metadata):
    enrollment = getattr(authorization, "enrollment", None) or getattr(transcript_request, "enrollment", None)
    if enrollment is None and student is not None:
        enrollment = student.user.academic_enrollments.select_related("programme__school", "branch", "academic_year").order_by("-created_at").first()
    from accounts.access import get_user_position
    AcademicDocumentAuditLog.objects.create(action=action, actor=request.user, student=student,
        authorization=authorization, transcript_request=transcript_request, metadata=metadata,
        ip_address=request.META.get("REMOTE_ADDR"), user_agent=request.META.get("HTTP_USER_AGENT", "")[:512],
        school=getattr(getattr(enrollment, "programme", None), "school", None),
        branch=getattr(enrollment, "branch", None), academic_year=getattr(enrollment, "academic_year", None),
        actor_role=get_user_position(request.user))


def _student_semester(request, semester_id):
    snapshot = get_student_academic_snapshot(request.user, academic_year_id=_selected_academic_year_id(request))
    enrollment = snapshot["academic_enrollment"]
    semester = get_object_or_404(Semester, pk=semester_id, academic_class=getattr(enrollment, "academic_class", None), status=Semester.STATUS_PUBLISHED)
    return snapshot["student"], enrollment, semester


@login_required
@role_required("student")
@require_POST
def request_results_access(request, semester_id):
    student, enrollment, semester = _student_semester(request, semester_id)
    clearance = get_financial_clearance(student, enrollment, semester)
    _result_audit(request, "results_financial_checked", student=student, required=str(clearance.required_amount), paid=str(clearance.paid_amount), outstanding=str(clearance.outstanding_amount))
    if not clearance.is_cleared:
        return render(request, "portal/student/partials/results_blocked.html", {"clearance": clearance, "semester": semester}, status=403)
    authorization, created = ResultAccessAuthorization.objects.get_or_create(
        student=student, enrollment=enrollment, academic_year=enrollment.academic_year, semester=semester,
        status=ResultAccessAuthorization.STATUS_PENDING,
    )
    if created:
        _result_audit(request, "results_access_requested", student=student, authorization=authorization)
        from portal.dg.selectors import get_active_branch_directors_of_studies
        for director in get_active_branch_directors_of_studies(
            [enrollment.branch_id], school=enrollment.programme.school,
        ):
            NotificationBus.notify(recipient=director.user, actor=request.user, event_type="results_access_requested",
                title="Autorisation de résultats demandée", body=f"{student.full_name} demande l'accès au semestre {semester.number}.",
                source_app="academics", priority=NotificationMessage.PRIORITY_HIGH, legacy_source="result_access_authorization", legacy_object_id=str(authorization.id))
    return render(request, "portal/student/partials/results_access_pending.html", {"authorization": authorization, "semester": semester})


@login_required
@role_required("student")
@require_POST
def verify_results_otp(request, authorization_id):
    authorization = get_object_or_404(ResultAccessAuthorization.objects.select_related("student__user", "semester", "enrollment"), pk=authorization_id, student__user=request.user)
    now = timezone.now()
    if authorization.status != authorization.STATUS_APPROVED or not authorization.expires_at or authorization.expires_at <= now:
        if authorization.status == authorization.STATUS_APPROVED:
            authorization.status = authorization.STATUS_EXPIRED; authorization.save(update_fields=["status"])
        _result_audit(request, "results_otp_expired", student=authorization.student, authorization=authorization)
        raise PermissionDenied("Cette autorisation a expiré.")
    code = (request.POST.get("otp") or "").strip()
    if authorization.attempts >= 5 or not check_password(code, authorization.otp_hash):
        authorization.attempts += 1
        if authorization.attempts >= 5: authorization.status = authorization.STATUS_EXPIRED
        authorization.save(update_fields=["attempts", "status"])
        _result_audit(request, "results_otp_rejected", student=authorization.student, authorization=authorization)
        raise PermissionDenied("Code invalide.")
    authorization.status = authorization.STATUS_USED; authorization.used_at = now
    authorization.save(update_fields=["status", "used_at"])
    grades = ECGrade.objects.filter(enrollment=authorization.enrollment, ec__ue__semester=authorization.semester).select_related("ec", "ec__ue")
    _result_audit(request, "results_consulted", student=authorization.student, authorization=authorization)
    return render(request, "portal/student/partials/results_simplified.html", {"semester": authorization.semester, "grades": grades, "student": authorization.student, "consulted_at": now})


@login_required
@role_required("student")
@require_POST
def request_official_transcript(request, semester_id):
    student, enrollment, semester = _student_semester(request, semester_id)
    transcript_request, created = OfficialTranscriptRequest.objects.get_or_create(
        student=student, enrollment=enrollment, academic_year=enrollment.academic_year,
        semester=semester, status=OfficialTranscriptRequest.STATUS_REQUESTED,
    )
    if created:
        _result_audit(request, "official_transcript_requested", student=student, transcript_request=transcript_request)
        from portal.dg.selectors import get_active_branch_directors_of_studies
        for director in get_active_branch_directors_of_studies(
            [enrollment.branch_id], school=enrollment.programme.school,
        ):
            NotificationBus.notify(recipient=director.user, actor=request.user, event_type="official_transcript_requested", title="Nouvelle demande de relevé officiel", body=f"{student.full_name} — semestre {semester.number}.", source_app="academics", priority=NotificationMessage.PRIORITY_HIGH, legacy_source="official_transcript_request", legacy_object_id=str(transcript_request.id))
    return render(request, "portal/student/partials/official_transcript_request_status.html", {"transcript_request": transcript_request})


@login_required
@role_required("student")
def diplomas_partial(request):
    return _render_student_section(request, "diplomas")


@login_required
@role_required("student")
def finance_partial(request):
    academic_year_id = _selected_academic_year_id(request)
    context = get_student_dashboard_base_context(request.user, academic_year_id=academic_year_id)
    context.update(get_finance_widget(
        request.user,
        academic_year_id=academic_year_id,
    ))
    return render(request, "portal/student/partials/finance.html", context)


@login_required
@role_required("student")
def settings_partial(request):
    return _render_student_section(request, "settings")

def _render_settings_response(request, context):
    context["finance_widget"] = get_finance_widget(
        request.user,
        academic_year_id=_selected_academic_year_id(request),
    )
    return render(request, "portal/student/partials/settings_student.html", context)


@login_required
@role_required("student")
def courses_partial(request):
    return _render_student_section(request, "courses")


@login_required
@role_required("student")
def messages_partial(request):
    from communications.compat import redirect_legacy_messages
    return redirect_legacy_messages(request)
    response = _render_student_section(request, "messages")
    academic_year_id = _selected_academic_year_id(request)
    dashboard_url = f"{reverse('portal_student:dashboard')}?section=messages"
    if academic_year_id:
        dashboard_url += f"&academic_year_id={academic_year_id}"
    response["HX-Push-Url"] = dashboard_url
    return response


@login_required
@role_required("student")
@require_POST
def mark_message_read(request, message_id):
    notification = get_object_or_404(
        NotificationMessage,
        pk=message_id,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    if notification.read_at is None:
        now = timezone.now()
        notification.read_at = now
        notification.status = NotificationMessage.STATUS_READ
        notification.save(update_fields=["read_at", "status", "updated_at"])

    unread_count = NotificationMessage.objects.filter(
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
        read_at__isnull=True,
    ).count()
    return JsonResponse({"ok": True, "unread_count": unread_count, "message_id": notification.id})


@login_required
@role_required("student")
@require_POST
def mark_all_messages_read(request):
    now = timezone.now()
    NotificationMessage.objects.filter(
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
        read_at__isnull=True,
    ).update(
        read_at=now,
        status=NotificationMessage.STATUS_READ,
        updated_at=now,
    )
    return JsonResponse({"ok": True, "unread_count": 0})


@login_required
@role_required("student")
@require_POST
def mark_message_unread(request, message_id):
    notification = get_object_or_404(
        NotificationMessage,
        pk=message_id,
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
    )
    if notification.read_at is not None:
        notification.read_at = None
        notification.status = NotificationMessage.STATUS_DELIVERED
        notification.save(update_fields=["read_at", "status", "updated_at"])

    unread_count = NotificationMessage.objects.filter(
        recipient=request.user,
        channel=NotificationMessage.CHANNEL_IN_APP,
        read_at__isnull=True,
    ).count()
    return JsonResponse({"ok": True, "unread_count": unread_count, "message_id": notification.id})


@login_required
@role_required("student")
def shop_orders_partial(request):
    return _render_student_section(request, "shop")


@login_required
@role_required("student")
def shop_catalog_partial(request):
    from shop.models import ShopProduct
    from shop.services.shop_service import get_recommended_products_for_student

    products = get_recommended_products_for_student(request.user)
    query = (request.GET.get("q") or "").strip().casefold()
    category = (request.GET.get("category") or "").strip()
    sort = (request.GET.get("sort") or "featured").strip()
    if query:
        products = [
            product for product in products
            if query in product.name.casefold()
            or query in (product.sku or "").casefold()
            or query in product.get_category_display().casefold()
        ]
    if category:
        products = [product for product in products if product.category == category]
    if sort == "price_asc":
        products.sort(key=lambda product: product.effective_price)
    elif sort == "price_desc":
        products.sort(key=lambda product: product.effective_price, reverse=True)
    elif sort == "promotion":
        products = [product for product in products if product.sale_price is not None]
    return render(request, "portal/student/partials/shop_catalog_student.html", {
        "products": products,
        "query": request.GET.get("q", ""),
        "selected_category": category,
        "selected_sort": sort,
        "product_categories": ShopProduct.CATEGORY_CHOICES,
    })


@login_required
@role_required("student")
def shop_cart_partial(request):
    from shop.forms import StudentRemoteOrderRequestForm
    from shop.services.shop_service import get_student_cart

    cart = get_student_cart(request.user)

    return render(request, "shop/partials/student_cart.html", {
        "cart": cart,
        "order_request_form": StudentRemoteOrderRequestForm(
            branch=getattr(cart, "branch", None),
        ),
    })


@login_required
@role_required("student")
def timetable_partial(request):
    return _render_student_section(request, "schedule")


@login_required
@role_required("student")
def student_courses(request):
    url = f"{reverse('portal_student:dashboard')}?section=courses"
    academic_year_id = _selected_academic_year_id(request)
    if academic_year_id:
        url += f"&academic_year_id={academic_year_id}"
    return redirect(url)


def _build_course_player_context(request, ec_id):
    academic_snapshot = get_student_academic_snapshot(
        request.user,
        academic_year_id=_selected_academic_year_id(request),
    )
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.filter(pk=getattr(academic_snapshot["academic_enrollment"], "pk", None)),
    )

    ec_queryset = EC.objects.select_related(
        "ue",
        "ue__semester",
        "ue__semester__academic_class",
    )
    if _academic_chapters_available():
        ec_queryset = ec_queryset.prefetch_related(
            Prefetch(
                "chapters",
                queryset=ECChapter.objects.prefetch_related(_content_prefetch()).order_by("order", "id"),
            )
        )

    ec = get_object_or_404(
        ec_queryset,
        pk=ec_id,
        ue__semester__academic_class=enrollment.academic_class,
    )
    if not is_semester_unlocked_for_enrollment(enrollment, ec.ue.semester.number):
        raise PermissionDenied("Ce semestre est verrouille tant que les semestres precedents ne sont pas valides.")

    chapters = list(ec.chapters.all()) if _academic_chapters_available() else []
    _prepare_chapter_contents(request, request.user, chapters)
    total_active_content_count = sum(chapter.active_content_count for chapter in chapters)
    total_completed_content_count = sum(chapter.completed_content_count for chapter in chapters)
    has_any_accessible_content = any(chapter.has_accessible_content for chapter in chapters)

    selected_content_id = request.GET.get("content_id")
    selected_content_id = int(selected_content_id) if str(selected_content_id).isdigit() else None
    player_bundle = _build_course_player_bundle(chapters, selected_content_id)
    ordered_contents = [
        content
        for chapter in chapters
        for content in getattr(chapter, "active_contents", [])
    ]
    selected_content = next(
        (content for content in ordered_contents if content.id == player_bundle["initialId"]),
        None,
    )
    selected_index = ordered_contents.index(selected_content) if selected_content else -1
    course_resources = []
    for chapter in chapters:
        for content in getattr(chapter, "active_contents", []):
            for resource in getattr(content, "available_resources", []):
                resource.chapter_title = chapter.title
                resource.lesson_title = content.title
                resource.is_legacy_course_resource = False
                course_resources.append(resource)
            # Legacy file-based lessons remain available as course resources;
            # their pedagogical lesson rendering is deliberately unchanged.
            if content.file and content.content_type != ECContent.CONTENT_TYPE_VIDEO:
                course_resources.append({
                    "id": f"legacy-{content.id}",
                    "title": content.title,
                    "chapter_title": chapter.title,
                    "lesson_title": content.title,
                    "resource_type_label": content.get_content_type_display(),
                    "size_label": content.legacy_file_size_label,
                    "download_url": content.legacy_file_url,
                    "preview_url": content.legacy_file_url,
                    "is_legacy_course_resource": True,
                    "is_pdf": content.content_type == ECContent.CONTENT_TYPE_PDF,
                })
    return {
        "page_title": ec.title,
        "subtitle": "Contenus lies a cette matiere.",
        "enrollment": enrollment,
        "ec": ec,
        "chapters_available": _academic_chapters_available(),
        "chapters": chapters,
        "chapter_count": len(chapters),
        "total_active_content_count": total_active_content_count,
        "total_completed_content_count": total_completed_content_count,
        "has_any_accessible_content": has_any_accessible_content,
        "player_bundle": player_bundle,
        "selected_content": selected_content,
        "previous_content": ordered_contents[selected_index - 1] if selected_index > 0 else None,
        "next_content": (
            ordered_contents[selected_index + 1]
            if selected_index >= 0 and selected_index + 1 < len(ordered_contents)
            else None
        ),
        "course_resources": course_resources,
        "course_progress_percent": (
            round((total_completed_content_count / total_active_content_count) * 100)
            if total_active_content_count else 0
        ),
    }


def _student_interaction_context(request, player_context, *, question_form=None, answer_form=None, selected_question=None, toast=None):
    enrollment, ec, selected_content = player_context["enrollment"], player_context["ec"], player_context["selected_content"]
    questions = student_questions(enrollment=enrollment, ec=ec)
    scope = request.GET.get("question_scope", "all")
    if scope == "lesson" and selected_content:
        questions = questions.filter(lesson=selected_content)
    elif scope == "unanswered":
        questions = questions.filter(answers__isnull=True)
    elif scope == "recent":
        questions = questions.order_by("-created_at", "-id")
    query = (request.GET.get("question_q") or "").strip()
    if query:
        questions = questions.filter(Q(title__icontains=query) | Q(body__icontains=query))
    if selected_question is not None:
        selected_question = questions.filter(pk=selected_question.pk).prefetch_related("answers__author").first()
    return {
        "course_questions": questions,
        "course_question_scope": scope,
        "course_question_query": query,
        "course_question_form": question_form or PedagogicalQuestionForm(),
        "course_answer_form": answer_form or PedagogicalAnswerForm(),
        "selected_course_question": selected_question,
        "course_interaction_toast": toast,
        "course_interactions_url": reverse("portal_student:course_questions", args=[ec.id]),
        "course_question_create_url": reverse("portal_student:course_question_create", args=[ec.id]),
        "course_selected_lesson": selected_content,
    }
@login_required
@role_required("student")
def course_learn(request, ec_id):
    """Dedicated learning page; HTMX stays inside the page only."""
    context = _build_course_player_context(request, ec_id)
    academic_year_id = _selected_academic_year_id(request)
    player_tab = (request.GET.get("tab") or "course").strip().lower()
    if player_tab not in {"course", "resources", "questions", "exercises"}:
        player_tab = "course"
    context["player_tab"] = player_tab
    context.update(
        {
            "course_url": reverse("portal_student:course_learn", args=[ec_id]),
            "selected_academic_year_id": academic_year_id,
            "back_to_courses_url": (
                f"{reverse('portal_student:dashboard')}?section=courses"
                f"{'&academic_year_id=' + str(academic_year_id) if academic_year_id else ''}"
            ),
        }
    )
    context.update(_student_interaction_context(request, context))
    if getattr(request, "htmx", False):
        return render(request, "portal/student/course_player_page.html", context)
    return render(request, "portal/student/course_player.html", context)


@login_required
@role_required("student")
def course_questions(request, ec_id):
    context = _build_course_player_context(request, ec_id)
    question_id = request.GET.get("question_id")
    selected_question = None
    if str(question_id).isdigit():
        selected_question = get_object_or_404(student_questions(enrollment=context["enrollment"], ec=context["ec"]), pk=int(question_id))
    context.update(_student_interaction_context(request, context, selected_question=selected_question))
    return render(request, "portal/student/partials/course_interactions.html", context)


@login_required
@role_required("student")
def course_question_thread(request, ec_id, question_id):
    context = _build_course_player_context(request, ec_id)
    question = get_object_or_404(
        student_questions(enrollment=context["enrollment"], ec=context["ec"]), pk=question_id
    )
    context.update(_student_interaction_context(request, context, selected_question=question))
    return render(request, "portal/student/partials/course_interaction_thread_history.html", context)


@login_required
@role_required("student")
@require_POST
def course_question_create(request, ec_id):
    context = _build_course_player_context(request, ec_id)
    form = PedagogicalQuestionForm(request.POST)
    toast = None
    if form.is_valid():
        lesson = None if request.POST.get("scope") == "course" else context["selected_content"]
        try:
            create_student_question(student=request.user, enrollment=context["enrollment"], ec=context["ec"], lesson=lesson, **form.cleaned_data)
            form = PedagogicalQuestionForm()
            toast = {"level": "success", "message": "Votre question a été publiée."}
        except ValidationError as exc:
            form.add_error(None, exc)
    context.update(_student_interaction_context(request, context, question_form=form, toast=toast))
    return render(request, "portal/student/partials/course_interactions.html", context)


@login_required
@role_required("student")
@require_POST
def course_question_answer(request, ec_id, question_id):
    context = _build_course_player_context(request, ec_id)
    question = get_object_or_404(student_questions(enrollment=context["enrollment"], ec=context["ec"]), pk=question_id)
    form = PedagogicalAnswerForm(request.POST)
    toast = None
    if form.is_valid():
        try:
            create_student_answer(student=request.user, enrollment=context["enrollment"], question=question, **form.cleaned_data)
            form = PedagogicalAnswerForm()
            toast = {"level": "success", "message": "Votre réponse a été publiée."}
        except ValidationError as exc:
            form.add_error(None, exc)
    context.update(_student_interaction_context(request, context, answer_form=form, selected_question=question, toast=toast))
    return render(request, "portal/student/partials/course_interactions.html", context)


@login_required
@role_required("student")
def ec_detail(request, ec_id):
    """Compatibility endpoint for historical course links."""
    # Do not turn a historical URL into an authorization bypass.  The
    # dedicated player owns the authoritative class/year/semester checks, so
    # validate them before issuing the redirect as well.
    _build_course_player_context(request, ec_id)
    url = reverse("portal_student:course_learn", args=[ec_id])
    academic_year_id = _selected_academic_year_id(request)
    if academic_year_id:
        url = f"{url}?academic_year_id={academic_year_id}"
    return redirect(url)


@login_required
@role_required("student")
def course_resource_download(request, resource_id):
    """Serve a private lesson resource only after enrolment and publication checks."""
    academic_snapshot = get_student_academic_snapshot(
        request.user,
        academic_year_id=_selected_academic_year_id(request),
    )
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.filter(pk=getattr(academic_snapshot["academic_enrollment"], "pk", None)),
    )
    resource = get_object_or_404(
        ECResource.objects.select_related("lesson__chapter__ec__ue__semester__academic_class"),
        pk=resource_id,
        is_active=True,
        status=ECResource.STATUS_READY,
        lesson__is_active=True,
        lesson__status=ECContent.STATUS_PUBLISHED,
        lesson__chapter__ec__ue__semester__academic_class=enrollment.academic_class,
    )
    if not resource.file:
        raise PermissionDenied("Cette ressource n'est pas disponible.")
    if not is_semester_unlocked_for_enrollment(
        enrollment,
        resource.lesson.chapter.ec.ue.semester.number,
    ):
        raise PermissionDenied("Ce semestre est verrouille tant que les semestres precedents ne sont pas valides.")
    if settings.COURSE_MEDIA_S3_CONFIGURED:
        # The storage backend generates a short-lived signed B2/S3 URL only
        # after all student/enrolment/publication checks above have passed.
        return redirect(resource.file.url)
    disposition = "inline" if request.GET.get("disposition") == "inline" and resource.resource_type == ECResource.RESOURCE_TYPE_PDF else "attachment"
    return FileResponse(
        resource.file.open("rb"),
        as_attachment=disposition == "attachment",
        filename=resource.original_filename or resource.title,
    )


@login_required
@role_required("student")
@require_POST
def update_content_progress(request, content_id):
    academic_snapshot = get_student_academic_snapshot(
        request.user,
        academic_year_id=_selected_academic_year_id(request),
    )
    enrollment = get_object_or_404(
        AcademicEnrollment.objects.filter(pk=getattr(academic_snapshot["academic_enrollment"], "pk", None)),
    )
    content = get_object_or_404(
        ECContent.objects.select_related("chapter__ec__ue__semester"),
        pk=content_id,
        is_active=True,
        status=ECContent.STATUS_PUBLISHED,
        chapter__ec__ue__semester__academic_class=enrollment.academic_class,
    )
    if not is_semester_unlocked_for_enrollment(
        enrollment,
        content.chapter.ec.ue.semester.number,
    ):
        raise PermissionDenied("Ce semestre est verrouille tant que les semestres precedents ne sont pas valides.")

    payload = json.loads(request.body or "{}")
    progress_percent = int(payload.get("progress_percent", 0) or 0)
    last_position = int(payload.get("last_position", 0) or 0)
    progress_percent = max(0, min(progress_percent, 100))
    # Completion is a consequence of meaningful consumption. The client can
    # report a reading/video position but cannot turn a lesson into completed
    # with an arbitrary boolean flag.
    is_completed = progress_percent >= 90

    progress, _ = StudentContentProgress.objects.get_or_create(
        student=request.user,
        content=content,
        defaults={
            "progress_percent": progress_percent,
            "last_position": max(0, last_position),
            "is_completed": is_completed,
        },
    )

    if progress.progress_percent < progress_percent:
        progress.progress_percent = progress_percent
    progress.last_position = max(progress.last_position, max(0, last_position))
    progress.is_completed = progress.is_completed or is_completed or progress.progress_percent >= 100
    if progress.is_completed:
        progress.progress_percent = 100
    progress.save()

    return JsonResponse(
        {
            "ok": True,
            "progress_percent": progress.progress_percent,
            "is_completed": progress.is_completed,
        }
    )


@login_required
@role_required("student")
@require_POST
def update_settings_profile(request):
    academic_year_id = _selected_academic_year_id(request)
    try:
        context = update_editable_fields(
            request.user,
            {
                "email": request.POST.get("email", ""),
                "phone": request.POST.get("phone", ""),
            },
            academic_year_id=academic_year_id,
        )
        context["form_success"] = "Informations mises a jour."
        context["form_errors"] = {}
    except ValidationError as exc:
        context = get_profile_data(request.user, academic_year_id=academic_year_id)
        context["form_success"] = ""
        context["form_errors"] = getattr(exc, "message_dict", {"__all__": exc.messages})
    return _render_settings_response(request, context)


@login_required
@role_required("student")
@require_POST
def upload_settings_document(request):
    academic_year_id = _selected_academic_year_id(request)
    try:
        context = handle_document_upload(
            request.user,
            request.FILES.get("file"),
            int(request.POST.get("document_type_id") or 0),
            academic_year_id=academic_year_id,
        )
        context["form_success"] = "Document televerse avec succes."
        context["form_errors"] = {}
    except (ValidationError, ValueError) as exc:
        context = get_profile_data(request.user, academic_year_id=academic_year_id)
        if isinstance(exc, ValidationError):
            context["form_errors"] = getattr(exc, "message_dict", {"__all__": exc.messages})
        else:
            context["form_errors"] = {"document_type_id": ["Type de document invalide."]}
        context["form_success"] = ""
    return _render_settings_response(request, context)


@login_required
@role_required("student")
@require_POST
def update_settings_account(request):
    academic_year_id = _selected_academic_year_id(request)
    try:
        context = update_account_center(request.user, request.POST, academic_year_id=academic_year_id)
        context["form_success"] = "Informations du compte mises a jour."
        context["form_errors"] = {}
    except ValidationError as exc:
        context = get_profile_data(request.user, academic_year_id=academic_year_id)
        context["form_success"] = ""
        context["form_errors"] = getattr(exc, "message_dict", {"__all__": exc.messages})
    return _render_settings_response(request, context)


@login_required
@role_required("student")
@require_POST
def update_settings_preferences(request):
    academic_year_id = _selected_academic_year_id(request)
    try:
        context = update_account_preferences(request.user, request.POST, academic_year_id=academic_year_id)
        context["form_success"] = "Preferences mises a jour."
        context["form_errors"] = {}
    except ValidationError as exc:
        context = get_profile_data(request.user, academic_year_id=academic_year_id)
        context["form_success"] = ""
        context["form_errors"] = getattr(exc, "message_dict", {"__all__": exc.messages})
    return _render_settings_response(request, context)


@login_required
@role_required("student")
@require_POST
def update_settings_password(request):
    academic_year_id = _selected_academic_year_id(request)
    try:
        context = update_account_password(request.user, request.POST, academic_year_id=academic_year_id)
        update_session_auth_hash(request, request.user)
        from accounts.models import AccountSecurityEvent, AccountSessionRecord
        from accounts.session_policy import SESSION_ID_KEY, log_security_event
        from accounts.session_security import revoke_user_sessions

        log_security_event(
            user=request.user,
            event_type=AccountSecurityEvent.PASSWORD_CHANGED,
            request=request,
            identifier=request.session.get(SESSION_ID_KEY),
            reason=AccountSessionRecord.END_PASSWORD_CHANGED,
            authentication_method="self_service",
        )
        revoke_user_sessions(
            request.user,
            exclude_session_key=request.session.session_key,
            reason=AccountSessionRecord.END_PASSWORD_CHANGED,
        )
        context["form_success"] = "Mot de passe mis a jour."
        context["form_errors"] = {}
    except ValidationError as exc:
        context = get_profile_data(request.user, academic_year_id=academic_year_id)
        context["form_success"] = ""
        context["form_errors"] = getattr(exc, "message_dict", {"__all__": exc.messages})
    return _render_settings_response(request, context)
