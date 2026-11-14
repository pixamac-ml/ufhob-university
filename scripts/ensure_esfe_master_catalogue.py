"""Create only missing ESFé Master catalogue rows confirmed by the user.

Default is a read-only plan; --apply adds programmes and curriculum years only.
It never installs fees, classes, semesters, UE, EC or admission requirements.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.conf import settings
from django.db import connection, transaction
from formations.models import Cycle, Diploma, Filiere, Programme, ProgrammeYear
from core.models import School

EXPECTED = (
    "Biologie Médicale", "Gynécologie Obstétrique", "Manager en Santé",
    "Pédagogie en Santé", "Épidémiologie", "Nutrition", "Santé Environnementale",
)


def normalized(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    value = re.sub(r"[^a-z0-9]+", " ", value).strip()
    return re.sub(r"^(?:cycle superieur master|cycle master|master professionnel en|master en|master)\s*", "", value).strip()


def candidates(title, programmes, cycle):
    key = normalized(title)
    aliases = {
        "manager en sante": {"management des services de sante", "management en sante"},
        "pedagogie en sante": {"pedagogie des sciences de la sante", "pedagogie en sciences de la sante"},
        "nutrition": {"nutrition et science alimentaire", "nutrition et sciences alimentaires", "nutrition dietetique"},
    }
    keys = {key} | aliases.get(key, set())
    found = []
    from difflib import SequenceMatcher
    for programme in programmes:
        # A Licence with the same title never satisfies a Master requirement.
        is_master = programme.cycle_id == cycle.pk or "master" in programme.cycle.name.lower()
        if not is_master:
            continue
        name = normalized(programme.title)
        if name in keys or any(SequenceMatcher(None, name, alias).ratio() >= .88 for alias in keys):
            found.append(programme)
    return found


def execute(apply=False):
    if settings.DATABASES["default"]["NAME"] != "ufhob_db":
        raise RuntimeError("This operation is restricted to ufhob_db.")
    with transaction.atomic():
        with connection.cursor() as cursor:
            if not apply:
                cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != "ufhob_db":
                raise RuntimeError("Connected database is not ufhob_db.")
            if apply:
                # Serialize this catalogue operation and prevent a concurrent insert.
                cursor.execute("LOCK TABLE formations_programme IN SHARE ROW EXCLUSIVE MODE")
        school = School.objects.get(short_name__iexact="ESFé Sup")
        cycle = Cycle.objects.get(name__iexact="Master")
        diploma = Diploma.objects.get(name__iexact="Master")
        filiere = Filiere.objects.get(name__iexact="Sciences de la Santé")
        programmes = list(Programme.objects.select_related("cycle", "diploma_awarded", "school"))
        plan = []
        for title in EXPECTED:
            matches = candidates(title, programmes, cycle)
            if len(matches) > 1:
                raise RuntimeError(f"Ambiguous Master candidates for {title}: {[p.pk for p in matches]}")
            programme = matches[0] if matches else None
            if programme and (programme.school_id != school.pk or programme.diploma_awarded_id != diploma.pk):
                raise RuntimeError(f"Existing candidate #{programme.pk} needs school/diploma review; no duplicate will be created.")
            row = {"formation": title, "programme_id": programme.pk if programme else None,
                   "cycle": cycle.name, "diploma": diploma.name, "school": school.short_name,
                   "programme_action": "EXISTS" if programme else "CREATE",
                   "year_actions": {}}
            if apply and programme is None:
                programme = Programme(
                    title=f"Master — {title}", school=school, cycle=cycle,
                    diploma_awarded=diploma, filiere=filiere, duration_years=2,
                    short_description=f"Cycle supérieur Master — {title} : 1re et 2e année.",
                    description=f"Formation {title}, cycle supérieur Master, 1re et 2e année, confirmée par la fiche institutionnelle communiquée le 8 octobre 2026.",
                    # Catalogue verification does not authorize public admissions.
                    is_public=False, admissions_open=False,
                )
                programme.full_clean(exclude=["slug"])
                programme.save()
                programmes.append(programme)
                row["programme_id"] = programme.pk
            for number in (1, 2):
                existing = programme.years.filter(year_number=number).first() if programme else None
                row["year_actions"][str(number)] = {"action": "EXISTS" if existing else "CREATE", "id": existing.pk if existing else None}
                if apply and existing is None:
                    year = ProgrammeYear(programme=programme, year_number=number)
                    year.full_clean()
                    year.save()
                    row["year_actions"][str(number)]["id"] = year.pk
            plan.append(row)
        return {"database": "ufhob_db", "apply": apply, "expected": 7, "rows": plan}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = execute(args.apply)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + "\n", encoding="utf-8")
    print(output)
