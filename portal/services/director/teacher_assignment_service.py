from accounts.scoping import scoped
from accounts.position_registry import TEACHING_POSITIONS
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from academics.models import (
    AcademicScheduleEvent,
    AcademicScheduleExecutionLog,
    LessonLog,
    WeeklyScheduleSlot,
)
from academics.services.teaching_metrics import teaching_time_metrics
from portal.models import DirectorTeacherAssignment, TeacherDocument
from students.models import TeacherAttendance


COURSE_EVENT_TYPES = (
    AcademicScheduleEvent.EVENT_TYPE_COURSE,
    AcademicScheduleEvent.EVENT_TYPE_PRACTICAL,
    AcademicScheduleEvent.EVENT_TYPE_SEMINAR,
)


def _hours_between(start, end):
    """Return an exact Decimal duration; never estimate teaching time."""
    if not start or not end or end <= start:
        return Decimal("0")
    seconds = Decimal(str((datetime.combine(timezone.localdate(), end) - datetime.combine(timezone.localdate(), start)).total_seconds()))
    return seconds / Decimal("3600")


def _lesson_hours(lesson_log):
    return _hours_between(lesson_log.start_time, lesson_log.end_time)


def build_teacher_service_monitoring_context(*, branch, academic_year, teacher_ids=None):
    """Build the DE's auditable teaching-service view from authoritative data.

    A scheduled event never becomes a completed or payable session by itself.
    Completion needs an operational trace (attendance, execution trace, or an
    approved lesson log); payment eligibility is restricted to the exact same
    validated lesson logs consumed by the manager honorarium workflow.
    """
    User = get_user_model()
    teachers = scoped(User).none()
    if branch is not None:
        teachers = scoped(User).select_related("profile").filter(
            is_active=True,
            profile__position__in=TEACHING_POSITIONS,
            profile__branch=branch,
        )
    if teacher_ids is not None:
        teachers = teachers.filter(pk__in=teacher_ids)
    teachers = list(teachers.order_by("first_name", "last_name", "username"))
    teacher_id_set = {teacher.id for teacher in teachers}
    if not teacher_id_set or branch is None or academic_year is None:
        return {
            "teacher_service_rows": [],
            "teacher_service_summary": {
                "assigned_hours": Decimal("0"), "scheduled_hours": Decimal("0"),
                "actual_hours": Decimal("0"), "validated_hours": Decimal("0"),
                "payable_hours": Decimal("0"), "anomaly_count": 0,
            },
            "teacher_service_anomalies": [],
        }

    assignments = list(
        scoped(DirectorTeacherAssignment).select_related("academic_class", "ec")
        .filter(
            branch=branch,
            teacher_id__in=teacher_id_set,
            is_active=True,
            academic_class__academic_year=academic_year,
        )
        # ``display_name`` is a Python property of AcademicClass, not a SQL
        # field.  Order through persisted fields so this works on PostgreSQL.
        .order_by(
            "teacher_id",
            "academic_class__programme__title",
            "academic_class__level",
            "academic_class__name",
            "ec__title",
            "id",
        )
    )
    events = list(
        scoped(AcademicScheduleEvent).select_related("academic_class", "ec", "teacher")
        .filter(
            branch=branch,
            academic_year=academic_year,
            teacher_id__in=teacher_id_set,
            event_type__in=COURSE_EVENT_TYPES,
            is_active=True,
        )
        .exclude(status__in=(AcademicScheduleEvent.STATUS_DRAFT, AcademicScheduleEvent.STATUS_CANCELLED))
        .order_by("teacher_id", "start_datetime", "id")
    )
    event_ids = [event.id for event in events]
    attendance_by_event = {
        (item.schedule_event_id, item.teacher_id): item
        for item in TeacherAttendance.objects.filter(
            branch=branch, schedule_event_id__in=event_ids
        )
    }
    executions_by_event = defaultdict(list)
    for execution in AcademicScheduleExecutionLog.objects.filter(event_id__in=event_ids):
        executions_by_event[execution.event_id].append(execution)

    lesson_logs = list(
        scoped(LessonLog).select_related("academic_class", "ec", "schedule_event", "validated_by")
        .filter(
            branch=branch,
            teacher_id__in=teacher_id_set,
            academic_class__academic_year=academic_year,
        )
        .order_by("teacher_id", "date", "start_time", "id")
    )
    logs_by_event = defaultdict(list)
    manual_logs_by_teacher = defaultdict(list)
    for lesson_log in lesson_logs:
        if lesson_log.schedule_event_id:
            logs_by_event[lesson_log.schedule_event_id].append(lesson_log)
        else:
            manual_logs_by_teacher[lesson_log.teacher_id].append(lesson_log)

    rows = {
        teacher.id: {
            "teacher": teacher,
            "assigned_hours": Decimal("0"),
            "scheduled_hours": Decimal("0"),
            "actual_hours": Decimal("0"),
            "validated_hours": Decimal("0"),
            # Kept distinct in the payload even though the finance source uses
            # these exact validated hours.  This makes the hand-off explicit.
            "payable_hours": Decimal("0"),
            "assigned_count": 0,
            "scheduled_count": 0,
            "actual_count": 0,
            "validated_count": 0,
            "pending_validation_count": 0,
            "absence_count": 0,
            "late_count": 0,
            "missing_evidence_count": 0,
            "unplanned_log_count": 0,
            "subjects": {},
            "anomalies": [],
            "recent_sessions": [],
        }
        for teacher in teachers
    }
    now = timezone.now()

    def subject_row(row, *, ec):
        return row["subjects"].setdefault(
            ec.id,
            {
                "ec_id": ec.id,
                "ec_title": ec.title,
                "assigned_hours": Decimal("0"),
                "scheduled_hours": Decimal("0"),
                "actual_hours": Decimal("0"),
                "validated_hours": Decimal("0"),
                "payable_hours": Decimal("0"),
                "scheduled_count": 0,
                "actual_count": 0,
                "validated_count": 0,
                "pending_validation_count": 0,
                "absence_count": 0,
            },
        )

    for assignment in assignments:
        row = rows[assignment.teacher_id]
        hours = assignment.planned_hours or Decimal("0")
        row["assigned_hours"] += hours
        row["assigned_count"] += 1
        if assignment.ec_id:
            subject_row(row, ec=assignment.ec)["assigned_hours"] += hours

    for event in events:
        row = rows[event.teacher_id]
        subject = subject_row(row, ec=event.ec)
        scheduled_hours = Decimal(event.duration_minutes) / Decimal("60")
        row["scheduled_hours"] += scheduled_hours
        row["scheduled_count"] += 1
        subject["scheduled_hours"] += scheduled_hours
        subject["scheduled_count"] += 1

        attendance = attendance_by_event.get((event.id, event.teacher_id))
        event_logs = [log for log in logs_by_event.get(event.id, []) if log.teacher_id == event.teacher_id]
        validated_logs = [
            log for log in event_logs
            if log.status == LessonLog.STATUS_DONE and log.validated_by_id
        ]
        submitted_logs = [log for log in event_logs if log.status == LessonLog.STATUS_SUBMITTED]
        event_executions = executions_by_event.get(event.id, [])
        execution_completed = any(item.is_completed for item in event_executions)
        actual_log = next((log for log in reversed(event_logs) if log.status == LessonLog.STATUS_DONE), None)
        has_actual_evidence = bool(
            (attendance and attendance.course_delivered is True)
            or execution_completed
            or actual_log
        )
        metrics = teaching_time_metrics(
            event=event,
            lesson_log=actual_log,
            execution_logs=event_executions,
        )
        actual_hours = Decimal(metrics["actual_minutes"] or 0) / Decimal("60")

        if has_actual_evidence:
            row["actual_hours"] += actual_hours
            row["actual_count"] += 1
            subject["actual_hours"] += actual_hours
            subject["actual_count"] += 1
        if validated_logs:
            # A single scheduled session has one payable service amount even if
            # legacy imports left more than one log linked to it.
            validated_metrics = teaching_time_metrics(
                event=event,
                lesson_log=validated_logs[-1],
                execution_logs=event_executions,
            )
            validated_hours = Decimal(validated_metrics["validatable_minutes"]) / Decimal("60")
            row["validated_hours"] += validated_hours
            row["payable_hours"] += validated_hours
            row["validated_count"] += 1
            subject["validated_hours"] += validated_hours
            subject["payable_hours"] += validated_hours
            subject["validated_count"] += 1
        elif submitted_logs:
            row["pending_validation_count"] += 1
            subject["pending_validation_count"] += 1

        if attendance and attendance.status == TeacherAttendance.STATUS_ABSENT:
            row["absence_count"] += 1
            subject["absence_count"] += 1
            row["anomalies"].append({
                "kind": "absence", "event": event,
                "message": "Absence enseignant constatée pour cette séance.",
            })
        elif attendance and attendance.course_delivered is False:
            row["anomalies"].append({
                "kind": "not_delivered", "event": event,
                "message": "Cours constaté non assuré par la supervision.",
            })
        elif event.end_datetime < now and not has_actual_evidence:
            # Missing optional traces are an evidence gap, never a fabricated
            # absence.  The DE can investigate from the linked session.
            row["missing_evidence_count"] += 1
            row["anomalies"].append({
                "kind": "missing_evidence", "event": event,
                "message": "Séance passée sans preuve de réalisation ni cahier validé.",
            })
        if attendance and attendance.status == TeacherAttendance.STATUS_LATE:
            row["late_count"] += 1

        row["recent_sessions"].append({
            "event": event,
            "is_replacement": bool(event.original_teacher_id),
            "attendance": attendance,
            "lesson_log": event_logs[-1] if event_logs else None,
            "is_actual": has_actual_evidence,
            "is_validated": bool(validated_logs),
            "time_metrics": metrics,
        })

    for teacher_id, logs in manual_logs_by_teacher.items():
        row = rows[teacher_id]
        for lesson_log in logs:
            subject = subject_row(row, ec=lesson_log.ec)
            row["unplanned_log_count"] += 1
            row["anomalies"].append({
                "kind": "unplanned_log", "event": None, "lesson_log": lesson_log,
                "message": "Cahier déclaré sans séance officielle liée.",
            })
            if lesson_log.status == LessonLog.STATUS_DONE:
                hours = _lesson_hours(lesson_log)
                row["actual_hours"] += hours
                row["actual_count"] += 1
                subject["actual_hours"] += hours
                subject["actual_count"] += 1
                if lesson_log.validated_by_id:
                    row["validated_hours"] += hours
                    row["payable_hours"] += hours
                    row["validated_count"] += 1
                    subject["validated_hours"] += hours
                    subject["payable_hours"] += hours
                    subject["validated_count"] += 1

    anomalies = []
    result_rows = []
    for row in rows.values():
        row["is_monitor"] = row["teacher"].profile.position == "moniteur"
        row["replacement_count"] = sum(1 for item in row["recent_sessions"] if item["event"].original_teacher_id)
        if row["is_monitor"]:
            row["payable_hours"] = Decimal("0")
            for subject in row["subjects"].values():
                subject["payable_hours"] = Decimal("0")
        row["subject_rows"] = sorted(row.pop("subjects").values(), key=lambda item: item["ec_title"].casefold())
        row["recent_sessions"] = sorted(
            row["recent_sessions"], key=lambda item: item["event"].start_datetime, reverse=True
        )[:8]
        row["anomaly_count"] = len(row["anomalies"])
        row["service_status"] = (
            "attention" if row["anomaly_count"] or row["pending_validation_count"]
            else "validated" if row["validated_hours"]
            else "scheduled" if row["scheduled_hours"]
            else "unassigned"
        )
        anomalies.extend({**item, "teacher": row["teacher"]} for item in row["anomalies"])
        result_rows.append(row)
    result_rows.sort(key=lambda item: (item["teacher"].get_full_name() or item["teacher"].username).casefold())
    summary = {
        key: sum((row[key] for row in result_rows), Decimal("0"))
        for key in ("assigned_hours", "scheduled_hours", "actual_hours", "validated_hours", "payable_hours")
    }
    summary["anomaly_count"] = len(anomalies)
    summary["pending_validation_count"] = sum(row["pending_validation_count"] for row in result_rows)
    return {
        "teacher_service_rows": result_rows,
        "teacher_service_summary": summary,
        "teacher_service_anomalies": sorted(
            anomalies,
            key=lambda item: getattr(item.get("event"), "start_datetime", timezone.now()),
            reverse=True,
        ),
    }


def build_director_teacher_assignment_context(*, branch, schedule_stats, teacher_q="", teacher_scope="all", academic_year=None):
    User = get_user_model()
    teachers = scoped(User).none()
    if branch:
        teachers = scoped(User).select_related("profile").filter(
            is_active=True,
            profile__position__in=TEACHING_POSITIONS,
            profile__branch=branch,
        )
    teacher_list = list(teachers.order_by("first_name", "last_name", "username")[:150])
    teacher_ids = [teacher.id for teacher in teacher_list]
    weekly_slots = scoped(WeeklyScheduleSlot).select_related("academic_class", "ec", "teacher").filter(
        teacher_id__in=teacher_ids,
        is_active=True,
    )
    if branch:
        weekly_slots = weekly_slots.filter(branch=branch)

    planned_events = scoped(AcademicScheduleEvent).select_related("academic_class", "ec", "teacher").filter(
        teacher_id__in=teacher_ids,
        is_active=True,
    )
    if branch:
        planned_events = planned_events.filter(branch=branch)

    slots_by_teacher = defaultdict(list)
    classes_by_teacher = defaultdict(dict)
    ecs_by_teacher = defaultdict(dict)
    for slot in weekly_slots:
        slots_by_teacher[slot.teacher_id].append(slot)
        classes_by_teacher[slot.teacher_id][slot.academic_class_id] = slot.academic_class.display_name
        ecs_by_teacher[slot.teacher_id][slot.ec_id] = slot.ec.title

    events_by_teacher = defaultdict(list)
    for event in planned_events.order_by("start_datetime", "id"):
        events_by_teacher[event.teacher_id].append(event)
        classes_by_teacher[event.teacher_id][event.academic_class_id] = event.academic_class.display_name
        ecs_by_teacher[event.teacher_id][event.ec_id] = event.ec.title

    assignments = scoped(DirectorTeacherAssignment).select_related("academic_class", "ec").filter(
        teacher_id__in=teacher_ids,
        is_active=True,
    )
    if branch:
        assignments = assignments.filter(branch=branch)
    if academic_year is not None:
        assignments = assignments.filter(academic_class__academic_year=academic_year)
    rooms_by_teacher = defaultdict(dict)
    planned_hours_by_teacher = defaultdict(Decimal)
    assignments_by_teacher = defaultdict(list)
    for assignment in assignments:
        assignments_by_teacher[assignment.teacher_id].append(assignment)
        if assignment.academic_class_id:
            classes_by_teacher[assignment.teacher_id][assignment.academic_class_id] = assignment.academic_class.display_name
        if assignment.ec_id:
            ecs_by_teacher[assignment.teacher_id][assignment.ec_id] = assignment.ec.title
        if assignment.room_label:
            rooms_by_teacher[assignment.teacher_id][assignment.id] = assignment.room_label
        if assignment.planned_hours is not None:
            planned_hours_by_teacher[assignment.teacher_id] += assignment.planned_hours

    document_count_by_teacher = defaultdict(int)
    pending_document_count_by_teacher = defaultdict(int)
    teacher_documents = TeacherDocument.objects.filter(teacher_id__in=teacher_ids)
    if branch:
        teacher_documents = teacher_documents.filter(branch=branch)
    for document in teacher_documents.only("teacher_id", "is_verified"):
        document_count_by_teacher[document.teacher_id] += 1
        if not document.is_verified:
            pending_document_count_by_teacher[document.teacher_id] += 1

    teacher_load_map = schedule_stats.get("teacher_load") or {}
    teacher_rows = []
    for teacher in teacher_list:
        teacher_key = teacher.get_full_name() or teacher.username
        load = teacher_load_map.get(teacher_key, {"count": 0, "hours": Decimal("0")})
        slot_items = slots_by_teacher.get(teacher.id, [])
        event_items = events_by_teacher.get(teacher.id, [])
        class_labels = list(classes_by_teacher.get(teacher.id, {}).values())
        ec_labels = list(ecs_by_teacher.get(teacher.id, {}).values())
        room_labels = list(rooms_by_teacher.get(teacher.id, {}).values())
        planned_hours_target = planned_hours_by_teacher.get(teacher.id, Decimal("0"))
        has_assignment = bool(classes_by_teacher.get(teacher.id) or ecs_by_teacher.get(teacher.id))
        teacher_rows.append({
            "teacher": teacher,
            "label": teacher_key,
            "email": teacher.email or "Email non renseigne",
            "hours": load.get("hours", Decimal("0")),
            "count": load.get("count", 0),
            "status": getattr(getattr(teacher, "profile", None), "employment_status", "active"),
            "status_label": getattr(getattr(teacher, "profile", None), "get_employment_status_display", lambda: "Actif")(),
            "branch_name": getattr(getattr(teacher, "profile", None), "branch", None).name if getattr(getattr(teacher, "profile", None), "branch", None) else "",
            "employee_code": getattr(getattr(teacher, "profile", None), "employee_code", "") or "Code absent",
            "class_labels": class_labels[:6],
            "ec_labels": ec_labels[:8],
            "room_labels": room_labels[:6],
            "planned_hours_target": planned_hours_target,
            "total_planned_hours": planned_hours_target,
            "planned_hours_gap": planned_hours_target - Decimal(str(load.get("hours", Decimal("0")) or Decimal("0"))),
            "assignments": assignments_by_teacher.get(teacher.id, []),
            "assignment_count": len(assignments_by_teacher.get(teacher.id, [])),
            "document_count": document_count_by_teacher[teacher.id],
            "pending_document_count": pending_document_count_by_teacher[teacher.id],
            "slot_count": len(slot_items),
            "event_count": len(event_items),
            "first_events": event_items[:4],
            "has_load": bool(load.get("count") or slot_items or event_items or has_assignment),
        })

    teachers_total = len(teacher_rows)
    teacher_unassigned_count = sum(1 for item in teacher_rows if not item["has_load"])
    teacher_pending_documents = sum(item["pending_document_count"] for item in teacher_rows)

    normalized_query = (teacher_q or "").strip().casefold()
    if normalized_query:
        teacher_rows = [
            item
            for item in teacher_rows
            if normalized_query
            in " ".join(
                [
                    item["label"],
                    item["email"],
                    item["employee_code"],
                    getattr(item["teacher"].profile, "main_domain", "") or "",
                ]
            ).casefold()
        ]
    teacher_scope = teacher_scope if teacher_scope in {"all", "assigned", "unassigned", "documents_pending"} else "all"
    if teacher_scope == "assigned":
        teacher_rows = [item for item in teacher_rows if item["has_load"]]
    elif teacher_scope == "unassigned":
        teacher_rows = [item for item in teacher_rows if not item["has_load"]]
    elif teacher_scope == "documents_pending":
        teacher_rows = [item for item in teacher_rows if item["pending_document_count"]]

    return {
        "teacher_rows": teacher_rows,
        "teachers_total": teachers_total,
        "teacher_assigned_count": teachers_total - teacher_unassigned_count,
        "teacher_unassigned_count": teacher_unassigned_count,
        "teacher_pending_documents": teacher_pending_documents,
        "teacher_filtered_count": len(teacher_rows),
        "teacher_scope": teacher_scope,
    }
