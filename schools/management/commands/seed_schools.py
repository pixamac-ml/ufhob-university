# schools/management/commands/seed_schools.py

from django.core.management.base import BaseCommand
from schools.models import School


class Command(BaseCommand):
    help = "Crée les écoles de l'UFHOB : EsMed, ESGA, FATEC"

    def handle(self, *args, **options):
        schools_data = [
            {
                "name": "École des Sciences Médicales Félix Houphouët-Boigny",
                "short_name": "EsMed",
                "code": "ESMED",
                "description": "L'École des Sciences Médicales forme les futurs professionnels de la santé avec des programmes reconnus internationalement.",
                "mission": "Former des professionnels de santé compétents et éthiques pour servir la communauté.",
                "primary_color": "#1E3A8A",
                "secondary_color": "#3B82F6",
                "order": 1,
            },
            {
                "name": "École de Sciences de Gestion Appliquée",
                "short_name": "ESGA",
                "code": "ESGA",
                "description": "L'ESGA prépare les leaders de demain dans les domaines de la gestion, du management et de l'entrepreneuriat.",
                "mission": "Développer les compétences managériales et entrepreneuriales pour stimuler l'économie.",
                "primary_color": "#059669",
                "secondary_color": "#10B981",
                "order": 2,
            },
            {
                "name": "Faculté Appliquée de Technologies et de Communication",
                "short_name": "FATEC",
                "code": "FATEC",
                "description": "FATEC forme les experts en technologies de l'information, télécommunications et médias numériques.",
                "mission": "Innover et former les talents technologiques pour la transformation digitale de l'Afrique.",
                "primary_color": "#7C3AED",
                "secondary_color": "#A78BFA",
                "order": 3,
            },
        ]

        self.stdout.write("\n🏫 Création des écoles UFHOB...\n")

        for data in schools_data:
            school, created = School.objects.update_or_create(
                code=data["code"],
                defaults=data
            )
            status = "✅ Créée" if created else "🔄 Mise à jour"
            self.stdout.write(f"   {status}: {school.short_name} - {school.name}")

        self.stdout.write(self.style.SUCCESS("\n🎉 Écoles UFHOB créées avec succès !\n"))