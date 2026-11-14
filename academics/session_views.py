import json

from django.db import transaction
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from django.utils import timezone

from accounts.scoping import object_in_scope, scoped
from academics.models import AcademicScheduleEvent, CourseSessionAssistSession, LessonLog
from academics.services.course_session_lifecycle import (
    CONTROL_POSITIONS,
    MANAGER_POSITIONS,
    create_assisted_session,
    end_teacher_session,
    get_effective_status,
    teacher_check_in,
    record_journal_submission,
    validate_service_exception,
)
from academics.services.lesson_log_service import create_lesson_log, update_lesson_log
from academics.services.online_class_service import end_teacher_online_session


def _position(user):
    return str(getattr(getattr(user, "profile", None), "position", "") or "")


def _request_metadata(request):
    return {
        "ip": request.META.get("REMOTE_ADDR", ""),
        "user_agent": (request.META.get("HTTP_USER_AGENT", "") or "")[:300],
    }


def _htmx_result(request, *, message, level="success", status=204):
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(status=status)
        response["HX-Trigger"] = json.dumps({
            "teacher-toast": {"message": message, "type": level},
            "teacher-dashboard-refresh": True,
        })
        return response
    messages.success(request, message)
    return redirect("academics:course_session_detail", event_id=request.resolver_match.kwargs["event_id"])


def _validation_error_response(request, exc):
    if hasattr(exc, "message_dict"):
        message = " ".join(item for values in exc.message_dict.values() for item in values)
    else:
        message = " ".join(getattr(exc, "messages", [])) or str(exc)
    if request.headers.get("HX-Request") == "true":
        response = HttpResponse(message, status=400)
        response["HX-Trigger"] = json.dumps({"teacher-toast": {"message": message, "type": "error"}})
        return response
    messages.error(request, message)
    return redirect("academics:course_session_detail", event_id=request.resolver_match.kwargs["event_id"])


@login_required
@require_POST
def course_session_check_in(request, event_id):
    event = get_object_or_404(AcademicScheduleEvent, pk=event_id, is_active=True)
    try:
        result = teacher_check_in(
            event=event,
            teacher=request.user,
            request_metadata=_request_metadata(request),
        )
    except PermissionDenied as exc:
        return HttpResponseForbidden(str(exc))
    except ValidationError as exc:
        return _validation_error_response(request, exc)
    if result.effective_status == "scheduled":
        local_start = timezone.localtime(result.starts_at).strftime("%H:%M")
        message = f"Presence enregistree. La seance commence a {local_start}."
    else:
        message = "Seance demarree."
    return _htmx_result(request, message=message)


@login_required
@require_POST
def course_session_end(request, event_id):
    event = get_object_or_404(AcademicScheduleEvent, pk=event_id, is_active=True)
    try:
        if event.is_online:
            end_teacher_online_session(
                teacher=request.user,
                branch=event.branch,
                event_id=event.pk,
            )
        else:
            end_teacher_session(
                event=event,
                teacher=request.user,
                request_metadata=_request_metadata(request),
            )
    except PermissionDenied as exc:
        return HttpResponseForbidden(str(exc))
    except ValidationError as exc:
        return _validation_error_response(request, exc)
    return _htmx_result(request, message="Seance terminee. Completez maintenant le cahier de texte.")


@login_required
@never_cache
def course_session_detail(request, event_id):
    event = get_object_or_404(
        scoped(AcademicScheduleEvent, user=request.user).select_related(
            "teacher__profile", "academic_class__programme__school", "branch", "ec"
        ),
        pk=event_id,
    )
    position = _position(request.user)
    can_read = request.user.pk == event.teacher_id or request.user.is_superuser or position in (
        CONTROL_POSITIONS | {"executive_director", "deputy_executive_director", "super_admin"}
    )
    if not can_read or not object_in_scope(event, user=request.user):
        raise PermissionDenied("Cette seance est hors de votre perimetre.")
    lesson_log = event.lesson_logs.select_related("validated_by", "assisted_by").order_by("-created_at").first()
    attendance = event.teacher_attendances.select_related("recorded_by").order_by("-created_at").first()
    execution = event.execution_logs.select_related("completed_by").order_by("-created_at").first()
    audits = event.workflow_audit_logs.select_related("actor").order_by("created_at", "id")
    from ui.services.standalone_shell import build_standalone_shell

    context = build_standalone_shell(request, key="course-session", title="Detail de la seance")
    context.update({
        "event": event,
        "lesson_log": lesson_log,
        "attendance": attendance,
        "execution": execution,
        "audits": audits,
        "effective_status": get_effective_status(event, lesson_log=lesson_log),
        "can_validate_exception": (
            (request.user.is_superuser or position in MANAGER_POSITIONS)
            and lesson_log is not None
            and lesson_log.status == LessonLog.STATUS_SUBMITTED
        ),
        "can_start_assist": (
            (request.user.is_superuser or position in MANAGER_POSITIONS)
            and timezone.now() >= event.start_datetime
            and (lesson_log is None or lesson_log.status in {LessonLog.STATUS_PLANNED, LessonLog.STATUS_RETURNED})
        ),
    })
    return render(request, "academics/course_session_detail.html", context)


@login_required
@require_POST
def course_session_validate_exception(request, event_id):
    event = get_object_or_404(scoped(AcademicScheduleEvent, user=request.user), pk=event_id)
    lesson_log = event.lesson_logs.order_by("-created_at").first()
    if lesson_log is None:
        return HttpResponseBadRequest("Aucun cahier soumis pour cette seance.")
    try:
        validate_service_exception(
            lesson_log=lesson_log,
            manager=request.user,
            reason=request.POST.get("reason"),
            comment=request.POST.get("comment"),
            request_metadata=_request_metadata(request),
        )
    except PermissionDenied as exc:
        return HttpResponseForbidden(str(exc))
    except ValidationError as exc:
        return _validation_error_response(request, exc)
    messages.success(request, "Service valide exceptionnellement. La seance est prete pour les honoraires.")
    return redirect("academics:course_session_detail", event_id=event.pk)


@login_required
@require_POST
def course_session_assist_start(request, event_id):
    event = get_object_or_404(scoped(AcademicScheduleEvent, user=request.user), pk=event_id, is_active=True)
    try:
        assist_session, raw_token = create_assisted_session(event=event, manager=request.user)
    except PermissionDenied as exc:
        return HttpResponseForbidden(str(exc))
    except ValidationError as exc:
        return _validation_error_response(request, exc)
    assist_link = request.build_absolute_uri(reverse("academics:course_session_assist", args=[raw_token]))
    from ui.services.standalone_shell import build_standalone_shell

    context = build_standalone_shell(request, key="course-session", title="Session assistee")
    context.update({"event": event, "assist_session": assist_session, "assist_link": assist_link})
    return render(request, "academics/course_session_assist_started.html", context)


@never_cache
def course_session_assist(request, token):
    token_hash = CourseSessionAssistSession.hash_token(token)
    assist_session = CourseSessionAssistSession.objects.select_related(
        "event__teacher", "event__academic_class", "event__ec", "event__branch", "manager"
    ).filter(token_hash=token_hash).first()
    if assist_session is None or assist_session.is_expired or assist_session.used_at:
        return render(request, "academics/course_session_assist.html", {"invalid": True}, status=410)
    event = assist_session.event
    context = {"assist_session": assist_session, "event": event, "token": token}
    if request.method != "POST":
        return render(request, "academics/course_session_assist.html", context)

    username = (request.POST.get("username") or "").strip()
    password = request.POST.get("password") or ""
    teacher = authenticate(request=request, username=username, password=password)
    if teacher is None or teacher.pk != event.teacher_id:
        context["error"] = "Identifiants invalides pour l'enseignant affecte a cette seance."
        return render(request, "academics/course_session_assist.html", context, status=400)
    if request.POST.get("certified") != "on":
        context["error"] = "La certification de l'enseignant est obligatoire."
        return render(request, "academics/course_session_assist.html", context, status=400)
    content = (request.POST.get("content") or "").strip()
    if not content:
        context["error"] = "Le contenu effectivement traite est obligatoire."
        return render(request, "academics/course_session_assist.html", context, status=400)
    try:
        with transaction.atomic():
            locked = CourseSessionAssistSession.objects.select_for_update().get(pk=assist_session.pk)
            if locked.used_at or locked.is_expired:
                raise ValidationError("Cette session assistee a expire ou a deja ete utilisee.")
            lesson_log = event.lesson_logs.order_by("-created_at").first()
            payload = {
                "status": LessonLog.STATUS_PLANNED,
                "content": content,
                "chapter_progress": request.POST.get("chapter_progress", ""),
                "homework": request.POST.get("homework", ""),
                "observations": request.POST.get("observations", ""),
                "session_outcome": request.POST.get("session_outcome", LessonLog.OUTCOME_NORMAL),
            }
            if lesson_log is None:
                local_start = timezone.localtime(event.start_datetime)
                local_end = timezone.localtime(event.end_datetime)
                lesson_log = create_lesson_log(
                    academic_class=event.academic_class,
                    ec=event.ec,
                    teacher=teacher,
                    date=local_start.date(),
                    start_time=local_start.time(),
                    end_time=local_end.time(),
                    branch=event.branch,
                    created_by=teacher,
                    schedule_event=event,
                    **payload,
                )
            else:
                if lesson_log.validated_by_id or lesson_log.status == LessonLog.STATUS_SUBMITTED:
                    raise ValidationError("Ce cahier est deja soumis ou valide.")
                lesson_log = update_lesson_log(lesson_log, updated_by=teacher, **payload)
            record_journal_submission(
                lesson_log=lesson_log,
                teacher=teacher,
                assisted_by=locked.manager,
                request_metadata=_request_metadata(request),
            )
            locked.used_at = timezone.now()
            locked.save(update_fields=["used_at"])
    except ValidationError as exc:
        context["error"] = " ".join(exc.messages)
        return render(request, "academics/course_session_assist.html", context, status=400)
    context["completed"] = True
    return render(request, "academics/course_session_assist.html", context)
