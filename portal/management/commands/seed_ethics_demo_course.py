from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics.models import AcademicClass, EC, ECChapter, ECContent
from portal.models import DirectorTeacherAssignment


COURSE_TITLE = "Déontologie et éthique"
CLASS_NAME = "PILOTE ISMI - L1"

COURSE_PLAN = (
    (
        "Fondements de la déontologie et de l’éthique",
        (
            ("Introduction à la déontologie professionnelle", "La déontologie professionnelle donne des repères concrets pour exercer une responsabilité de soin avec rigueur, respect et discernement.", "Avant de transmettre une information sensible, le soignant vérifie qui est présent, ce qui est nécessaire à la prise en charge et la façon la plus respectueuse de communiquer."),
            ("Définition de l’éthique", "L’éthique consiste à examiner une situation, les valeurs en présence et les conséquences possibles afin de choisir une action juste.", "Face à une décision difficile, l’équipe prend un temps de discussion au lieu de s’appuyer uniquement sur une habitude."),
            ("Morale, éthique et déontologie", "La morale renvoie aux repères partagés, l’éthique à la réflexion sur une décision et la déontologie aux devoirs liés à une profession.", "Une règle de service peut guider l’action, mais le professionnel doit encore apprécier les besoins singuliers du patient."),
            ("Valeurs fondamentales du professionnel de santé", "Le respect, la probité, la compétence, la responsabilité et la compassion soutiennent une pratique de santé digne de confiance.", "Un soignant reconnaît une limite de compétence et demande l’appui approprié plutôt que de laisser le patient exposé à un risque."),
            ("Principes généraux de conduite professionnelle", "Une conduite professionnelle s’appuie sur la ponctualité, la discrétion, une communication claire et le respect des protocoles utiles.", "Lors d’une relève, les informations sont transmises de manière exacte, concise et réservée aux personnes concernées."),
            ("Importance de l’éthique dans les professions de santé", "L’éthique protège le patient, soutient la qualité des soins et aide les équipes à maintenir une relation de confiance durable.", "Lorsqu’un proche insiste pour obtenir une information non autorisée, le soignant protège la confidentialité tout en expliquant son rôle."),
            ("Cadre professionnel et obligations du soignant", "Le cadre professionnel réunit les obligations légales, institutionnelles et déontologiques qui organisent un soin responsable.", "Le professionnel documente une observation utile dans le dossier avec des termes factuels et respecte les procédures prévues."),
        ),
    ),
    (
        "Principes éthiques fondamentaux",
        (
            ("Respect de la dignité humaine", "La dignité humaine exige de considérer chaque personne comme un sujet de droits, quelle que soit sa situation clinique ou sociale.", "Pendant un soin intime, le soignant protège l’intimité, explique chaque geste et limite les présences au strict nécessaire."),
            ("Principe d’autonomie", "L’autonomie suppose que le patient reçoive une information compréhensible et puisse participer librement aux décisions qui le concernent.", "Avant un examen, le professionnel vérifie ce que le patient a compris et lui laisse la possibilité de poser des questions."),
            ("Bienfaisance", "La bienfaisance conduit à rechercher activement le bénéfice réel du patient en tenant compte de ses besoins et de son projet de vie.", "L’équipe adapte l’éducation thérapeutique au niveau de compréhension de la personne afin qu’elle puisse réellement en tirer profit."),
            ("Non-malfaisance", "La non-malfaisance impose de prévenir les dommages évitables, d’évaluer les risques et de signaler les situations dangereuses.", "Avant l’administration d’un traitement, le soignant contrôle l’identité, la prescription et les contre-indications connues."),
            ("Justice et équité dans les soins", "La justice demande une répartition équitable de l’attention, du temps et des ressources, sans discrimination arbitraire.", "En période d’affluence, les priorités sont fixées selon l’état clinique et non selon la pression d’un accompagnant."),
            ("Consentement libre et éclairé", "Le consentement est valable lorsqu’il est donné sans pression, après une explication accessible des objectifs, bénéfices, risques et alternatives.", "Un patient qui hésite peut demander un délai raisonnable ou une explication complémentaire avant de choisir."),
            ("Respect des croyances et des choix du patient", "Le soin respecte les convictions religieuses, culturelles et personnelles tant qu’elles ne mettent pas directement autrui en danger.", "L’équipe cherche une organisation compatible avec les habitudes du patient sans abandonner les exigences de sécurité."),
        ),
    ),
    (
        "Secret professionnel et confidentialité",
        (
            ("Définition du secret professionnel", "Le secret professionnel protège les informations connues dans l’exercice du soin et préserve la confiance indispensable à la relation thérapeutique.", "Une conversation sur l’état d’un patient ne se tient pas dans un couloir ou un espace accessible aux visiteurs."),
            ("Informations couvertes par le secret", "Les données médicales, sociales, familiales et administratives identifiantes sont couvertes dès lors qu’elles concernent la personne soignée.", "Même une information apparemment anodine ne doit pas être partagée si elle permet d’identifier ou de stigmatiser un patient."),
            ("Confidentialité du dossier du patient", "Le dossier est un outil de soin : son accès est réservé aux professionnels autorisés et justifié par la prise en charge.", "Avant de consulter un dossier numérique, le professionnel s’assure qu’il intervient bien auprès du patient concerné."),
            ("Communication des informations de santé", "La communication d’informations de santé doit être adaptée au destinataire, au cadre légal et à la volonté exprimée par le patient.", "Lors d’un appel téléphonique, l’identité et l’habilitation de l’interlocuteur sont vérifiées avant toute transmission."),
            ("Secret professionnel au sein d’une équipe de soins", "Le partage au sein de l’équipe est limité aux informations nécessaires à la continuité, à la qualité et à la sécurité des soins.", "Pendant une réunion clinique, les membres évitent les détails sans utilité pour la décision collective."),
            ("Limites et exceptions au secret professionnel", "Certaines exceptions sont prévues par la loi ou par une nécessité de protection, mais elles doivent être interprétées avec prudence et traçabilité.", "Avant un signalement, le professionnel consulte le responsable compétent et documente les éléments strictement nécessaires."),
            ("Responsabilité du professionnel face aux données confidentielles", "La responsabilité inclut la protection matérielle des documents, des écrans, des mots de passe et des échanges électroniques.", "En quittant un poste de travail, le soignant verrouille la session et ne laisse aucun dossier visible."),
        ),
    ),
    (
        "Responsabilité et relation soignant-patient",
        (
            ("Responsabilité professionnelle du soignant", "La responsabilité professionnelle implique d’agir dans son champ de compétence, de rendre compte de ses actes et de demander de l’aide si nécessaire.", "Un professionnel qui identifie une erreur potentielle alerte sans délai afin de limiter ses conséquences pour le patient."),
            ("Devoirs envers le patient", "Les devoirs envers le patient comprennent l’écoute, la loyauté, la sécurité, l’information adaptée et le respect de la personne.", "Le soignant annonce un retard, explique la suite de la prise en charge et évite de laisser la personne sans repère."),
            ("Qualité de la relation soignant-patient", "Une relation de qualité repose sur l’attention, la disponibilité raisonnable, l’empathie et la juste distance professionnelle.", "Le professionnel reformule la demande du patient pour vérifier sa compréhension avant de proposer une réponse."),
            ("Communication professionnelle avec le patient", "Une communication professionnelle emploie des mots simples, évite les jugements et tient compte de l’état émotionnel de la personne.", "Après une mauvaise nouvelle, l’équipe ménage un temps de silence et vérifie les besoins immédiats du patient."),
            ("Respect et comportement professionnel", "Le respect se manifeste dans le langage, les gestes, la présentation, la ponctualité et l’absence de discrimination.", "Même dans une situation tendue, le soignant évite les propos humiliants et sollicite un collègue si la discussion s’envenime."),
            ("Gestion des situations difficiles", "Les situations difficiles demandent de reconnaître les émotions, de sécuriser l’environnement et de chercher une solution proportionnée.", "Face à une famille inquiète, le professionnel fixe un cadre d’échange calme et transmet les informations qu’il est autorisé à donner."),
            ("Responsabilité au sein de l’équipe de santé", "Le travail d’équipe suppose de respecter les rôles, d’alerter utilement et de contribuer à une culture de sécurité partagée.", "Lors d’une relève, une information préoccupante est transmise explicitement plutôt que laissée dans une note ambiguë."),
        ),
    ),
    (
        "Éthique appliquée et bonnes pratiques professionnelles",
        (
            ("Dilemmes éthiques dans les soins", "Un dilemme éthique apparaît lorsque plusieurs valeurs importantes semblent entrer en tension et qu’aucune réponse n’est entièrement simple.", "Une équipe doit concilier le souhait d’autonomie d’un patient et la prévention d’un risque grave en recherchant des options graduées."),
            ("Analyse d’une situation éthique", "L’analyse éthique clarifie les faits, les personnes concernées, les valeurs en jeu, les options possibles et leurs conséquences.", "Avant de décider, l’équipe distingue ce qui est établi de ce qui relève d’une supposition ou d’une inquiétude."),
            ("Prise de décision professionnelle", "Une décision professionnelle responsable est expliquée, proportionnée, traçable et réévaluée lorsque de nouvelles informations apparaissent.", "Après concertation, le plan choisi est présenté au patient dans un langage accessible et les raisons principales sont consignées."),
            ("Respect du patient en situation de vulnérabilité", "La vulnérabilité exige une attention accrue au consentement, à la compréhension, à la protection contre les abus et à l’accès effectif aux soins.", "Pour une personne désorientée, l’équipe adapte l’explication et associe les représentants légitimes selon le cadre applicable."),
            ("Comportement professionnel en milieu clinique", "Le milieu clinique demande une attitude fiable : hygiène, discrétion, disponibilité, respect des consignes et signalement des risques.", "Un étudiant ne publie jamais une image ou un récit identifiable issu d’un stage, même avec une intention pédagogique."),
            ("Bonnes pratiques professionnelles", "Les bonnes pratiques associent compétence technique, communication, documentation, coordination et questionnement éthique régulier.", "Une check-list de sécurité est utilisée comme un soutien à la vigilance et non comme une formalité mécanique."),
            ("Synthèse : adopter une conduite professionnelle éthique", "Une conduite éthique durable relie les principes appris à des décisions quotidiennes, réfléchies et respectueuses de chaque personne.", "Après une situation complexe, le professionnel prend un temps de retour d’expérience pour améliorer la pratique de l’équipe."),
        ),
    ),
)


def lesson_html(*, chapter_title, lesson_title, focus, scenario, link=None):
    link_paragraph = ""
    if link:
        link_paragraph = f'<p>Pour prolonger la réflexion, consultez <a href="{link}">cette ressource vidéo publique</a> puis notez les principes qui peuvent guider votre pratique.</p>'
    return f"""
<h2>{lesson_title}</h2>
<p><strong>Introduction.</strong> {focus}</p>
<p>Dans le cadre du chapitre <em>{chapter_title}</em>, cette leçon aide à relier les principes professionnels aux décisions prises au quotidien auprès des patients, des proches et de l’équipe.</p>
<h3>Notions importantes</h3>
<p>Une décision éthique commence par une observation attentive de la situation. Elle demande de distinguer les faits, les besoins de la personne, les règles applicables et les conséquences possibles.</p>
<ul>
  <li><strong>Respecter la personne</strong> dans son histoire, ses droits et sa parole.</li>
  <li><strong>Prévenir les risques évitables</strong> par une pratique prudente et documentée.</li>
  <li><strong>Communiquer avec clarté</strong> afin de soutenir une décision réellement comprise.</li>
</ul>
<h3>Mise en pratique</h3>
<ol>
  <li>Identifier ce qui pose question dans la situation.</li>
  <li>Recueillir les informations utiles sans diffuser de données inutiles.</li>
  <li>Choisir une réponse proportionnée et en expliquer le sens.</li>
</ol>
<p><strong>Situation professionnelle.</strong> {scenario}</p>
{link_paragraph}
<h3>Synthèse</h3>
<p>Le professionnalisme ne se limite pas à appliquer une consigne : il consiste à agir avec compétence, responsabilité et attention constante à la dignité de la personne soignée.</p>
""".strip()


class Command(BaseCommand):
    help = "Crée le cours de démonstration Déontologie et éthique pour PILOTE ISMI - L1."

    def handle(self, *args, **options):
        academic_class = AcademicClass.objects.filter(name=CLASS_NAME).select_related("branch", "academic_year").first()
        if academic_class is None:
            raise CommandError(f"Classe introuvable : {CLASS_NAME}.")
        ec = EC.objects.filter(title=COURSE_TITLE, ue__semester__academic_class=academic_class).first()
        if ec is None:
            raise CommandError(f"Matière introuvable pour {CLASS_NAME} : {COURSE_TITLE}.")
        assignment = DirectorTeacherAssignment.objects.filter(
            academic_class=academic_class,
            ec=ec,
            is_active=True,
        ).select_related("teacher").first()
        if assignment is None:
            raise CommandError("Aucun enseignant actif n'est affecté à la matière cible.")

        created_chapters = created_lessons = 0
        with transaction.atomic():
            for chapter_order, (chapter_title, lessons) in enumerate(COURSE_PLAN, start=1):
                chapter, chapter_created = ECChapter.objects.get_or_create(
                    ec=ec,
                    title=chapter_title,
                    defaults={"order": chapter_order},
                )
                created_chapters += int(chapter_created)
                for lesson_order, (lesson_title, focus, scenario) in enumerate(lessons, start=1):
                    link = None
                    if lesson_title == "Principe d’autonomie":
                        link = "https://www.youtube.com/watch?v=-86N4JOX4NE"
                    content, lesson_created = ECContent.objects.get_or_create(
                        chapter=chapter,
                        title=lesson_title,
                        defaults={
                            "content_type": ECContent.CONTENT_TYPE_TEXT,
                            "text_content": lesson_html(
                                chapter_title=chapter_title,
                                lesson_title=lesson_title,
                                focus=focus,
                                scenario=scenario,
                                link=link,
                            ),
                            "duration": 12,
                            "order": lesson_order,
                            "status": ECContent.STATUS_PUBLISHED,
                            "published_at": timezone.now(),
                            "is_active": True,
                        },
                    )
                    created_lessons += int(lesson_created)
                    if not lesson_created and content.status != ECContent.STATUS_PUBLISHED:
                        self.stdout.write(self.style.WARNING(
                            f"Leçon existante conservée en brouillon : {content.title}."
                        ))

        total_chapters = ECChapter.objects.filter(ec=ec, title__in=[row[0] for row in COURSE_PLAN]).count()
        total_lessons = ECContent.objects.filter(chapter__ec=ec, chapter__title__in=[row[0] for row in COURSE_PLAN]).count()
        self.stdout.write(self.style.SUCCESS(
            f"Cours prêt pour {academic_class.name} / {ec.title} — enseignant affecté : "
            f"{assignment.teacher.get_full_name() or assignment.teacher.get_username()}. "
            f"{created_chapters} chapitre(s) et {created_lessons} leçon(s) créés "
            f"({total_chapters} chapitres, {total_lessons} leçons au total)."
        ))
