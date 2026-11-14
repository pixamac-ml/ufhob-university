"""Seed a minimal, neutral public-news preview for an otherwise empty UFHOB site."""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from news.models import Category, Event, EventType, News


class Command(BaseCommand):
    help = "Creates neutral UFHOB public-news and agenda demo content when it is absent."

    def handle(self, *args, **options):
        categories = {
            "Vie universitaire": "vie-universitaire",
            "Admissions": "admissions",
            "Pédagogie": "pedagogie",
            "Recherche & innovation": "recherche-innovation",
        }
        category_by_slug = {}
        for order, (name, slug) in enumerate(categories.items(), start=1):
            category, _ = Category.objects.get_or_create(
                slug=slug,
                defaults={"nom": name, "ordre": order, "is_active": True},
            )
            category_by_slug[slug] = category

        now = timezone.now()
        news_items = [
            ("ufhob-rentree-universitaire-2026-2027", "Rentrée universitaire 2026-2027 : préparer son parcours", "vie-universitaire", "L’UFHOB accompagne les futurs étudiants dans la préparation de leur parcours universitaire.", "Retrouvez les informations utiles pour préparer votre arrivée, découvrir les services universitaires et organiser les premières étapes de votre parcours."),
            ("ufhob-ouverture-admissions", "Ouverture des admissions : découvrir les parcours proposés", "admissions", "Les candidatures s’inscrivent dans un parcours unifié, par école, programme et campus disponible.", "Les futurs candidats peuvent explorer les formations publiées puis commencer leur démarche auprès de l’université. Les informations pratiques sont mises à jour dans le parcours de candidature."),
            ("ufhob-journee-orientation", "Une journée d’orientation pour mieux choisir sa formation", "vie-universitaire", "Une occasion de découvrir les écoles, les programmes et l’environnement universitaire.", "L’orientation aide chaque candidat à identifier un parcours cohérent avec son projet. Cette rencontre présente l’organisation de l’université et les informations utiles à la candidature."),
            ("ufhob-rencontre-pedagogique", "Rencontre pédagogique : partager les pratiques d’apprentissage", "pedagogie", "La communauté académique échange autour de l’accompagnement et de la progression des étudiants.", "Cette publication illustre la place du dialogue pédagogique dans la vie universitaire. Les contenus et modalités des rencontres sont communiqués par les services concernés."),
            ("ufhob-recherche-innovation", "Recherche et innovation : une démarche ouverte sur les enjeux contemporains", "recherche-innovation", "L’UFHOB valorise une culture de méthode, de créativité et de diffusion des savoirs.", "La recherche et l’innovation nourrissent l’apprentissage et l’ouverture sur la société. Les travaux effectivement publiés sont présentés dans les espaces dédiés de la plateforme."),
        ]
        created_news = 0
        for index, (slug, title, category_slug, summary, content) in enumerate(news_items):
            _, created = News.objects.get_or_create(
                slug=slug,
                defaults={
                    "titre": title,
                    "categorie": category_by_slug[category_slug],
                    "resume": summary,
                    "contenu": content,
                    "status": News.STATUS_PUBLISHED,
                    "published_at": now - timedelta(days=index * 4),
                },
            )
            created_news += int(created)

        event_type, _ = EventType.objects.get_or_create(
            slug="agenda-ufhob",
            defaults={"name": "Agenda UFHOB", "is_active": True},
        )
        events = [
            ("ufhob-accueil-orientation", "Accueil et orientation des futurs étudiants", "Un temps d’information générique consacré aux parcours, aux écoles et aux démarches de candidature.", date.today() + timedelta(days=14)),
            ("ufhob-rencontre-academique", "Rencontre académique et pédagogique", "Un rendez-vous de partage autour de la vie académique et de l’accompagnement des étudiants.", date.today() + timedelta(days=28)),
            ("ufhob-echange-recherche-innovation", "Échange autour de la recherche et de l’innovation", "Un temps de dialogue ouvert sur les savoirs, la recherche et l’innovation au sein de l’université.", date.today() + timedelta(days=42)),
        ]
        created_events = 0
        for slug, title, description, event_date in events:
            _, created = Event.objects.get_or_create(
                slug=slug,
                defaults={
                    "title": title,
                    "event_type": event_type,
                    "description": description,
                    "event_date": event_date,
                    "is_published": True,
                },
            )
            created_events += int(created)

        self.stdout.write(self.style.SUCCESS(
            f"UFHOB public demo: {created_news} news item(s), {created_events} event(s) created."
        ))
