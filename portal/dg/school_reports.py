"""School-level DG read models; no changes to admission or finance workflows."""

from calendar import monthrange
from datetime import datetime, time, timedelta
from io import BytesIO
from urllib.parse import urlencode

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Greatest
from django.http import HttpResponse, HttpResponseBadRequest
from django.urls import reverse
from django.utils import timezone

from accounts.models import BranchCashMovement
from .selectors import get_dg_base_querysets

CASH_PENDING = "Données de caisse par école bientôt disponibles"
HEADERS = ["École", "Effectifs actifs", "Candidatures reçues / acceptées / en attente",
           "Inscriptions", "Encaissé mois / année (FCFA)", "Impayés (FCFA)", "Solde de caisse (FCFA)"]
METRICS = ("students", "received", "accepted", "pending", "inscriptions", "month", "year", "due")


def school_summary(navigation):
    """Aggregate independently to avoid multiplying payments by enrollments."""
    base = get_dg_base_querysets(navigation.scoped_branch_ids, academic_year=navigation.academic_year)
    today = timezone.localdate()
    month_start = timezone.make_aware(datetime.combine(today.replace(day=1), time.min))
    month_end = month_start + timedelta(days=monthrange(today.year, today.month)[1])

    def grouped(queryset, path, **aggregates):
        return {row[path]: row for row in queryset.order_by().values(path).annotate(**aggregates)}

    students = grouped(base["enrollments"], "programme__school_id", students=Count("student_id", distinct=True))
    applications = grouped(base["candidatures"], "programme__school_id", received=Count("pk"),
        accepted=Count("pk", filter=Q(status__in={"accepted", "accepted_with_reserve"})),
        pending=Count("pk", filter=Q(status__in={"submitted", "under_review", "to_complete"})))
    inscriptions = grouped(base["administrative_inscriptions"], "candidature__programme__school_id",
        inscriptions=Count("pk"), due=Sum(Greatest(F("amount_due") - F("amount_paid"), 0)))
    payments = grouped(base["payments"], "inscription__candidature__programme__school_id",
        year=Sum("amount"), month=Sum("amount", filter=Q(paid_at__gte=month_start, paid_at__lt=month_end)))
    # Cash is a ledger balance, never revenue minus campus expenses. Legacy
    # ledgers without a school cannot be distributed across its schools.
    cash = None
    if any(field.name == "school" for field in BranchCashMovement._meta.fields):
        movements = BranchCashMovement.objects.filter(branch_id__in=navigation.scoped_branch_ids)
        if navigation.selected_school:
            movements = movements.filter(school=navigation.selected_school)
        if navigation.academic_year:
            movements = movements.filter(movement_date__lte=navigation.academic_year.end_date)
        cash = grouped(movements, "school_id",
            incoming=Sum("amount", filter=Q(movement_type=BranchCashMovement.TYPE_IN)),
            outgoing=Sum("amount", filter=Q(movement_type=BranchCashMovement.TYPE_OUT)))

    schools = [navigation.selected_school] if navigation.selected_school else navigation.available_schools
    rows = []
    total = dict.fromkeys(METRICS, 0)
    for school in schools:
        item = {"school": school, **dict.fromkeys(METRICS, 0)}
        for source in (students, applications, inscriptions, payments):
            item.update({key: value or 0 for key, value in source.get(school.pk, {}).items() if key in METRICS})
        ledger = cash.get(school.pk, {}) if cash is not None else None
        item["cash"] = ((ledger.get("incoming") or 0) - (ledger.get("outgoing") or 0)) if ledger is not None else None
        for key in METRICS:
            total[key] += item[key]
        rows.append(item)
    total.update(school=None, cash=sum(row["cash"] for row in rows) if cash is not None else None)
    return rows, total


def summary_values(item):
    return [item["school"].display_name if item["school"] else "TOTAL", item["students"],
        f'{item["received"]} / {item["accepted"]} / {item["pending"]}', item["inscriptions"],
        f'{item["month"]} / {item["year"]}', item["due"],
        item["cash"] if item["cash"] is not None else CASH_PENDING]


def summary_context(navigation):
    rows, total = school_summary(navigation)
    table_rows = []
    for item in [*rows, total]:
        school = item["school"]
        params = urlencode({"scope_school_id": school.pk if school else "",
            "scope_branch_id": navigation.selected_branch_id,
            "academic_year_id": navigation.academic_year.pk if navigation.academic_year else ""})
        href = reverse("accounts_portal:portal_dg") + "?" + params
        table_rows.append({"id": f'dg-school-{school.pk if school else "total"}',
            "label": summary_values(item)[0], "href": href,
            "cells": [{"value": value, **({"href": href} if index == 0 else {"amount": True})}
                      for index, value in enumerate(summary_values(item))]})
    return {"school_summary": rows, "school_summary_total": total,
            "school_summary_headers": HEADERS, "school_summary_rows": table_rows}


def export_school_summary(request, navigation):
    """Excel and PDF use exactly the same read model as the cockpit."""
    rows, total = school_summary(navigation)
    values = [HEADERS, *[summary_values(item) for item in [*rows, total]]]
    output_format = request.GET.get("format", "xlsx")
    if output_format == "xlsx":
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Écoles"
        sheet.append(["UFHOB · " + navigation.scope_label,
                      navigation.academic_year.name if navigation.academic_year else "Toutes années"])
        for row in values:
            sheet.append(row)
        for cell in sheet[2]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(wrap_text=True)
        for column in "ABCDEFG":
            sheet.column_dimensions[column].width = 28 if column != "G" else 48
        sheet.freeze_panes = "B3"
        stream = BytesIO()
        workbook.save(stream)
        content, mime = stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    elif output_format == "pdf":
        from django.utils.html import escape
        from weasyprint import HTML
        # Standalone export document, not a dashboard component or screen.
        title = f"UFHOB · {navigation.scope_label} · {navigation.academic_year or 'Toutes années'}"
        body = "".join("<tr>" + "".join(f"<td>{escape(str(cell))}</td>" for cell in row) + "</tr>" for row in values)
        content = HTML(string=f'<html lang="fr"><meta charset="utf-8"><title>{escape(title)}</title>'
            f'<style>@page{{size:A4 landscape;margin:12mm}}body{{font:10pt sans-serif}}'
            f'table{{width:100%;border-collapse:collapse}}td{{border:1px solid #aaa;padding:7px}}'
            f'tr:first-child{{font-weight:bold}}tr{{break-inside:avoid}}</style><h1>{escape(title)}</h1>'
            f'<table>{body}</table></html>').write_pdf()
        mime = "application/pdf"
    else:
        return HttpResponseBadRequest("Format attendu : xlsx ou pdf.")
    response = HttpResponse(content, content_type=mime)
    response["Content-Disposition"] = f'attachment; filename="dg-ecoles.{output_format}"'
    return response


def export_school_bulletins(request, navigation):
    """Render existing published snapshots, without recalculation or publication."""
    from zipfile import ZipFile, ZIP_DEFLATED
    from academics.models import AcademicBulletin
    from academics.services.documents import render_bulletin_pdf_bytes
    from .scoping import scoped

    bulletins = scoped(AcademicBulletin).filter(status=AcademicBulletin.STATUS_PUBLISHED,
        enrollment__branch_id__in=navigation.scoped_branch_ids)
    if navigation.academic_year:
        bulletins = bulletins.filter(enrollment__academic_year=navigation.academic_year)
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for bulletin in bulletins.select_related("enrollment__programme__school", "enrollment__branch", "enrollment__academic_year").iterator():
            archive.writestr(f"bulletin-{bulletin.pk}.pdf", render_bulletin_pdf_bytes(bulletin))
    response = HttpResponse(stream.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = 'attachment; filename="dg-bulletins-publies.zip"'
    return response
