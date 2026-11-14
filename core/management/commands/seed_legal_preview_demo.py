from django.core.management.base import BaseCommand

from core.models import LegalPage, LegalSection


PAGES = {
    "legal": ("Mentions légales", "Éditeur du site", "Informations institutionnelles à compléter avant publication définitive."),
    "privacy": ("Politique de confidentialité", "Données traitées", "Les formulaires et espaces authentifiés peuvent traiter les données nécessaires à leur fonctionnement."),
    "terms": ("Conditions d’utilisation", "Accès au site", "L’accès aux services est soumis aux règles applicables et aux droits attribués."),
}


class Command(BaseCommand):
    help = "Publie des aperçus juridiques fictifs, clairement identifiés comme provisoires."

    def handle(self, *args, **options):
        for page_type, (title, section_title, section_content) in PAGES.items():
            page, _ = LegalPage.objects.update_or_create(
                page_type=page_type,
                defaults={
                    "title": title,
                    "introduction": "<p><strong>Aperçu provisoire de démonstration.</strong> Contenu à valider par l’université avant publication définitive.</p>",
                    "status": "published",
                    "version": "Aperçu 0.1",
                },
            )
            LegalSection.objects.update_or_create(
                page=page, title=section_title,
                defaults={"content": f"<p>{section_content}</p>", "is_active": True, "order": 1},
            )
        self.stdout.write(self.style.SUCCESS("Trois aperçus juridiques publiés."))
