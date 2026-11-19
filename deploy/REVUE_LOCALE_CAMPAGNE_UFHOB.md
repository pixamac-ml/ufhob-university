# Revue locale campagne UFHOB — 18 novembre 2026

## A. État général

Inspection réelle par Microsoft Edge piloté par Playwright, sur le serveur existant http://127.0.0.1:8000 (PID 5232, commande UFHOB manage.py runserver). Aucun serveur du propriétaire arrêté ou relancé. Python UFHOB .venv, Django 6.0.5, PostgreSQL ufhob_db vérifiés. Inventaire réalisé dans une transaction PostgreSQL READ ONLY. Aucun enregistrement métier créé, modifié ou supprimé. La navigation peut créer ses cookies/sessions techniques ordinaires. Aucun commit, push, déploiement ni correctif applicatif.

Inventaire : 1 institution ; 4 écoles ; 2 campus ; 5 associations ; 40 programmes ; 40 programmes publics ; 1 classe ; 0 candidature au relevé. Les 6 offres publicitaires ne représentent donc pas tout le catalogue.

Migration en attente, non appliquée : memoires.0008_portable_private_storage.

## B. Écoles

| École | Nom officiel | Statut | Campus | Description institutionnelle | Logo | Rendu |
|---|---|---|---|---|---|---|
|ESGA|École Supérieure de Gestion Alassane Dramane Ouattara|True|Moribabougou|VIDE ; détail VIDE|absent, logo UFHOB de repli|/ecoles/esga/ : voir mesures HTTP ci-dessous ; navigation formations présente|
|FATEC|Faculté des Technologies Appliquées Cheick Modibo Diarra|True|Moribabougou|VIDE ; détail VIDE|absent, logo UFHOB de repli|/ecoles/fatec/ : voir mesures HTTP ci-dessous ; navigation formations présente|

ESMed et ESFé Sup sont également actives. Leur présence est une donnée existante : elle n’est pas assimilée à une erreur sans décision institutionnelle. ESGA et FATEC ont chacune 15 programmes publics (3 offres campagne + 12 parcours historiques). Des disciplines sont présentées dans les deux écoles via des programmes distincts ; rattachements à faire confirmer.

## C. Six formations

| Formation / URL | Description réelle en base | Affichée navigateur | Débouchés | Statut / candidature |
|---|---|---|---|---|
|Finance et Comptabilité — `/formations/esga/finance-comptabilite/`|249 caractères ; 3 phrases|OUI (4 résolutions)|Comptable, Contrôleur de gestion, Assistant financier|HTTP [200] ; actif=True, public=True|
|Gestion des entreprises et administration — `/formations/esga/gestion-des-entreprises-et-administration/`|252 caractères ; 3 phrases|OUI (4 résolutions)|Gestionnaire d’entreprise, Assistant de direction, Responsable administratif|HTTP [200] ; actif=True, public=True|
|Gestion des ressources humaines — `/formations/fatec/gestion-des-ressources-humaines/`|245 caractères ; 3 phrases|OUI (4 résolutions)|Assistant RH, Chargé de recrutement, Gestionnaire de paie|HTTP [200] ; actif=True, public=True|
|Informatique de gestion — `/formations/esga/informatique-de-gestion/`|260 caractères ; 3 phrases|OUI (4 résolutions)|Analyste programmeur, Développeur d’applications, Analyste de données|HTTP [200] ; actif=True, public=True|
|Marketing et Communication — `/formations/fatec/marketing-communication/`|263 caractères ; 3 phrases|OUI (4 résolutions)|Chargé de marketing digital, Community manager, Chargé de communication|HTTP [200] ; actif=True, public=True|
|Réseaux et Télécommunications — `/formations/fatec/reseaux-telecommunications/`|278 caractères ; 3 phrases|OUI (4 résolutions)|Administrateur réseau, Technicien télécoms, Technicien support|HTTP [200] ; actif=True, public=True|

**Finance et Comptabilité — contenu enregistré**

Explorez les fondamentaux de la comptabilité et de la finance d’entreprise. Apprenez à lire les informations financières et à comprendre leur rôle dans la prise de décision. Développez une approche rigoureuse de la gestion et du suivi des activités.

Champs vides : cycle_id, diploma_awarded_id, duration_years, illustration.
Champs présents : id, title, slug, school__code, is_public, is_active, campaign_published, description, short_description, career_opportunities, delivery_modes, registration_notice, meta_title, meta_description.

**Gestion des entreprises et administration — contenu enregistré**

Explorez les principales fonctions de l’entreprise et leurs interactions. Développez vos connaissances en organisation et en coordination administrative. Préparez-vous à accompagner les activités quotidiennes et le suivi des projets d’une organisation.

Champs vides : cycle_id, diploma_awarded_id, duration_years, illustration.
Champs présents : id, title, slug, school__code, is_public, is_active, campaign_published, description, short_description, career_opportunities, delivery_modes, registration_notice, meta_title, meta_description.

**Gestion des ressources humaines — contenu enregistré**

Découvrez les principales activités de la gestion des ressources humaines. Explorez le recrutement, le suivi administratif du personnel et les principes de la paie. Développez une approche attentive et structurée de l’accompagnement des équipes.

Champs vides : cycle_id, diploma_awarded_id, duration_years, illustration.
Champs présents : id, title, slug, school__code, is_public, is_active, campaign_published, description, short_description, career_opportunities, delivery_modes, registration_notice, meta_title, meta_description.

**Informatique de gestion — contenu enregistré**

Découvrez comment l’informatique accompagne la gestion des organisations. Approfondissez votre compréhension des applications et de l’exploitation des données. Développez une démarche d’analyse pour proposer des solutions adaptées aux besoins des utilisateurs.

Champs vides : cycle_id, diploma_awarded_id, duration_years, illustration.
Champs présents : id, title, slug, school__code, is_public, is_active, campaign_published, description, short_description, career_opportunities, delivery_modes, registration_notice, meta_title, meta_description.

**Marketing et Communication — contenu enregistré**

Explorez les fondamentaux du marketing et de la communication des organisations. Découvrez comment comprendre un public, construire un message et choisir des canaux adaptés. Développez une approche cohérente des contenus et des actions de communication numérique.

Champs vides : cycle_id, diploma_awarded_id, duration_years, illustration.
Champs présents : id, title, slug, school__code, is_public, is_active, campaign_published, description, short_description, career_opportunities, delivery_modes, registration_notice, meta_title, meta_description.

**Réseaux et Télécommunications — contenu enregistré**

Découvrez les principes des réseaux informatiques et des télécommunications. Développez votre compréhension de la connectivité, de l’administration et du support des infrastructures. Adoptez une démarche méthodique pour analyser les besoins et résoudre les incidents techniques.

Champs vides : cycle_id, diploma_awarded_id, duration_years, illustration.
Champs présents : id, title, slug, school__code, is_public, is_active, campaign_published, description, short_description, career_opportunities, delivery_modes, registration_notice, meta_title, meta_description.

Les six descriptions sont des contenus de campagne de trois phrases, pas des champs vides validés par défaut. Les identifiants 58–63 correspondent aux six créations de la mission précédente (selon son journal local). Les autres références sont antérieures ; leur origine réelle/démonstration n’est pas déductible avec certitude des seuls champs. Aucun nettoyage effectué.

## D. Accueil

En-tête/menu, bannière, présentation, vision/mission/valeurs, rectorat, gouvernance, écoles, six formations, recherche, campus, vie universitaire, actualités, CTA et pied de page présents. Les compteurs 4/40/1 reflètent les données actives, sans compteur nul inventé. Contact provisoire et WhatsApp présents. Les cartes des écoles sans description sont visiblement moins informatives. La section Actualités affiche un état vide. Le bloc présentation réserve une grande place à une image absente et son cartouche « Notre signature » frôle/recouvre le lien de découverte sur la capture mobile.

## E. Admissions

Depuis chacune des six offres : clic réel vers le tunnel ; relevé de la formation présélectionnée et des UTM (table ci-dessous). Aucun POST d’admission autorisé par le navigateur connecté au PostgreSQL du propriétaire. Les créations de dossiers sont testées exclusivement avec config.settings_test_campaign, SQLite isolé.

La suite standard a obtenu 21 succès serveur et une erreur du test navigateur : sélecteur ambigu pendant la transition Alpine (deux boutons Suivant visibles temporairement). Le script de recette temporaire cible l’étape active et attend la fin de la transition ; résultat complémentaire indiqué en livraison. Aucun fichier de test applicatif corrigé.

| Formation demandée | Résolutions contrôlées | Présélection | UTM |
|---|---|---|---|
|finance-comptabilite|[320, 390, 768, 1366]|True|True|
|gestion-des-entreprises-et-administration|[320, 390, 768, 1366]|True|True|
|gestion-des-ressources-humaines|[320, 390, 768, 1366]|True|True|
|informatique-de-gestion|[320, 390, 768, 1366]|True|True|
|marketing-communication|[320, 390, 768, 1366]|True|True|
|reseaux-telecommunications|[320, 390, 768, 1366]|True|True|

## F. Mobile et bureau

| Largeur | Vues mesurées | Débordements horizontaux | Erreurs de mesure |
|---|---|---|---|
|320|11|[]|[]|
|390|11|[]|[{'page': '/', 'erreur': 'Locator.click: Timeout 30000ms exceeded.\nCall log:\n  - waiting for get_by_role("button", name="Ouvrir le menu")\n    - locator resolved to <button type="button" aria-expanded="false" :aria-expanded="menuOpen" aria-label="Ouvrir le menu" @click="menuOpen = !menuOpen" class="ml-auto rounded-ufhob-sm border border-white/20 p-2.5 xl:hidden">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    51 × waiting for element to be visible, enabled and stable\n       - element is visible, enabled and stable\n       - scrolling into view if needed\n       - done scrolling\n       - element is outside of the viewport\n     - retrying click action\n       - waiting 500ms\n'}]|
|768|11|[]|[]|
|1366|11|[]|[]|

## G. Anomalies

- **P0 :** aucun blocage des six pages établi par les mesures réussies. Les éventuels échecs techniques ci-dessous restent des réserves, pas des validations implicites.
- **P1 confirmé :** `/plan-du-site/` renvoie HTTP 500 : `FieldError`, tri sur `School.display_order` inexistant (champ réel `order`). Lien présent dans le pied de page. Aucun correctif réalisé.
- **P1 :** descriptions institutionnelles ESGA/FATEC vides ; logos spécifiques absents. Le texte de repli ne remplace pas une présentation validée.
- **P1 :** périmètre éditorial à valider : 4 écoles/40 programmes affichés, incluant ESFé Sup et les déclinaisons historiques dont certaines disciplines sont rattachées différemment des six offres publicitaires.
- **P1 :** cartouche de présentation de l’accueil à contrôler au mobile : espace vide et proximité du lien ; voir capture.
- **P2 :** compteurs du pied de page : mots « COMPOSANTES » et « FORMATIONS » coupés sur plusieurs lignes à 320 px.
- **P2 :** WhatsApp peut recouvrir du texte pendant le défilement (capture Finance 320 : voisin du titre Débouchés) ; aucun recouvrement du CTA initial constaté.
- **P2 :** section actualités vide ; ne pas la considérer comme un contenu institutionnel final.
- **P2 :** test navigateur existant sensible au chevauchement transitoire des boutons Alpine ; réserve sur la stabilité de la recette automatisée.

Erreurs JavaScript relevées :
```json
[]
```
Réponses HTTP >=400 observées (ressources incluses) :
```json
[]
```
Destinations internes ne répondant pas en 2xx/3xx :
```json
[
  {
    "url": "/plan-du-site/",
    "status": 500
  }
]
```

## H. Captures et preuves

Captures : `.tmp-revue-locale/page-NN-LARGEUR.png` ; 00 accueil, 01 ESGA, 02 FATEC, 03 catalogue, 04 contact, 05 finance, 06 informatique, 07 gestion entreprises, 08 réseaux, 09 marketing, 10 RH. Menu mobile : `.tmp-revue-locale/menu-mobile.png` si disponible. Captures de candidature isolée : `.tmp-campaign-browser/`.

Inventaire ORM complet sans coordonnées personnelles : `.tmp-revue-locale/inventory.json`. Mesures navigateur, textes effectivement rendus, métadonnées OG, liens, couleurs et positions CTA : `.tmp-revue-locale/browser.json`. Les images signalées non chargées au relevé peuvent être simplement différées : la photo du recteur a été vérifiée séparément HTTP 200 image/jpeg ; ne pas la classer comme lien cassé sur ce seul indicateur.

## I. Recommandations avant publication

1. Faire valider le périmètre des quatre écoles et des quarante programmes, sans suppression automatique.
2. Fournir les descriptions officielles et logos ESGA/FATEC.
3. Valider les coordonnées et les anciennes présentations institutionnelles affichées.
4. Faire approuver les corrections de chevauchement/espacement et des compteurs mobiles avant modification.
5. Examiner les erreurs HTTP/JavaScript et réserves de mesure ci-dessus ; traiter tout lien public cassé confirmé.
6. Garder la migration en attente identifiée hors de cette inspection ; planifier son traitement séparément.
7. Ne pas assimiler un succès serveur à une validation exhaustive du contenu institutionnel.

### Inventaire détaillé des références existantes
```json
{
  "institutions": [
    {
      "id": 1,
      "name": "Université Félix Houphouët Boigny - Mali",
      "short_name": "UFHOB"
    }
  ],
  "campuses": [
    {
      "id": 2,
      "name": "Djélibougou",
      "slug": "djelibougou",
      "is_active": false,
      "accepts_online_registration": true
    },
    {
      "id": 1,
      "name": "Moribabougou",
      "slug": "moribabougou",
      "is_active": true,
      "accepts_online_registration": true
    }
  ],
  "presences": [
    {
      "school__code": "ESMED",
      "branch__name": "Djélibougou",
      "is_active": false
    },
    {
      "school__code": "ESMED",
      "branch__name": "Moribabougou",
      "is_active": true
    },
    {
      "school__code": "ESGA",
      "branch__name": "Moribabougou",
      "is_active": true
    },
    {
      "school__code": "FATEC",
      "branch__name": "Moribabougou",
      "is_active": true
    },
    {
      "school__code": "ESFÉ",
      "branch__name": "Moribabougou",
      "is_active": true
    }
  ],
  "years": [
    {
      "name": "2026-2027",
      "is_active": true,
      "start_date": "2026-10-01",
      "end_date": "2027-07-31"
    }
  ],
  "classes": [
    {
      "id": 75,
      "name": "Master 1 Biologie Médicale",
      "programme__title": "Master — Biologie Médicale",
      "branch__name": "Moribabougou"
    }
  ]
}
```

### Statuts HTTP et CTA par page/résolution
```json
[
  {
    "path": "/",
    "width": 320,
    "status": 200
  },
  {
    "path": "/ecoles/esga/",
    "width": 320,
    "status": 200
  },
  {
    "path": "/ecoles/fatec/",
    "width": 320,
    "status": 200
  },
  {
    "path": "/formations/",
    "width": 320,
    "status": 200
  },
  {
    "path": "/contact/",
    "width": 320,
    "status": 200
  },
  {
    "path": "/formations/esga/finance-comptabilite/",
    "width": 320,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=finance-comptabilite",
      "box": {
        "x": 16,
        "y": 254.375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/esga/informatique-de-gestion/",
    "width": 320,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=informatique-de-gestion",
      "box": {
        "x": 16,
        "y": 254.375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/esga/gestion-des-entreprises-et-administration/",
    "width": 320,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=gestion-des-entreprises-et-administration",
      "box": {
        "x": 16,
        "y": 286.5625,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/reseaux-telecommunications/",
    "width": 320,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=reseaux-telecommunications",
      "box": {
        "x": 16,
        "y": 286.5625,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/marketing-communication/",
    "width": 320,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=marketing-communication",
      "box": {
        "x": 16,
        "y": 254.375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/gestion-des-ressources-humaines/",
    "width": 320,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=gestion-des-ressources-humaines",
      "box": {
        "x": 16,
        "y": 286.5625,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/",
    "width": 390,
    "error": "Locator.click: Timeout 30000ms exceeded.\nCall log:\n  - waiting for get_by_role(\"button\", name=\"Ouvrir le menu\")\n    - locator resolved to <button type=\"button\" aria-expanded=\"false\" :aria-expanded=\"menuOpen\" aria-label=\"Ouvrir le menu\" @click=\"menuOpen = !menuOpen\" class=\"ml-auto rounded-ufhob-sm border border-white/20 p-2.5 xl:hidden\">…</button>\n  - attempting click action\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n    - waiting 20ms\n    2 × waiting for element to be visible, enabled and stable\n      - element is visible, enabled and stable\n      - scrolling into view if needed\n      - done scrolling\n      - element is outside of the viewport\n    - retrying click action\n      - waiting 100ms\n    51 × waiting for element to be visible, enabled and stable\n       - element is visible, enabled and stable\n       - scrolling into view if needed\n       - done scrolling\n       - element is outside of the viewport\n     - retrying click action\n       - waiting 500ms\n"
  },
  {
    "path": "/ecoles/esga/",
    "width": 390,
    "status": 200
  },
  {
    "path": "/ecoles/fatec/",
    "width": 390,
    "status": 200
  },
  {
    "path": "/formations/",
    "width": 390,
    "status": 200
  },
  {
    "path": "/contact/",
    "width": 390,
    "status": 200
  },
  {
    "path": "/formations/esga/finance-comptabilite/",
    "width": 390,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=finance-comptabilite&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 16,
        "y": 222.1875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/esga/informatique-de-gestion/",
    "width": 390,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=informatique-de-gestion&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 16,
        "y": 222.1875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/esga/gestion-des-entreprises-et-administration/",
    "width": 390,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=gestion-des-entreprises-et-administration&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 16,
        "y": 254.375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/reseaux-telecommunications/",
    "width": 390,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=reseaux-telecommunications&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 16,
        "y": 254.375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/marketing-communication/",
    "width": 390,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=marketing-communication&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 16,
        "y": 254.375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/gestion-des-ressources-humaines/",
    "width": 390,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=gestion-des-ressources-humaines&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 16,
        "y": 254.375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/",
    "width": 768,
    "status": 200
  },
  {
    "path": "/ecoles/esga/",
    "width": 768,
    "status": 200
  },
  {
    "path": "/ecoles/fatec/",
    "width": 768,
    "status": 200
  },
  {
    "path": "/formations/",
    "width": 768,
    "status": 200
  },
  {
    "path": "/contact/",
    "width": 768,
    "status": 200
  },
  {
    "path": "/formations/esga/finance-comptabilite/",
    "width": 768,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=finance-comptabilite&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 24,
        "y": 242.984375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/esga/informatique-de-gestion/",
    "width": 768,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=informatique-de-gestion&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 24,
        "y": 242.984375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/esga/gestion-des-entreprises-et-administration/",
    "width": 768,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=gestion-des-entreprises-et-administration&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 24,
        "y": 295.96875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/reseaux-telecommunications/",
    "width": 768,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=reseaux-telecommunications&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 24,
        "y": 295.96875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/marketing-communication/",
    "width": 768,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=marketing-communication&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 24,
        "y": 242.984375,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/gestion-des-ressources-humaines/",
    "width": 768,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=gestion-des-ressources-humaines&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 24,
        "y": 295.96875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/",
    "width": 1366,
    "status": 200
  },
  {
    "path": "/ecoles/esga/",
    "width": 1366,
    "status": 200
  },
  {
    "path": "/ecoles/fatec/",
    "width": 1366,
    "status": 200
  },
  {
    "path": "/formations/",
    "width": 1366,
    "status": 200
  },
  {
    "path": "/contact/",
    "width": 1366,
    "status": 200
  },
  {
    "path": "/formations/esga/finance-comptabilite/",
    "width": 1366,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=finance-comptabilite&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 75,
        "y": 253.1875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/esga/informatique-de-gestion/",
    "width": 1366,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=informatique-de-gestion&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 75,
        "y": 253.1875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/esga/gestion-des-entreprises-et-administration/",
    "width": 1366,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=gestion-des-entreprises-et-administration&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 75,
        "y": 253.1875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/reseaux-telecommunications/",
    "width": 1366,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=reseaux-telecommunications&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 75,
        "y": 253.1875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/marketing-communication/",
    "width": 1366,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=marketing-communication&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 75,
        "y": 253.1875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  },
  {
    "path": "/formations/fatec/gestion-des-ressources-humaines/",
    "width": 1366,
    "status": 200,
    "cta": {
      "url": "/admissions/?formation=gestion-des-ressources-humaines&utm_source=recette&utm_campaign=audit",
      "box": {
        "x": 75,
        "y": 253.1875,
        "width": 245.3125,
        "height": 52.78125
      },
      "background": "rgb(245, 130, 32)"
    }
  }
]
```
## Résultats complémentaires de recette

- 11 pages publiques contrôlées visuellement aux 4 largeurs, soit 44 vues ; 6 entrées de candidature à chaque largeur, soit 24 présélections. 113 destinations internes contrôlées, une erreur 500 confirmée.
- 45 captures enregistrées, dont le menu ouvert. Le premier essai de clic menu à 390 px échoue car le menu est volontairement hors écran au sommet du hero ; après défilement vers Nos écoles, ouverture réelle réussie (`aria-expanded=true`, liens visibles). Cette réserve de mesure ne constitue donc pas un menu cassé.
- Les 21 tests serveur de la suite standard passent ; son test navigateur échoue sur un sélecteur ambigu pendant les transitions. Relance avec un adaptateur de recette temporaire ciblant l’étape active et attendant 350 ms : **test navigateur complet réussi**, formulaire soumis et formation/UTM persistés exclusivement dans SQLite isolé. Les quatre étapes et la confirmation ont été traversées. Aucun POST de candidature effectué sur PostgreSQL local.
- Les titres et boutons des six pages apparaissent dans le premier écran à toutes les résolutions : bas du CTA entre 275 et 349 px. Boutons orange `rgb(245, 130, 32)`. Aucun débordement horizontal sur les 44 vues.
- Aucun tarif ni mention État/CAMES trouvé dans les textes rendus des six pages de campagne ; les contenus historiques des autres formations ne sont pas validés par ce constat.
- P0 établi : aucun. Réserves P1 : page plan du site en erreur, présentations/logo des deux écoles manquants, périmètre éditorial historique et espacement du bloc présentation à valider. P2 : compteurs mobiles, WhatsApp sur le texte au défilement, actualités vides et stabilité du test.

### Inventaire des programmes

| ID | Programme | École | Public (champ) | Actif | Campagne | Description (caractères) |
|---|---|---|---|---|---|---|
|3|Chirurgie dentaire|ESMED|True|True|False|258|
|13|DUT — Audiovisuel multimédia|FATEC|True|True|False|236|
|16|DUT — Finance / Comptabilité|ESGA|True|True|False|234|
|7|DUT — Génie logiciel|FATEC|True|True|False|220|
|19|DUT — Gestion des entreprises et administration|ESGA|True|True|False|272|
|22|DUT — Gestion des ressources humaines|ESGA|True|True|False|252|
|4|DUT — Informatique de gestion|FATEC|True|True|False|238|
|25|DUT — Marketing communication|ESGA|True|True|False|236|
|10|DUT — Réseau et télécommunication|FATEC|True|True|False|246|
|58|Finance et Comptabilité|ESGA|True|True|True|249|
|60|Gestion des entreprises et administration|ESGA|True|True|True|252|
|63|Gestion des ressources humaines|FATEC|True|True|True|245|
|59|Informatique de gestion|ESGA|True|True|True|260|
|14|Licence — Audiovisuel multimédia|FATEC|True|True|False|240|
|17|Licence — Finance / Comptabilité|ESGA|True|True|False|238|
|8|Licence — Génie logiciel|FATEC|True|True|False|224|
|20|Licence — Gestion des entreprises et administration|ESGA|True|True|False|276|
|23|Licence — Gestion des ressources humaines|ESGA|True|True|False|256|
|5|Licence — Informatique de gestion|FATEC|True|True|False|242|
|26|Licence — Marketing communication|ESGA|True|True|False|240|
|11|Licence — Réseau et télécommunication|FATEC|True|True|False|250|
|62|Marketing et Communication|FATEC|True|True|True|263|
|15|Master — Audiovisuel multimédia|FATEC|True|True|False|239|
|51|Master — Biologie Médicale|ESFÉ|True|True|False|247|
|55|Master — Épidémiologie|ESFÉ|True|True|False|267|
|18|Master — Finance / Comptabilité|ESGA|True|True|False|237|
|9|Master — Génie logiciel|FATEC|True|True|False|223|
|21|Master — Gestion des entreprises et administration|ESGA|True|True|False|275|
|24|Master — Gestion des ressources humaines|ESGA|True|True|False|255|
|52|Master — Gynécologie Obstétrique|ESFÉ|True|True|False|262|
|6|Master — Informatique de gestion|FATEC|True|True|False|241|
|53|Master — Manager en Santé|ESFÉ|True|True|False|251|
|27|Master — Marketing communication|ESGA|True|True|False|239|
|56|Master — Nutrition|ESFÉ|True|True|False|264|
|54|Master — Pédagogie en Santé|ESFÉ|True|True|False|265|
|12|Master — Réseau et télécommunication|FATEC|True|True|False|249|
|57|Master — Santé Environnementale|ESFÉ|True|True|False|279|
|1|Médecine|ESMED|True|True|False|326|
|2|Pharmacie|ESMED|True|True|False|348|
|61|Réseaux et Télécommunications|FATEC|True|True|True|278|

Les descriptions non vides des autres programmes ne sont pas certifiées complètes éditorialement par ce relevé. Les six descriptions publicitaires sont vérifiées en base et dans les textes du navigateur. Aucun changement aux références ESFé ni à esfe_db ; aucun fichier de production modifié.
