"""Official-document projection for the canonical academic calendar.

This module owns no calendar data.  It adapts the effective calendar schedule
for PDF rendering so every document uses exactly the same period dates and
scope rules as the interactive views.
"""

from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils.text import slugify
from django.utils import timezone

from academics.models import AcademicCalendar
from academics.services.calendar_service import (
    get_calendar_document_reference,
    get_effective_calendar_projection,
)
from core.pdf_documents import get_document_branding_context


def build_calendar_document_context(
    calendar,
    *,
    request=None,
    school=None,
    programme=None,
    academic_class=None,
    semester_ids=(),
    public_only=False,
):
    """Build one document context from the published/effective calendar only."""
    projection = get_effective_calendar_projection(
        calendar,
        school=school,
        programme=programme,
        academic_class=academic_class,
        semester_ids=semester_ids,
        public_only=public_only,
        # A director's draft preview explains a cancellation; an official
        # document omits it, exactly like the published student projection.
        include_cancelled=not public_only,
    )
    return {
        "calendar": calendar,
        "branding": get_document_branding_context(
            branch=calendar.branch,
            academic_year=calendar.academic_year,
            school=school,
            programme=programme,
            request=request,
        ),
        "projection": projection,
        "generated_on": timezone.localdate(),
        "is_draft": calendar.status != AcademicCalendar.STATUS_PUBLISHED,
        "document_reference": get_calendar_document_reference(calendar),
        "document_school": school,
        "document_programme": programme,
        "document_academic_class": academic_class,
    }


def render_calendar_pdf_response(calendar, *, request=None, **context_scope):
    """Render the official A4 PDF without introducing a second event store."""
    context = build_calendar_document_context(
        calendar, request=request, **context_scope
    )
    html = render_to_string(
        "portal/staff/director/partials/calendar/pdf.html", context, request=request
    )
    from weasyprint import HTML

    # Branding URLs are local ``file:`` URLs where possible.  WeasyPrint reads
    # and embeds them while creating the PDF, so the document is portable.
    pdf_bytes = HTML(string=html, base_url=None).write_pdf()
    filename = "calendrier-{}-v{}.pdf".format(
        slugify(calendar.academic_year.name), calendar.version
    )
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
