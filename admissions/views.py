# admissions/views.py

import json
import logging

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.urls import reverse
from django.core.validators import validate_email
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.templatetags.static import static

from branches.models import Branch
from core.models import School, SchoolBranch
from formations.models import Programme
from academics.services.academic_years import get_current_academic_year_name
from .forms import CandidatureForm
from .models import CandidatureDocument, Candidature
from .tracking import capture_tracking, admission_url, tracked_redirect_url
from formations.fatec_esga import canonical_slug


logger = logging.getLogger(__name__)


def _programme_cycle_key(programme):
    return (programme.cycle.slug or "").lower() if programme.cycle_id else "programme"


def _build_formation_cards(cycle_slug="all", branch_id=None, school_code="", page=1, per_page=6):
    if not school_code or not branch_id:
        return [], Paginator([], per_page).get_page(1)

    selected_branch = (
        Branch.objects.filter(id=branch_id, is_active=True, accepts_online_registration=True)
        .first()
    )
    if not selected_branch:
        return [], Paginator([], per_page).get_page(1)

    formations_qs = (
        Programme.objects.accepting_admissions()
        .filter(school__code__iexact=school_code)
        .available_on(selected_branch)
        .select_related("school", "cycle", "diploma_awarded")
        .prefetch_related("years__fees")
        .order_by("title", "pk")
    )
    if cycle_slug == "programme":
        formations_qs = formations_qs.filter(cycle__isnull=True)
    elif cycle_slug and cycle_slug != "all":
        formations_qs = formations_qs.filter(cycle__slug__iexact=cycle_slug)

    page_obj = Paginator(formations_qs, per_page).get_page(page)
    cards = []
    for formation in page_obj:
        first_year = next(iter(formation.years.all()), None)
        first_year_cost = 0
        if first_year:
            first_year_cost = sum(fee.amount for fee in first_year.fees.all())

        cards.append(
            {
                "title": formation.title,
                "slug": formation.slug,
                "cycle": formation.cycle.name if formation.cycle_id else "",
                "diploma": formation.diploma_awarded.name if formation.diploma_awarded_id else "",
                "duration_years": formation.duration_years,
                "first_year_cost": first_year_cost,
                "short_description": formation.short_description,
                "image_url": formation.illustration.url if formation.illustration else "",
                "details_url": formation.get_absolute_url(),
            }
        )

    return cards, page_obj


def _build_school_campus_cards(school):
    """Renvoie les campus compatibles avec une ecole donnee (via SchoolBranch)."""
    if not school or not school.id or not school.is_active:
        return []
    return [
        {
            "id": branch.id,
            "name": branch.name,
            "city": branch.city,
            "image_url": branch.image.url if branch.image else "",
        }
        for branch in Branch.objects.filter(
            is_active=True,
            accepts_online_registration=True,
            school_branches__school=school,
            school_branches__is_active=True,
        )
        .distinct()
        .order_by("name")
    ]


def _default_form_data():
    return {
        "last_name": "",
        "first_name": "",
        "city": "",
        "email": "",
        "phone": "",
        "birth_date": "",
        "birth_place": "",
        "gender": "",
        "current_level": "",
        "current_cycle_name": "",
        "formation": "",
        "formation_slug": "",
        "branch_id": "",
        "branch_name": "",
        "branch_city": "",
        "campus_image": "",
        "school_code": "",
        "school_name": "",
    }


def _resolve_branch_token(token):
    token = (token or "").strip()
    if not token:
        return None
    queryset = Branch.objects.filter(is_active=True, accepts_online_registration=True)
    if token.isdigit():
        return queryset.filter(id=int(token)).first()
    return queryset.filter(slug=token).first()


def _initial_tunnel_state(request):
    form_data = _default_form_data()
    cycle_filter = request.GET.get("cycle", "all").strip().lower()
    if not cycle_filter:
        cycle_filter = "all"

    school_token = (request.GET.get("school") or request.GET.get("school_code") or "").strip()
    school = School.objects.public().filter(code__iexact=school_token).first() if school_token else None

    branch_token = (
        request.GET.get("branch")
        or request.GET.get("annexe")
        or request.GET.get("branch_id")
        or request.GET.get("annexe_id")
    )
    branch = _resolve_branch_token(branch_token)
    if branch:
        form_data.update(
            {
                "branch_id": str(branch.id),
                "branch_name": branch.name,
                "branch_city": branch.city,
                "campus_image": branch.image.url if branch.image else "",
            }
        )

    formation_slug = (
        request.GET.get("formation") or request.GET.get("formation_slug") or ""
    ).strip()
    from formations.fatec_esga import canonical_slug
    formation_slug = canonical_slug(formation_slug)
    programme = (
        Programme.objects.accepting_admissions().filter(slug=formation_slug)
        .select_related("school", "cycle")
        .first()
        if formation_slug
        else None
    )
    if formation_slug and not programme:
        from django.http import Http404
        raise Http404("La formation demandée est inconnue ou fermée aux candidatures. Choisissez une formation depuis le catalogue.")
    if programme:
        programme_cycle = _programme_cycle_key(programme)
        form_data.update(
            {
                "formation": programme.title,
                "formation_slug": programme.slug,
                "current_level": programme_cycle,
                "current_cycle_name": programme.cycle.name if programme.cycle_id else "",
            }
        )
        if programme_cycle:
            cycle_filter = programme_cycle
        if programme.school_id:
            school = programme.school

    if school:
        form_data.update({"school_code": school.code, "school_name": school.display_name})

    if branch and school and not SchoolBranch.objects.filter(
        school=school, branch=branch, is_active=True
    ).exists():
        branch = None
        form_data.update({"branch_id": "", "branch_name": "", "branch_city": "", "campus_image": ""})

    requested_step = request.GET.get("step", "").strip()
    initial_step = int(requested_step) if requested_step in {"1", "2", "3"} else 1
    # A direct programme link preserves its destination without skipping identity.

    if school and branch and programme:
        step3_phase = "program"
    elif school and branch:
        step3_phase = "cycle"
    elif school:
        step3_phase = "campus"
    else:
        step3_phase = "school"

    has_direct_state = bool(request.GET.keys())
    return form_data, cycle_filter, initial_step, step3_phase, not has_direct_state


def _tunnel_context(
    *,
    form_data,
    cycle_filter,
    branches,
    schools,
    academic_year_name,
    initial_step,
    initial_step3_phase,
    backend_error="",
    backend_errors=None,
    backend_error_step=1,
    backend_error_field="",
    restore_draft=False,
):
    return {
        "formation_cards": [],
        "selected_cycle": cycle_filter,
        "branches": branches,
        "schools": schools,
        "academic_year_name": academic_year_name,
        "initial_form_json": json.dumps(form_data),
        "initial_step": initial_step,
        "initial_step3_phase": initial_step3_phase,
        "backend_error": backend_error,
        "backend_errors_json": json.dumps(backend_errors or {}),
        "backend_error_step": backend_error_step,
        "backend_error_field": backend_error_field,
        "restore_draft": restore_draft,
    }


def _first_tunnel_error(errors):
    field_steps = {
        "last_name": 1,
        "first_name": 1,
        "city": 1,
        "email": 2,
        "phone": 2,
        "birth_date": 2,
        "gender": 2,
        "school_code": 3,
        "current_level": 3,
        "branch_id": 3,
        "formation_slug": 3,
        "documents": 4,
    }
    for field_name, step_no in field_steps.items():
        if field_name in errors:
            return field_name, step_no, errors[field_name]
    return "", 1, ""


def admission_tunnel(request):
    campaign_tracking = capture_tracking(request)
    wants_json = request.headers.get("Accept", "").startswith("application/json")
    branches = Branch.objects.filter(is_active=True, accepts_online_registration=True).order_by("name")
    schools = list(
        School.objects.public()
        .prefetch_related(
            Prefetch(
                "school_branches",
                queryset=SchoolBranch.objects.filter(
                    is_active=True,
                    branch__is_active=True,
                    branch__accepts_online_registration=True,
                ).select_related("branch").order_by("branch__name"),
                to_attr="admission_school_branches",
            )
        )
        .order_by("order", "code")
    )
    academic_year_name = get_current_academic_year_name()
    form_data, cycle_filter, initial_step, initial_step3_phase, restore_draft = _initial_tunnel_state(request)
    backend_error = ""
    backend_errors = {}
    backend_error_step = 1
    backend_error_field = ""

    if request.method == "POST":
        form_data = {
            "last_name": request.POST.get("last_name", "").strip(),
            "first_name": request.POST.get("first_name", "").strip(),
            "city": request.POST.get("city", "").strip(),
            "email": request.POST.get("email", "").strip(),
            "phone": request.POST.get("phone", "").strip(),
            "birth_date": request.POST.get("birth_date", "").strip(),
            "birth_place": request.POST.get("birth_place", "").strip(),
            "gender": request.POST.get("gender", "").strip(),
            "current_level": request.POST.get("current_level", "").strip(),
            "current_cycle_name": request.POST.get("current_cycle_name", "").strip(),
            "formation": request.POST.get("formation", "").strip(),
            "formation_slug": canonical_slug(request.POST.get("formation_slug", "").strip()),
            "branch_id": request.POST.get("branch_id", "").strip(),
            "branch_name": request.POST.get("branch_name", "").strip(),
            "branch_city": request.POST.get("branch_city", "").strip(),
            "campus_image": request.POST.get("campus_image", "").strip(),
            "school_code": request.POST.get("school_code", "").strip(),
            "school_name": request.POST.get("school_name", "").strip(),
        }
        restore_draft = False
        initial_step = 4
        if form_data.get("school_code") and form_data.get("branch_id") and form_data.get("current_level") and form_data.get("formation_slug"):
            initial_step3_phase = "program"
        elif form_data.get("school_code") and form_data.get("branch_id") and form_data.get("current_level"):
            initial_step3_phase = "program"
        elif form_data.get("school_code") and form_data.get("branch_id"):
            initial_step3_phase = "cycle"
        elif form_data.get("school_code"):
            initial_step3_phase = "campus"
        else:
            initial_step3_phase = "school"

        required_fields = [
            ("last_name", "Le champ nom est obligatoire.", 1),
            ("first_name", "Le champ prenom est obligatoire.", 1),
            ("city", "Veuillez renseigner votre ville d'origine.", 1),
            ("email", "Le champ email est obligatoire.", 2),
            ("phone", "Veuillez renseigner votre numero de telephone.", 2),
            ("birth_date", "Veuillez renseigner votre date de naissance.", 2),
            ("gender", "Veuillez selectionner votre genre.", 2),
            ("school_code", "Veuillez selectionner une ecole.", 3),
            ("branch_id", "Veuillez selectionner un campus.", 3),
            ("current_level", "Veuillez selectionner un cycle.", 3),
            ("formation_slug", "Veuillez selectionner une formation.", 3),
        ]

        for field_name, field_message, _step_no in required_fields:
            if not form_data.get(field_name):
                backend_errors[field_name] = field_message
        if form_data["email"]:
            try:
                validate_email(form_data["email"])
            except ValidationError:
                backend_errors["email"] = "Saisissez une adresse email valide."

        try:
            birth_date = parse_date(form_data["birth_date"]) if form_data["birth_date"] else None
        except ValueError:
            birth_date = None
        if form_data["birth_date"] and not birth_date:
            backend_errors["birth_date"] = "Saisissez une date de naissance valide."
        elif birth_date and birth_date > timezone.localdate():
            backend_errors["birth_date"] = "La date de naissance ne peut pas etre dans le futur."

        if form_data["gender"] and form_data["gender"] not in {"male", "female"}:
            backend_errors["gender"] = "Veuillez selectionner un genre valide."
        field_max_lengths = {
            "last_name": 150,
            "first_name": 150,
            "city": 100,
            "email": 254,
            "phone": 30,
            "birth_place": 150,
        }
        for field_name, max_length in field_max_lengths.items():
            if len(form_data[field_name]) > max_length:
                backend_errors[field_name] = "Cette valeur est trop longue."
        if len(form_data["phone"]) > 30:
            backend_errors["phone"] = "Le numero de telephone est trop long."

        programme = None
        if form_data["formation_slug"]:
            programme = (
                Programme.objects.accepting_admissions().filter(slug=form_data["formation_slug"])
                .select_related("cycle")
                .first()
            )
            if not programme:
                backend_errors["formation_slug"] = "La formation selectionnee n'est plus disponible."
            else:
                form_data["formation"] = programme.title
                form_data["current_cycle_name"] = programme.cycle.name if programme.cycle_id else ""
                if form_data["current_level"].lower() != _programme_cycle_key(programme):
                    backend_errors["current_level"] = "La formation choisie ne correspond pas au niveau selectionne."

        school = None
        if form_data["school_code"]:
            school = School.objects.public().filter(code__iexact=form_data["school_code"]).first()
            if not school:
                backend_errors["school_code"] = "L'ecole selectionnee n'est plus disponible."
            else:
                form_data["school_code"] = school.code
                form_data["school_name"] = school.display_name
        if programme and school and programme.school_id != school.id:
            backend_errors["formation_slug"] = "Cette formation n'appartient pas a l'ecole selectionnee."

        branch = None
        if form_data["branch_id"]:
            if form_data["branch_id"].isdigit():
                branch = Branch.objects.filter(
                    id=int(form_data["branch_id"]),
                    is_active=True,
                    accepts_online_registration=True,
                ).first()
            if not branch:
                backend_errors["branch_id"] = "Le campus selectionne n'est plus disponible."
            else:
                form_data["branch_name"] = branch.name
                form_data["branch_city"] = branch.city
                form_data["campus_image"] = branch.image.url if branch.image else ""

        if school and branch and not SchoolBranch.objects.filter(
            school=school, branch=branch, is_active=True
        ).exists():
            backend_errors["branch_id"] = "Ce campus n'accueille pas l'ecole selectionnee."

        if programme and branch and not Programme.objects.available_on(branch).filter(pk=programme.pk).exists():
            backend_errors["formation_slug"] = "Cette formation n'est pas disponible sur le campus choisi."

        if not backend_errors:
            if not academic_year_name:
                backend_errors["formation_slug"] = "Aucune annee academique active n'est configuree."

        if not backend_errors:
            email_in_use = Candidature.objects.filter(
                email__iexact=form_data["email"],
                programme=programme,
                academic_year=academic_year_name,
            ).exists()
            if email_in_use:
                backend_errors["email"] = "Cette adresse email est deja utilisee pour cette formation cette annee."

        missing_documents = []
        if request.FILES:
            backend_errors["documents"] = "Les fichiers ne sont pas acceptés dans ce formulaire. Envoyez votre candidature sans pièce jointe."
        if not backend_errors:
            missing_documents = list(
                programme.required_documents.filter(document__is_mandatory=True)
                .values_list("document__name", flat=True)
            )

        if not backend_errors:
            entry_year = 4 if _programme_cycle_key(programme) == "master" else 1
            try:
                with transaction.atomic():
                    candidature = Candidature.objects.create(
                        programme=programme,
                        branch=branch,
                        academic_year=academic_year_name,
                        entry_year=entry_year,
                        first_name=form_data["first_name"],
                        last_name=form_data["last_name"],
                        birth_date=form_data["birth_date"],
                        birth_place=form_data["birth_place"] or form_data["city"],
                        gender=form_data["gender"],
                        phone=form_data["phone"],
                        email=form_data["email"],
                        city=form_data["city"],
                        country="Mali",
                        status="to_complete" if missing_documents else "submitted",
                        completion_message=(
                            "Pièces à fournir ultérieurement : " + ", ".join(missing_documents)
                        ) if missing_documents else "",
                        campaign_tracking=campaign_tracking,
                    )

                request.session["pixel_lead_candidature"] = candidature.pk
                messages.success(request, "Votre candidature a été enregistrée avec succès.")
                if wants_json:
                    return JsonResponse({"ok": True, "redirect": tracked_redirect_url(request, reverse("admissions:done", args=[candidature.pk]))})
                return redirect(tracked_redirect_url(request, reverse("admissions:done", args=[candidature.pk])))
            except IntegrityError:
                backend_errors["email"] = "Cette adresse email est deja utilisee pour cette formation cette annee."
            except Exception:
                logger.exception("Echec de creation d'une candidature depuis le tunnel")
                backend_errors["formation_slug"] = "Une erreur technique est survenue. Reessayez dans un instant."

        if backend_errors:
            backend_error_field, backend_error_step, error_message = _first_tunnel_error(backend_errors)
            backend_error = f"Etape {backend_error_step} : {error_message}"
            initial_step = backend_error_step
            if backend_error_step == 3:
                if backend_error_field == "branch_id":
                    initial_step3_phase = "campus"
                elif backend_error_field == "school_code":
                    initial_step3_phase = "school"
                elif backend_error_field == "current_level":
                    initial_step3_phase = "cycle"
                elif backend_error_field == "documents":
                    initial_step3_phase = "program"
                else:
                    initial_step3_phase = "program"

    if request.method == "POST" and backend_errors and wants_json:
        return JsonResponse({"ok": False, "errors": backend_errors}, status=422)

    return render(
        request,
        "admissions/tunnel.html",
        _tunnel_context(
            form_data=form_data,
            cycle_filter=cycle_filter,
            branches=branches,
            schools=schools,
            academic_year_name=academic_year_name,
            initial_step=initial_step,
            initial_step3_phase=initial_step3_phase,
            backend_error=backend_error,
            backend_errors=backend_errors,
            backend_error_step=backend_error_step,
            backend_error_field=backend_error_field,
            restore_draft=restore_draft,
        ),
    )


def admission_step3_formations(request):
    cycle_slug = request.GET.get("cycle", "").strip().lower()
    if not cycle_slug:
        cycle_slug = request.GET.get("current_level", "all").strip().lower()
    if not cycle_slug:
        cycle_slug = "all"

    branch_id_raw = request.GET.get("branch_id", "").strip() or request.GET.get("annexe_id", "").strip()
    branch_id = int(branch_id_raw) if branch_id_raw.isdigit() else None
    school_code = request.GET.get("school_code", "").strip()

    per_page = 4 if request.GET.get("page_size") == "4" else 6
    formation_cards, page_obj = _build_formation_cards(
        cycle_slug, branch_id=branch_id, school_code=school_code,
        page=request.GET.get("page", "1"), per_page=per_page,
    )
    return render(
        request,
        "admissions/partials/formation_options.html",
        {
            "formation_cards": formation_cards,
            "selected_cycle": cycle_slug,
            "selected_school_code": school_code,
            "programme_page": page_obj,
        },
    )


def admission_step3_documents(request):
    formation_slug = request.GET.get("formation_slug", "").strip()
    selected_programme = None
    required_documents = []

    if formation_slug:
        selected_programme = Programme.objects.accepting_admissions().filter(slug=formation_slug).first()
        if selected_programme:
            required_documents = selected_programme.required_documents.select_related("document")

    return render(
        request,
        "admissions/partials/step3_documents.html",
        {
            "selected_programme": selected_programme,
            "required_documents": required_documents,
        },
    )


def admission_step3_campuses(request):
    school_code = request.GET.get("school_code", "").strip()
    school = None
    campuses = []

    if school_code:
        school = School.objects.public().filter(code__iexact=school_code).first()

    if school:
        campuses = _build_school_campus_cards(school)

    return render(
        request,
        "admissions/partials/campus_options.html",
        {
            "school": school,
            "campuses": campuses,
        },
    )


def admission_step3_cycles(request):
    school_code = request.GET.get("school_code", "").strip()
    branch_id_raw = request.GET.get("branch_id", "").strip() or request.GET.get("annexe_id", "").strip()
    branch_id = int(branch_id_raw) if branch_id_raw.isdigit() else None

    cycles = []
    if school_code and branch_id:
        branch = Branch.objects.filter(
            id=branch_id, is_active=True, accepts_online_registration=True
        ).first()
        if branch:
            cycles = [
                {
                    "slug": item["cycle__slug"] or "programme",
                    "name": item["cycle__name"] or "Formations ouvertes à la candidature",
                    "min_duration_years": item["cycle__min_duration_years"],
                }
                for item in Programme.objects.accepting_admissions()
                .filter(school__code__iexact=school_code)
                .available_on(branch)
                .order_by("cycle__min_duration_years", "cycle__name")
                .distinct()
                .values("cycle__slug", "cycle__name", "cycle__min_duration_years")
            ]

    return render(
        request,
        "admissions/partials/cycle_options.html",
        {
            "cycles": cycles,
            "school_code": school_code,
            "branch_id": branch_id,
        },
    )


def admission_done(request, candidature_id):
    candidature = get_object_or_404(Candidature.objects.select_related("programme", "programme__school", "branch"), id=candidature_id)
    pixel_lead = request.session.get("pixel_lead_candidature") == candidature.pk
    if pixel_lead:
        del request.session["pixel_lead_candidature"]
    return render(request, "admissions/done.html", {"candidature": candidature, "pixel_lead": pixel_lead})


def apply_to_programme(request, slug):
    """
    Vue publique de candidature :
    - formation préchargée
    - formulaire candidat avec choix d'annexe
    - dépôt des documents requis
    - prévention des doublons d'email
    """

    from formations.fatec_esga import canonical_slug
    slug = canonical_slug(slug)
    programme = get_object_or_404(
        Programme.objects.accepting_admissions(),
        slug=slug,
    )

    # Conserver l'ancienne URL pour les favoris existants tout en utilisant
    # exclusivement le tunnel UFHOB et ses validations Ecole/Campus.
    return redirect(admission_url(request, programme))

    if request.method == "GET":
        return redirect(f"/admissions/?formation={programme.slug}")

    # Documents requis pour ce programme
    required_documents = programme.required_documents.select_related("document")

    if request.method == "POST":

        form = CandidatureForm(request.POST, programme=programme)

        if form.is_valid():

            # On prépare la candidature sans sauvegarder
            candidature = form.save(commit=False)
            candidature.programme = programme

            # année académique actuelle
            current_academic_year_name = get_current_academic_year_name()
            if not current_academic_year_name:
                form.add_error(None, "Aucune annee academique active n'est configuree.")
                messages.error(
                    request,
                    "Impossible d'enregistrer la candidature sans annee academique active configuree."
                )
                context = {
                    "programme": programme,
                    "form": form,
                    "required_documents": required_documents,
                    "lab_image": static("images/lab_students.png"),
                }
                return render(
                    request,
                    "admissions/apply.html",
                    context
                )
            candidature.academic_year = current_academic_year_name

            # ==============================
            # VERIFICATION EMAIL EXISTANT
            # ==============================

            email = candidature.email

            existing = Candidature.objects.filter(
                email=email,
                programme=programme,
                academic_year=candidature.academic_year
            ).exists()

            if existing:

                form.add_error(
                    "email",
                    "Une candidature existe déjà avec cette adresse email pour ce programme cette année."
                )

                messages.warning(
                    request,
                    "Une candidature avec cette adresse email existe déjà."
                )

            else:

                # ==============================
                # ENREGISTREMENT CANDIDATURE
                # ==============================

                candidature.save()

                # ==============================
                # TRAITEMENT DES DOCUMENTS
                # ==============================

                for prd in required_documents:

                    uploaded_file = request.FILES.get(
                        f"document_{prd.document.id}"
                    )

                    if uploaded_file:

                        CandidatureDocument.objects.create(
                            candidature=candidature,
                            document_type=prd.document,
                            file=uploaded_file
                        )

                messages.success(
                    request,
                    f"Votre candidature à l'annexe {candidature.branch.name} a été envoyée avec succès."
                )

                return redirect(
                    "admissions:confirmation",
                    candidature_id=candidature.id
                )

        else:

            messages.error(
                request,
                "Veuillez corriger les erreurs du formulaire."
            )

    else:
        form = CandidatureForm(programme=programme)

    context = {
        "programme": programme,
        "form": form,
        "required_documents": required_documents,
        "lab_image": static("images/lab_students.png"),
    }

    return render(
        request,
        "admissions/apply.html",
        context
    )


def candidature_confirmation(request, candidature_id):

    candidature = get_object_or_404(
        Candidature.objects.select_related("programme", "branch"),
        id=candidature_id
    )

    return render(request, "admissions/done.html", {"candidature": candidature})
