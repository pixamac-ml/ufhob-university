# payments/forms.py

from django import forms
from payments.services.cash import (
    verify_agent_and_create_session,
    validate_cash_code,
)


class StudentPaymentForm(forms.Form):
    """
    Formulaire utilisé par l'étudiant
    pour INITIER une demande de paiement.
    """

    method = forms.ChoiceField(
        choices=[],
        label="Méthode de paiement",
        widget=forms.Select(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-4 py-2"
            }
        )
    )

    # R-I3 : plus de nom à taper. L'agent est la gestionnaire de l'école du
    # dossier ; le code n'est demandé que s'il y en a plusieurs sur le campus.
    agent_code = forms.CharField(
        required=False,
        label="Gestionnaire qui encaisse",
        max_length=8,
    )

    verification_code = forms.CharField(
        required=False,
        label="Code de validation",
        widget=forms.TextInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-4 py-2",
                "placeholder": "Code à 6 chiffres"
            }
        )
    )

    amount = forms.IntegerField(
        min_value=1,
        label="Montant à payer (FCFA)",
        widget=forms.NumberInput(
            attrs={
                "class": "w-full border border-gray-300 rounded-lg px-4 py-2",
                "placeholder": "Ex : 50000"
            }
        )
    )

    def __init__(self, *args, inscription=None, **kwargs):
        super().__init__(*args, **kwargs)

        from payments.models import Payment
        # V1 exposes physical collection only.  Historical Orange Money and
        # bank-transfer records remain readable at model/report level.
        self.fields["method"].choices = [(Payment.METHOD_CASH, "Espèces")]

        self.inscription = inscription
        self.agent = None
        self.cash_session = None

    # ==================================================
    # VALIDATION GLOBALE
    # ==================================================
    def clean(self):
        cleaned_data = super().clean()

        method = cleaned_data.get("method")
        agent_code = cleaned_data.get("agent_code")
        code = cleaned_data.get("verification_code")
        amount = cleaned_data.get("amount")

        # Sécurité de base
        if not self.inscription:
            raise forms.ValidationError("Inscription invalide.")

        if not amount or amount <= 0:
            raise forms.ValidationError("Montant invalide.")

        # ==================================================
        # CAS PAIEMENT EN ESPÈCES
        # ==================================================
        if method == "cash":

            # 1️⃣ Agent = gestionnaire de l'école + campus du dossier
            agent, error = verify_agent_and_create_session(
                self.inscription,
                agent_code,
            )

            if error:
                raise forms.ValidationError(error)

            # 3️⃣ Code obligatoire
            if not code:
                raise forms.ValidationError(
                    "Veuillez entrer le code de validation communiqué par l'agent."
                )

            # 4️⃣ Validation code dynamique
            session, error = validate_cash_code(
                self.inscription,
                agent,
                code
            )

            if not session:
                raise forms.ValidationError(error)

            # 5️⃣ OK
            self.agent = agent
            self.cash_session = session

        return cleaned_data
