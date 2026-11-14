from io import BytesIO
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.template.loader import render_to_string

# Shared institutional identity. School is an academic context, not a brand.
OFFICIAL_UNIVERSITY_NAME = "Université Félix Houphouët-Boigny - Mali"
OFFICIAL_SLOGAN = "Demain, c'est aujourd'hui"


TEMPLATE_MAP = {
    "esfe_document_base": "documents/base_document/base_document.html",
    "esfe_receipt": "documents/payment_receipt/payment_receipt.html",
    "esfe_shop_invoice": "documents/shop_invoice/shop_invoice.html",
    "esfe_salary_slip": "documents/salary_slip/salary_slip.html",
    "esfe_teacher_service_sheet": "documents/teacher_service_sheet/teacher_service_sheet.html",
    "esfe_refund": "documents/refund_document/refund_document.html",
    "esfe_cash_receipt": "documents/cash_receipt/cash_receipt.html",
    "esfe_bank_transfer_slip": "documents/bank_transfer_slip/bank_transfer_slip.html",
    "esfe_donation_receipt": "documents/donation_receipt/donation_receipt.html",
    "esfe_inscription_certificate": "documents/inscription_certificate/inscription_certificate.html",
}


def _related(obj, *path):
    """Read an optional relationship without forcing unrelated model shapes."""
    for attribute in path:
        if obj is None:
            return None
        obj = getattr(obj, attribute, None)
    return obj


def _image_uri(image):
    if not image:
        return ""
    name = getattr(image, "name", "")
    storage = getattr(image, "storage", None)
    if name and storage is not None:
        try:
            if not storage.exists(name):
                return ""
        except (OSError, NotImplementedError):
            pass
    try:
        path = Path(image.path)
        if path.is_file():
            return path.resolve().as_uri()
    except (AttributeError, NotImplementedError, OSError, ValueError):
        pass
    try:
        return image.url
    except (AttributeError, ValueError):
        return ""


def get_document_branding_context(source=None, *, institution=None, school=None,
                                  branch=None, programme=None, academic_year=None, request=None):
    """Resolve official document identity from the business record being printed.

    In particular, enrollment and class links take precedence over a student's
    current profile so historical documents keep their original context.
    """
    institution = institution or _related(school, "institution")
    programme = programme or _related(source, "programme") or _related(source, "academic_class", "programme")
    enrollment = _related(source, "enrollment") or source
    academic_class = _related(enrollment, "academic_class") or _related(source, "academic_class")
    if programme is None:
        programme = _related(academic_class, "programme") or _related(source, "inscription", "candidature", "programme")
    school = school or _related(programme, "school")
    branch = (branch or _related(enrollment, "branch") or _related(academic_class, "branch")
              or _related(source, "branch") or _related(source, "inscription", "candidature", "branch"))
    academic_year = (academic_year or _related(enrollment, "academic_year")
                     or _related(academic_class, "academic_year") or _related(source, "academic_year")
                     or _related(source, "inscription", "candidature", "academic_year"))
    if institution is None:
        institution = _related(source, "institution") or _related(programme, "school", "institution")
    if institution is None:
        from core.models import Institution
        institution = Institution.objects.filter(is_active=True).first()

    school_logo = _image_uri(_related(school, "logo"))
    university_logo = _image_uri(None)
    if not university_logo:
        university_logo = _resolve_logo_url()
    # Keep a local ``file:`` URI when it is available.  WeasyPrint resolves it
    # while writing the PDF, embedding the image in the resulting document.
    # Replacing it with a request URL made calendar PDFs depend on localhost
    # (or a live web server) during generation.
    return {
        "institution": institution,
        "institution_official_name": OFFICIAL_UNIVERSITY_NAME,
        "institution_slogan": OFFICIAL_SLOGAN,
        "institution_address": getattr(institution, "address", "") or "",
        "institution_city": getattr(institution, "city", "") or "",
        "institution_phone": getattr(institution, "phone", "") or "",
        "institution_email": getattr(institution, "email", "") or "",
        "university_logo": university_logo,
        "school": school,
        "school_name": (getattr(school, "official_name", "") or getattr(school, "short_name", "")
                        or getattr(school, "code", "")),
        "school_short_name": getattr(school, "short_name", "") or getattr(school, "code", ""),
        "school_logo": school_logo,
        "document_logo": school_logo or university_logo,
        "branch": branch,
        "branch_name": getattr(branch, "name", "") or "",
        "programme": programme,
        "programme_name": getattr(programme, "title", "") or "",
        "cycle": _related(programme, "cycle"),
        "cycle_name": getattr(_related(programme, "cycle"), "name", "") or "",
        "academic_year": academic_year,
        "academic_year_name": getattr(academic_year, "name", "") or (str(academic_year) if academic_year else ""),
        "academic_class": academic_class,
        "class_name": getattr(academic_class, "display_name", "") or "",
    }


def _resolve_logo_url():
    logo_path = finders.find("images/students/logo-ubhob.png")
    if logo_path:
        return Path(logo_path).resolve().as_uri()
    return ""


def _get_template_name(component_name):
    name = TEMPLATE_MAP.get(component_name)
    if not name:
        raise ValueError(f"Unknown document component: {component_name}")
    return name


def _render_html(component_name, context, request=None):
    source = (context.get("document_context") or context.get("enrollment") or context.get("payment")
              or context.get("inscription") or context.get("academic_class"))
    institution_context = get_document_branding_context(
        source,
        institution=context.get("institution"),
        school=context.get("school_object"),
        branch=context.get("branch"),
        programme=context.get("programme_object"),
        academic_year=context.get("academic_year_object"),
        request=request,
    )
    student_matricule = str(context.get("student_matricule") or "")
    # Legacy matricules remain valid backend identifiers, but are not public
    # institutional references on UFHOB documents.
    institution_context["document_student_matricule"] = (
        "" if student_matricule.upper().startswith("ESFE-") else student_matricule
    )
    context = {**institution_context, **context}
    if "logo_url" not in context:
        context = {**context, "logo_url": institution_context["document_logo"] or _resolve_logo_url()}
    return render_to_string(
        _get_template_name(component_name), context, request=request
    )


def generate_pdf(component_name, context, request=None):
    html_string = _render_html(component_name, context, request=request)
    try:
        from weasyprint import HTML

        if request:
            base_url = request.build_absolute_uri()
        else:
            base_url = _resolve_logo_url().rsplit("/", 1)[0] if _resolve_logo_url() else None

        return HTML(string=html_string, base_url=base_url).write_pdf()
    except ImportError:
        raise RuntimeError("weasyprint not installed") from None


def generate_pdf_response(component_name, context, filename="document.pdf", request=None):
    from django.http import HttpResponse

    pdf_bytes = generate_pdf(component_name, context, request=request)
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Content-Length"] = len(pdf_bytes)
    return response
