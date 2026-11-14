"""Scoped, additive installation of the seven institutional ESF Sup Masters.

SchoolBranch supplies campus availability. ProgrammeYear supplies curriculum
years; AcademicClass additionally requires a campus and an AcademicYear.
Missing EC credits/coefficients never receive inferred defaults.
"""

import json
from pathlib import Path
import re
import unicodedata
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from academics.models import AcademicClass, AcademicYear, EC, Semester, UE
from core.models import School, SchoolBranch
from formations.models import Cycle, Diploma, Filiere, Programme, ProgrammeYear

EXPECTED = (
    "Biologie Médicale", "Gynécologie Obstétrique", "Manager en Santé",
    "Pédagogie en Santé", "Épidémiologie", "Nutrition", "Santé Environnementale",
)
MANIFEST = Path(settings.BASE_DIR) / "docs/esf_sup_master_matrix_sources.json"


def normalize(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def programme_key(value):
    return re.sub(r"^master(?: professionnel)?(?: en)?\s+", "", normalize(value))


def find_school(*, lock=False):
    queryset = School.objects.select_for_update() if lock else School.objects.all()
    matches = [s for s in queryset if
               normalize(s.short_name) in {"esf sup", "esfe sup"}
               or normalize(s.code) in {"esfe", "esf sup", "esv"}]
    if len(matches) != 1:
        raise ValidationError(f"ESF Sup : {len(matches)} écoles candidates ; aucune création autorisée.")
    return matches[0]


def one_reference(model, labels):
    matches = [x for x in model.objects.all() if normalize(x.name) in labels]
    if len(matches) != 1:
        raise ValidationError(f"{model.__name__} : référence absente ou multiple.")
    return matches[0]


def load_manifest():
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


@transaction.atomic
def install_masters(*, apply=False, manifest=None):
    manifest = load_manifest() if manifest is None else manifest
    school = find_school(lock=apply)
    cycle = one_reference(Cycle, {"master", "cycle master", "cycle superieur master"})
    diploma = one_reference(Diploma, {"master"})
    filiere = one_reference(Filiere, {"sciences de la sante"})
    if not school.is_active or not cycle.is_active or not filiere.is_active:
        raise ValidationError("École, cycle et filière doivent être actifs ; aucune réactivation implicite.")
    if {x["formation"] for x in manifest["programmes"]} != set(EXPECTED):
        raise ValidationError("Le manifeste doit contenir exactement les sept Masters confirmés.")

    counts = dict.fromkeys(("schools", "programmes", "programme_years", "campus_relations",
                           "school_branches", "classes", "semesters", "ues", "ecs"), 0)
    updates = {"school_label": 0, "public_programmes": 0, "administrative_descriptions_removed": 0}
    result = {"apply": apply, "school_id": school.pk, "school_code": school.code,
              "created": counts, "updated": updates, "rows": [], "blockers": []}
    if school.short_name != "ESFé Sup":
        updates["school_label"] += 1
        if apply:
            school.short_name = "ESFé Sup"
            school.save(update_fields=["short_name", "updated_at"])

    presences = list(SchoolBranch.objects.filter(
        school=school, is_active=True, branch__is_active=True,
    ).select_related("branch"))
    years = list(AcademicYear.objects.filter(is_active=True))
    year = years[0] if len(years) == 1 else None
    if not presences:
        result["blockers"].append("NO_ACTIVE_SCHOOL_CAMPUS: fournir le campus autorisé pour ESF Sup.")
    if year is None:
        result["blockers"].append(f"ACTIVE_ACADEMIC_YEAR_COUNT={len(years)}: année et dates à confirmer.")

    programme_queryset = Programme.objects.select_related("cycle", "school", "diploma_awarded")
    if apply:
        programme_queryset = programme_queryset.select_for_update(of=("self",))
    programmes = list(programme_queryset)
    aliases = {
        "manager en sante": {"management des services de sante", "management en sante"},
        "pedagogie en sante": {"pedagogie des sciences de la sante", "pedagogie en sciences de la sante"},
        "nutrition": {"nutrition dietetique", "nutrition et science alimentaire"},
    }
    from difflib import SequenceMatcher
    for source in manifest["programmes"]:
        title = source["formation"]
        for matrix in source["semesters"]:
            if matrix["confidence"] == "AMBIGUOUS":
                continue
            if all(unit.get("credits") is not None for unit in matrix["ues"]):
                total = sum(Decimal(str(unit["credits"])) for unit in matrix["ues"])
                total += Decimal(str(matrix.get("unallocated_stage_credits", 0)))
                if total != Decimal(str(matrix["credits"])):
                    raise ValidationError(f"SOURCE_CONFLICT {title}/S{matrix['number']} : somme crédits UE et stages documentés != semestre.")
        keys = {normalize(title)} | aliases.get(normalize(title), set())
        candidates = [p for p in programmes if p.cycle_id == cycle.pk and
                      any(programme_key(p.title) == key or SequenceMatcher(None, programme_key(p.title), key).ratio() >= .88 for key in keys)]
        if len(candidates) > 1:
            raise ValidationError(f"Master {title} : programmes multiples {[p.pk for p in candidates]}.")
        programme = candidates[0] if candidates else None
        if programme and (programme.school_id != school.pk or programme.diploma_awarded_id != diploma.pk):
            raise ValidationError(f"Master {title} #{programme.pk} : école/diplôme divergent, pas de doublon ni déplacement.")
        row = {"formation": title, "school": "ESFé Sup", "cycle": cycle.name,
               "programme_id": programme.pk if programme else None,
               "programme_found": programme is not None,
               "campus_relations": [p.branch_id for p in presences],
               "schoolbranch_relations": [p.pk for p in presences],
               "academic_year": year.name if year else None, "programme_years": [],
               "classes": [], "matrices": [], "actions": []}
        if programme is None:
            counts["programmes"] += 1
            row["actions"].append("CREATE_PROGRAMME")
            if apply:
                programme = Programme(
                    title=f"Master — {title}", school=school, cycle=cycle,
                    filiere=filiere, diploma_awarded=diploma, duration_years=2,
                    short_description=f"Master — {title} · 1re et 2e année.",
                    description="", is_public=True, admissions_open=False,
                )
                programme.full_clean(exclude=["slug", "description"])
                programme.save()
                programmes.append(programme)
                row["programme_id"] = programme.pk
        elif not programme.is_active or programme.is_archived:
            raise ValidationError(f"Programme #{programme.pk} inactif/archivé : décision requise.")
        else:
            row["actions"].append("KEEP")
            fields = []
            if not programme.is_public:
                updates["public_programmes"] += 1
                row["actions"].append("FIX_PUBLIC_VISIBILITY")
                if apply:
                    programme.is_public = True
                    fields.append("is_public")
            # These seven descriptions were administrative provenance from the
            # previous audit, not institutionally supplied presentation copy.
            if programme.description == f"Formation {title}, cycle supérieur Master, 1re et 2e année, confirmée par la fiche institutionnelle communiquée le 8 octobre 2026.":
                updates["administrative_descriptions_removed"] += 1
                if apply:
                    programme.description = ""
                    fields.append("description")
            if fields:
                programme.save(update_fields=fields + ["updated_at"])
        for number in (1, 2):
            cursus = programme.years.filter(year_number=number).first() if programme else None
            if cursus is None:
                counts["programme_years"] += 1
                if apply:
                    cursus = ProgrammeYear.objects.create(programme=programme, year_number=number)
            row["programme_years"].append({"number": number, "id": cursus.pk if cursus else None})

        if year:
            for presence in presences:
                for number in (1, 2):
                    level = f"M{number}"
                    classes = list(AcademicClass.objects.filter(
                        programme=programme, branch=presence.branch, academic_year=year,
                    )) if programme else []
                    level_aliases = {f"m{number}", f"master {number}", f"{number}re annee", f"{number}ere annee", f"{number}e annee", f"{number} annee", "premiere annee" if number == 1 else "deuxieme annee"}
                    matches = [c for c in classes if normalize(c.level) in level_aliases]
                    if len(matches) > 1:
                        raise ValidationError(f"Classes {title}/{level}/{presence.branch.name} multiples ; aucune suppression.")
                    academic_class = matches[0] if matches else None
                    if academic_class and (academic_class.is_archived or not academic_class.is_active):
                        raise ValidationError(f"Classe #{academic_class.pk} inactive : décision requise.")
                    if academic_class is None:
                        counts["classes"] += 1
                        row["actions"].append("CREATE_CLASS")
                        if apply:
                            academic_class = AcademicClass(
                                programme=programme, branch=presence.branch, academic_year=year,
                                level=level, name=f"{level} — {title}", study_level="MASTER",
                                # No validation policy is inferred from another curriculum.
                                validation_threshold=None,
                            )
                            academic_class.full_clean()
                            academic_class.save()
                    row["classes"].append({"year": number, "campus": presence.branch.name, "id": academic_class.pk if academic_class else None})
                    for matrix in source["semesters"]:
                        if matrix["year"] != number:
                            continue
                        entry = {"campus": presence.branch.name, **matrix, "imported": False, "missing": []}
                        row["matrices"].append(entry)
                        if matrix["confidence"] == "AMBIGUOUS":
                            entry["missing"].append("AMBIGUOUS_SOURCE_NOT_IMPORTED")
                            continue
                        semester = Semester.objects.filter(academic_class=academic_class, number=matrix["number"]).first() if academic_class else None
                        if semester and semester.total_required_credits != Decimal(str(matrix["credits"])):
                            raise ValidationError(f"SOURCE_CONFLICT semestre #{semester.pk} : crédits différents.")
                        if semester is None:
                            counts["semesters"] += 1
                            row["actions"].append("CREATE_SEMESTER")
                            if apply:
                                semester = Semester(academic_class=academic_class, number=matrix["number"], total_required_credits=Decimal(str(matrix["credits"])))
                                semester.full_clean()
                                semester.save()
                        for unit in matrix["ues"]:
                            ue = UE.objects.filter(semester=semester, code=unit["code"]).first() if semester else None
                            if ue and ue.title != unit["title"]:
                                raise ValidationError(f"SOURCE_CONFLICT UE #{ue.pk} : intitulés différents, aucun écrasement.")
                            if ue is None:
                                counts["ues"] += 1
                                row["actions"].append("IMPORT_MATRIX")
                                if apply:
                                    ue = UE(semester=semester, code=unit["code"], title=unit["title"])
                                    ue.full_clean()
                                    ue.save()
                            # UE credit/coef are computed from EC in the real
                            # model. Preserve source totals in the manifest;
                            # never invent an EC to make those properties match.
                            elements = unit.get("ecs", [])
                            if not elements or any(e.get("credits") is None or e.get("coefficient") is None for e in elements):
                                entry["missing"].append(f"{unit['code']}: EC_CREDIT_OR_COEFFICIENT_SOURCE_MISSING")
                                continue
                            credit_sum = sum(Decimal(str(e["credits"])) for e in elements)
                            coefficient_sum = sum(Decimal(str(e["coefficient"])) for e in elements)
                            if unit.get("credits") is not None and credit_sum != Decimal(str(unit["credits"])):
                                raise ValidationError(f"SOURCE_CONFLICT {unit['code']} : somme crédits EC != UE.")
                            if unit.get("coefficient") is not None and coefficient_sum != Decimal(str(unit["coefficient"])):
                                raise ValidationError(f"SOURCE_CONFLICT {unit['code']} : somme coefficients EC != UE.")
                            # Existing shared governance constraints remain in
                            # force; a source exceeding them needs a domain change.
                            if credit_sum > Decimal("6"):
                                entry["missing"].append(f"{unit['code']}: MODEL_UE_CREDIT_LIMIT_6")
                                continue
                            for element in elements:
                                ecs = list(EC.objects.filter(ue=ue, title=element["title"])) if ue else []
                                if len(ecs) > 1:
                                    raise ValidationError(f"SOURCE_CONFLICT EC {element['title']} en doublon.")
                                ec = ecs[0] if ecs else None
                                credits = Decimal(str(element["credits"]))
                                coefficient = Decimal(str(element["coefficient"]))
                                if ec and (ec.credit_required != credits or ec.coefficient != coefficient):
                                    raise ValidationError(f"SOURCE_CONFLICT EC #{ec.pk} : valeurs différentes.")
                                if ec is None:
                                    prospective = EC(ue=ue, title=element["title"], credit_required=credits, coefficient=coefficient)
                                    if apply:
                                        prospective.full_clean()
                                        prospective.save()
                                    counts["ecs"] += 1
                        entry["imported"] = bool(apply)
        row["public_visible"] = bool(programme and (apply or programme.is_public))
        row["ue_count"] = UE.objects.filter(semester__academic_class__programme=programme).count() if programme else 0
        row["ec_count"] = EC.objects.filter(ue__semester__academic_class__programme=programme).count() if programme else 0
        result["rows"].append(row)
    return result
