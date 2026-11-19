from collections import Counter
from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import connections, transaction
from django.db.models import Q

from branches.models import Branch
from core.models import Institution, School, SchoolBranch
from formations.campaign_catalogue import OFFERS, SCHOOLS
from formations.models import Filiere, Programme


class Command(BaseCommand):
    help = "Publie les deux écoles et les six offres UFHOB sans supprimer les données historiques."

    def add_arguments(self, parser):
        parser.add_argument("--campus", action="append", default=[], help="Slug d'un campus existant et validé (répétable).")
        parser.add_argument("--dry-run", action="store_true", help="Vérifie et affiche le bilan sans conserver les changements.")
        parser.add_argument("--require-ready", action="store_true", help="Échoue atomiquement si un campus ou l'année active manque.")
        parser.add_argument("--campus-name", help="Nom officiel pour créer un campus absent ; exige un seul --campus et --campus-code.")
        parser.add_argument("--campus-code", help="Code officiel du campus à créer. Ne modifie pas un campus existant.")
        parser.add_argument("--year-start", help="Date officielle de début 2026-2027 (AAAA-MM-JJ), pour une année absente seulement.")
        parser.add_argument("--year-end", help="Date officielle de fin 2026-2027 (AAAA-MM-JJ), pour une année absente seulement.")

    @transaction.atomic
    def handle(self, *args, **options):
        db = connections["default"]
        if db.vendor == "postgresql" and db.settings_dict["NAME"] != "ufhob_db":
            raise CommandError("Initialisation interdite : la base doit être ufhob_db.")
        counts = Counter()
        if bool(options["campus_name"]) != bool(options["campus_code"]) or (options["campus_name"] and len(options["campus"]) != 1):
            raise CommandError("Créer un campus exige --campus SLUG --campus-name NOM --campus-code CODE.")
        if options["year_start"] or options["year_end"]:
            from academics.models import AcademicYear
            from django.core.exceptions import ValidationError
            existing_year = AcademicYear.objects.filter(name="2026-2027").first()
            if AcademicYear.objects.filter(is_active=True).exclude(name="2026-2027").exists():
                raise CommandError("Une autre année est active ; un arbitrage institutionnel est nécessaire.")
            try:
                year = AcademicYear(name="2026-2027", start_date=date.fromisoformat(options["year_start"] or ""), end_date=date.fromisoformat(options["year_end"] or ""), is_active=True)
                if existing_year:
                    if (existing_year.start_date, existing_year.end_date, existing_year.is_active) != (year.start_date, year.end_date, True):
                        raise CommandError("L'année 2026-2027 existe avec d'autres paramètres ; aucune réécriture automatique.")
                else:
                    year.full_clean()
                    year.save()
            except (ValueError, ValidationError) as exc:
                raise CommandError("Fournir les deux dates officielles valides avec --year-start et --year-end.") from exc
            counts["inchangés" if existing_year else "créés"] += 1
        institution = Institution.objects.select_for_update().first()
        readiness_errors = []
        if institution is None:
            institution = Institution.objects.create(
                name="Université Privée Félix Houphouët-Boigny – Mali", short_name="UFHOB-Mali",
                phone="+223 76 88 24 79", address="", city="", email="",
            )
            counts["créés"] += 1
        campuses = []
        for slug in options["campus"]:
            try:
                campuses.append(Branch.objects.get(slug=slug, is_active=True, accepts_online_registration=True))
            except Branch.DoesNotExist as exc:
                if options["campus_name"] and not Branch.objects.filter(slug=slug).exists():
                    from django.core.exceptions import ValidationError
                    campus = Branch(name=options["campus_name"], code=options["campus_code"], slug=slug, city="", is_active=True, accepts_online_registration=True)
                    try:
                        # Location stays empty until validated; validate all other fields.
                        campus.full_clean(exclude=["city"])
                        campus.save()
                    except ValidationError as validation_error:
                        raise CommandError(f"Référence campus invalide : {validation_error}") from validation_error
                    campuses.append(campus)
                    counts["créés"] += 1
                else:
                    raise CommandError(f"Campus actif et ouvert aux candidatures introuvable : {slug}. Aucune implantation n'est inventée.") from exc
        for code, name in SCHOOLS.items():
            matches = list(School.objects.filter(code__iexact=code))
            if len(matches) > 1 or (matches and matches[0].institution_id != institution.pk):
                raise CommandError(f"École ambiguë : {code}. Aucun changement conservé.")
            school = matches[0] if matches else School(institution=institution, code=code, short_name=code)
            self._save(school, {"official_name": name, "is_active": True}, counts, f"École {code}")
            for campus in campuses:
                presence, created = SchoolBranch.objects.get_or_create(school=school, branch=campus)
                if created:
                    counts["créés"] += 1
                elif not presence.is_active:
                    raise CommandError(f"Présence {code}/{campus.slug} désactivée : validation institutionnelle nécessaire.")
            if not SchoolBranch.objects.filter(school=school, is_active=True, branch__is_active=True, branch__accepts_online_registration=True).exists():
                message = f"{code} : aucun campus de candidature. Relancer avec --campus SLUG_VALIDÉ avant la campagne."
                readiness_errors.append(message)
                self.stderr.write(self.style.WARNING(message))
            for offer in (item for item in OFFERS if item[0] == code):
                _, title, slug, intro, description, careers = offer
                candidates = list(Programme.objects.filter(Q(slug=slug) | Q(title__iexact=title)))
                if len(candidates) > 1:
                    raise CommandError(f"Plusieurs programmes correspondent à {title}. Aucun rapprochement automatique.")
                programme = candidates[0] if candidates else None
                if programme and programme.school_id not in {None, school.pk}:
                    raise CommandError(f"{title} appartient déjà à une autre école. Historique conservé ; arbitrage requis.")
                if programme and (programme.is_archived or programme.slug != slug):
                    raise CommandError(f"{title} : référence archivée ou slug historique différent ({programme.slug}). Aucune réécriture silencieuse.")
                if programme is None:
                    filiere, created = Filiere.objects.get_or_create(name=title)
                    counts["créés"] += int(created)
                    programme = Programme(title=title, slug=slug, school=school, filiere=filiere)
                if not programme.filiere.is_active or (programme.cycle_id and not programme.cycle.is_active):
                    raise CommandError(f"{title} dépend d'un référentiel inactif. Validation requise.")
                # Existing editorial content and all academic/financial records survive.
                values = {
                    "school": school, "is_active": True, "is_public": True,
                    "admissions_open": True, "campaign_published": True,
                    "delivery_modes": "En présentiel ; En ligne, à distance",
                    "registration_notice": "Inscriptions ouvertes 2026-2027",
                }
                for field, value in {
                    "short_description": intro, "description": description,
                    "career_opportunities": careers, "meta_title": f"{title} | UFHOB-Mali"[:70],
                    "meta_description": f"{intro} Inscriptions ouvertes 2026-2027 à l’UFHOB-Mali."[:160],
                }.items():
                    if not getattr(programme, field):
                        values[field] = value
                self._save(programme, values, counts, title)
        from academics.services.academic_years import get_current_academic_year_name
        if get_current_academic_year_name() != "2026-2027":
            message = "Année active 2026-2027 absente : configurer ses dates officielles avant de recevoir les candidatures."
            readiness_errors.append(message)
            self.stderr.write(self.style.WARNING(message))
        if options["require_ready"] and readiness_errors:
            raise CommandError("Lancement bloqué : " + " ".join(readiness_errors) + " Aucun changement conservé.")
        self.stdout.write(self.style.SUCCESS("Bilan : " + ", ".join(f"{key} : {counts[key]}" for key in ("créés", "mis à jour", "inchangés"))))
        if options["dry_run"]:
            transaction.set_rollback(True)
            self.stdout.write("Simulation : aucun changement conservé.")

    def _save(self, obj, values, counts, label):
        created = obj.pk is None
        changed = [key for key, value in values.items() if getattr(obj, key) != value]
        for key, value in values.items():
            setattr(obj, key, value)
        state = "créés" if created else "mis à jour" if changed else "inchangés"
        if created or changed:
            obj.save()
        counts[state] += 1
        self.stdout.write(f"{state} : {label}")
