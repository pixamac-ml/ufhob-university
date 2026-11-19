#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Seed idempotent du catalogue académique UFHOB réel.

Crée ou met à jour (get_or_create / update_or_create) :
- les cycles académiques
- les filières / disciplines
- les diplômes
- les Programmes ESMED / FATEC / ESGA
- les années, frais et faits rapides des programmes
- les documents requis pour l'admission
- les liens School ↔ Branch (Moribabougou)
- les partenaires institutionnels
- les coordonnées institutionnelles

Une seconde exécution ne crée aucun doublon.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Seed du catalogue académique UFHOB (ESMED, FATEC, ESGA)"

    def handle(self, *args, **kwargs):
        self.stdout.write("Seed catalogue UFHOB...")

        from django.db import transaction
        from core.models import Institution, School, Partner, SchoolBranch
        from branches.models import Branch
        from formations.models import (
            Cycle,
            Diploma,
            Filiere,
            Fee,
            Programme,
            ProgrammeQuickFact,
            ProgrammeRequiredDocument,
            ProgrammeYear,
            RequiredDocument,
        )

        institution = Institution.objects.first()
        branch_moribabougou = Branch.objects.filter(name="Moribabougou").first()

        # =====================================================
        # 1. INSTITUTION — coordonnées publiques
        # =====================================================
        if institution:
            institution.address = "Moribabougou"
            institution.city = "Bamako"
            institution.country = "Mali"
            institution.phone = "+223 95 33 75 01"
            institution.email = "contact@univ-fhb-mali.org"
            institution.short_name = "UFHOB"
            institution.legal_status = (
                "Université privée d'enseignement supérieur agréée par les autorités compétentes "
                "de la République du Mali."
            )
            institution.save()
            self.stdout.write("  OK Coordonnées institutionnelles mises à jour")

        # =====================================================
        # 2. SCHOOLS — noms institutionnels complets
        # =====================================================
        SCHOOL_NAMES = {
            "ESMED": "École des Sciences Médicales Félix Houphouët Boigny",
            "FATEC": "Faculté des Technologies Appliquées Cheick Modibo Diarra",
            "ESGA": "École Supérieure de Gestion Alassane Dramane Ouattara",
        }

        schools_by_code = {}
        SCHOOL_DISPLAY_NAMES = {"ESMED": "ESMed", "ESGA": "ESGA", "FATEC": "FATEC"}
        for code, official in SCHOOL_NAMES.items():
            school, _ = School.objects.update_or_create(
                code=code,
                defaults={
                    "official_name": official,
                    "short_name": SCHOOL_DISPLAY_NAMES[code],
                    "is_active": True,
                },
            )
            schools_by_code[code] = school
            self.stdout.write(f"  OK School {code}")

        # =====================================================
        # 3. SCHOOLBRANCH — Moribabougou
        # =====================================================
        if branch_moribabougou:
            for code, school in schools_by_code.items():
                sb, _ = SchoolBranch.objects.get_or_create(
                    school=school,
                    branch=branch_moribabougou,
                    defaults={"is_active": True},
                )
            self.stdout.write("  OK Liaisons School <-> Moribabougou")

        # =====================================================
        # 4. CYCLES
        # =====================================================
        CYCLES = {
            "DUT": (2, 2, "accent"),
            "Licence": (3, 3, "accent"),
            "Master": (2, 2, "secondary"),
            "Doctorat": (5, 7, "dark"),
        }

        cycles_by_name = {}
        for name, (min_y, max_y, theme) in CYCLES.items():
            cycle, _ = Cycle.objects.get_or_create(
                name=name,
                defaults={
                    "min_duration_years": min_y,
                    "max_duration_years": max_y,
                    "theme": theme,
                    "is_active": True,
                },
            )
            cycles_by_name[name] = cycle

        # =====================================================
        # 5. DIPLÔMES
        # =====================================================
        DIPLOMAS = {
            "DUT": "Diplôme Universitaire de Technologie",
            "Licence": "Licence professionnelle",
            "Master": "Master",
            "Doctorat en Médecine": "Doctorat en Médecine",
            "Doctorat en Pharmacie": "Doctorat en Pharmacie",
            "Doctorat en Chirurgie Dentaire": "Doctorat en Chirurgie Dentaire",
        }

        diplomas_by_name = {}
        for name, diploma_name in DIPLOMAS.items():
            diploma, _ = Diploma.objects.get_or_create(
                name=diploma_name,
                defaults={"level": "superieur"},
            )
            diplomas_by_name[name] = diploma

        # =====================================================
        # 6. FILIÈRES
        # =====================================================
        FILIERES = [
            "Sciences de la Santé",
            "Informatique de Gestion",
            "Génie Logiciel",
            "Réseau et Télécommunication",
            "Audiovisuel Multimédia",
            "Finance / Comptabilité",
            "Gestion des Entreprises et Administration",
            "Gestion des Ressources Humaines",
            "Marketing Communication",
        ]

        filieres_by_name = {}
        for f_name in FILIERES:
            filiere, _ = Filiere.objects.get_or_create(
                name=f_name,
                defaults={"is_active": True},
            )
            filieres_by_name[f_name] = filiere

        # =====================================================
        # 7. DOCUMENTS REQUIS
        # =====================================================
        ESMED_DOCS = [
            "Demande manuscrite adressée au Recteur",
            "Extrait de naissance",
            "Copie légalisée du diplôme",
            "Relevés de notes",
            "Quatre (04) photos d'identité",
            "Certificat médical et visite contre-visite",
        ]

        FATEC_ESGA_DOCS = [
            "Demande timbrée",
            "Copie d'extrait de naissance ou jugement supplétif",
            "Copie légalisée du diplôme requis",
            "Quatre (04) photos d'identité",
        ]

        required_docs = {}
        for doc in ESMED_DOCS + FATEC_ESGA_DOCS:
            obj, _ = RequiredDocument.objects.get_or_create(name=doc)
            required_docs[doc] = obj

        # =====================================================
        # 8. PROGRAMMES — ESMED
        # =====================================================
        esmed_programmes = [
            {
                "title": "Médecine",
                "filiere": "Sciences de la Santé",
                "cycle": "Doctorat",
                "diploma": "Doctorat en Médecine",
                "duration_years": 7,
                "semestres": 14,
                "credits": 420,
                "short": "Doctorat en Médecine",
                "description": (
                    "<p>Le doctorat en médecine forme des médecins autonomes et éthiques, "
                    "experts en diagnostic, traitement et gestion des maladies.</p>"
                    "<p>Il intègre la recherche scientifique à la pratique, prépare à l'évolution "
                    "technologique, encourage une approche centrée sur le patient et renforce "
                    "le leadership dans les systèmes de santé.</p>"
                ),
            },
            {
                "title": "Pharmacie",
                "filiere": "Sciences de la Santé",
                "cycle": "Doctorat",
                "diploma": "Doctorat en Pharmacie",
                "duration_years": 7,
                "semestres": 14,
                "credits": 420,
                "short": "Doctorat en Pharmacie",
                "description": (
                    "<p>Le doctorat en pharmacie forme des professionnels de la santé compétents "
                    "en soins pharmaceutiques et en gestion des médicaments.</p>"
                    "<p>Il allie théorie et pratique, avec un accent sur la recherche, l'éthique "
                    "et l'application clinique. Les diplômés peuvent travailler dans des pharmacies, "
                    "hôpitaux, l'industrie pharmaceutique et la recherche.</p>"
                ),
            },
            {
                "title": "Chirurgie dentaire",
                "filiere": "Sciences de la Santé",
                "cycle": "Doctorat",
                "diploma": "Doctorat en Chirurgie Dentaire",
                "duration_years": 6,
                "semestres": 12,
                "credits": 360,
                "short": "Doctorat en Chirurgie Dentaire",
                "description": (
                    "<p>Le doctorat en chirurgie dentaire prépare des praticiens capables "
                    "d'exercer la médecine bucco-dentaire avec autonomie et rigueur clinique.</p>"
                    "<p>La formation allie sciences fondamentales, pratiques cliniques et éthique "
                    "professionnelle sur six années.</p>"
                ),
            },
        ]

        esmed_fees = {
            "Inscription": 1100000,
            "Scolarité": 1000000,
        }

        with transaction.atomic():
            for p in esmed_programmes:
                programme, _ = Programme.objects.update_or_create(
                    title=p["title"],
                    school=schools_by_code["ESMED"],
                    defaults={
                        "filiere": filieres_by_name[p["filiere"]],
                        "cycle": cycles_by_name[p["cycle"]],
                        "diploma_awarded": diplomas_by_name[p["diploma"]],
                        "duration_years": p["duration_years"],
                        "short_description": p["short"],
                        "description": p["description"],
                        "is_active": True,
                        "is_public": True,
                        "admissions_open": True,
                        "is_archived": False,
                    },
                )

                # Années + frais
                for year in range(1, p["duration_years"] + 1):
                    py, _ = ProgrammeYear.objects.get_or_create(
                        programme=programme,
                        year_number=year,
                    )
                    for label, amount in esmed_fees.items():
                        Fee.objects.get_or_create(
                            programme_year=py,
                            label=label,
                            defaults={"amount": amount, "due_month": "Octobre"},
                        )

                # Quick facts
                facts = [
                    ("Durée", f"{p['duration_years']} ans"),
                    ("Semestres", str(p["semestres"])),
                    ("Crédits", str(p["credits"])),
                    ("Système", "LMD"),
                ]
                for label, value in facts:
                    ProgrammeQuickFact.objects.get_or_create(
                        programme=programme,
                        label=label,
                        defaults={
                            "icon": "academic_cap",
                            "value": value,
                            "order": 0,
                        },
                    )

                # Documents requis
                for doc in ESMED_DOCS:
                    ProgrammeRequiredDocument.objects.get_or_create(
                        programme=programme,
                        document=required_docs[doc],
                    )

                self.stdout.write(f"  OK {programme.title}")

        # =====================================================
        # 9. PROGRAMMES — FATEC / ESGA
        # =====================================================
        FATEC_DOMAINS = [
            ("Informatique de Gestion", "Informatique de Gestion"),
            ("Génie Logiciel", "Génie Logiciel"),
            ("Réseau et Télécommunication", "Réseau et Télécommunication"),
            ("Audiovisuel Multimédia", "Audiovisuel Multimédia"),
        ]

        ESGA_DOMAINS = [
            ("Finance / Comptabilité", "Finance / Comptabilité"),
            ("Gestion des Entreprises et Administration", "Gestion des Entreprises et Administration"),
            ("Gestion des Ressources Humaines", "Gestion des Ressources Humaines"),
            ("Marketing Communication", "Marketing Communication"),
        ]

        SCHOOL_DOMAINS = {
            "FATEC": FATEC_DOMAINS,
            "ESGA": ESGA_DOMAINS,
        }

        # Grilles tarifaires par cycle/année
        fee_schedules = {
            "DUT": [
                {"Inscription": 175000, "Janvier": 100000, "Mars": 100000},
            ],
            "Licence": [
                {"Inscription": 300000, "Janvier": 150000, "Mars": 150000},
            ],
            "Master": [
                {"Inscription": 400000, "Janvier": 175000, "Mars": 175000},  # Année 1
                {"Inscription": 450000, "Janvier": 200000, "Mars": 200000},  # Année 2
            ],
        }

        for school_code, domains in SCHOOL_DOMAINS.items():
            for domain, filiere in domains:
                for cycle_name in ["DUT", "Licence", "Master"]:
                    cycle = cycles_by_name[cycle_name]
                    duration = cycle.min_duration_years

                    title = f"{domain} — {cycle_name}"
                    diploma_key = cycle_name

                    programme, _ = Programme.objects.update_or_create(
                        title=title,
                        school=schools_by_code[school_code],
                        defaults={
                            "filiere": filieres_by_name[filiere],
                            "cycle": cycle,
                            "diploma_awarded": diplomas_by_name[diploma_key],
                            "duration_years": duration,
                            "short_description": f"{domain} – {cycle_name}",
                            "description": (
                                f"<p>Programme {cycle_name} du domaine {domain} proposé par "
                                f"{SCHOOL_NAMES[school_code]}.</p>"
                                f"<p>Objectif : former des professionnels capables d'intervenir "
                                f"dans les métiers liés à {domain}.</p>"
                            ),
                            "is_active": True,
                            "is_public": True,
                            "admissions_open": True,
                            "is_archived": False,
                        },
                    )

                    # Années + frais
                    schedules = fee_schedules[cycle_name]
                    for year in range(1, duration + 1):
                        schedule = schedules[min(year - 1, len(schedules) - 1)]
                        py, _ = ProgrammeYear.objects.get_or_create(
                            programme=programme,
                            year_number=year,
                        )
                        for label, amount in schedule.items():
                            Fee.objects.get_or_create(
                                programme_year=py,
                                label=label,
                                defaults={"amount": amount, "due_month": "Octobre"},
                            )

                    # Quick facts
                    facts = [
                        ("Durée", f"{duration} ans"),
                        ("Système", "LMD"),
                    ]
                    if cycle_name == "DUT":
                        facts.append(("Crédits", "120"))
                    elif cycle_name == "Licence":
                        facts.append(("Crédits", "180"))
                    elif cycle_name == "Master":
                        facts.append(("Crédits", "120"))

                    for label, value in facts:
                        ProgrammeQuickFact.objects.get_or_create(
                            programme=programme,
                            label=label,
                            defaults={
                                "icon": "academic_cap",
                                "value": value,
                                "order": 0,
                            },
                        )

                    # Documents requis
                    for doc in FATEC_ESGA_DOCS:
                        ProgrammeRequiredDocument.objects.get_or_create(
                            programme=programme,
                            document=required_docs[doc],
                        )

                    self.stdout.write(f"  OK {school_code} – {title}")

        # =====================================================
        # 10. PARTENAIRES
        # =====================================================
        partners = [
            {
                "name": "Institut de Formation Sainte Marie",
                "city": "Abidjan",
                "country": "Côte d'Ivoire",
                "partner_type": "university",
            },
            {
                "name": "Université Koffi Anane",
                "city": None,
                "country": "Guinée",
                "partner_type": "university",
            },
            {
                "name": "Université Ibrahim Niass",
                "city": None,
                "country": "Sénégal",
                "partner_type": "university",
            },
            {
                "name": "RUSTA — Universités",
                "city": None,
                "country": None,
                "partner_type": "university",
            },
            {
                "name": "Université de Monastir",
                "city": "Monastir",
                "country": "Tunisie",
                "partner_type": "university",
            },
        ]

        for index, p in enumerate(partners):
            partner, _ = Partner.objects.get_or_create(
                name=p["name"],
                defaults={
                    "partner_type": p["partner_type"],
                    "is_active": True,
                    "order": index,
                },
            )

        self.stdout.write(self.style.SUCCESS("[OK] Catalogue UFHOB seedé proprement."))
