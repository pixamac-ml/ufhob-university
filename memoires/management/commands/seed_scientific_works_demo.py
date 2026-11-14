"""Seed explicit, reversible-in-practice demonstration records for the public catalogue."""

import fitz

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from formations.models import Filiere
from memoires.models import Memoire
from memoires.services.rendering import render_memoire_pages


WORKS = [
    ("memoire", "Étude exploratoire des pratiques d’apprentissage – démonstration", 2022),
    ("rapport", "Rapport de terrain sur les besoins de formation – démonstration", 2022),
    ("article", "Article de synthèse sur l’innovation pédagogique – démonstration", 2023),
    ("memoire", "Mémoire sur les usages responsables du numérique – démonstration", 2023),
    ("these", "Thèse pilote sur les dynamiques de recherche appliquée – démonstration", 2024),
    ("rapport", "Rapport d’analyse des initiatives communautaires – démonstration", 2024),
    ("article", "Article sur la coopération interdisciplinaire – démonstration", 2025),
    ("memoire", "Mémoire sur les compétences professionnelles émergentes – démonstration", 2026),
]


class Command(BaseCommand):
    help = "Crée huit travaux scientifiques fictifs et explicitement marqués comme démonstration."

    @staticmethod
    def _placeholder_pdf(title):
        document = fitz.open()
        page = document.new_page(width=595, height=842)
        page.insert_textbox(
            fitz.Rect(60, 280, 535, 560),
            f"{title}\n\nDOCUMENT DE DÉMONSTRATION\nContenu non institutionnel à remplacer avant publication réelle.",
            fontsize=15,
            align=1,
        )
        content = document.tobytes()
        document.close()
        return content

    def handle(self, *args, **options):
        filieres = list(Filiere.objects.filter(is_active=True).order_by("name"))
        if not filieres:
            self.stderr.write(self.style.WARNING("Aucune filière active : aucune donnée de démonstration créée."))
            return

        creator = get_user_model().objects.filter(is_superuser=True).order_by("id").first()
        created = skipped = 0
        for index, (work_type, title, year) in enumerate(WORKS, start=1):
            slug = slugify(title)
            if Memoire.objects.filter(slug=slug).exists():
                skipped += 1
                continue
            work = Memoire.objects.create(
                titre=title,
                slug=slug,
                type_travail=work_type,
                auteurs=f"Auteur de démonstration {index:02d}",
                encadreur="Encadrement de démonstration",
                filiere=filieres[(index - 1) % len(filieres)],
                niveau=Memoire.Niveau.MASTER if index % 2 else Memoire.Niveau.LICENCE,
                annee=year,
                resume=(
                    "<p><strong>Contenu de démonstration.</strong> Ce résumé fictif sert uniquement à "
                    "valider le catalogue public et doit être remplacé par une publication validée.</p>"
                ),
                mots_cles="démonstration, catalogue, recherche",
                statut=Memoire.Statut.PUBLIE,
                est_mis_en_avant=index <= 3,
                cree_par=creator,
            )
            work.fichier_source.save("demonstration.pdf", ContentFile(self._placeholder_pdf(title)), save=True)
            render_memoire_pages(work)
            created += 1
        self.stdout.write(self.style.SUCCESS(f"{created} travail(x) créé(s), {skipped} déjà présent(s)."))
