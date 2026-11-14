"""Dashboard forms for the existing university reference models."""

from django import forms
from django.db import transaction
from django.db.models import Q

from branches.models import Branch
from core.models import Institution, School, SchoolBranch
from academics.models import AcademicYear
from formations.models import Programme


def resolve_university_institution():
    """Return the singleton university institution (active preferred)."""
    return (
        Institution.objects.filter(is_active=True).order_by("id").first()
        or Institution.objects.order_by("id").first()
    )


class DgSchoolForm(forms.ModelForm):
    """School identity plus its campus implantations.

    ``branches`` is not a School field: it drives SchoolBranch pairs through
    the shared implantation service, keeping the many-to-many architecture.
    """

    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        label="Campus d'implantation",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = School
        fields = ["code", "short_name", "official_name", "description", "order", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, navigation=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.navigation = navigation
        if not self.instance.pk:
            self.instance.institution = resolve_university_institution()
        branches = Branch.objects.filter(
            Q(is_active=True) | Q(school_branches__school=self.instance)
        ).distinct().order_by("name") if self.instance.pk else Branch.objects.filter(is_active=True).order_by("name")
        self.fields["branches"].queryset = branches
        if self.instance.pk:
            self.fields["branches"].initial = self.instance.school_branches.filter(
                is_active=True,
            ).values_list("branch_id", flat=True)

    def clean_branches(self):
        branches = list(self.cleaned_data.get("branches") or [])
        # The campus currently selected in the DG context must never be
        # detached accidentally from its school while editing that school.
        navigation = self.navigation
        if (
            navigation is not None
            and navigation.selected_branch is not None
            and navigation.selected_school is not None
            and self.instance.pk
            and navigation.selected_school.pk == self.instance.pk
            and navigation.selected_branch not in branches
        ):
            branches.append(navigation.selected_branch)
        return branches

    @transaction.atomic
    def save(self, commit=True):
        school = super().save(commit=commit)
        if commit:
            from core.services.implantations import sync_school_branches

            sync_school_branches(school, self.cleaned_data["branches"])
        return school

    def clean_code(self):
        code = self.cleaned_data["code"].strip().upper()
        if School.objects.filter(institution_id=self.instance.institution_id, code__iexact=code).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ce code est déjà utilisé par une école de l’université.")
        return code

    def clean(self):
        cleaned = super().clean()
        if not self.instance.institution_id:
            raise forms.ValidationError(
                "Aucune institution n’est configurée. Créez l’institution universitaire avant d’ajouter une école."
            )
        return cleaned


class DgSchoolBranchForm(forms.ModelForm):
    class Meta:
        model = SchoolBranch
        fields = ["branch", "local_code", "opening_date", "closing_date", "is_active"]
        labels = {"branch": "Campus existant", "is_active": "Implantation active"}
        widgets = {
            "opening_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "closing_date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, school=None, navigation, **kwargs):
        super().__init__(*args, **kwargs)
        school = school or (self.instance.school if self.instance.school_id else None)
        if school is not None:
            self.instance.school = school
        if self.instance.pk or school is not None:
            # An implantation is a historical pair, never an editable reassignment.
            self.fields.pop("school", None)
        else:
            self.fields["school"] = forms.ModelChoiceField(
                queryset=School.objects.filter(is_active=True).order_by("order", "code"),
                label="École",
            )
            self.order_fields(["school", *self.Meta.fields])
        branches = Branch.objects.filter(Q(is_active=True) | Q(pk=self.instance.branch_id))
        if school is None and not self.is_bound:
            branches = branches.none()
        if navigation.selected_branch:
            branches = branches.filter(pk=navigation.selected_branch.pk)
        if not self.instance.pk and school is not None:
            # Only campuses without an active link are proposed; an inactive
            # link stays selectable so the form can reactivate it.
            branches = branches.exclude(pk__in=SchoolBranch.objects.filter(
                school=school, is_active=True,
            ).values("branch_id"))
        self.fields["branch"].queryset = branches.order_by("name")
        self.fields["branch"].disabled = bool(self.instance.pk)

    def clean(self):
        cleaned = super().clean()
        if "school" in self.fields:
            self.instance.school = cleaned.get("school")
        branch = cleaned.get("branch")
        school = self.instance.school if self.instance.school_id else None
        if school and branch and SchoolBranch.objects.filter(school=school, branch=branch).exclude(pk=self.instance.pk).exists():
            self.add_error("branch", "Cette école est déjà implantée sur ce campus. Réactivez ou modifiez le rattachement existant.")
        opening, closing = cleaned.get("opening_date"), cleaned.get("closing_date")
        if opening and closing and closing < opening:
            self.add_error("closing_date", "La fermeture doit être postérieure ou égale à l’ouverture.")
        if cleaned.get("is_active") and (school is not None and not school.is_active or (branch and not branch.is_active)):
            self.add_error("is_active", "L’école et le campus doivent être actifs pour activer cette implantation.")
        return cleaned


class DgAcademicClassForm(forms.Form):
    """Create an active class from the executive university context."""

    school = forms.ModelChoiceField(queryset=School.objects.none(), label="École")
    branch = forms.ModelChoiceField(queryset=Branch.objects.none(), label="Campus")
    programme = forms.ModelChoiceField(queryset=Programme.objects.none(), label="Programme")
    academic_year = forms.ModelChoiceField(queryset=AcademicYear.objects.none(), label="Année académique")
    level = forms.CharField(max_length=40, label="Niveau", help_text="Ex. Licence 1, 1ère année, Deuxième année")
    validation_threshold = forms.DecimalField(required=False, min_value=0.01, max_value=20, label="Seuil de validation")

    def __init__(self, *args, navigation, instance=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.navigation = navigation
        self.instance = instance
        self.fields["school"].queryset = School.objects.filter(is_active=True).order_by("order", "code")
        self.fields["branch"].queryset = Branch.objects.filter(is_active=True).order_by("name")
        self.fields["academic_year"].queryset = AcademicYear.objects.order_by("-start_date", "-id")
        self.fields["programme"].queryset = Programme.objects.filter(is_active=True).select_related("school").order_by("title")
        if navigation.selected_school:
            self.initial["school"] = navigation.selected_school.pk
            self.fields["programme"].queryset = self.fields["programme"].queryset.filter(school=navigation.selected_school)
        if navigation.selected_branch:
            self.initial["branch"] = navigation.selected_branch.pk
        if navigation.academic_year:
            self.initial["academic_year"] = navigation.academic_year.pk
        if instance is not None:
            self.initial.update({
                "school": instance.programme.school_id,
                "branch": instance.branch_id,
                "programme": instance.programme_id,
                "academic_year": instance.academic_year_id,
                "level": instance.level,
                "validation_threshold": instance.validation_threshold,
            })

        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "w-full rounded-ui-input border border-ui-border bg-ui-surface px-3 py-2 text-sm")

    def clean(self):
        cleaned = super().clean()
        school, branch, programme = cleaned.get("school"), cleaned.get("branch"), cleaned.get("programme")
        if school and programme and programme.school_id != school.pk:
            self.add_error("programme", "Le programme doit appartenir à l’école sélectionnée.")
        if school and branch and not SchoolBranch.objects.filter(school=school, branch=branch, is_active=True).exists():
            self.add_error("branch", "Cette école n’est pas active sur ce campus.")
        if self.navigation.selected_school and school and school.pk != self.navigation.selected_school.pk:
            self.add_error("school", "L’école ne correspond pas au contexte DG sélectionné.")
        if self.navigation.selected_branch and branch and branch.pk != self.navigation.selected_branch.pk:
            self.add_error("branch", "Le campus ne correspond pas au contexte DG sélectionné.")
        return cleaned

    def clean_level(self):
        return self.cleaned_data["level"].strip().upper()
