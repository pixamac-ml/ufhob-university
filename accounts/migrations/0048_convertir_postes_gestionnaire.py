"""Décisions D2 + D3 (20/11/2026) : gestionnaire unique et agent de caisse automatique.

Aller : tout compte « finance_manager », « payment_agent » ou « admissions »
devient « annex_manager » (Gestionnaire). Chaque conversion est tracée dans
LegacyPositionConversion. Une gestionnaire convertie qui a un campus et pas
encore de profil d'agent de caisse en reçoit un.

Retour : les anciens postes sont restaurés à partir de la trace, les agents
créés par cette migration sont supprimés (ou désactivés s'ils ont déjà servi).
"""

import secrets

from django.db import migrations
from django.db.models import ProtectedError

RETIRED = ("finance_manager", "payment_agent", "admissions")
MANAGER = "annex_manager"
OLD_ROLES = {"finance_manager": "finance", "payment_agent": "finance", "admissions": "admissions"}


def _unique_agent_code(PaymentAgent):
    while True:
        code = secrets.token_hex(3).upper()
        if not PaymentAgent.objects.filter(agent_code=code).exists():
            return code


def convertir(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    InstitutionalProfile = apps.get_model("accounts", "InstitutionalProfile")
    Conversion = apps.get_model("accounts", "LegacyPositionConversion")
    PaymentAgent = apps.get_model("payments", "PaymentAgent")
    Group = apps.get_model("auth", "Group")

    manager_group, _ = Group.objects.get_or_create(name=MANAGER)
    converted_users = {}

    # Mises à jour directes (sans signaux) : même résultat en migration et en test.
    for profile in list(Profile.objects.filter(position__in=RETIRED)):
        Conversion.objects.create(
            user_id=profile.user_id, source="profile", old_position=profile.position, new_position=MANAGER,
        )
        converted_users.setdefault(profile.user_id, profile.branch_id)
        Profile.objects.filter(pk=profile.pk).update(position=MANAGER, role="")

    for institutional in list(InstitutionalProfile.objects.filter(position__in=RETIRED)):
        Conversion.objects.create(
            user_id=institutional.user_id, source="institutional",
            old_position=institutional.position, new_position=MANAGER,
        )
        converted_users[institutional.user_id] = institutional.branch_id or converted_users.get(institutional.user_id)
        InstitutionalProfile.objects.filter(pk=institutional.pk).update(position=MANAGER)

    retired_groups = Group.objects.filter(name__in=RETIRED)
    for user_id, branch_id in converted_users.items():
        manager_group.user_set.add(user_id)
        for group in retired_groups:
            group.user_set.remove(user_id)
        if branch_id and not PaymentAgent.objects.filter(user_id=user_id).exists():
            PaymentAgent.objects.create(
                user_id=user_id, branch_id=branch_id, is_active=True, agent_code=_unique_agent_code(PaymentAgent),
            )
            Conversion.objects.filter(user_id=user_id).update(payment_agent_created=True)


def restaurer(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    InstitutionalProfile = apps.get_model("accounts", "InstitutionalProfile")
    Conversion = apps.get_model("accounts", "LegacyPositionConversion")
    PaymentAgent = apps.get_model("payments", "PaymentAgent")
    Group = apps.get_model("auth", "Group")

    for conversion in Conversion.objects.all():
        if conversion.source == "profile":
            Profile.objects.filter(user_id=conversion.user_id, position=MANAGER).update(
                position=conversion.old_position, role=OLD_ROLES.get(conversion.old_position, ""),
            )
        else:
            InstitutionalProfile.objects.filter(user_id=conversion.user_id, position=MANAGER).update(
                position=conversion.old_position,
            )
        old_group, _ = Group.objects.get_or_create(name=conversion.old_position)
        old_group.user_set.add(conversion.user_id)
        manager_group = Group.objects.filter(name=MANAGER).first()
        if manager_group is not None:
            manager_group.user_set.remove(conversion.user_id)
        if conversion.payment_agent_created:
            for agent in PaymentAgent.objects.filter(user_id=conversion.user_id):
                try:
                    agent.delete()
                except ProtectedError:
                    agent.is_active = False
                    agent.save(update_fields=["is_active"])
    Conversion.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0047_gestionnaire_unique"),
        ("payments", "0007_alter_financiallog_action"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(convertir, restaurer),
    ]
