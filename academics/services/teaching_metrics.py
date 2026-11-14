"""Canonical, non-financial metrics for an official teaching session.

The schedule event remains the source of truth.  This module only consolidates
evidence already attached to it; it never manufactures teaching time from a
planned slot or from a BBB room lifecycle.
"""

from __future__ import annotations

from datetime import timedelta


def _minutes_between(start, end) -> int:
    if not start or not end or end <= start:
        return 0
    return int((end - start).total_seconds() // 60)


def consolidated_interval_minutes(intervals) -> int:
    """Union overlapping/repeated intervals, including BBB reconnections."""
    normalized = sorted(
        ((start, end) for start, end in intervals if start and end and end > start),
        key=lambda item: item[0],
    )
    if not normalized:
        return 0
    total = 0
    current_start, current_end = normalized[0]
    for start, end in normalized[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
            continue
        total += _minutes_between(current_start, current_end)
        current_start, current_end = start, end
    return total + _minutes_between(current_start, current_end)


def teaching_time_metrics(*, event, lesson_log=None, execution_logs=()) -> dict:
    """Separate planned, evidenced actual and capped validatable minutes.

    A completed execution trace is evidence of execution.  A submitted or
    approved lesson log is the authoritative duration declaration for the
    session.  If no duration-bearing evidence exists, ``actual_minutes`` stays
    ``None``: absence of a trace must not silently become payable time.
    """
    planned_minutes = max(0, int(event.duration_minutes or 0))
    execution_minutes = consolidated_interval_minutes(
        (item.started_at, item.ended_at)
        for item in execution_logs
        if getattr(item, "is_completed", False)
    )
    log_minutes = 0
    if lesson_log is not None:
        start = getattr(lesson_log, "start_time", None)
        end = getattr(lesson_log, "end_time", None)
        if start and end and end > start:
            log_minutes = int(
                (timedelta(hours=end.hour, minutes=end.minute, seconds=end.second)
                 - timedelta(hours=start.hour, minutes=start.minute, seconds=start.second)).total_seconds()
                // 60
            )
    actual_minutes = log_minutes or execution_minutes or None
    validatable_minutes = min(actual_minutes, planned_minutes) if actual_minutes is not None else 0
    return {
        "planned_minutes": planned_minutes,
        "actual_minutes": actual_minutes,
        "validatable_minutes": validatable_minutes,
        "missing_minutes": max(0, planned_minutes - validatable_minutes),
        "overrun_minutes": max(0, (actual_minutes or 0) - planned_minutes),
    }
