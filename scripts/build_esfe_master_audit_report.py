"""Render the documentary findings of the 2026-10-08 audit; no database writes."""

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
applied = json.loads((ARTIFACTS / "audit_masters_catalogue_applied_20261008.json").read_text(encoding="utf-8"))
selected = json.loads((ARTIFACTS / "audit_masters_ooas_selected_pages_20261008.json").read_text(encoding="utf-8"))
OOAS = "Master maquette/DOC-20260423-WA0041..pdf"
BIO = "Master maquette/MPro -BIO bon.pdf"

# Each numeric series below is transcribed from a source, never assigned to EC.
COMMON = {
    "pages": [11, 12], "semesters": [1, 2],
    "ues": {"S1": ["MSS411", "SEP412", "GDS413", "BEB414"], "S2": ["ISP421", "SPP422", "CIA423", "MdR424"]},
    "credits": "S1 : UE 15/4/6/5, total 30. S2 : UE 7/7/11/3, total 28 enseignements + 2 stage. Répartition EC absente.",
    "coefficients": "S1 : UE 5/4/4/4 ; S2 : UE 3/3/4/2. Coefficients EC absents.",
}
SPECIAL = {
    "Gynecologie M2": {
        "ues": {"S3": ["PSN531", "SRM532", "SRN533", "SRJ534", "DSR535"], "S4": ["MFE541"]},
        "credits": "S3 : UE 7/4/3/3/8, total 25 + 5 stage ; S4 : 24 + 6 stage. Répartition EC absente.",
        "coefficients": "S3 : PSN 4, SRM 3, SRJ 3, DSR 4 ; SRN non lisible dans extraction, ne pas déduire du total 15. S4 : UE 5. Coefficients EC absents.",
    },
    "Manager M2": {
        "ues": {"S3": ["FTM531", "FDM532", "GRH533", "GFM534", "EMP535"], "S4": ["MFE541"]},
        "credits": "S3 : UE 2/9/3/9/5, total 28 ; note stage 90 h, 45 x 2, mais texte 6 crédits : incohérence. S4 : 24 + 6 stage. Répartition EC absente.",
        "coefficients": "S3 : seconde série 1/4/1/4/3, total 13 ; en-tête ECUE/UE incohérent, statut coefficient à confirmer. S4 : UE 5. Coefficients EC absents.",
    },
    "Pedagogie M2": {
        "ues": {"S3": ["FSP531", "EPF532", "PEA533", "MEA534", "EDS535"], "S4": ["MFE541"]},
        "credits": "S3 : UE 3/6/6/6/4, total 25 ; stage 225 h, note 4 crédits mais calcul 45 x 5. S4 : 30, note 24 + 6 stage. Répartition EC absente.",
        "coefficients": "S3 : UE 2/4/2/4/3. S4 : UE 5 mais total 30, contradiction. Coefficients EC absents.",
    },
    "Epidemiologie M2": {
        "ues": {"S3": ["FTE531", "QME532", "TEE533", "RAE534", "GEC535", "GDE536"], "S4": ["MFE541"]},
        "credits": "S3 : UE 3/3/6/5/6/7, total 30 ; S4 : total 30, note 24 + 6 stage, cellule crédit UE peu claire. Répartition EC absente.",
        "coefficients": "S3 : UE 2/2/4/4/4/4. S4 : 30 affiché et total 30, contrôler visuellement. Coefficients EC absents.",
    },
    "Nutrition M2": {
        "ues": {"S3": ["NUC531", "NSA532", "IAN533", "SEI534", "CSS535"], "S4": ["MFE541"]},
        "credits": "S3 : UE 4/7/8/5/6 (CSS535 comprend stage), total 26 + 4 stage. S4 : UE 30, total 24 + 6 stage. Excel S4 candidat : EC 4/6/20.",
        "coefficients": "S3 : UE 2/3/3/2/2. S4 PDF : UE 5 ; Excel candidat : UE 30, EC 4/6/20. Versions différentes.",
    },
    "Sante environnementale candidate M2": {
        "ues": {"S3": ["FST531", "TEP532", "SPS533", "PTE534", "LDS535", "SPR536"], "S4": ["MFE541"]},
        "credits": "CANDIDATE SST uniquement : S3 UE 2/7/4/2/5/7, total 27 + 3 stage ; S4 : 24 + 6 stage. Équivalence au Master exact non prouvée.",
        "coefficients": "CANDIDATE SST : S3 seconde série 1/4/2/1/3/4 ; S4 UE 5 mais total 30. Coefficients EC absents.",
    },
}
SPECIAL_KEYS = [None, "Gynecologie M2", "Manager M2", "Pedagogie M2", "Epidemiologie M2", "Nutrition M2", "Sante environnementale candidate M2"]

# Biologie: actual discipline names and their credits, pages 13–18.
BIO_BLOCKS = {
    1: [
        ("MBIO111", 9, [("Maintenance biomédicale", 2), ("Métrologie", 1), ("Management de la qualité", 2), ("Gestion des laboratoires", 4)]),
        ("MBIO112", 6, [("Entomologie appliquée", 2.5), ("Changements climatiques", 1.5), ("Santé environnementale", 2)]),
        ("MBIO113", 10.5, [("Pédagogie", 3), ("Législation de travail", 1.5), ("Genre et leadership", 1), ("Anglais technique", 2), ("Informatique", 3)]),
        ("MBIO114", 4.5, [("Biostatistique", 3.5), ("Épidémiologie appliquée", 1)]),
    ],
    2: [
        ("MBIO121", 15.5, [("Bactériologie I", 3), ("Virologie I", 2), ("Parasitologie I", 3), ("Biochimie I", 2), ("Immunologie I", 2.5), ("Hématologie I", 2), ("Immunohistochimie/Immunochimie", 1)]),
        ("MBIO122", 5, [("Cytologie et histologie", 1), ("Anatomie pathologie", 1.5), ("Biologie de la reproduction", 1), ("Biologie moléculaire I", 1.5)]),
        ("MBIO123", 3, [("Toxicologie I", 2), ("Pharmacologie", 1)]),
        ("MBIO124", 2, [("Biosécurité/Biosûreté", 2)]),
        ("MBIO125", 4.5, [("Projet de Recherche", 4), ("Éthique et déontologie", 0.5)]),
    ],
    3: [
        ("MBIO231", 20, [("Bactériologie II", 3.5), ("Virologie II", 3.5), ("Parasitologie II", 3.5), ("Biochimie II", 3.5), ("Immunologie II", 2.5), ("Hématologie II", 3.5)]),
        ("MBIO232", 4, [("Hémobiologie", 2), ("Biologie moléculaire II", 2)]),
        ("MBIO233", 4.5, [("Mycologie", 2.5), ("Toxicologie II", 2)]),
        ("MBIO234", 1.5, [("Projet de Recherche", 1.5)]),
    ],
    4: [
        ("MBIO241", 12, [("Bactériologie III", 2), ("Virologie III", 2), ("Parasitologie III", 2), ("Biochimie III", 2), ("Immunologie III", 2), ("Hématologie III", 2)]),
        ("MBIO242", 4, [("Hémobiologie II", 2), ("Biologie moléculaire III", 2)]),
        ("MBIO243", 4, [("Mycologie II", 2), ("Toxicologie III", 2)]),
        ("MBIO244", 10, [("Stage et rédaction du mémoire", 10)]),
    ],
}


def ec_codes(key):
    text = "\n".join(p["text"] for p in selected[key])
    return sorted({re.sub(r"\s+", "", c) for c in re.findall(r"\b([A-Za-z]{3}\s*[45][1-4]\d\d)\b", text)})


rows = []
for index, programme in enumerate(applied["rows"]):
    for year in (1, 2):
        status = "PARTIAL"
        if index == 0:
            semesters = [1, 2] if year == 1 else [3, 4]
            info = {
                "pages": [13, 14, 15, 16] if year == 1 else [17, 18],
                "semesters": semesters,
                "ues": {f"S{s}": [u for u, _, _ in BIO_BLOCKS[s]] for s in semesters},
                "credits": "30 par semestre ; crédits UE et disciplines explicites (détail ci-dessous).",
                "coefficients": "ABSENTS du dossier. Aucune valeur inventée.",
            }
            ecs = {f"S{s}": [{"ue": u, "title": n, "credits": c, "coefficient": None} for u, _, elements in BIO_BLOCKS[s] for n, c in elements] for s in semesters}
            source = BIO
        else:
            key = "M1" if year == 1 else SPECIAL_KEYS[index]
            info = dict(COMMON if year == 1 else SPECIAL[key])
            info["pages"] = [p["page"] for p in selected[key] if not (key == "Pedagogie M2" and p["page"] == 79)]
            info["semesters"] = [1, 2] if year == 1 else [3, 4]
            ecs = ec_codes(key)
            source = OOAS
            if index in (2, 3, 6) or (index == 5 and year == 2):
                status = "AMBIGUOUS"
        row = {
            "FORMATION": programme["formation"], "PROGRAMME_ID": programme["programme_id"],
            "CYCLE": "Master (Cycle #3)", "DIPLOME": "Master (Diploma #3)",
            "NIVEAU": "1re année / M1" if year == 1 else "2e année / M2",
            "PROGRAMME_YEAR_ID": programme["year_actions"][str(year)]["id"],
            "CLASSES FOUND": [], "SOURCE DOCUMENTS FOUND": [{"path": source, "pages": info["pages"]}],
            "SEMESTERS FOUND": {"database": [], "source": info["semesters"]},
            "UE FOUND": {"database": [], "source": info["ues"]},
            "EC FOUND": {"database": [], "source": ecs},
            "CREDITS FOUND": info["credits"], "COEFFICIENTS FOUND": info["coefficients"], "STATUS": status,
        }
        if index == 5 and year == 2:
            row["SOURCE DOCUMENTS FOUND"].append({"path": "Master maquette/odonto/réleve s4 odonto.xlsx", "sheet": "Feuil1", "note": "En-tête Nutrition mais nom odonto : attribution non certifiée ; S4 uniquement."})
        if index == 4:
            row["SOURCE DOCUMENTS FOUND"].append({"path": "SITE/UPFHOB/AMAQ 2024/UFHOB-MALI/ANNEXES/ANNEXES LIG.docx", "note": "Références historiques dans suppressions suivies, exclues comme maquette validée."})
        rows.append(row)

(ARTIFACTS / "audit_masters_esfe_14_years_20261008.json").write_text(json.dumps({"MASTER PROGRAMMES EXPECTED": 7, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [
    "# Audit des sept Masters ESFé Sup — 8 octobre 2026", "", "**MASTER PROGRAMMES EXPECTED: 7**", "",
    "## État vérifié et intervention", "",
    "Python 3.14.0, environnement virtuel UFHOB, config.settings ; cible et connexion PostgreSQL vérifiées par current_database() = ufhob_db. Avant intervention : 27 programmes, 74 ProgrammeYear, aucune classe, semestre, UE ou EC. Aucun des sept Masters attendus ne figurait dans les programmes, même inactifs ou archivés. Aucune Licence de santé homonyme ne figure dans cette base actuelle ; les rapports historiques ne constituent pas son état actuel.", "",
    "Création ciblée : 7 Programme et 14 ProgrammeYear. Réutilisation de School #4 ESFÉ / ESFé Sup, Cycle #3 Master, Diploma #3 Master (niveau supérieur), Filiere #1 Sciences de la Santé. Titres stockés « Master — [formation] », durée 2 ans. Aucun diplôme spécialisé supplémentaire inventé. Les programmes sont internes (is_public=False, admissions_open=False) pendant la vérification.", "",
    "ProgrammeYear = année de cursus ; ce n’est ni une année universitaire ni une classe. Les campus et années universitaires cibles ne sont pas précisés : aucune classe opérationnelle créée. Aucune classe supprimée, aucune UE/EC, note ou donnée validée modifiée. Les 27 programmes préexistants sont inchangés.", "",
    "| Formation | Programme ID | Cycle / diplôme réel | 1re année ID | 2e année ID | Classes trouvées |",
    "|---|---:|---|---:|---:|---|",
]
for p in applied["rows"]:
    lines.append(f"| {p['formation']} | {p['programme_id']} | Master #3 / Master #3 | {p['year_actions']['1']['id']} | {p['year_actions']['2']['id']} | Aucune, tous campus et années |")
lines += [
    "", "## Sources et précautions", "",
    "Inventaire récursif du dépôt incluant les fichiers ignorés par Git ; lecture textuelle des PDF et XML des DOCX sous SITE, plus Master maquette. Les environnements, dépendances et caches sont exclus. Les reçus et dossiers individuels ne servent pas de maquettes.", "",
    "Aucun dossier Relever/, Relevé/Relevés ou document explicitement identifié UAS trouvé dans l’arborescence actuelle. Les dossiers SITE/EPSFé et SITE/AMAQ 2024 contiennent des arborescences mais aucun fichier actuel. Les quatre relevés disponibles sont ceux de Master maquette/odonto. Le document OOAS/CEDEAO de février 2017 et le dossier Biologie novembre 2019 sont présents.", "",
    "La nouvelle fiche est connue par les intitulés et niveaux communiqués par l’utilisateur. Son original n’a pas été fourni ni retrouvé : aucune prétention à une lecture visuelle de cette fiche. Elle confirme le catalogue selon la consigne, pas les matières. Les licences et les doctorats ne sont jamais extrapolés vers les Masters.", "",
    "Les relevés odonto S1/S2/S3 ne sont pas attribués aux sept Masters : des matières communes ne prouvent pas leur applicabilité. Le S4 est une source candidate Nutrition car l’en-tête nomme Nutrition, mais son nom odonto rend sa provenance ambiguë. Aucun résultat ni identité d’étudiant importé.", "",
    "FILERES RUSTA-UFHOB-MALI.docx et Filières RUSTA.xlsx sont des références de catalogue, pas des maquettes pédagogiques complètes.", "",
    "### Annexes Word avec suppressions suivies", "",
    "ANNEXES LIG, D-FC, DUTIG, L-FC, L-GEA, L-GRH et L-MC, sous SITE/UPFHOB/AMAQ 2024/UFHOB-MALI/ANNEXES, contiennent des références historiques au Master en Épidémiologie et à d’autres formations de santé. Une extraction XML brute lit aussi les textes supprimés. Dans ANNEXES LIG, les tableaux 18–22 portent des lignes w:del et du texte w:delText, avec notamment MGO et FTE2301/MFE2401. Ces versions sont exclues des maquettes validées. Il faut la version finale acceptée ou la maquette approuvée ; le nom d’une annexe technique ou un mot-clé ne suffit pas.", "",
    "## Résultats obligatoires par année", "",
    "Les UE/EC ci-dessous sont des éléments trouvés dans les documents, pas installés en base. PARTIAL : source pertinente mais champs ou validation locale manquants. AMBIGUOUS : correspondance, attribution ou valeurs à départager. COMPLETE exige une maquette exacte et vérifiée ; NO_MATRIX_SOURCE signifie aucune source pertinente. Aucune ligne COMPLETE : aucun inventaire trouvé ne fournit toutes les preuves nécessaires à l’installation.", "",
    "Le tronc commun OOAS M1 est une référence documentée pour la mention Sciences infirmières et obstétricales, pas une attribution automatique à tous les Masters. La Biologie a son propre M1. Manager/Pédagogie demandent confirmation des correspondances d’intitulés ; Santé Environnementale est une option du référentiel dont la spécialité est Santé et sécurité au travail, pas une équivalence prouvée.", "",
    "| FORMATION | CYCLE | NIVEAU | CLASSES FOUND | SOURCE DOCUMENTS FOUND | SEMESTERS FOUND | UE FOUND | EC FOUND | CREDITS FOUND | COEFFICIENTS FOUND | STATUS |",
    "|---|---|---|---|---|---|---|---|---|---|---|",
]
for r in rows:
    source = r["SOURCE DOCUMENTS FOUND"][0]
    label = ("BIO 2019" if source["path"] == BIO else "OOAS 2017") + " p. " + ",".join(map(str, source["pages"]))
    if r["FORMATION"] == "Nutrition" and "M2" in r["NIVEAU"]:
        label += " ; Excel S4 candidat"
    ues = r["UE FOUND"]["source"]
    ecs = r["EC FOUND"]["source"]
    ec_count = sum(len(v) for v in ecs.values()) if isinstance(ecs, dict) else len(ecs)
    sem = "/".join(f"S{s}" for s in r["SEMESTERS FOUND"]["source"])
    lines.append(f"| {r['FORMATION']} | Master / Master | {r['NIVEAU']} | 0 | {label} | source {sem} ; base 0 | {sum(len(v) for v in ues.values())} source ; base 0 | {ec_count} source ; base 0 | {r['CREDITS FOUND']} | {r['COEFFICIENTS FOUND']} | {r['STATUS']} |")
lines += ["", "Les pages sont physiques PDF. Le JSON associé donne les 14 lignes, identifiants, sources et codes. Les codes source erronés ou atypiques restent signalés, sans correction silencieuse.", "", "## Inventaire des UE/EC documentaires", ""]
for key, info in [("M1", COMMON), *SPECIAL.items()]:
    lines += [f"### {key}", "", "UE : " + " ; ".join(s + " : " + ", ".join(us) for s, us in info["ues"].items()), "", "ECUE : " + ", ".join(ec_codes(key)), "", info["credits"], "", info["coefficients"], ""]
lines += ["### Biologie Médicale — crédits par discipline", "", "Aucun coefficient de notation explicite identifié. Les crédits ci-dessous viennent du dossier, sans assimiler crédit et coefficient.", "", "| Semestre | UE | Crédits UE | Disciplines et crédits |", "|---|---|---:|---|"]
for semester, blocks in BIO_BLOCKS.items():
    for code, credits, elements in blocks:
        lines.append(f"| S{semester} | {code} | {credits:g} | " + " ; ".join(f"{n} : {c:g}" for n, c in elements) + " |")
lines += [
    "", "M1 : 9 UE, 30 disciplines ; M2 : 8 UE, 22 disciplines. Les titres UE S4 diffèrent entre structuration (VI/VII/VIII) et tableaux (III/IV/V). Les volumes et objectifs figurent dans les extraits sources. Les règles de validation diffèrent entre Biologie (10/20) et OOAS (12/20) ; aucune règle du moteur modifiée.", "",
    "## Documents précisément nécessaires", "",
    "1. Original daté de la fiche institutionnelle des sept Masters, et libellés du diplôme délivré par formation si le diplôme générique Master doit être précisé.",
    "2. Biologie Médicale M1/M2 : grille officielle des coefficients EC de S1 à S4 ; confirmation que MPro-BIO 2019 est la version applicable, avec clarification des titres S4.",
    "3. Tronc commun M1 : maquette locale approuvée S1/S2 avec crédits et coefficients EC, stages compris, et liste explicite des formations concernées. Une pièce commune suffit si elle confirme les cinq/six parcours concernés ; les Excel odontologie ne constituent pas cette preuve.",
    "4. Gynécologie Obstétrique M2 : grille S3/S4 par EC et stages ; confirmation du coefficient SRN533 et des codes EC atypiques.",
    "5. Manager en Santé M2 : attestation de correspondance avec Management des services de santé ; grille EC S3/S4 ; clarification de l’en-tête et de la note stage 90 h / 6 crédits / 45 x 2.",
    "6. Pédagogie en Santé M2 : attestation de correspondance avec Pédagogie des sciences de la santé ; grille EC S3/S4 ; correction approuvée du stage 225 h annoncé 4 crédits (calcul 5), et coefficient S4 UE 5 contre total 30.",
    "7. Épidémiologie M1/M2 : version finale acceptée des maquettes S1–S4/rapport ou maquette locale explicitement approuvée ; grille par EC et confirmation des valeurs S4. Les suppressions suivies des annexes techniques ne suffisent pas.",
    "8. Nutrition M2 : modèle certifié S3/S4 ; confirmation de provenance du classeur nommé odonto à en-tête Nutrition ; grille départageant PDF S4 (UE coefficient 5) et Excel (UE 30 ; EC 4/6/20). Le classeur confirmé compléterait S4 uniquement.",
    "9. Santé Environnementale M1/M2 : maquette exacte S1–S4 ; si le parcours est Santé et sécurité au travail, attestation explicite de cette spécialité et grille EC approuvée. Une spécialité voisine ne suffit pas.",
    "10. Liste des campus et années universitaires où ouvrir les classes M1/M2, avec leurs libellés. Les deux ProgrammeYear déjà créés ne remplacent pas ces classes.",
    "11. Sources Relever/ et UAS pour les sept Masters si elles sont les références à appliquer : elles ne sont pas présentes actuellement. Aucun relevé Licence ne peut compléter une année Master.", "",
    "Inutile de fournir une nouvelle copie de OOAS 2017 ou MPro-BIO 2019 déjà lus ; les pièces demandées comblent les lacunes ou départagent les variantes.", "",
    "## Architecture et contrôles", "",
    "Modèles et services inspectés : School/SchoolBranch ; Programme/Cycle/Diploma/ProgrammeYear ; AcademicClass/Semester/UE/EC ; programme_structure_service ; anciennes commandes de catalogue et rapport institutionnel. Un moteur partagé est conservé. Le programme appartient à ESFé Sup ; le campus d’une future classe doit respecter SchoolBranch.", "",
    "Les validations UE/EC et le service de structure plafonnent actuellement les crédits à 6 ; cela bloque notamment MSS411=15, MBIO231=20 et des mémoires=30. EC impose aussi crédit >= coefficient. Aucune règle contournée ; aucune répartition UE→EC inventée. L’extension du moteur n’est pas réalisée dans cette mission de catalogue et de vérification.", "",
    "Script ajouté : scripts/ensure_esfe_master_catalogue.py. Lecture seule par défaut ; --apply ajoute uniquement les programmes et cursus absents. Matching accents/casse/ponctuation, alias et petites variantes, recherche Master distincte de Licence ; multiples candidats ou école/diplôme divergent arrêtent la transaction. Aucun bootstrap global, tarif, frais, classe, admission ni note ajouté.", "",
    "Validation : simulation, application puis nouvelle simulation (7 programmes et 14 années EXIST, aucune création supplémentaire proposée). Contrôle réel : 34 programmes, 88 ProgrammeYear ; 27 programmes antérieurs identiques ; classes/semestres/UE/EC toujours 0. Les niveaux créés sont #125 à #138, programmes #51 à #57.", "",
    "Vérifications ciblées du matching exécutées avec succès : normalisation accents/casse/préfixes/tirets, correspondance Gynécologie-Obstetrique et exclusion d’une Licence homonyme. Classeur artifacts/audit_sept_masters_esfe_sup_20261008.xlsx : 14 lignes et tous les champs demandés ; aucune note d’étudiant.", "",
    "python manage.py check : réussi, aucune anomalie. python manage.py makemigrations --check --dry-run : réussi, No changes detected. Aucune migration créée ou appliquée. Messages Windows GLib/UWP sans échec Django. Suites de tests générales non exécutées : contrôle ciblé des écritures réelles et intégrité du catalogue ; aucun moteur métier modifié. Vérification visuelle intégrale des tableaux non réalisée : champs peu clairs signalés pour contrôle avant import.", "",
    "Fichiers ajoutés : les deux scripts, ce rapport et les artefacts d’inventaire, lecture de base, plan/application/vérification, intégrité, extraits OOAS/Biologie, tableaux historiques Word et 14 lignes structurées dans artifacts/. Les modifications préexistantes ont été préservées.", "",
    "esfe-core : non touché. esfe_db : non touchée. ufhob_db : +7 Programme, +14 ProgrammeYear uniquement. Aucun secret ni résultat nominatif intégré au tableau final.", "",
]
(ROOT / "docs/audit_sept_masters_esfe_sup_20261008.md").write_text("\n".join(lines), encoding="utf-8")
assert len(rows) == 14
assert all(r["PROGRAMME_ID"] and r["PROGRAMME_YEAR_ID"] for r in rows)
print("Written: audit_sept_masters_esfe_sup_20261008.md; 14 year rows")
