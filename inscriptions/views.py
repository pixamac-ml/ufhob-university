# inscriptions/views.py

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.http import Http404
from django.views.decorators.http import require_POST

from core.models import ContactMessage
from inscriptions.models import Inscription
from payments.forms import StudentPaymentForm


def _can_initiate_payment(inscription, has_pending_payment):
    payable_statuses = {
        Inscription.STATUS_CREATED,
        Inscription.STATUS_AWAITING_PAYMENT,
        Inscription.STATUS_PARTIAL,
    }
    return (
        inscription.status in payable_statuses
        and inscription.balance > 0
        and not has_pending_payment
    )


def inscription_public_detail(request, token):
    """
    Vue publique sécurisée du dossier d'inscription.
    - Accès protégé par access_code via session
    - Retourne soit la page complète, soit un fragment HTMX pour instantanéité
    """

    inscription = get_object_or_404(
        Inscription.objects.select_related(
            "candidature__programme__school__institution",
            "candidature__branch",
            "academic_class",
            "student__user__profile",
        ),
        public_token=token,
    )

    # Vérification du code d'accès via session
    session_key = f"inscription_access_{inscription.id}"

    # Si accès non validé
    if not request.session.get(session_key):
        if request.method == "POST":
            entered_code = request.POST.get("access_code", "").strip()

            if entered_code == inscription.access_code:
                request.session[session_key] = True
            else:
                # Réponse HTMX si requête HTMX
                if request.headers.get("HX-Request"):
                    response = render(
                        request,
                        "payments/partials/access_form_error.html",
                        {"error": "Code d'accès incorrect."}
                    )
                    response["HX-Trigger"] = '{"toast": {"type": "error", "message": "Code d\'accès incorrect."}}'
                    return response
                return render(request, "inscriptions/access_required.html", {"error": "Code d'accès incorrect."})
        else:
            return render(request, "inscriptions/access_required.html")

    # Bloquer si suspendue
    if inscription.status == "suspended":
        raise Http404("Ce dossier est temporairement indisponible.")

    # Historique des paiements
    payments = inscription.payments.select_related("agent__user").order_by("-paid_at")
    has_pending_payment = payments.filter(status="pending").exists()
    can_pay = _can_initiate_payment(inscription, has_pending_payment)
    payment_form = StudentPaymentForm(inscription=inscription) if can_pay else None

    student = getattr(inscription, "student", None)
    student_photo = ""
    if student and getattr(student, "photo", None):
        student_photo = student.photo.url
    elif student and getattr(getattr(student.user, "profile", None), "avatar_url", ""):
        student_photo = student.user.profile.avatar_url

    context = {
        "inscription": inscription,
        "candidature": inscription.candidature,
        "programme": inscription.candidature.programme,
        "payments": payments,
        "payment_form": payment_form,
        "receipt_payment": payments.filter(status="validated", receipt_number__isnull=False).first(),
        "payment_receipts": payments.filter(status="validated", receipt_number__isnull=False),
        "status_history": inscription.history.order_by("created_at"),
        "student": student,
        "student_photo": student_photo,
        "institution": getattr(getattr(inscription.candidature.programme, "school", None), "institution", None),
        "admin_email": getattr(getattr(inscription.candidature.programme, "school", None).institution, "email", "") if getattr(inscription.candidature.programme, "school", None) else "",
        "can_pay": can_pay,
        "has_pending_payment": has_pending_payment,
    }

    # Réponse HTMX
    if request.headers.get("HX-Request"):
        return render(request, "payments/partials/inscription_finance.html", context)

    # Réponse classique
    return render(request, "inscriptions/public_detail.html", context)


@require_POST
def inscription_contact_administration(request, token):
    """Attach a compact support request to the secured annual dossier."""
    inscription = get_object_or_404(Inscription, public_token=token)
    if not request.session.get(f"inscription_access_{inscription.id}"):
        raise Http404("Dossier introuvable.")

    category = (request.POST.get("category") or "other").strip()
    subject_map = {
        "payment": "payment", "receipt": "payment", "inscription": "inscription",
        "access": "other", "documents": "other", "information": "other", "other": "other",
    }
    title = (request.POST.get("title") or "").strip()
    description = (request.POST.get("description") or "").strip()
    if category not in subject_map or not title or not description:
        messages.error(request, "Veuillez renseigner la catégorie, l’objet et votre message.")
        return redirect(inscription.get_public_url())

    candidature = inscription.candidature
    context_line = (
        f"Dossier {inscription.public_reference} | École {candidature.programme.school.code} | "
        f"Campus {candidature.branch.name} | Année {candidature.academic_year}\nObjet : {title}\n\n"
    )
    contact = ContactMessage.objects.create(
        full_name=candidature.full_name,
        email=candidature.email,
        phone=candidature.phone,
        subject=subject_map[category],
        message=context_line + description,
    )
    contact.auto_assign()
    contact.save(update_fields=["assigned_to"])
    messages.success(request, "Votre demande a été transmise à l’administration.")
    return redirect(inscription.get_public_url())

