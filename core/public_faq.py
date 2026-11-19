"""FAQ issue du catalogue public et des informations de rentrée validées."""
from django.shortcuts import render

from formations.models import Programme, RequiredDocument
from .models import School
from .seo import schema_json


def faq(request):
    programmes = Programme.objects.public().select_related("school", "cycle").order_by("school__order", "title")
    schools = School.objects.public()
    documents = list(RequiredDocument.objects.filter(
        programmerequireddocument__programme__in=programmes,
    ).order_by("name").values_list("name", flat=True).distinct())
    items = [
        ("Où se trouve l’UFHOB-Mali ?", "Le campus de Moribabougou se trouve dans la région de Koulikoro, près de Bamako, au Mali.", "core:contact"),
        ("Quelles filières sont proposées ?", "Le catalogue public présente les filières des écoles " + ", ".join(s.display_name for s in schools) + ". Consultez les fiches pour les programmes, compétences et débouchés.", "formations:list"),
        ("Peut-on préparer un DUT, une Licence ou un Master ?", "Les fiches du catalogue précisent le cycle de chaque formation : DUT, Licence ou Master selon la filière. Consultez la fiche du parcours choisi pour ses conditions d’accès et sa durée.", "formations:list"),
        ("Comment candidater en ligne ?", "Depuis une fiche filière, ouvrez la candidature en ligne, renseignez votre identité, choisissez une formation et un campus compatible, puis transmettez les pièces demandées. La réception du dossier ne constitue pas une décision d’admission.", "admissions:admission_tunnel"),
        ("Quels documents faut-il fournir ?", ("Les pièces indiquées dans le catalogue public comprennent : " + "; ".join(documents) + ". " if documents else "") + "La liste applicable est celle de votre fiche filière et du formulaire de candidature.", "formations:list"),
        ("Quelle est la date de rentrée annoncée ?", "La rentrée annoncée pour 2026-2027 est le 5 octobre 2026. Contactez l’université pour les informations pratiques de votre parcours.", "core:contact"),
        ("Comment contacter l’université ?", "Contactez UFHOB-Mali au +223 76 88 24 79 ou utilisez le formulaire de contact sur le site officiel https://www.ufhob-mali.ml.", "core:contact"),
        ("Où consulter les frais de formation ?", "Consultez les frais publiés sur la fiche de votre filière. Pour toute précision sur les versements et les modalités de paiement, contactez l’université.", "formations:list"),
    ]
    questions = [{"question": q, "answer": a, "url_name": url} for q, a, url in items]
    return render(request, "public/faq.html", {
        "faq_items": questions,
        "faq_schema_json": schema_json({
            "@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a, _ in items],
        }),
    })
