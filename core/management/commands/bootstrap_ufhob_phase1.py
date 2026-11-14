#!/usr/bin/env python
"""Bootstrap institutionnel idempotent Phase 1 UFHOB."""
from django.core.management.base import BaseCommand

from core.models import Institution, School


class Command(BaseCommand):
    """Crée l'institution racine UFHOB et les écoles initiales si absentes."""

    help = "Bootstrap idempotent Phase 1 UFHOB : institution et écoles ESMed, ESGA, FATEC."

    def handle(self, *args, **options):
        institution = Institution.objects.first()
        if institution is None:
            institution = Institution.objects.create(
                name="Université Félix Houphouët-Boigny",
                short_name="UFHOB",
                address="Bamako",
                city="Bamako",
                phone="-",
                email="contact@ufhob.local",
            )
            self.stdout.write(
                self.style.SUCCESS(f"Institution créée : {institution.name}")
            )
        else:
            self.stdout.write(f"Institution existante : {institution.name}")

        schools = [
            {"code": "ESMED", "short_name": "ESMed", "order": 1},
            {"code": "ESGA", "short_name": "ESGA", "order": 2},
            {"code": "FATEC", "short_name": "FATEC", "order": 3},
        ]

        for spec in schools:
            school, created = School.objects.get_or_create(
                institution=institution,
                code=spec["code"],
                defaults={
                    "short_name": spec["short_name"],
                    "official_name": "",
                    "order": spec["order"],
                    "is_active": True,
                },
            )
            if not created and school.short_name != spec["short_name"]:
                school.short_name = spec["short_name"]
                school.save(update_fields=["short_name", "updated_at"])
            verb = "créée" if created else "déjà présente"
            self.stdout.write(self.style.SUCCESS(f"School {spec['code']} : {verb}"))

        self.stdout.write(self.style.SUCCESS("Bootstrap UFHOB Phase 1 terminé."))
