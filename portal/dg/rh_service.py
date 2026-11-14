
from .scoping import scoped, staff_branch_filter
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models.deletion import Collector, ProtectedError, RestrictedError, SET_NULL, SET_DEFAULT
from django.db.models import Q
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils.text import slugify

from accounts.models import Profile, InstitutionalProfile, PublicCommunityProfile, AccountSessionRecord, AccountSecurityEvent
from accounts.position_registry import dg_assignable_positions, get_position_definition, normalize_position
from accounts.session_security import revoke_user_sessions
from accounts.services.institutional_access import compatibility_role_for_position
from core.emailing import get_email_branding_context, get_formatted_from_email
from portal.models import SupportAuditLog
from portal.services.it_support_service import reactivate_account, suspend_account


def get_dg_staff_profile(profile_id, *, branch_ids=None):
    queryset = scoped(Profile).select_related("user", "branch").filter(
        pk=profile_id,
        user_type="staff",
    )
    if branch_ids is not None:
        queryset = queryset.filter(staff_branch_filter(branch_ids))
    return queryset.first()


def get_dg_manageable_staff_profile(profile_id):
    """Resolve a DG target from institutional data, not a UI navigation filter.

    The DG dashboard's school/campus selector narrows lists only.  It must not
    turn a globally authorised DG into an unauthorised HR administrator when a
    modal POST no longer carries exactly the same display filter.
    """
    return (
        Profile.objects.select_related("user", "branch", "user__institutional_profile")
        .filter(pk=profile_id, user_type="staff")
        .first()
    )


def _locked_staff_profile(profile_id):
    return (
        # ``branch`` and ``institutional_profile`` are optional relations.
        # PostgreSQL cannot lock the nullable side of those outer joins; lock
        # the authoritative Profile row only, then read its related data.
        Profile.objects.select_for_update(of=("self",))
        .select_related("user", "branch", "user__institutional_profile")
        .filter(pk=profile_id, user_type="staff")
        .first()
    )


def _assert_dg_can_manage_staff(*, actor, profile):
    if profile is None:
        raise ValidationError("Membre du personnel introuvable.")
    if profile.user_id == actor.id:
        raise ValidationError("Vous ne pouvez pas modifier votre propre accès depuis le dashboard DG.")
    institutional_position = getattr(getattr(profile.user, "institutional_profile", None), "position", None)
    positions = [normalize_position(value) for value in (institutional_position, profile.position) if value]
    if (profile.user.is_superuser or not positions
            or any(position not in dg_assignable_positions() for position in positions)
            or profile.user.groups.filter(name="super_admin").exists()):
        raise ValidationError("Cette fonction exécutive nécessite le circuit institutionnel dédié.")


def can_dg_manage_staff(*, actor, profile):
    try:
        _assert_dg_can_manage_staff(actor=actor, profile=profile)
    except ValidationError:
        return False
    return True


def _deletion_collector(user):
    """Allow only empty account shells; retain any institutional history."""
    for relation in type(user)._meta.related_objects:
        field = relation.field
        if field.many_to_many or field.remote_field.on_delete not in {SET_NULL, SET_DEFAULT}:
            continue
        if relation.related_model is SupportAuditLog and field.name == "target_user":
            continue  # The audit keeps its label when this nullable target is removed.
        if relation.related_model is AccountSecurityEvent and field.name == "user":
            continue  # Technical assignment events survive with a nullable account link.
        if relation.related_model._base_manager.filter(**{field.name: user}).exists():
            return None
    collector = Collector(using=user._state.db or "default")
    try:
        collector.collect([user])
    except (ProtectedError, RestrictedError):
        return None
    safe_models = {type(user), Profile, InstitutionalProfile, PublicCommunityProfile}
    safe_join_tables = {"auth.user_groups", "auth.user_user_permissions"}
    for model, records in collector.data.items():
        if records and model not in safe_models and model._meta.label_lower not in safe_join_tables:
            return None
    for queryset in collector.fast_deletes:
        if not queryset.model._meta.auto_created and queryset.exists():
            return None
    return collector


def can_physically_delete_staff(*, actor, profile):
    return can_dg_manage_staff(actor=actor, profile=profile) and _deletion_collector(profile.user) is not None


def _staff_label(profile):
    return profile.user.get_full_name() or profile.user.username


def _save_staff_scope(profile, data, *, position=None):
    institutional = InstitutionalProfile.objects.select_for_update().select_related("school").get(user_id=profile.user_id)
    previous_school = institutional.school.display_name if institutional.school_id else "aucune"
    previous_scope = institutional.scope or "non défini"
    institutional.school = data.get("school")
    institutional.branch = data.get("branch")
    institutional.access_scope = data["access_scope"]
    institutional.position = position or profile.position
    institutional.full_clean()
    institutional.save()
    school = institutional.school
    return (
        f"École {previous_school} → {school.display_name if school else 'aucune'}; "
        f"périmètre {previous_scope} → {institutional.scope or 'non défini'}"
    )


@transaction.atomic
def apply_staff_lifecycle_action(*, actor, form, allowed_branch_ids=None, request=None):
    """Apply a DG-authorised staff decision without deleting institutional history."""

    data = form.cleaned_data
    action = data["action"]
    reason = (data.get("reason") or "").strip()
    profile = _locked_staff_profile(data["profile_id"])
    _assert_dg_can_manage_staff(actor=actor, profile=profile)
    target_user = profile.user
    previous_status = profile.employment_status
    previous_branch = profile.branch

    if action == "suspend":
        if profile.employment_status == "suspended" and not target_user.is_active:
            return {"ok": True, "message": f"{_staff_label(profile)} est déjà suspendu.", "close_modal": True}
        profile.employment_status = "suspended"
        profile.save(update_fields=["employment_status", "updated_at"])
        suspend_account(
            actor=actor,
            branch=profile.branch,
            target_user=target_user,
            reason=reason,
            audit_details=(
                f"Décision DG : statut RH {previous_status or 'non défini'} → suspendu. "
                f"Motif : {reason}"
            ),
            allow_global_dg=True,
        )
        return {"ok": True, "message": f"Accès suspendu pour {_staff_label(profile)}.", "close_modal": True}

    if action == "reactivate":
        if profile.employment_status == "active" and target_user.is_active:
            return {"ok": True, "message": f"{_staff_label(profile)} est déjà actif.", "close_modal": True}
        profile.employment_status = "active"
        profile.save(update_fields=["employment_status", "updated_at"])
        reactivate_account(
            actor=actor,
            branch=profile.branch,
            target_user=target_user,
            audit_details=(
                f"Décision DG : statut RH {previous_status or 'non défini'} → actif. "
                f"Motif : {reason or 'Réactivation autorisée par la Direction générale.'}"
            ),
            allow_global_dg=True,
        )
        return {"ok": True, "message": f"Accès réactivé pour {_staff_label(profile)}.", "close_modal": True}

    if action == "revoke":
        if profile.employment_status == "inactive" and not target_user.is_active:
            return {"ok": True, "message": f"{_staff_label(profile)} est déjà révoqué.", "close_modal": True}
        support_state = getattr(target_user, "support_state", None)
        if support_state and support_state.is_suspended:
            support_state.is_suspended = False
            support_state.updated_by = actor
            support_state.save(update_fields=["is_suspended", "updated_by", "updated_at"])
        profile.employment_status = "inactive"
        profile.save(update_fields=["employment_status", "updated_at"])
        target_user.is_active = False
        target_user.save(update_fields=["is_active"])
        SupportAuditLog.objects.create(
            branch=profile.branch,
            actor=actor,
            target_user=target_user,
            action_type=SupportAuditLog.ACTION_ACCOUNT_DEACTIVATED,
            target_label=_staff_label(profile),
            details=(
                f"Décision DG : affectation conservée, accès révoqué. "
                f"Statut RH {previous_status or 'non défini'} → inactif. Motif : {reason}"
            ),
        )
        return {"ok": True, "message": f"Accès révoqué pour {_staff_label(profile)} ; l'historique est conservé.", "close_modal": True}

    if action == "resend_invitation":
        if request is None:
            raise ValidationError("La demande d'invitation est incomplète.")
        if not target_user.is_active or profile.employment_status != "active" or target_user.has_usable_password() or not target_user.email:
            raise ValidationError("Ce compte n'est pas éligible à une invitation de première connexion.")
        target_user.set_unusable_password()  # Rotates Django's existing one-time token.
        target_user.save(update_fields=["password"])
        try:
            _send_staff_activation_invitation(
                user=target_user, position=profile.position, recipient=target_user.email,
                request=request,
            )
        except Exception as exc:
            raise ValidationError("L'invitation n'a pas pu être envoyée. Réessayez plus tard.") from exc
        SupportAuditLog.objects.create(
            branch=profile.branch, actor=actor, target_user=target_user,
            action_type=SupportAuditLog.ACTION_PASSWORD_RESET,
            target_label=_staff_label(profile),
            details="Invitation de première connexion renvoyée par la Direction générale.",
        )
        return {"ok": True, "message": "Invitation sécurisée renvoyée.", "close_modal": True}

    if action == "delete":
        target_user = type(target_user).objects.select_for_update().get(pk=target_user.pk)
        collector = _deletion_collector(target_user)
        if collector is None:
            raise ValidationError("Ce compte possède un historique institutionnel à conserver. La suppression définitive est impossible ; révoquez ses accès.")
        label = _staff_label(profile)
        revoke_user_sessions(target_user, reason=AccountSessionRecord.END_ADMIN_REVOKED, global_scope=True)
        SupportAuditLog.objects.create(
            branch=profile.branch, actor=actor, target_user=target_user,
            action_type=SupportAuditLog.ACTION_ACCOUNT_DEACTIVATED,
            target_label=label,
            details=f"Suppression physique du compte DG (identifiant {target_user.pk}). Motif : {reason}",
        )
        # The existing pre-delete signal records the assignment revocation;
        # do it before User.delete() builds its collector so that event is retained.
        InstitutionalProfile.objects.filter(user=target_user).delete()
        target_user.delete()
        return {"ok": True, "message": f"Utilisateur {label} supprimé définitivement.", "close_modal": True}

    if action == "reassign":
        branch = data.get("branch")
        if allowed_branch_ids is not None and branch is not None and branch.id not in allowed_branch_ids:
            raise ValidationError("Le campus de destination est hors du contexte DG actif.")
        definition = get_position_definition(profile.position)
        if definition and definition.branch_required and branch is None and data.get("access_scope") != "SCHOOL":
            raise ValidationError("Un campus actif est obligatoire pour cette fonction.")
        scope_changes = _save_staff_scope(profile, data)
        profile.branch = branch
        profile.save(update_fields=["branch", "updated_at"])
        from payments.services.agents import ensure_cash_agent_for_manager

        ensure_cash_agent_for_manager(user=target_user, branch=profile.branch)
        SupportAuditLog.objects.create(
            branch=branch or previous_branch,
            actor=actor,
            target_user=target_user,
            action_type=SupportAuditLog.ACTION_STAFF_ASSIGNED,
            target_label=_staff_label(profile),
            details=(
                f"Décision DG : affectation {getattr(previous_branch, 'name', 'globale')} → "
                f"{getattr(branch, 'name', 'globale')}; {scope_changes}. Motif : {reason}"
            ),
        )
        return {"ok": True, "message": f"Affectation mise à jour pour {_staff_label(profile)}.", "close_modal": True}

    if action == "update_assignment":
        branch = data.get("branch")
        position = data.get("position")
        if allowed_branch_ids is not None and branch is not None and branch.id not in allowed_branch_ids:
            raise ValidationError("Le campus de destination est hors du contexte DG actif.")
        definition = get_position_definition(position)
        if not definition or position not in dg_assignable_positions():
            raise ValidationError("Ce rôle ne peut pas être attribué depuis le workflow RH courant.")
        if definition.branch_required and branch is None and data.get("access_scope") != "SCHOOL":
            raise ValidationError("Un campus actif est obligatoire pour cette fonction.")
        if position == "moniteur":
            if not (profile.main_domain or "").strip():
                raise ValidationError("Renseignez la spécialité avant d'attribuer la fonction de moniteur.")
            if profile.salary_base <= 0:
                raise ValidationError("Renseignez le salaire fixe avant d'attribuer la fonction de moniteur.")

        previous_position = profile.position
        scope_changes = _save_staff_scope(profile, data, position=position)

        profile.position = position
        profile.role = compatibility_role_for_position(position)
        profile.branch = branch
        update_fields = ["position", "role", "branch", "updated_at"]
        if position == "moniteur" and profile.teacher_hourly_rate:
            # Le tarif du profil n'est pas un historique financier : le remettre
            # à zéro empêche toute nouvelle préparation d'honoraires, sans
            # modifier les fiches historiques déjà constituées.
            profile.teacher_hourly_rate = 0
            update_fields.append("teacher_hourly_rate")
        profile.save(update_fields=update_fields)
        from payments.services.agents import ensure_cash_agent_for_manager

        ensure_cash_agent_for_manager(user=target_user, branch=profile.branch)
        SupportAuditLog.objects.create(
            branch=branch or previous_branch,
            actor=actor,
            target_user=target_user,
            action_type=SupportAuditLog.ACTION_STAFF_ASSIGNED,
            target_label=_staff_label(profile),
            details=(
                f"Décision DG : rôle {previous_position or 'non défini'} → {position}; "
                f"affectation {getattr(previous_branch, 'name', 'sans campus')} → "
                f"{getattr(branch, 'name', 'sans campus')}; {scope_changes}. Motif : {reason}"
            ),
        )
        return {
            "ok": True,
            "message": f"Rôle et affectation mis à jour pour {_staff_label(profile)}.",
            "close_modal": True,
        }

    raise ValidationError("Action RH DG inconnue.")


@transaction.atomic
def update_staff_identity(*, actor, form):
    """Update ordinary account identity data while preserving RH relationships."""

    profile = _locked_staff_profile(form.cleaned_data["profile_id"])
    _assert_dg_can_manage_staff(actor=actor, profile=profile)
    target_user = profile.user
    before = {
        "first_name": target_user.first_name,
        "last_name": target_user.last_name,
        "email": target_user.email,
        "username": target_user.username,
        "phone": profile.phone,
    }
    data = form.cleaned_data
    target_user.first_name = data["first_name"]
    target_user.last_name = data["last_name"]
    target_user.email = data["email"]
    target_user.username = data["username"]
    target_user.full_clean(exclude=["password"])
    target_user.save(update_fields=["first_name", "last_name", "email", "username"])
    profile.phone = data["phone"]
    profile_updates = ["phone", "updated_at"]
    # Ces champs sont facultatifs pour les anciennes soumissions d'identité,
    # mais deviennent éditables depuis la fiche RH actuelle.
    numeric_fields = {"salary_base", "teacher_hourly_rate", "amo_rate", "inps_rate"}
    for field in ("salary_base", "teacher_hourly_rate", "amo_applicable", "amo_rate", "inps_applicable", "inps_rate"):
        if field in form.data:
            value = (data.get(field) or 0) if field in numeric_fields else bool(data.get(field))
            setattr(profile, field, value)
            profile_updates.append(field)
    profile.save(update_fields=profile_updates)
    changed = [key for key, value in before.items() if value != data[key]]
    if changed:
        SupportAuditLog.objects.create(
            branch=profile.branch,
            actor=actor,
            target_user=target_user,
            action_type=SupportAuditLog.ACTION_EMAIL_UPDATED,
            target_label=_staff_label(profile),
            details="Décision DG : informations de compte corrigées (" + ", ".join(changed) + ").",
        )
    return {
        "ok": True,
        "message": f"Informations mises à jour pour {_staff_label(profile)}.",
        "close_modal": True,
    }


def _build_username(first_name, last_name):
    user_model = get_user_model()
    base = slugify(f"{first_name}.{last_name}") or "staff"
    username = base
    index = 1
    while user_model.objects.filter(username=username).exists():
        index += 1
        username = f"{base}{index}"
    return username


def _send_staff_activation_invitation(*, user, position, recipient, request):
    """Deliver the existing one-time password setup link with institution data."""

    activation_url = request.build_absolute_uri(
        reverse(
            "accounts_portal:dg_staff_activation",
            kwargs={
                "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
                "token": default_token_generator.make_token(user),
            },
        )
    )
    branding = get_email_branding_context()
    institution_name = branding["institution_name"]
    definition = get_position_definition(position)
    position_label = definition.label if definition else position
    recipient_name = user.get_full_name() or user.username
    send_mail(
        f"Activez votre accès {institution_name}",
        (
            f"Bonjour {recipient_name},\n\n"
            f"Votre compte {institution_name} est prêt pour le poste : {position_label}.\n\n"
            "Définissez votre mot de passe personnel depuis ce lien sécurisé à usage unique :\n"
            f"{activation_url}\n\n"
            f"Votre identifiant de connexion : {user.username}\n\n"
            "Ne partagez pas ce lien."
        ),
        get_formatted_from_email(),
        [recipient],
        fail_silently=False,
    )


def create_staff_from_recruitment(*, actor, form, request):
    """Create the authoritative record first; an SMTP failure cannot roll it back."""

    data = form.cleaned_data
    if data["position"] not in dg_assignable_positions():
        raise ValidationError("Ce poste ne peut pas être créé par la Direction générale.")
    user_model = get_user_model()
    email = data.get("professional_email") or data.get("personal_email") or ""
    generate_access = bool(data.get("generate_access"))

    with transaction.atomic():
        user = user_model.objects.create_user(
            username=_build_username(data["first_name"], data["last_name"]),
            email=email,
            password=None,
            first_name=data["first_name"],
            last_name=data["last_name"],
            is_staff=True,
            is_active=generate_access,
        )
        profile, _created = Profile.objects.get_or_create(user=user)
        profile.role = form.profile_role()
        profile.user_type = "staff"
        profile.position = form.profile_position()
        profile.branch = data.get("branch")
        profile.phone = data.get("phone") or ""
        profile.main_domain = data.get("main_domain") or ""
        profile.salary_base = data.get("salary_base") or 0
        profile.teacher_hourly_rate = data.get("teacher_hourly_rate") or 0
        profile.amo_applicable = bool(data.get("amo_applicable"))
        profile.inps_applicable = bool(data.get("inps_applicable"))
        profile.amo_rate = data.get("amo_rate") or 0
        profile.inps_rate = data.get("inps_rate") or 0
        profile.employment_status = "active"
        profile.is_public = False
        profile.save(
            update_fields=[
                "role", "user_type", "position", "branch", "phone", "main_domain", "salary_base",
                "teacher_hourly_rate", "amo_applicable", "inps_applicable", "amo_rate", "inps_rate",
                "employment_status",
                "is_public", "updated_at",
            ]
        )
        _save_staff_scope(profile, data)
        SupportAuditLog.objects.create(
            branch=data.get("branch"),
            actor=actor,
            target_user=user,
            action_type=(SupportAuditLog.ACTION_ACCOUNT_ACTIVATED if generate_access else SupportAuditLog.ACTION_ACCOUNT_DEACTIVATED),
            target_label=user.get_full_name() or user.username,
            details=(
                "Dossier RH créé depuis le dashboard DG. Invitation de première connexion à remettre."
                if generate_access
                else "Dossier RH créé depuis le dashboard DG sans accès actif."
            ),
        )

    access_delivery = "not_requested"
    if generate_access:
        try:
            _send_staff_activation_invitation(
                user=user,
                position=profile.position,
                recipient=email,
                request=request,
            )
        except Exception:
            access_delivery = "activation_email_failed"
            SupportAuditLog.objects.create(
                branch=profile.branch,
                actor=actor,
                target_user=user,
                action_type=SupportAuditLog.ACTION_ACCOUNT_ACTIVATED,
                target_label=user.get_full_name() or user.username,
                details="Dossier RH créé ; l'envoi de l'invitation sécurisée est à relancer.",
            )
        else:
            access_delivery = "activation_email_sent"

    return {
        "user": user,
        "profile": profile,
        "ticket": None,
        "access_delivery": access_delivery,
        "access_delivery_label": (
            "Lien sécurisé de première connexion envoyé par email."
            if access_delivery == "activation_email_sent"
            else "Le compte est créé, mais l'invitation email n'a pas pu être envoyée. Relancez-la depuis l'administration."
            if access_delivery == "activation_email_failed"
            else "Aucun accès actif n'a été demandé ; le dossier RH a été créé."
        ),
    }
