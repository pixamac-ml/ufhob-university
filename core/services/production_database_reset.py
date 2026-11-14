"""Controlled UFHOB pre-production reset.

This service deliberately separates the university reference data from the
operational records created by demonstrations.  It is not a Django flush and
never touches migrations, permissions, groups, the Institution, Schools,
Campuses, SchoolBranch, or the programme catalogue.
"""

from __future__ import annotations

import unicodedata
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterable

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import CommandError
from django.db import connection, transaction
from django.db.models import FileField

from core.services.business_data_reset import deletion_order, _clear_nullable_self_references


# The list is explicit so that adding an app never silently makes its records
# eligible for destructive deletion.
OPERATIONAL_APP_LABELS = {
    "academic_cycle",
    "accounts",
    "admissions",
    "axes",
    "communications",
    "coupons",
    "inscriptions",
    "notifier",
    "notification_center",
    "payments",
    "portal",
    "secretary",
    "students",
    "sessions",
}

OTHER_OPERATIONAL_MODEL_LABELS = {
    "community.gamificationprofile",
    "community.xptransaction",
    "superadmin.superadmincockpitpreference",
    "news.news",
    "news.event",
}

MEMOIRE_MODEL_LABELS = {
    "memoires.memoire",
    "memoires.pagememoire",
    "memoires.consultationlog",
}

STRUCTURAL_CONTENT_MODEL_LABELS = {
    "news.category",
    "news.news",
    "news.eventtype",
    "news.event",
}

# These apps may contain an institutional public catalogue or editorial data.
# They require an explicit classification before any production reset can run.
REVIEW_APP_LABELS = {"blog", "community", "marketing", "memoires", "news", "shop", "superadmin"}

# These are reference/configuration records rather than transactional data.
OPERATIONAL_MODEL_EXCLUSIONS = {
    "accounts.accountingdocumentsequence",
    "accounts.profile",
    "accounts.institutionalprofile",
    "accounts.publiccommunityprofile",
    "academics.language",
    "academics.profession",
    "portal.branchitsettings",
}

ACADEMIC_OPERATIONAL_LABELS = {
    model_label
    for model_label in (
        "academics.academicbulletin",
        "academics.academicyear",
        "academics.coursesessionauditlog",
        "academics.academiccalendar",
        "academics.academiccalendaradjustment",
        "academics.academiccalendardisruption",
        "academics.academiccalendarentry",
        "academics.academicclass",
        "academics.academicdebt",
        "academics.academicdecisionlog",
        "academics.academicdiplomaaward",
        "academics.academicdocumentauditlog",
        "academics.academicenrollment",
        "academics.academicschedulechangelog",
        "academics.academicscheduleevent",
        "academics.academicscheduleexecutionlog",
        "academics.coursesessionassistsession",
        "academics.ec",
        "academics.ecchapter",
        "academics.eccontent",
        "academics.ecgrade",
        "academics.ecpedagogicalanswer",
        "academics.ecpedagogicalquestion",
        "academics.ecresource",
        "academics.evaluationcampaign",
        "academics.evaluationcampaignscope",
        "academics.evaluationproctor",
        "academics.evaluationproctorassignment",
        "academics.evaluationrequirement",
        "academics.evaluationscriptbatch",
        "academics.lessonlog",
        "academics.officialtranscriptrequest",
        "academics.onlineclassrecording",
        "academics.resultaccessauthorization",
        "academics.semester",
        "academics.studentcontentprogress",
        "academics.ue",
        "academics.weeklyscheduleslot",
    )
}

CORE_OPERATIONAL_LABELS = {
    "core.contactmessage",
    "core.infrastructure",
    "core.signaturerequest",
    "core.staff",
    "core.statushistory",
}

PROFILE_LABELS = (
    "accounts.profile",
    "accounts.institutionalprofile",
    "accounts.publiccommunityprofile",
)


def _normalise(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKD", value or "")
        if not unicodedata.combining(character)
    ).upper()


def _model(label: str):
    try:
        return apps.get_model(label)
    except LookupError:
        return None


def operational_models(*, keep_class_ids: Iterable[int] = (), remove_memoires: bool = False) -> list[type]:
    """Return only explicitly classified transactional models.

    The institutional catalogue, School and Campus models are intentionally
    absent. Academic years and classes are operational. Keeping a class is
    incompatible with the complete academic-year reset and is refused below.
    """

    models: list[type] = []
    for model in apps.get_models():
        opts = model._meta
        if not opts.managed or opts.proxy or opts.auto_created:
            continue
        label = opts.label_lower
        if (
            label in ACADEMIC_OPERATIONAL_LABELS
            or label in CORE_OPERATIONAL_LABELS
            or label in OTHER_OPERATIONAL_MODEL_LABELS
            or (remove_memoires and label in MEMOIRE_MODEL_LABELS)
        ):
            models.append(model)
        elif opts.app_label in OPERATIONAL_APP_LABELS and label not in OPERATIONAL_MODEL_EXCLUSIONS:
            models.append(model)
    return models


@dataclass(frozen=True)
class ProductionResetPlan:
    protected_usernames: tuple[str, ...]
    keep_class_ids: tuple[int, ...]
    memoire_disposition: str
    delete_counts: dict[str, int]
    structural_keep: dict[str, list[dict[str, object]]]
    structural_remove: dict[str, list[dict[str, object]]]
    structural_unknown: dict[str, list[dict[str, object]]]
    candidate_users: list[dict[str, object]]
    operational_classes: list[dict[str, object]]
    media_files: list[tuple[object, str]]

    @property
    def delete_total(self) -> int:
        return sum(self.delete_counts.values())


def _user_candidates() -> list[dict[str, object]]:
    user_model = get_user_model()
    candidates = []
    for user in user_model.objects.select_related("profile__branch").order_by("username"):
        profile = getattr(user, "profile", None)
        candidates.append(
            {
                "username": user.username,
                "email": user.email,
                "position": getattr(profile, "position", "") or "",
                "is_superuser": user.is_superuser,
                "is_staff": user.is_staff,
                "campus": getattr(getattr(profile, "branch", None), "name", "") or "",
            }
        )
    return candidates


def _structural_classification(*, memoire_disposition: str) -> tuple[dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]], dict[str, list[dict[str, object]]]]:
    keep: dict[str, list[dict[str, object]]] = defaultdict(list)
    remove: dict[str, list[dict[str, object]]] = defaultdict(list)
    unknown: dict[str, list[dict[str, object]]] = defaultdict(list)

    institution_model = _model("core.institution")
    if institution_model:
        keep["Institution"] = [
            {"id": item.pk, "name": str(item), "active": getattr(item, "is_active", None)}
            for item in institution_model.objects.order_by("pk")
        ]

    school_model = _model("core.school")
    if school_model:
        for school in school_model.objects.order_by("pk"):
            data = {
                "id": school.pk,
                "code": school.code,
                "name": school.display_name,
                "active": school.is_active,
            }
            # A historical code alone does not authorize deletion of a School.
            keep["Écoles"].append(data)

    branch_model = _model("branches.branch")
    if branch_model:
        keep["Campus"] = [
            {
                "id": item.pk,
                "code": item.code,
                "name": item.name,
                "active": getattr(item, "is_active", None),
            }
            for item in branch_model.objects.order_by("pk")
        ]

    programme_model = _model("formations.programme")
    if programme_model:
        for programme in programme_model.objects.select_related("school").order_by("pk"):
            data = {
                "id": programme.pk,
                "title": programme.title,
                "school": getattr(getattr(programme, "school", None), "code", ""),
                "active": programme.is_active,
            }
            if not programme.school_id:
                unknown["Programmes"] .append(data)
            else:
                keep["Programmes"] .append(data)

    for label in ("core.schoolbranch", "formations.cycle", "formations.diploma", "formations.filiere"):
        model = _model(label)
        if model:
            keep[model._meta.label] = list(model.objects.order_by("pk").values("pk"))

    for model in apps.get_models():
        if model._meta.label_lower in MEMOIRE_MODEL_LABELS and memoire_disposition == "keep":
            keep["Mémoires"] .append({"model": model._meta.label, "count": model._default_manager.count()})
            continue
        if (
            model._meta.app_label not in REVIEW_APP_LABELS
            or model._meta.label_lower in STRUCTURAL_CONTENT_MODEL_LABELS
            or model._meta.label_lower in OTHER_OPERATIONAL_MODEL_LABELS
            or (memoire_disposition == "remove" and model._meta.label_lower in MEMOIRE_MODEL_LABELS)
            or not model._meta.managed
            or model._meta.proxy
            or model._meta.auto_created
        ):
            continue
        count = model._default_manager.count()
        if count:
            unknown["Données à classifier"] .append(
                {"model": model._meta.label, "count": count}
            )

    return dict(keep), dict(remove), dict(unknown)


def _collect_media_files(models: Iterable[type]) -> list[tuple[object, str]]:
    files: list[tuple[object, str]] = []
    for model in models:
        file_fields = [field for field in model._meta.fields if isinstance(field, FileField)]
        if not file_fields:
            continue
        for item in model._default_manager.all().only("pk", *[field.name for field in file_fields]):
            for field in file_fields:
                file = getattr(item, field.name)
                if file and file.name:
                    files.append((file.storage, file.name))
    return files


def build_production_reset_plan(
    *,
    preserve_usernames: Iterable[str] = (),
    keep_class_ids: Iterable[int] = (),
    memoire_disposition: str = "unknown",
) -> ProductionResetPlan:
    if memoire_disposition not in {"unknown", "keep", "remove"}:
        raise CommandError("Disposition des mémoires invalide.")
    usernames = tuple(dict.fromkeys(item.strip() for item in preserve_usernames if item and item.strip()))
    protected_ids: set[int] = set()
    if usernames:
        user_model = get_user_model()
        protected_ids = set(user_model.objects.filter(username__in=usernames).values_list("pk", flat=True))

    classes_to_keep = tuple(sorted({int(item) for item in keep_class_ids}))
    if classes_to_keep:
        raise CommandError("Conserver des classes est incompatible avec le reset des années académiques.")
    counts: dict[str, int] = {}
    models = operational_models(
        keep_class_ids=classes_to_keep,
        remove_memoires=memoire_disposition == "remove",
    )
    for model in models:
        queryset = model._default_manager.all()
        if model._meta.label_lower == "academics.academicclass" and classes_to_keep:
            queryset = queryset.exclude(pk__in=classes_to_keep)
        count = queryset.count()
        if count:
            counts[model._meta.label] = count

    user_model = get_user_model()
    user_count = user_model.objects.exclude(pk__in=protected_ids).count()
    if user_count:
        counts[user_model._meta.label] = user_count
    for label in PROFILE_LABELS:
        model = _model(label)
        if model:
            count = model.objects.exclude(user_id__in=protected_ids).count()
            if count:
                counts[model._meta.label] = count

    keep, remove, unknown = _structural_classification(memoire_disposition=memoire_disposition)
    class_model = _model("academics.academicclass")
    semester_model = _model("academics.semester")
    schedule_model = _model("academics.academicscheduleevent")
    operational_classes: list[dict[str, object]] = []
    if class_model:
        for academic_class in (
            class_model.objects.select_related("programme", "branch", "academic_year")
            .exclude(pk__in=classes_to_keep)
            .order_by("pk")
        ):
            operational_classes.append(
                {
                    "id": academic_class.pk,
                    "class": academic_class.display_name,
                    "programme": academic_class.programme.title,
                    "campus": academic_class.branch.name,
                    "academic_year": academic_class.academic_year.name,
                    "semesters": semester_model.objects.filter(academic_class=academic_class).count() if semester_model else 0,
                    "schedule_events": schedule_model.objects.filter(academic_class=academic_class).count() if schedule_model else 0,
                }
            )
    return ProductionResetPlan(
        protected_usernames=usernames,
        keep_class_ids=classes_to_keep,
        memoire_disposition=memoire_disposition,
        delete_counts=dict(sorted(counts.items())),
        structural_keep=keep,
        structural_remove=remove,
        structural_unknown=unknown,
        candidate_users=_user_candidates(),
        operational_classes=operational_classes,
        media_files=_collect_media_files(models) + [
            (file.storage, file.name)
            for label in PROFILE_LABELS
            for profile in _model(label).objects.exclude(user_id__in=protected_ids)
            for field in profile._meta.fields if isinstance(field, FileField)
            for file in [getattr(profile, field.name)] if file and file.name
        ],
    )


def validate_execute_plan(plan: ProductionResetPlan) -> list[int]:
    if not plan.protected_usernames:
        raise CommandError("Exécution refusée : indiquez chaque compte bootstrap avec --keep-user.")
    if plan.structural_unknown:
        details = ", ".join(sorted(plan.structural_unknown))
        raise CommandError(f"Exécution refusée : référentiels UNKNOWN : {details}.")
    user_model = get_user_model()
    users = list(user_model.objects.filter(username__in=plan.protected_usernames))
    found = {user.username for user in users}
    missing = sorted(set(plan.protected_usernames).difference(found))
    if missing:
        raise CommandError("Compte bootstrap introuvable : " + ", ".join(missing))
    if not any(user.is_superuser for user in users):
        raise CommandError("Exécution refusée : la whitelist doit inclure un SuperAdmin actif.")
    if any(not user.is_active or not user.has_usable_password() for user in users):
        raise CommandError("Exécution refusée : les comptes bootstrap doivent être actifs et utilisables.")
    protected_ids = [user.pk for user in users]
    selected = {model: model.objects.all() for model in operational_models(
        keep_class_ids=plan.keep_class_ids, remove_memoires=plan.memoire_disposition == "remove",
    )}
    selected[user_model] = user_model.objects.exclude(pk__in=protected_ids)
    selected.update({_model(label): _model(label).objects.exclude(user_id__in=protected_ids)
                     for label in PROFILE_LABELS})
    for model in apps.get_models():
        if not model._meta.managed or model._meta.proxy:
            continue
        kept = model.objects.all()
        if model in selected:
            kept = kept.exclude(pk__in=selected[model].values("pk"))
        if not kept.exists():
            continue
        for field in model._meta.fields:
            if field.is_relation and field.remote_field.model in selected:
                if kept.filter(**{field.name + "__in": selected[field.remote_field.model]}).exists():
                    raise CommandError(f"Reset refusé : dépendance protégée {model._meta.label}.{field.name}.")
    return [user.pk for user in users]


@contextmanager
def _defer_memoire_media_cleanup():
    """Only the checked post-commit cleanup may remove physical files.

    The normal mémoire deletion signals delete files immediately, even if the
    surrounding database transaction later rolls back.
    """
    from django.db.models.signals import post_delete
    from memoires.models import Memoire, PageMemoire
    from memoires.signals import _supprimer_fichier_source, _supprimer_image_page

    receivers = [(Memoire, _supprimer_fichier_source), (PageMemoire, _supprimer_image_page)]
    disconnected = [(model, receiver) for model, receiver in receivers
                    if post_delete.disconnect(receiver, sender=model)]
    try:
        yield
    finally:
        for model, receiver in disconnected:
            post_delete.connect(receiver, sender=model)


def _preserved_snapshot(models, protected_ids):
    """Detect indirect cascades or SET_NULL writes into preserved records."""
    excluded = set(models)
    user_model = get_user_model()
    snapshots = {}
    for model in apps.get_models():
        if model in excluded or not model._meta.managed or model._meta.proxy:
            continue
        queryset = model._default_manager.order_by("pk")
        if model is user_model:
            queryset = queryset.filter(pk__in=protected_ids)
        elif model._meta.label_lower in PROFILE_LABELS:
            queryset = queryset.filter(user_id__in=protected_ids)
        snapshots[model._meta.label] = list(queryset.values())
    snapshots["protected_user_groups"] = list(
        user_model.groups.through.objects.filter(user_id__in=protected_ids).order_by("pk").values()
    )
    snapshots["protected_user_permissions"] = list(
        user_model.user_permissions.through.objects.filter(user_id__in=protected_ids).order_by("pk").values()
    )
    return snapshots


def execute_production_reset(plan: ProductionResetPlan) -> dict[str, int]:
    """Delete operational data while retaining the plan's university reference data."""

    deleted: dict[str, int] = {}
    with _defer_memoire_media_cleanup(), transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", ["ufhob:production-reset"])

        protected_ids = validate_execute_plan(plan)
        list(get_user_model().objects.select_for_update().filter(pk__in=protected_ids))
        models = operational_models(
            keep_class_ids=plan.keep_class_ids,
            remove_memoires=plan.memoire_disposition == "remove",
        )
        before = _preserved_snapshot(models, protected_ids)
        _clear_nullable_self_references(models)

        # Profiles are handled before Users; canonical roles/groups themselves
        # remain available to the application after the reset.
        for label in PROFILE_LABELS:
            model = _model(label)
            if model:
                queryset = model.objects.exclude(user_id__in=protected_ids)
                count = queryset.count()
                if count:
                    queryset.delete()
                    deleted[model._meta.label] = count

        for model in deletion_order(models):
            queryset = model._default_manager.all()
            if model._meta.label_lower == "academics.academicclass" and plan.keep_class_ids:
                queryset = queryset.exclude(pk__in=plan.keep_class_ids)
            count = queryset.count()
            if count:
                queryset.delete()
                deleted[model._meta.label] = count

        user_model = get_user_model()
        queryset = user_model.objects.exclude(pk__in=protected_ids)
        count = queryset.count()
        if count:
            queryset.delete()
            deleted[user_model._meta.label] = count

        after = _preserved_snapshot(models, protected_ids)
        changed = [label for label in before if before[label] != after[label]]
        if changed:
            raise CommandError("Reset annulé : données protégées modifiées : " + ", ".join(changed))
        remaining = {model._meta.label: model.objects.count() for model in models if model.objects.exists()}
        if remaining:
            raise CommandError("Reset annulé : données opérationnelles restantes : " + str(remaining))
        if deleted:
            # Technical maintenance uses Django's existing administration log.
            # It survives because its actor is the preserved SuperAdmin.
            import json
            from django.contrib.admin.models import CHANGE, LogEntry
            LogEntry.objects.create(
                user_id=get_user_model().objects.filter(pk__in=protected_ids, is_superuser=True).first().pk,
                action_flag=CHANGE,
                object_repr="UFHOB — reset pré-production",
                change_message=json.dumps({"reset": "demo data", "deleted": plan.delete_counts}, ensure_ascii=False),
            )

    return dict(sorted(deleted.items()))


def delete_collected_media(files: Iterable[tuple[object, str]]) -> tuple[int, list[str]]:
    from pathlib import Path
    from urllib.parse import unquote
    from django.conf import settings
    from django.db.models import CharField, TextField, JSONField

    deleted = 0
    failures: list[str] = []
    # FileFields are not the only way a CMS can reference a media: rich text
    # and JSON content must be checked too. Uncertainty means preservation.
    references = []
    for model in apps.get_models():
        if not model._meta.managed or model._meta.proxy:
            continue
        fields = [field.name for field in model._meta.fields
                  if isinstance(field, (FileField, CharField, TextField, JSONField))]
        if fields:
            references.extend(unquote(str(row)) for row in model.objects.values_list(*fields))
    roots = [Path(settings.MEDIA_ROOT).resolve(), (Path(settings.BASE_DIR) / "private_media").resolve()]
    seen = set()
    for storage, name in files:
        try:
            path = Path(storage.path(name)).resolve()
            if path in seen:
                continue
            seen.add(path)
            if not any(path.is_relative_to(root) and path != root for root in roots):
                failures.append(f"{name}: hors des répertoires médias autorisés")
                continue
            if any(name in reference or path.name in reference for reference in references):
                failures.append(f"{name}: encore référencé, conservé")
                continue
            if storage.exists(name):
                storage.delete(name)
                deleted += 1
        except (OSError, NotImplementedError) as exc:
            failures.append(f"{name}: {exc}")
    return deleted, failures
