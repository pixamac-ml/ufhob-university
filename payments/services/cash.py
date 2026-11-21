# payments/services/cash.py

from django.utils import timezone
from datetime import timedelta
import secrets
from django.db import transaction

from payments.models import PaymentAgent, CashPaymentSession


MANAGER_POSITIONS = ("annex_manager", "branch_manager")
NO_AGENT_MESSAGE = (
    "Aucune gestionnaire de votre école n'est disponible sur ce campus. "
    "Adressez-vous au service des admissions."
)


def eligible_agents_for_inscription(inscription):
    """Gestionnaires pouvant encaisser ce dossier (décision D3, R-I3).

    L'agent est la gestionnaire de l'ÉCOLE de la formation, sur le CAMPUS
    du dossier. Deux écoles d'un même campus ne partagent jamais d'agent.
    """
    candidature = getattr(inscription, "candidature", None)
    branch = getattr(candidature, "branch", None)
    school = getattr(getattr(candidature, "programme", None), "school", None)
    if branch is None or school is None:
        return PaymentAgent.objects.none()
    return (
        PaymentAgent.objects.select_related("user", "branch")
        .filter(
            is_active=True,
            user__is_active=True,
            branch=branch,
            user__institutional_profile__position__in=MANAGER_POSITIONS,
            user__institutional_profile__school=school,
        )
        .order_by("user__last_name", "user__first_name", "pk")
    )


def resolve_cash_agent(inscription, agent_code=None):
    """Retourne (agent, erreur). Plus aucune recherche par nom approché."""
    agents = list(eligible_agents_for_inscription(inscription))
    if not agents:
        return None, NO_AGENT_MESSAGE
    code = (agent_code or "").strip().upper()
    if code:
        for agent in agents:
            if agent.agent_code.upper() == code:
                return agent, None
        return None, "Ce code agent ne correspond à aucune gestionnaire de votre école sur ce campus."
    if len(agents) == 1:
        return agents[0], None
    return None, "Choisissez la gestionnaire qui encaisse votre paiement."


# ============================================================
# 1️⃣ Déterminer l'agent + créer (ou récupérer) session active
# ============================================================

def verify_agent_and_create_session(inscription, agent_code=None):
    """
    Détermine l'agent (gestionnaire de l'école + campus du dossier).

    Réutilise une session active si elle existe.
    Sinon crée une nouvelle session (valide 5 minutes).

    Retourne:
        (agent, error)
    """

    agent, error = resolve_cash_agent(inscription, agent_code)
    if error:
        return None, error

    with transaction.atomic():

        # Nettoyer sessions expirées
        CashPaymentSession.objects.filter(
            inscription=inscription,
            agent=agent,
            expires_at__lt=timezone.now()
        ).update(is_used=True)

        # Vérifier session active
        session = (
            CashPaymentSession.objects
            .select_for_update()
            .filter(
                inscription=inscription,
                agent=agent,
                is_used=False,
                expires_at__gt=timezone.now()
            )
            .order_by("-created_at")
            .first()
        )

        if not session:

            verification_code = str(secrets.randbelow(900000) + 100000)

            session = CashPaymentSession.objects.create(
                inscription=inscription,
                agent=agent,
                verification_code=verification_code,
                expires_at=timezone.now() + timedelta(minutes=5),
                is_used=False
            )

    return agent, None


# ============================================================
# 2️⃣ Validation code dynamique
# ============================================================

def validate_cash_code(inscription, agent, code):
    """
    Vérifie que :

    - une session active existe
    - le code correspond
    - il n’est pas expiré

    Marque la session comme utilisée si OK.

    Retourne :
        (session, error)
    """

    if not code:
        return None, "Code requis."

    with transaction.atomic():
        session = (
            CashPaymentSession.objects
            .select_for_update()
            .filter(
                inscription=inscription,
                agent=agent,
                is_used=False
            )
            .order_by("-created_at")
            .first()
        )

        if not session:
            return None, "Aucune session active trouvée."

        # ⏳ Code expiré
        if timezone.now() > session.expires_at:
            session.is_used = True
            session.save(update_fields=["is_used"])
            return None, "Code expiré."

        # ❌ Mauvais code
        if session.verification_code != code:
            return None, "Code invalide."

        # ✅ Validation
        session.is_used = True
        session.save(update_fields=["is_used"])

    return session, None
