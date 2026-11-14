from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string

from .models import (
    BranchBankTransfer,
    BranchCashMovement,
    BranchCashRegisterSession,
    BranchWallet,
    BranchExpense,
    BranchMonthlyClosure,
    Donation,
    PayrollEntry,
    Profile,
    TeacherHonorariumEntry,
    UserPreference,
)

User = get_user_model()


# ==========================
# CLASSE CSS DE BASE
# ==========================
INPUT_CLASS = (
    "w-full border border-gray-200 rounded-xl px-4 py-3.5 text-gray-700 "
    "placeholder-gray-400 bg-gray-50/50 "
    "focus:bg-white focus:border-primary-400 focus:ring-2 focus:ring-primary-100 "
    "transition-all duration-200 outline-none"
)

TEXTAREA_CLASS = (
    "w-full border border-gray-200 rounded-xl px-4 py-3.5 text-gray-700 "
    "placeholder-gray-400 bg-gray-50/50 min-h-[120px] resize-none "
    "focus:bg-white focus:border-primary-400 focus:ring-2 focus:ring-primary-100 "
    "transition-all duration-200 outline-none"
)


# ==========================
# INSCRIPTION
# ==========================
class CustomUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("username", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["username"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Choisissez un identifiant unique"
        })

        self.fields["password1"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Minimum 8 caractères"
        })

        self.fields["password2"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Confirmez votre mot de passe"
        })


# ==========================
# PROFIL COMPLET
# ==========================
class ProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = Profile
        fields = [
            "avatar",
            "bio",
            "location",
            "phone",
            "address",
            "main_domain",
            "website",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user_id:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name

        self.fields["first_name"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Prenom",
        })
        self.fields["last_name"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Nom",
        })

        # Avatar
        self.fields["avatar"].widget.attrs.update({
            "class": "hidden",
            "accept": "image/jpeg,image/png,image/webp",
            "id": "avatar-input"
        })

        # Bio
        self.fields["bio"].widget = forms.Textarea()
        self.fields["bio"].widget.attrs.update({
            "class": TEXTAREA_CLASS,
            "placeholder": "Décrivez votre parcours, spécialité ou centres d'intérêt...",
            "rows": 4
        })

        # Localisation
        self.fields["location"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: Douala, Cameroun"
        })

        self.fields["phone"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: +237 6 00 00 00 00",
        })

        self.fields["address"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: Quartier, ville, annexe ou adresse administrative",
        })

        # Domaine principal
        self.fields["main_domain"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: Médecine générale, Pédiatrie..."
        })

        # Site web
        self.fields["website"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "https://votre-site.com"
        })

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = profile.user
        user.first_name = self.cleaned_data.get("first_name", "").strip()
        user.last_name = self.cleaned_data.get("last_name", "").strip()
        if commit:
            user.save(update_fields=["first_name", "last_name"])
            profile.save()
        return profile


class SystemProfileForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=False)
    last_name = forms.CharField(max_length=150, required=False)

    class Meta:
        model = Profile
        fields = [
            "avatar",
            "phone",
            "address",
        ]

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.user_id:
            self.fields["first_name"].initial = self.instance.user.first_name
            self.fields["last_name"].initial = self.instance.user.last_name

        for field_name, placeholder in {
            "first_name": "Prenom",
            "last_name": "Nom",
        }.items():
            self.fields[field_name].widget.attrs.update({"class": INPUT_CLASS, "placeholder": placeholder})

        self.fields["avatar"].widget.attrs.update({
            "class": "hidden",
            "accept": "image/jpeg,image/png,image/webp",
            "id": "avatar-input",
            "x-ref": "avatarInput",
        })
        self.fields["phone"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: +223 70 00 00 00",
        })
        self.fields["address"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "Ex: Adresse administrative",
        })

    def save(self, commit=True):
        profile = super().save(commit=False)
        user = self.user or profile.user
        user.first_name = self.cleaned_data.get("first_name", "").strip()
        user.last_name = self.cleaned_data.get("last_name", "").strip()
        if commit:
            user.save(update_fields=["first_name", "last_name"])
            profile._skip_public_mirror = True
            profile.save()
        return profile


# ==========================
# EMAIL
# ==========================
class EmailUpdateForm(forms.ModelForm):
    current_password = forms.CharField(
        label="Mot de passe actuel",
        strip=False,
        widget=forms.PasswordInput(render_value=False),
    )

    class Meta:
        model = User
        fields = ["email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["email"].widget.attrs.update({
            "class": INPUT_CLASS,
            "placeholder": "exemple@domaine.com",
            "type": "email"
        })
        self.fields["current_password"].widget.attrs.update({
            "class": INPUT_CLASS,
            "autocomplete": "current-password",
        })

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Cette adresse email est déjà utilisée.")
        return email

    def clean_current_password(self):
        password = self.cleaned_data["current_password"]
        user = self.user or self.instance
        if not user.check_password(password):
            raise forms.ValidationError("Le mot de passe actuel est incorrect.")
        return password


class UserPreferenceForm(forms.ModelForm):
    class Meta:
        model = UserPreference
        fields = [
            "notify_email",
            "notify_in_app",
            "ui_sidebar_collapsed",
            "ui_compact_mode",
            "ui_autorefresh",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        checkbox_class = (
            "h-5 w-5 rounded border-gray-300 text-primary-600 "
            "focus:ring-2 focus:ring-primary-200"
        )
        labels = {
            "notify_email": "Recevoir les notifications par email",
            "notify_in_app": "Recevoir les notifications dans la plateforme",
            "ui_sidebar_collapsed": "Ouvrir les espaces avec barre laterale reduite",
            "ui_compact_mode": "Activer l'affichage compact",
            "ui_autorefresh": "Autoriser l'actualisation automatique des widgets",
        }
        for field_name, field in self.fields.items():
            field.widget.attrs.update({"class": checkbox_class})
            field.label = labels[field_name]


class PayrollEntryForm(forms.ModelForm):
    class Meta:
        model = PayrollEntry
        fields = [
            "base_salary",
            "allowances",
            "amo_applicable",
            "amo_rate",
            "inps_applicable",
            "inps_rate",
            "advances",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        self.fields["base_salary"].label = "Salaire brut de base (FCFA)"
        self.fields["allowances"].label = "Primes / indemnités (FCFA)"
        self.fields["advances"].label = "Avances déjà versées (FCFA)"
        for field_name in [
            "base_salary", "allowances", "amo_rate", "inps_rate", "advances",
        ]:
            self.fields[field_name].widget.attrs.update({"class": "dg-input"})
        self.fields["amo_applicable"].label = "Appliquer l'AMO pour cette paie"
        self.fields["inps_applicable"].label = "Appliquer l'INPS pour cette paie"
        self.fields["amo_rate"].label = "Taux AMO (%)"
        self.fields["inps_rate"].label = "Taux INPS (%)"
        self.fields["amo_rate"].required = False
        self.fields["inps_rate"].required = False
        self.fields["amo_rate"].help_text = "Saisissez uniquement le pourcentage. Le montant en FCFA est calculé automatiquement sur le brut."
        self.fields["inps_rate"].help_text = "Saisissez uniquement le pourcentage. Le montant en FCFA est calculé automatiquement sur le brut."
        for field_name in ["amo_rate", "inps_rate"]:
            self.fields[field_name].widget.attrs.update({"min": "0", "max": "100", "step": "0.01", "inputmode": "decimal"})
        self.fields["notes"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Observations internes sur la paie du mois...",
        })

    def clean(self):
        cleaned = super().clean()
        for enabled, rate, label in (
            ("amo_applicable", "amo_rate", "AMO"),
            ("inps_applicable", "inps_rate", "INPS"),
        ):
            if cleaned.get(enabled) and not cleaned.get(rate):
                # Keep legacy already-recorded amount-only sheets editable.
                legacy_amount = getattr(self.instance, "amo_amount" if label == "AMO" else "inps_amount", 0)
                if not legacy_amount:
                    self.add_error(rate, f"Renseignez le taux {label} en pourcentage.")
            if not cleaned.get(enabled):
                # Décocher une retenue désactive aussi son taux pour cette paie.
                cleaned[rate] = 0
        return cleaned


class TeacherHonorariumEntryForm(forms.ModelForm):
    class Meta:
        model = TeacherHonorariumEntry
        fields = [
            "adjustments",
            "deductions",
            "advances",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["adjustments", "deductions", "advances"]:
            self.fields[field_name].widget.attrs.update({"class": "dg-input"})
        self.fields["notes"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Observations internes sur les honoraires du mois...",
        })


class BranchMonthlyClosureForm(forms.ModelForm):
    class Meta:
        model = BranchMonthlyClosure
        fields = [
            "period_month",
            "physical_cash_count",
            "difference_justification",
            "notes",
        ]
        widgets = {
            "period_month": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "period_month": "Période",
            "physical_cash_count": "Montant physique compté",
            "difference_justification": "Justification de l'écart",
            "notes": "Observations",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["period_month", "physical_cash_count"]:
            self.fields[field_name].widget.attrs.update({"class": "dg-input"})
        self.fields["physical_cash_count"].widget.attrs.update({"min": "0"})
        self.fields["physical_cash_count"].required = True
        self.fields["difference_justification"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Obligatoire uniquement si le comptage diffère du solde théorique...",
        })
        self.fields["notes"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Motif de cloture ou observations de fin de periode...",
        })


class BranchBankTransferForm(forms.ModelForm):
    request_token = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = BranchBankTransfer
        fields = [
            "bank_name",
            "transfer_date",
            "amount",
            "proof",
            "comment",
        ]
        widgets = {
            "transfer_date": forms.DateInput(attrs={"type": "date"}),
            "comment": forms.Textarea(attrs={"rows": 3}),
        }
        labels = {
            "bank_name": "Banque",
            "transfer_date": "Date du versement",
            "amount": "Montant",
            "proof": "Justificatif bancaire",
            "comment": "Commentaire",
        }

    def __init__(self, *args, **kwargs):
        available_cash_balance = kwargs.pop("available_cash_balance", None)
        super().__init__(*args, **kwargs)
        for field_name in ["bank_name", "transfer_date", "amount"]:
            self.fields[field_name].widget.attrs.update({"class": "dg-input"})
        self.fields["request_token"].initial = self.initial.get("request_token") or get_random_string(48)
        self.fields["amount"].widget.attrs.update({"min": "1", "inputmode": "numeric", "x-model.number": "amount"})
        if available_cash_balance is not None:
            self.fields["amount"].widget.attrs["max"] = str(max(int(available_cash_balance), 0))
        self.fields["proof"].label = "Justificatif bancaire"
        self.fields["proof"].widget.attrs.update({
            "class": "dg-input",
            "accept": ".pdf,image/jpeg,image/png,image/webp",
        })
        self.fields["proof"].required = False
        self.fields["comment"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Commentaire interne sur le versement bancaire...",
        })
        self.fields["comment"].required = False


class BranchBankTransferProofForm(forms.ModelForm):
    class Meta:
        model = BranchBankTransfer
        fields = ["proof"]
        labels = {"proof": "Justificatif bancaire"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proof"].widget.attrs.update({
            "class": "dg-input",
            "accept": ".pdf,image/jpeg,image/png,image/webp",
        })
        self.fields["proof"].required = True


class BranchExpenseForm(forms.ModelForm):
    class Meta:
        model = BranchExpense
        fields = [
            "title",
            "category",
            "amount",
            "expense_date",
            "supplier",
            "receipt",
            "notes",
        ]
        widgets = {
            "expense_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ["title", "category", "amount", "expense_date", "supplier"]:
            self.fields[field_name].widget.attrs.update({"class": "dg-input"})
        self.fields["receipt"].widget.attrs.update({
            "class": "dg-input",
            "accept": ".pdf,image/jpeg,image/png,image/webp",
        })
        self.fields["notes"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Motif, details ou justification interne...",
        })


class BranchCashMovementForm(forms.ModelForm):
    ALLOWED_MANUAL_SOURCES = {
        BranchCashMovement.SOURCE_MANUAL,
        BranchCashMovement.SOURCE_ADJUSTMENT,
    }

    class Meta:
        model = BranchCashMovement
        fields = [
            "movement_type",
            "source",
            "amount",
            "label",
            "movement_date",
            "notes",
        ]
        widgets = {
            "movement_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source"].choices = [
            choice
            for choice in BranchCashMovement.SOURCE_CHOICES
            if choice[0] in self.ALLOWED_MANUAL_SOURCES
        ]
        for field_name in ["movement_type", "source", "amount", "label", "movement_date"]:
            self.fields[field_name].widget.attrs.update({"class": "dg-input"})
        self.fields["notes"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Commentaire interne sur ce mouvement...",
        })

    def clean_source(self):
        source = self.cleaned_data["source"]
        if source not in self.ALLOWED_MANUAL_SOURCES:
            raise forms.ValidationError(
                "Un mouvement manuel doit utiliser la source Manuel ou Ajustement."
            )
        return source


class CashRegisterOpenForm(forms.Form):
    opening_amount = forms.IntegerField(min_value=0, label="Comptage d'ouverture")
    opening_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["opening_amount"].widget.attrs.update({"class": "dg-input", "min": "0"})
        self.fields["opening_notes"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Observation d'ouverture (facultatif)...",
        })


class CashRegisterCloseForm(forms.Form):
    counted_amount = forms.IntegerField(min_value=0, label="Comptage physique de fermeture")
    closing_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["counted_amount"].widget.attrs.update({"class": "dg-input", "min": "0"})
        self.fields["closing_notes"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Justification obligatoire en cas d'ecart...",
        })


class BranchWalletForm(forms.ModelForm):
    """A deliberately small, business-facing form for logical cash compartments."""

    PROFILE_CHOICES = [
        ("salary", "Salaires du personnel"),
        ("honorarium", "Honoraires des enseignants"),
        ("expense", "Dépenses quotidiennes"),
        ("event", "Événement ou mission temporaire"),
        ("shop", "Recettes de la boutique"),
        ("student_payment", "Encaissements étudiants"),
        ("donation", "Dons reçus"),
        ("other", "Autre besoin"),
    ]
    PROFILE_CONFIGURATION = {
        "salary": (BranchWallet.TYPE_DISBURSEMENT, "salary", BranchWallet.NATURE_RECURRING),
        "honorarium": (BranchWallet.TYPE_DISBURSEMENT, "honorarium", BranchWallet.NATURE_RECURRING),
        "expense": (BranchWallet.TYPE_DISBURSEMENT, "expense", BranchWallet.NATURE_RECURRING),
        "event": (BranchWallet.TYPE_DISBURSEMENT, "event", BranchWallet.NATURE_TEMPORARY),
        "shop": (BranchWallet.TYPE_RECEIPT, "shop", BranchWallet.NATURE_RECURRING),
        "student_payment": (BranchWallet.TYPE_RECEIPT, "student_payment", BranchWallet.NATURE_RECURRING),
        "donation": (BranchWallet.TYPE_RECEIPT, "donation", BranchWallet.NATURE_RECURRING),
        "other": (BranchWallet.TYPE_DISBURSEMENT, "other", BranchWallet.NATURE_RECURRING),
    }

    profile = forms.ChoiceField(label="Usage", choices=PROFILE_CHOICES)

    class Meta:
        model = BranchWallet
        fields = ["name"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "dg-input"})
        self.fields["name"].widget.attrs.update(
            {"placeholder": "Ex. Salaires septembre"}
        )

    def apply_profile(self, wallet):
        """Apply controlled technical values after the user chose an understandable use."""
        wallet.wallet_type, wallet.category, wallet.nature = self.PROFILE_CONFIGURATION[
            self.cleaned_data["profile"]
        ]
        return wallet


class WalletAmountForm(forms.Form):
    amount = forms.IntegerField(min_value=1)
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({"class": "dg-input"})


class DonationForm(forms.ModelForm):
    class Meta:
        model = Donation
        fields = [
            "donor_name",
            "amount",
            "date",
            "motif",
            "payment_method",
            "description",
            "receipt_number",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "description": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["payment_method"].choices = [(Donation.PAYMENT_CASH, "Espèces")]
        for field_name in ["donor_name", "amount", "date", "motif", "payment_method", "receipt_number"]:
            self.fields[field_name].widget.attrs.update({"class": "dg-input"})
        self.fields["description"].widget.attrs.update({
            "class": "dg-input",
            "placeholder": "Remerciements ou note...",
        })
