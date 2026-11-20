from .scoping import scoped
from datetime import timedelta
import re

from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.db import transaction
from django.utils import timezone

from accounts.models import Profile
from accounts.position_registry import POSITION_REGISTRY, dg_assignable_positions, get_position_definition
from branches.models import Branch
from coupons.models import Coupon
from formations.models import Cycle, Diploma, Filiere, Programme
from core.models import School, SchoolBranch
from .scoping import current_navigation


DG_RECRUITMENT_POSITION_CHOICES = [
    (code, "Directeur d’école" if code == "director_of_studies" else
     "Gestionnaire" if code == "secretary" else definition.label)
    for code, definition in dg_assignable_positions().items()
    if code not in {"finance_manager", "payment_agent", "admissions"}
]


class StaffScopeForm(forms.Form):
    school = forms.ModelChoiceField(queryset=School.objects.none(), required=False, label="École")
    access_scope = forms.ChoiceField(required=False, label="Périmètre", choices=[
        ("", "Selon l’affectation"), ("SCHOOL_BRANCH", "École et campus"),
        ("SCHOOL", "École · tous ses campus"), ("BRANCH", "Campus · toutes ses écoles"),
        ("GLOBAL", "Université"),
    ])

    def configure_scope(self, allowed_branch_ids):
        navigation = current_navigation()
        schools = School.objects.filter(is_active=True)
        branches = Branch.objects.filter(is_active=True)
        if allowed_branch_ids is not None:
            branches = branches.filter(pk__in=allowed_branch_ids)
        if navigation and navigation.selected_school:
            schools = schools.filter(pk=navigation.selected_school.pk)
            self.initial["school"] = navigation.selected_school.pk
            self.fields["school"].disabled = True
        if navigation and navigation.selected_branch:
            self.initial["branch"] = navigation.selected_branch.pk
            self.fields["branch"].disabled = True
        if navigation:
            allowed = {"", "SCHOOL_BRANCH"}
            if not navigation.selected_branch:
                allowed.add("SCHOOL")
            if not navigation.selected_school:
                allowed.add("BRANCH")
                if not navigation.selected_branch:
                    allowed.add("GLOBAL")
            self.fields["access_scope"].choices = [(value, label) for value, label in self.fields["access_scope"].choices if value in allowed]
        self.fields["school"].queryset = schools
        self.global_positions = [code for code, definition in POSITION_REGISTRY.items() if definition.scope == "GLOBAL"]
        pairs = list(SchoolBranch.objects.filter(is_active=True, school__in=schools, branch__in=branches).values_list("school_id", "branch_id"))
        self.campus_options = [{"id": b.pk, "label": b.name, "schools": [s for s, campus in pairs if campus == b.pk]} for b in branches.order_by("name")]
        school_id = self.initial.get("school") if self.fields["school"].disabled or not self.is_bound else self.data.get("school")
        if school_id:
            branches = branches.filter(school_branches__school_id=school_id, school_branches__is_active=True) if str(school_id).isdigit() else branches.none()
        self.fields["branch"].queryset = branches.order_by("name")
        self.fields["branch"].label = "Campus"

    def clean_scope(self, cleaned):
        for name in ("school", "branch"):
            if self.fields[name].disabled and name in self.data and str(self.data[name]) != str(self.initial.get(name) or ""):
                self.add_error(name, "Ce choix ne correspond pas au contexte actif.")
        school, branch = cleaned.get("school"), cleaned.get("branch")
        position = cleaned.get("position") or self.initial.get("position")
        if cleaned.get("action") == "reassign":
            position = self.initial.get("position")
        definition = get_position_definition(position)
        scope = cleaned.get("access_scope")
        if not scope:
            scope = ("SCHOOL_BRANCH" if branch else "SCHOOL") if school else (definition.scope if definition else "BRANCH")
        if scope in {"SCHOOL", "SCHOOL_BRANCH"} and not school:
            self.add_error("school", "Sélectionnez l’école de cette affectation.")
        if scope in {"BRANCH", "SCHOOL_BRANCH"} and not branch:
            self.add_error("branch", "Sélectionnez un campus autorisé.")
        if scope in {"GLOBAL", "BRANCH"} and school:
            self.add_error("access_scope", "Choisissez un périmètre incluant cette école.")
        if scope in {"GLOBAL", "SCHOOL"} and branch:
            self.add_error("branch", "Ce périmètre ne doit pas être limité à un campus.")
        if scope == "GLOBAL" and (not definition or definition.scope != "GLOBAL"):
            self.add_error("access_scope", "Cette fonction ne permet pas une affectation universitaire globale depuis ce formulaire.")
        if definition and definition.scope == "GLOBAL" and scope != "GLOBAL":
            self.add_error("access_scope", "Cette fonction institutionnelle nécessite la vue universitaire, sans restriction école ou campus.")
        if position in {"teacher", "moniteur"} and not branch:
            self.add_error("branch", "Choisissez le campus principal ; les affectations pédagogiques restent transversales.")
        if school and branch and not SchoolBranch.objects.filter(school=school, branch=branch, is_active=True).exists():
            self.add_error("branch", "Cette école n’est pas implantée sur ce campus.")
        cleaned["access_scope"] = scope
        return cleaned


class DgRecruitmentForm(StaffScopeForm):
    # Le registre institutionnel est l'unique nomenclature de rôles. Les
    # fonctions exécutives protégées et le profil étudiant ne sont pas des
    # recrutements RH ordinaires.
    POSITION_CHOICES = DG_RECRUITMENT_POSITION_CHOICES

    first_name = forms.CharField(max_length=80, label="Prénom")
    last_name = forms.CharField(max_length=80, label="Nom")
    personal_email = forms.EmailField(required=False, label="Email personnel")
    professional_email = forms.EmailField(required=False, label="Email professionnel")
    phone = forms.CharField(max_length=30, required=False, label="Téléphone")
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), required=False, label="Campus")
    position = forms.ChoiceField(choices=POSITION_CHOICES, label="Poste")
    salary_base = forms.IntegerField(min_value=0, required=False, label="Salaire de base")
    teacher_hourly_rate = forms.IntegerField(min_value=0, required=False, label="Tarif horaire enseignant")
    main_domain = forms.CharField(max_length=120, required=False, label="Spécialité / domaine principal")
    amo_applicable = forms.BooleanField(required=False, initial=False, label="Appliquer l'AMO")
    inps_applicable = forms.BooleanField(required=False, initial=False, label="Appliquer l'INPS")
    amo_rate = forms.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2, required=False, initial=0, label="Taux AMO (%)")
    inps_rate = forms.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2, required=False, initial=0, label="Taux INPS (%)")
    generate_access = forms.BooleanField(required=False, initial=False, label="Créer un compte de connexion")
    send_access_email = forms.BooleanField(required=False, initial=False, label="Envoyer le lien sécurisé par email")
    def __init__(self, *args, allowed_branch_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["salary_base"].label = "Salaire brut mensuel (FCFA)"
        self.fields["teacher_hourly_rate"].label = "Tarif horaire enseignant (FCFA)"
        self.fields["amo_rate"].help_text = "Saisir un taux en %. Le montant FCFA sera calculé automatiquement sur le salaire brut."
        self.fields["inps_rate"].help_text = "Saisir un taux en %. Le montant FCFA sera calculé automatiquement sur le salaire brut."
        for field_name in ("amo_rate", "inps_rate"):
            self.fields[field_name].widget.attrs.update({"min": "0", "max": "100", "step": "0.01", "inputmode": "decimal"})
        branches = Branch.objects.filter(is_active=True)
        if allowed_branch_ids is not None:
            branches = branches.filter(id__in=allowed_branch_ids)
        self.fields["branch"].queryset = branches.order_by("name")
        self.configure_scope(allowed_branch_ids)

    def clean(self):
        cleaned = self.clean_scope(super().clean())
        for enabled, rate, label in (
            ("amo_applicable", "amo_rate", "AMO"),
            ("inps_applicable", "inps_rate", "INPS"),
        ):
            if cleaned.get(enabled) and not cleaned.get(rate):
                self.add_error(rate, f"Renseignez le taux {label} en pourcentage.")
            elif not cleaned.get(enabled):
                cleaned[rate] = 0
        if cleaned.get("position") == "moniteur":
            if not cleaned.get("main_domain"):
                self.add_error("main_domain", "La spécialité du moniteur est obligatoire.")
            if not cleaned.get("branch"):
                self.add_error("branch", "Le campus principal du moniteur est obligatoire.")
            if not cleaned.get("salary_base"):
                self.add_error("salary_base", "Le salaire fixe du moniteur est obligatoire.")
            if cleaned.get("teacher_hourly_rate"):
                self.add_error("teacher_hourly_rate", "Le moniteur est salarié : aucun tarif horaire pédagogique.")
        generate_access = bool(cleaned.get("generate_access"))
        send_access_email = bool(cleaned.get("send_access_email"))
        has_email = bool((cleaned.get("professional_email") or cleaned.get("personal_email") or "").strip())
        if generate_access and not has_email:
            self.add_error("professional_email", "Un email est obligatoire pour remettre un accès sécurisé.")
        if generate_access and not send_access_email:
            self.add_error("send_access_email", "La remise d'accès doit passer par le lien sécurisé envoyé par email.")
        if send_access_email and not generate_access:
            self.add_error("send_access_email", "Activez d'abord la génération d'accès ou décochez l'envoi d'email.")
        email = (cleaned.get("professional_email") or cleaned.get("personal_email") or "").strip()
        if email:
            from django.contrib.auth import get_user_model

            if get_user_model().objects.filter(email__iexact=email).exists():
                self.add_error("professional_email", "Un compte utilise déjà cette adresse email.")
        return cleaned

    def profile_position(self):
        position = self.cleaned_data["position"]
        return position

    def profile_role(self):
        # Compatibilite temporaire : la position est la source d'autorite.
        from accounts.services.institutional_access import compatibility_role_for_position

        return compatibility_role_for_position(self.profile_position())


class DgStaffLifecycleForm(StaffScopeForm):
    ACTION_SUSPEND = "suspend"
    ACTION_REACTIVATE = "reactivate"
    ACTION_REVOKE = "revoke"
    ACTION_REASSIGN = "reassign"
    ACTION_UPDATE_ASSIGNMENT = "update_assignment"
    ACTION_RESEND_INVITATION = "resend_invitation"
    ACTION_DELETE = "delete"

    ACTION_CHOICES = [
        (ACTION_SUSPEND, "Suspendre l'accès"),
        (ACTION_REACTIVATE, "Réactiver l'accès"),
        (ACTION_REVOKE, "Révoquer l'accès"),
        (ACTION_REASSIGN, "Changer l'affectation"),
        (ACTION_UPDATE_ASSIGNMENT, "Modifier le rôle et l'affectation"),
        (ACTION_RESEND_INVITATION, "Renvoyer l'invitation"),
        (ACTION_DELETE, "Supprimer l'utilisateur"),
    ]

    profile_id = forms.IntegerField(min_value=1)
    action = forms.ChoiceField(choices=ACTION_CHOICES)
    reason = forms.CharField(max_length=500, required=False, label="Motif de la décision", widget=forms.Textarea)
    confirm_delete = forms.BooleanField(required=False, label="Je confirme la suppression définitive de ce compte")
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), required=False, label="Campus")
    position = forms.ChoiceField(choices=DgRecruitmentForm.POSITION_CHOICES, required=False, label="Rôle institutionnel")

    def __init__(self, *args, allowed_branch_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True)
        if allowed_branch_ids is not None:
            branches = branches.filter(id__in=allowed_branch_ids)
        self.fields["branch"].queryset = branches.order_by("name")
        profile_id = self.data.get("profile_id") if self.is_bound else self.initial.get("profile_id")
        if str(profile_id or "").isdigit():
            # The view has already checked DG authority.  Navigation is a
            # display filter and must not erase a target's saved assignment
            # while rendering a sensitive lifecycle form.
            profile = Profile.objects.select_related("user__institutional_profile").filter(
                pk=profile_id, user_type="staff"
            ).first()
            institutional = getattr(getattr(profile, "user", None), "institutional_profile", None)
            if institutional:
                self.initial.update(school=institutional.school_id, access_scope=institutional.access_scope, position=institutional.position)
        self.configure_scope(allowed_branch_ids)

    def clean(self):
        cleaned = super().clean()
        action = cleaned.get("action")
        if action in {self.ACTION_REASSIGN, self.ACTION_UPDATE_ASSIGNMENT}:
            self.clean_scope(cleaned)
        reason = (cleaned.get("reason") or "").strip()
        if action in {
            self.ACTION_SUSPEND,
            self.ACTION_REVOKE,
            self.ACTION_REASSIGN,
            self.ACTION_UPDATE_ASSIGNMENT,
            self.ACTION_DELETE,
        } and not reason:
            self.add_error("reason", "Un motif est obligatoire pour cette décision DG.")
        if action == self.ACTION_DELETE and not cleaned.get("confirm_delete"):
            self.add_error("confirm_delete", "Confirmez explicitement la suppression définitive.")
        if action == self.ACTION_UPDATE_ASSIGNMENT and not cleaned.get("position"):
            self.add_error("position", "Sélectionnez un rôle institutionnel.")
        cleaned["reason"] = reason
        return cleaned


class DgStaffIdentityForm(forms.Form):
    """Business-facing identity fields; never exposes Django privileges."""

    profile_id = forms.IntegerField(min_value=1, widget=forms.HiddenInput)
    first_name = forms.CharField(max_length=150, label="Prénom")
    last_name = forms.CharField(max_length=150, label="Nom")
    email = forms.EmailField(required=False, label="Email")
    username = forms.CharField(max_length=150, label="Identifiant")
    phone = forms.CharField(max_length=30, required=False, label="Téléphone")
    salary_base = forms.IntegerField(min_value=0, required=False, label="Salaire brut mensuel (FCFA)")
    teacher_hourly_rate = forms.IntegerField(min_value=0, required=False, label="Tarif horaire (FCFA)")
    amo_applicable = forms.BooleanField(required=False, label="Appliquer l'AMO")
    amo_rate = forms.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2, required=False, label="Taux AMO (%)")
    inps_applicable = forms.BooleanField(required=False, label="Appliquer l'INPS")
    inps_rate = forms.DecimalField(min_value=0, max_value=100, max_digits=5, decimal_places=2, required=False, label="Taux INPS (%)")

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile = profile
        self.fields["amo_rate"].help_text = "Saisir un taux en %. Le montant FCFA sera calculé automatiquement sur le salaire brut."
        self.fields["inps_rate"].help_text = "Saisir un taux en %. Le montant FCFA sera calculé automatiquement sur le salaire brut."
        for field_name in ("amo_rate", "inps_rate"):
            self.fields[field_name].widget.attrs.update({"min": "0", "max": "100", "step": "0.01", "inputmode": "decimal"})
        if profile is not None and not self.is_bound:
            self.initial.update(
                profile_id=profile.pk,
                first_name=profile.user.first_name,
                last_name=profile.user.last_name,
                email=profile.user.email,
                username=profile.user.username,
                phone=profile.phone,
                salary_base=profile.salary_base,
                teacher_hourly_rate=profile.teacher_hourly_rate,
                amo_applicable=profile.amo_applicable,
                amo_rate=profile.amo_rate,
                inps_applicable=profile.inps_applicable,
                inps_rate=profile.inps_rate,
            )

    def clean(self):
        cleaned = super().clean()
        for enabled, rate, label in (
            ("amo_applicable", "amo_rate", "AMO"),
            ("inps_applicable", "inps_rate", "INPS"),
        ):
            if cleaned.get(enabled) and not cleaned.get(rate):
                self.add_error(rate, f"Renseignez le taux {label} en pourcentage.")
            if not cleaned.get(enabled):
                cleaned[rate] = 0
        return cleaned

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        from django.contrib.auth import get_user_model

        queryset = get_user_model().objects.filter(email__iexact=email) if email else get_user_model().objects.none()
        if self.profile is not None:
            queryset = queryset.exclude(pk=self.profile.user_id)
        if queryset.exists():
            raise ValidationError("Un compte utilise déjà cette adresse email.")
        return email

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        from django.contrib.auth import get_user_model

        queryset = get_user_model().objects.filter(username__iexact=username)
        if self.profile is not None:
            queryset = queryset.exclude(pk=self.profile.user_id)
        if queryset.exists():
            raise ValidationError("Cet identifiant est déjà utilisé.")
        return username


class DgBranchForm(forms.ModelForm):
    """Thin DG adapter over the authoritative Branch model.

    ``schools`` is not a Branch field: it drives SchoolBranch pairs through the
    shared implantation service, keeping the many-to-many architecture intact.
    """

    schools = forms.ModelMultipleChoiceField(
        queryset=School.objects.none(),
        required=False,
        label="Écoles présentes sur ce campus",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Branch
        fields = [
            "name",
            "code",
            "slug",
            "address",
            "city",
            "phone",
            "email",
            "manager",
            "is_active",
            "accepts_online_registration",
        ]

    def __init__(self, *args, context_school=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.context_school = context_school
        self.fields["name"].label = "Nom du campus"
        schools = School.objects.filter(
            Q(is_active=True) | Q(school_branches__branch=self.instance)
        ).distinct().order_by("order", "code") if self.instance.pk else School.objects.filter(is_active=True).order_by("order", "code")
        self.fields["schools"].queryset = schools
        self.fields["schools"].label_from_instance = (
            lambda school: f"{school.code} — {school.official_name or school.short_name}"
        )
        if self.instance.pk:
            self.fields["schools"].initial = self.instance.school_branches.filter(
                is_active=True,
            ).values_list("school_id", flat=True)
        elif context_school is not None:
            self.fields["schools"].initial = [context_school.pk]
        self.fields["manager"].queryset = (
            Profile.objects.filter(
                user__is_active=True,
                user_type="staff",
                position__in={"annex_manager", "branch_manager"},
            )
            .select_related("user")
            .order_by("user__first_name", "user__last_name", "user__username")
            .values_list("user_id", flat=True)
        )
        from django.contrib.auth import get_user_model

        self.fields["manager"].queryset = get_user_model().objects.filter(
            id__in=self.fields["manager"].queryset
        ).order_by("first_name", "last_name", "username")

    def clean_code(self):
        return (self.cleaned_data.get("code") or "").strip().upper()

    def clean_schools(self):
        schools = list(self.cleaned_data.get("schools") or [])
        # The school that opened this campus editor must never be detached
        # accidentally: it stays attached even if its checkbox is unticked.
        if self.context_school is not None and self.context_school not in schools:
            schools.append(self.context_school)
        return schools

    @transaction.atomic
    def save(self, commit=True):
        branch = super().save(commit=commit)
        if commit:
            from core.services.implantations import sync_branch_schools

            sync_branch_schools(branch, self.cleaned_data["schools"])
        return branch


class DgProgrammeForm(forms.ModelForm):
    """Adaptateur DG sur le catalogue institutionnel existant."""

    class Meta:
        model = Programme
        fields = [
            "title", "school", "filiere", "cycle", "diploma_awarded", "duration_years",
            "short_description", "description", "is_active", "is_public",
            "admissions_open",
        ]
        labels = {
            "title": "Intitulé de la formation",
            "filiere": "Filière",
            "cycle": "Cycle",
            "diploma_awarded": "Diplôme délivré",
            "duration_years": "Durée de la formation",
            "short_description": "Présentation courte",
            "description": "Description détaillée",
            "is_active": "Formation active",
            "is_public": "Visible sur le site public",
            "admissions_open": "Admissions ouvertes",
        }
        help_texts = {
            "duration_years": "Indiquez la durée en années, par exemple 3 ans.",
            "short_description": "Texte court affiché dans les listes et aperçus.",
            "description": "Présentez le contenu et les objectifs de la formation.",
        }
        widgets = {
            "duration_years": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric", "placeholder": "Ex. 3"}),
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    IDENTITY_FIELDS = {
        "title", "school", "filiere", "cycle", "diploma_awarded", "duration_years",
        "short_description", "description",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from core.models import School
        from .scoping import scoped, current_navigation

        self.fields["school"].queryset = scoped(School).filter(Q(is_active=True) | Q(pk=self.instance.school_id))
        self.fields["school"].required = not self.instance.pk or bool(self.instance.school_id)
        navigation = current_navigation()
        if navigation and navigation.selected_school:
            self.initial["school"] = navigation.selected_school.pk
            self.fields["school"].disabled = True
        elif self.instance.pk and self.is_bound and "school" not in self.data:
            # Old clients may edit publication fields without submitting School.
            self.fields["school"].disabled = True
        self.fields["filiere"].queryset = Filiere.objects.filter(is_active=True).order_by("name")
        self.fields["cycle"].queryset = Cycle.objects.filter(is_active=True).order_by("min_duration_years", "name")
        self.fields["diploma_awarded"].queryset = Diploma.objects.order_by("name")

    def clean(self):
        cleaned = super().clean()
        cycle = cleaned.get("cycle")
        duration = cleaned.get("duration_years")
        if cycle and duration and not cycle.min_duration_years <= duration <= cycle.max_duration_years:
            self.add_error(
                "duration_years",
                f"La durée doit être comprise entre {cycle.min_duration_years} et {cycle.max_duration_years} ans pour ce cycle.",
            )
        if cleaned.get("admissions_open") and (not cleaned.get("is_active") or not cleaned.get("is_public")):
            self.add_error("admissions_open", "Les admissions exigent une formation active et publiée.")
        if not self.instance.pk and all(cleaned.get(name) for name in ("title", "filiere", "cycle", "diploma_awarded")):
            duplicate = Programme.objects.filter(
                title__iexact=cleaned["title"].strip(),
                school=cleaned.get("school"),
                filiere=cleaned["filiere"],
                cycle=cleaned["cycle"],
                diploma_awarded=cleaned["diploma_awarded"],
            ).exists()
            if duplicate:
                self.add_error("title", "Cette formation existe déjà pour cette filière, ce cycle et ce diplôme.")
        return cleaned


class _DgReferenceBaseForm(forms.ModelForm):
    """Petite administration DG des référentiels déjà détenus par formations."""

    def clean_name(self):
        name = " ".join((self.cleaned_data.get("name") or "").split())
        model_class = self._meta.model
        duplicate = model_class.objects.filter(name__iexact=name)
        if self.instance.pk:
            duplicate = duplicate.exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise ValidationError("Ce référentiel existe déjà.")
        return name


class DgFiliereForm(_DgReferenceBaseForm):
    class Meta:
        model = Filiere
        fields = ["name", "description", "is_active"]
        labels = {
            "name": "Nom de la filière",
            "description": "Description",
            "is_active": "Filière active",
        }
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class DgCycleForm(_DgReferenceBaseForm):
    class Meta:
        model = Cycle
        fields = ["name", "min_duration_years", "max_duration_years", "description", "is_active"]
        labels = {
            "name": "Nom du cycle",
            "min_duration_years": "Durée minimale (années)",
            "max_duration_years": "Durée maximale (années)",
            "description": "Description",
            "is_active": "Cycle actif",
        }
        widgets = {
            "min_duration_years": forms.NumberInput(attrs={"min": 1}),
            "max_duration_years": forms.NumberInput(attrs={"min": 1}),
            "description": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        minimum = cleaned.get("min_duration_years")
        maximum = cleaned.get("max_duration_years")
        if minimum and maximum and minimum > maximum:
            self.add_error("max_duration_years", "La durée maximale doit être supérieure ou égale à la durée minimale.")
        return cleaned


class DgDiplomaForm(_DgReferenceBaseForm):
    class Meta:
        model = Diploma
        fields = ["name", "level"]
        labels = {"name": "Intitulé du diplôme", "level": "Niveau d'enseignement"}


class DgCouponForm(forms.Form):
    INPUT_CLASS = "h-ui-control w-full rounded-ui-input border border-ui-border bg-ui-surface px-3 text-sm text-ui-text focus:border-ui-focus focus:ring-ui-focus"
    DATETIME_FORMAT = "%Y-%m-%dT%H:%M"

    code = forms.CharField(
        max_length=32,
        widget=forms.TextInput(attrs={
            "class": f"{INPUT_CLASS} uppercase",
            "placeholder": "Ex: MASTER-DG-2026",
            "autocomplete": "off",
        }),
    )
    label = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={"class": INPUT_CLASS, "placeholder": "Description interne"}),
    )
    discount_type = forms.ChoiceField(
        choices=Coupon.DISCOUNT_TYPE_CHOICES,
        widget=forms.Select(attrs={"class": INPUT_CLASS}),
    )
    value = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
    )
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": INPUT_CLASS, "id": "dg-coupon-branches"}),
        label="Campus (vide = tous les campus)",
    )
    programmes = forms.ModelMultipleChoiceField(
        queryset=Programme.objects.none(),
        required=False,
        widget=forms.SelectMultiple(attrs={"class": INPUT_CLASS, "id": "dg-coupon-programmes"}),
        label="Formations (vide = toutes les formations)",
    )
    valid_from = forms.DateTimeField(
        required=False,
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
        ),
    )
    valid_until = forms.DateTimeField(
        input_formats=[DATETIME_FORMAT],
        widget=forms.DateTimeInput(
            format=DATETIME_FORMAT,
            attrs={"class": INPUT_CLASS, "type": "datetime-local"},
        ),
    )
    max_redemptions = forms.IntegerField(
        min_value=1,
        initial=1,
        widget=forms.NumberInput(attrs={"class": INPUT_CLASS}),
    )

    def __init__(self, *args, allowed_branch_ids=None, **kwargs):
        super().__init__(*args, **kwargs)
        branches = Branch.objects.filter(is_active=True)
        if allowed_branch_ids is not None:
            branches = branches.filter(id__in=allowed_branch_ids)
        self.fields["branches"].queryset = branches.order_by("name")
        self.fields["valid_from"].initial = timezone.now()

        selected_branch_ids = []
        if self.is_bound:
            if hasattr(self.data, "getlist"):
                selected_branch_ids = self.data.getlist("branches")
            else:
                selected_branch_ids = self.data.get("branches") or []
        self.fields["programmes"].queryset = self.programmes_queryset_for_branches(selected_branch_ids)

    @staticmethod
    def programmes_queryset_for_branches(branch_ids):
        from academics.models import AcademicClass

        branch_ids = [value for value in (branch_ids or []) if str(value).strip()]
        if not branch_ids:
            return scoped(Programme).order_by("title")
        programme_ids = (
            scoped(AcademicClass).filter(branch_id__in=branch_ids, is_active=True)
            .values_list("programme_id", flat=True)
            .distinct()
        )
        return scoped(Programme).filter(id__in=programme_ids).order_by("title")

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9_-]+", code):
            raise ValidationError(
                "Utilisez uniquement des lettres, chiffres, tirets et underscores, sans espace."
            )
        return code

    def clean(self):
        cleaned = super().clean()
        discount_type = cleaned.get("discount_type")
        value = cleaned.get("value")
        if discount_type == Coupon.DISCOUNT_PERCENTAGE and value is not None and value > 100:
            self.add_error("value", "Un pourcentage doit être compris entre 1 et 100.")

        valid_from = cleaned.get("valid_from") or timezone.now()
        valid_until = cleaned.get("valid_until")
        self.long_validity_warning = bool(
            valid_until and valid_until - valid_from > timedelta(days=30)
        )
        if valid_until and valid_from and valid_until <= valid_from:
            raise ValidationError({"valid_until": "La date de fin doit être postérieure à la date de début."})
        return cleaned
