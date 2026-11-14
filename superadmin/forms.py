from django import forms
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.db.models import Q
from django_ckeditor_5.widgets import CKEditor5Widget

from branches.models import Branch
from core.models import DirectorGeneralMessage, Infrastructure, School, Staff, UniversityLifeItem, Value
from formations.models import Programme
from portal.dg.forms import DgBranchForm

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024


class DirectorGeneralMessageForm(forms.ModelForm):
    class Meta:
        model = DirectorGeneralMessage
        fields = (
            "full_name", "position", "photo", "title", "message", "signature",
            "published_at", "order", "is_active",
        )
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-input"}),
            "position": forms.TextInput(attrs={"class": "form-input"}),
            "photo": forms.FileInput(attrs={"class": "form-input", "accept": "image/*"}),
            "title": forms.TextInput(attrs={"class": "form-input"}),
            "message": forms.Textarea(attrs={"class": "form-textarea", "rows": 8}),
            "signature": forms.TextInput(attrs={"class": "form-input"}),
            "published_at": forms.DateTimeInput(attrs={"class": "form-input", "type": "datetime-local"}),
            "order": forms.NumberInput(attrs={"class": "form-input", "min": 0}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > MAX_IMAGE_SIZE_BYTES:
            raise forms.ValidationError("La photo ne doit pas dépasser 5 Mo.")
        return photo


class StaffPublicForm(forms.ModelForm):
    """Editorial staff entries, separate from authenticated user accounts."""

    class Meta:
        model = Staff
        fields = (
            "full_name", "position", "category", "photo", "bio", "email", "linkedin",
            "is_featured", "order", "is_active",
        )
        widgets = {
            "full_name": forms.TextInput(attrs={"class": "form-input"}),
            "position": forms.TextInput(attrs={"class": "form-input"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "photo": forms.FileInput(attrs={"class": "form-input", "accept": "image/*"}),
            "bio": forms.Textarea(attrs={"class": "form-textarea", "rows": 5}),
            "email": forms.EmailInput(attrs={"class": "form-input"}),
            "linkedin": forms.URLInput(attrs={"class": "form-input"}),
            "order": forms.NumberInput(attrs={"class": "form-input", "min": 0}),
        }

    def clean_photo(self):
        photo = self.cleaned_data.get("photo")
        if photo and photo.size > MAX_IMAGE_SIZE_BYTES:
            raise forms.ValidationError("La photo ne doit pas depasser 5 Mo.")
        return photo


class CampusAdminForm(DgBranchForm):
    """Superadmin presentation fields over the shared campus editor rules."""

    class Meta(DgBranchForm.Meta):
        fields = [*DgBranchForm.Meta.fields, 'image', 'public_description', 'access_information']

    def __init__(self, *args, **kwargs):
        if args and args[0] is not None:
            data = args[0].copy()
            name = data.get('name', '').strip()
            data['code'] = data.get('code', '').strip() or slugify(name)[:8].upper()
            data['slug'] = data.get('slug', '').strip() or slugify(name)
            data['city'] = data.get('city', '').strip() or 'Bamako'
            args = (data, *args[1:])
        super().__init__(*args, **kwargs)
        self.fields['manager'].queryset = get_user_model().objects.filter(is_active=True)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs['class'] = 'form-input'


class ProgrammeForm(forms.ModelForm):

    class Meta:
        model = Programme
        fields = [
            'title',
            'school',
            'short_description',
            'description',
            'cycle',
            'filiere',
            'diploma_awarded',
            'duration_years',
            'learning_outcomes',
            'career_opportunities',
            'program_structure',
            'illustration',
            'meta_title',
            'meta_description',
            'og_image',
            'is_active',
            'is_public',
            'admissions_open',
            'is_featured',
        ]

        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-input',
                'placeholder': 'Ex: Licence en Sciences Informatiques',
            }),
            'school': forms.Select(attrs={'class': 'form-select'}),
            'short_description': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': 300,
                'placeholder': 'Ex: Formation complète en développement logiciel et algorithmes',
            }),
            'description': CKEditor5Widget(
                attrs={'class': 'django_ckeditor_5'},
                config_name='default',
            ),
            'cycle': forms.Select(attrs={'class': 'form-select'}),
            'filiere': forms.Select(attrs={'class': 'form-select'}),
            'diploma_awarded': forms.Select(attrs={'class': 'form-select'}),
            'duration_years': forms.NumberInput(attrs={
                'class': 'form-input', 'min': 1, 'max': 10,
            }),
            'learning_outcomes': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': '- Maitrise des algorithmes et structures de donnees\n- Programmation orientee objet\n- Gestion de bases de donnees',
            }),
            'career_opportunities': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': '- Developpeur logiciel\n- Ingenieur systeme\n- Analyste de donnees',
            }),
            'program_structure': forms.Textarea(attrs={
                'class': 'form-textarea', 'rows': 4,
                'placeholder': 'Cours theoriques: 60%\nTravaux pratiques: 30%\nStages: 10%',
            }),
            'illustration': forms.FileInput(attrs={
                'class': 'form-input', 'accept': 'image/*',
            }),
            'meta_title': forms.TextInput(attrs={
                'class': 'form-input',
                'maxlength': 70,
                'placeholder': "Ex: Licence en Sciences Informatiques - ESFE",
            }),
            'meta_description': forms.Textarea(attrs={
                'class': 'form-textarea',
                'rows': 3,
                'maxlength': 160,
                'placeholder': "Resume accrocheur affiche dans les partages Facebook et les resultats de recherche.",
            }),
            'og_image': forms.FileInput(attrs={
                'class': 'form-input', 'accept': 'image/*',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'sr-only'}),
            'is_public': forms.CheckboxInput(attrs={'class': 'sr-only'}),
            'admissions_open': forms.CheckboxInput(attrs={'class': 'sr-only'}),
            'is_featured': forms.CheckboxInput(attrs={'class': 'sr-only'}),
        }

        labels = {
            'title': 'Titre du programme',
            'school': 'École',
            'short_description': 'Description courte',
            'description': 'Description',
            'cycle': 'Cycle',
            'filiere': 'Filière',
            'diploma_awarded': 'Diplôme délivré',
            'duration_years': 'Durée (années)',
            'learning_outcomes': 'Compétences acquises',
            'career_opportunities': 'Débouchés professionnels',
            'program_structure': 'Structure pédagogique',
            'illustration': 'Image du programme',
            'meta_title': 'Titre SEO / réseaux sociaux',
            'meta_description': 'Description SEO / réseaux sociaux',
            'og_image': 'Image de partage social',
            'is_active': 'Programme actif',
            'is_public': 'Visible sur le site public',
            'admissions_open': 'Candidatures ouvertes',
            'is_featured': 'Programme en vedette',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['duration_years'].initial = 3
        self.fields['school'].required = True
        # Keep the current relation editable even when a School is temporarily
        # unpublished from the public website.
        self.fields['school'].queryset = School.objects.all().order_by('order', 'code')

    def _clean_image_size(self, field_name):
        uploaded = self.cleaned_data.get(field_name)
        if uploaded and hasattr(uploaded, 'size') and uploaded.size > MAX_IMAGE_SIZE_BYTES:
            raise forms.ValidationError("L'image ne doit pas dépasser 5 Mo.")
        return uploaded

    def clean_illustration(self):
        return self._clean_image_size('illustration')

    def clean_og_image(self):
        return self._clean_image_size('og_image')


class SchoolPublicForm(forms.ModelForm):
    branches = forms.ModelMultipleChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        label="Campus d'implantation",
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = School
        fields = [
            'code', 'short_name', 'official_name', 'description',
            'detailed_description', 'logo', 'hero_image', 'cta_title',
            'cta_text', 'cta_button_text', 'cta_button_url', 'is_active',
            'is_featured', 'order',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'detailed_description': forms.Textarea(attrs={'rows': 7}),
            'cta_text': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            from portal.dg.university_forms import resolve_university_institution

            self.instance.institution = resolve_university_institution()
        self.fields['branches'].queryset = Branch.objects.filter(
            Q(is_active=True) | Q(school_branches__school_id=self.instance.pk)
        ).distinct().order_by('name')
        if self.instance.pk:
            self.fields['branches'].initial = self.instance.school_branches.filter(
                is_active=True,
            ).values_list('branch_id', flat=True)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs['class'] = 'rounded border-slate-300 text-emerald-600'
            elif isinstance(field.widget, forms.CheckboxSelectMultiple):
                field.widget.attrs['class'] = 'space-y-2'
            else:
                field.widget.attrs['class'] = 'form-input'

    def clean_code(self):
        code = self.cleaned_data['code'].strip().upper()
        if School.objects.filter(
            institution_id=self.instance.institution_id, code__iexact=code,
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Ce code est déjà utilisé par une école de l’université.')
        return code

    def _clean_image_size(self, field_name):
        uploaded = self.cleaned_data.get(field_name)
        if uploaded and hasattr(uploaded, 'size') and uploaded.size > MAX_IMAGE_SIZE_BYTES:
            raise forms.ValidationError("L'image ne doit pas dépasser 5 Mo.")
        return uploaded

    def clean_logo(self):
        return self._clean_image_size('logo')

    def clean_hero_image(self):
        return self._clean_image_size('hero_image')


class ValuePublicForm(forms.ModelForm):
    class Meta:
        model = Value
        fields = ['title', 'description', 'icon', 'is_active', 'order']
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'rounded border-slate-300 text-emerald-600'
                if isinstance(field.widget, forms.CheckboxInput)
                else 'form-input'
            )


class InfrastructurePublicForm(forms.ModelForm):
    class Meta:
        model = Infrastructure
        fields = ['name', 'category', 'description', 'image', 'features', 'is_active', 'order']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'features': forms.Textarea(attrs={'rows': 3, 'placeholder': '["Équipement 1", "Équipement 2"]'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = (
                'rounded border-slate-300 text-emerald-600'
                if isinstance(field.widget, forms.CheckboxInput)
                else 'form-input'
            )

    def clean_image(self):
        uploaded = self.cleaned_data.get('image')
        if uploaded and hasattr(uploaded, 'size') and uploaded.size > MAX_IMAGE_SIZE_BYTES:
            raise forms.ValidationError("L'image ne doit pas dépasser 5 Mo.")
        return uploaded


class UniversityLifeItemForm(forms.ModelForm):
    class Meta:
        model = UniversityLifeItem
        fields = ["title", "category", "description", "image", "link_url", "is_active", "order"]
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "rounded border-slate-300 text-emerald-600"
                if isinstance(field.widget, forms.CheckboxInput)
                else "form-input"
            )

    def clean_image(self):
        uploaded = self.cleaned_data.get("image")
        if uploaded and hasattr(uploaded, "size") and uploaded.size > MAX_IMAGE_SIZE_BYTES:
            raise forms.ValidationError("L'image ne doit pas dépasser 5 Mo.")
        return uploaded
