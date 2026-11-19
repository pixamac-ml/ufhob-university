# Mission 1 — Catalogue FATEC/ESGA

## Choix d'architecture avant implémentation

Analyse : Programme possède déjà cycle, diplôme, durée, filière, modes, débouchés et mention d'inscription. ProgrammeYear et Fee portent les tarifs et tranches administrables ; RequiredDocument et ProgrammeRequiredDocument portent les pièces. ProgrammeTab/ProgrammeSection portent des conditions éditoriales administrables. Les paiements opérationnels et leurs journaux ne sont pas des tarifs de référence et ne seront pas modifiés.

Décision : réutiliser ces modèles sans migration. Les 24 programmes historiques sont identifiés par leurs slugs stables (pas par des ID dépendants de la base). Les six alias publicitaires seront définis dans un module de compatibilité versionné et redirigés vers les Licences ; aucun second moteur d'admission. Les associations SchoolBranch, candidatures et écoles hors périmètre restent intactes. Les conditions seront stockées dans un onglet Programme existant. Les anciens frais restent conservés ; les montants DUT/Licence seront présentés comme échéancier communiqué, dont le caractère annuel reste à confirmer, sans multiplier le total par la durée. Master présente explicitement ses deux années.

Les pages FATEC/ESGA utiliseront un regroupement par filière puis cycle, avec le shell public existant. Aucun remaniement esthétique général. Le rendu des autres écoles restera sur ses templates actuels.

## Points à confirmer

- Durée DUT : 2 ans, à confirmer.
- Caractère annuel des montants DUT (375 000 FCFA) et Licence (600 000 FCFA).
- Les mois précis des trois versements ne sont pas fournis : ne pas en inventer. Règle générale : au plus tard le 05 du mois.
- memoires.0008 remplace les stockages des fichiers source de mémoire et des images de pages par le fournisseur de stockage privé portable ; migration non appliquée dans cette mission.

## Livraison et validation

Aucune migration créée. `check` : réussi ; `makemigrations --check --dry-run` : aucun changement. Aucun commit, push ni déploiement.

Le dry-run a été exécuté et présenté avant la mutation. Premier passage : 152 créations de références/liens, 30 mises à jour et 96 remplacements de liens de pièces. Aucun programme créé localement : les ID 4–27 sont conservés. Les ID 58–63 restent présents, avec `is_public=False` et `campaign_published=False`. Second passage : **0 création, 0 mise à jour, 0 remplacement de lien**, 422 références inchangées.

Les 96 liens retirés sont uniquement des exigences ProgrammeRequiredDocument devenues obsolètes ; les RequiredDocument eux-mêmes et les CandidatureDocument sont conservés. Sauvegarde préalable : `.tmp-mission1/reference-before.json`. Comparaison sérialisée des programmes hors périmètre, de leurs frais/pièces/onglets, de toutes les écoles, associations SchoolBranch et candidatures/documents : **aucune différence** (`.tmp-mission1/outside-before.json`).

Tarifs administrables : ProgrammeYear/Fee. Trois lignes affichées par échéancier. Les années DUT/Licence historiques supplémentaires restent en base sans modification ni exposition comme coût pluriannuel. Les échéanciers DUT/Licence sont affichés sans présumer de leur annualité. Les mois historiques restent conservés dans Fee ; ils ne sont pas présentés comme dates officiellement validées. Conditions : ProgrammeTab `conditions-catalogue` et ProgrammeSection `Conditions`, éditables dans Django Admin. Dossier : RequiredDocument/ProgrammeRequiredDocument.

Descriptions : les textes des six sources 58–63 sont repris, avec un repère de niveau ajouté au titre, à l’accroche et à la présentation ; aucune compétence, habilitation ou promesse spécifique au niveau n’est inventée. Les débouchés restent ceux fournis. Génie logiciel et Audiovisuel : textes et débouchés historiques conservés, à relire ci-dessous.

## Tableau des 24 formations

| ID | École | Niveau | Intitulé | Slug conservé | Durée | Frais affichés |
|---|---|---|---|---|---|---|
|4|FATEC|DUT|DUT — Informatique de gestion|`informatique-de-gestion-dut`|2 ans — à confirmer|375 000 FCFA (annualité à confirmer)|
|5|FATEC|Licence|Licence — Informatique de gestion|`informatique-de-gestion-licence`|3 ans|600 000 FCFA (annualité à confirmer)|
|6|FATEC|Master|Master — Informatique de gestion|`informatique-de-gestion-master`|2 ans|M1 : 750 000 ; M2 : 850 000 FCFA|
|7|FATEC|DUT|DUT — Génie logiciel|`genie-logiciel-dut`|2 ans — à confirmer|375 000 FCFA (annualité à confirmer)|
|8|FATEC|Licence|Licence — Génie logiciel|`genie-logiciel-licence`|3 ans|600 000 FCFA (annualité à confirmer)|
|9|FATEC|Master|Master — Génie logiciel|`genie-logiciel-master`|2 ans|M1 : 750 000 ; M2 : 850 000 FCFA|
|10|FATEC|DUT|DUT — Réseaux et Télécommunications|`reseau-et-telecommunication-dut`|2 ans — à confirmer|375 000 FCFA (annualité à confirmer)|
|11|FATEC|Licence|Licence — Réseaux et Télécommunications|`reseau-et-telecommunication-licence`|3 ans|600 000 FCFA (annualité à confirmer)|
|12|FATEC|Master|Master — Réseaux et Télécommunications|`reseau-et-telecommunication-master`|2 ans|M1 : 750 000 ; M2 : 850 000 FCFA|
|13|FATEC|DUT|DUT — Audiovisuel multimédia|`audiovisuel-multimedia-dut`|2 ans — à confirmer|375 000 FCFA (annualité à confirmer)|
|14|FATEC|Licence|Licence — Audiovisuel multimédia|`audiovisuel-multimedia-licence`|3 ans|600 000 FCFA (annualité à confirmer)|
|15|FATEC|Master|Master — Audiovisuel multimédia|`audiovisuel-multimedia-master`|2 ans|M1 : 750 000 ; M2 : 850 000 FCFA|
|16|ESGA|DUT|DUT — Finance et Comptabilité|`finance-comptabilite-dut`|2 ans — à confirmer|375 000 FCFA (annualité à confirmer)|
|17|ESGA|Licence|Licence — Finance et Comptabilité|`finance-comptabilite-licence`|3 ans|600 000 FCFA (annualité à confirmer)|
|18|ESGA|Master|Master — Finance et Comptabilité|`finance-comptabilite-master`|2 ans|M1 : 750 000 ; M2 : 850 000 FCFA|
|19|ESGA|DUT|DUT — Gestion des entreprises et administration|`gestion-des-entreprises-et-administration-dut`|2 ans — à confirmer|375 000 FCFA (annualité à confirmer)|
|20|ESGA|Licence|Licence — Gestion des entreprises et administration|`gestion-des-entreprises-et-administration-licence`|3 ans|600 000 FCFA (annualité à confirmer)|
|21|ESGA|Master|Master — Gestion des entreprises et administration|`gestion-des-entreprises-et-administration-master`|2 ans|M1 : 750 000 ; M2 : 850 000 FCFA|
|22|ESGA|DUT|DUT — Gestion des ressources humaines|`gestion-des-ressources-humaines-dut`|2 ans — à confirmer|375 000 FCFA (annualité à confirmer)|
|23|ESGA|Licence|Licence — Gestion des ressources humaines|`gestion-des-ressources-humaines-licence`|3 ans|600 000 FCFA (annualité à confirmer)|
|24|ESGA|Master|Master — Gestion des ressources humaines|`gestion-des-ressources-humaines-master`|2 ans|M1 : 750 000 ; M2 : 850 000 FCFA|
|25|ESGA|DUT|DUT — Marketing et Communication|`marketing-communication-dut`|2 ans — à confirmer|375 000 FCFA (annualité à confirmer)|
|26|ESGA|Licence|Licence — Marketing et Communication|`marketing-communication-licence`|3 ans|600 000 FCFA (annualité à confirmer)|
|27|ESGA|Master|Master — Marketing et Communication|`marketing-communication-master`|2 ans|M1 : 750 000 ; M2 : 850 000 FCFA|

## Redirections et compatibilité admissions

| Ancien slug | Licence canonique | École correcte |
|---|---|---|
|`informatique-de-gestion`|`/formations/fatec/informatique-de-gestion-licence/`|FATEC|
|`reseaux-telecommunications`|`/formations/fatec/reseau-et-telecommunication-licence/`|FATEC|
|`finance-comptabilite`|`/formations/esga/finance-comptabilite-licence/`|ESGA|
|`gestion-des-entreprises-et-administration`|`/formations/esga/gestion-des-entreprises-et-administration-licence/`|ESGA|
|`gestion-des-ressources-humaines`|`/formations/esga/gestion-des-ressources-humaines-licence/`|ESGA|
|`marketing-communication`|`/formations/esga/marketing-communication-licence/`|ESGA|

Les anciennes URLs `/formations/ANCIEN-SLUG/` et `/formations/ANCIENNE-ECOLE/ANCIEN-SLUG/` répondent en 301 vers la bonne Licence. La query string est conservée. `/admissions/?formation=ANCIEN-SLUG` résout la Licence avant la présélection, sans créer un autre tunnel ; les UTM sont maintenus. Les anciens points d’entrée `s-inscrire/SLUG` sont également compatibles.

## Tests

- `formations.test_fatec_esga` : 5 tests ciblés (idempotence/dry-run, 24 pages/écoles/niveaux/frais/pièces/mentions interdites, 12 redirections testées, alias et UTM, 8 Licences d’accueil, conservation d’une candidature liée à un ancien programme).
- `admissions.tests` : 13 tests réussis sur SQLite isolé.
- Aucun faux dossier créé en PostgreSQL local. Aucune suite générale des autres moteurs exécutée. Les anciens tests de campagne basés sur les six offres sans cycle représentent le contrat remplacé et ne sont pas présentés comme compatibles.

## Captures et inspection navigateur

12 captures réelles Microsoft Edge sur le serveur existant, sans relance :

| Page | 390 px | 1366 px |
|---|---|---|
|École FATEC|`.tmp-mission1/capture-0-390.png`|`.tmp-mission1/capture-0-1366.png`|
|École ESGA|`.tmp-mission1/capture-1-390.png`|`.tmp-mission1/capture-1-1366.png`|
|Catalogue|`.tmp-mission1/capture-2-390.png`|`.tmp-mission1/capture-2-1366.png`|
|DUT Informatique de gestion|`.tmp-mission1/capture-3-390.png`|`.tmp-mission1/capture-3-1366.png`|
|Licence Finance et Comptabilité|`.tmp-mission1/capture-4-390.png`|`.tmp-mission1/capture-4-1366.png`|
|Master Réseaux et Télécommunications|`.tmp-mission1/capture-5-390.png`|`.tmp-mission1/capture-5-1366.png`|

Mesures : 12 réponses HTTP 200 ; débordements : 0 ; erreurs JavaScript : []. Les captures DUT, Licence et Master montrent les montants et les pièces dans le navigateur. Le bouton WhatsApp peut masquer un morceau du titre Débouchés en défilement mobile : défaut préexistant documenté, laissé pour la mission 2.

## Textes historiques conservés : points éditoriaux

### DUT — Génie logiciel

Présentation : <p>Programme DUT du domaine Génie Logiciel proposé par Faculté de Technologies Appliquées Cheick Modibo Diarra.</p><p>Objectif : former des professionnels capables d'intervenir dans les métiers liés à Génie Logiciel.</p>

Débouchés : VIDES — à compléter avec la direction

### Licence — Génie logiciel

Présentation : <p>Programme Licence du domaine Génie Logiciel proposé par Faculté de Technologies Appliquées Cheick Modibo Diarra.</p><p>Objectif : former des professionnels capables d'intervenir dans les métiers liés à Génie Logiciel.</p>

Débouchés : VIDES — à compléter avec la direction

### Master — Génie logiciel

Présentation : <p>Programme Master du domaine Génie Logiciel proposé par Faculté de Technologies Appliquées Cheick Modibo Diarra.</p><p>Objectif : former des professionnels capables d'intervenir dans les métiers liés à Génie Logiciel.</p>

Débouchés : VIDES — à compléter avec la direction

### DUT — Audiovisuel multimédia

Présentation : <p>Programme DUT du domaine Audiovisuel Multimédia proposé par Faculté de Technologies Appliquées Cheick Modibo Diarra.</p><p>Objectif : former des professionnels capables d'intervenir dans les métiers liés à Audiovisuel Multimédia.</p>

Débouchés : VIDES — à compléter avec la direction

### Licence — Audiovisuel multimédia

Présentation : <p>Programme Licence du domaine Audiovisuel Multimédia proposé par Faculté de Technologies Appliquées Cheick Modibo Diarra.</p><p>Objectif : former des professionnels capables d'intervenir dans les métiers liés à Audiovisuel Multimédia.</p>

Débouchés : VIDES — à compléter avec la direction

### Master — Audiovisuel multimédia

Présentation : <p>Programme Master du domaine Audiovisuel Multimédia proposé par Faculté de Technologies Appliquées Cheick Modibo Diarra.</p><p>Objectif : former des professionnels capables d'intervenir dans les métiers liés à Audiovisuel Multimédia.</p>

Débouchés : VIDES — à compléter avec la direction

Ces présentations historiques restent génériques ; leur précision et leur adaptation à chaque niveau demandent validation éditoriale. Aucun enrichissement institutionnel inventé.

Incohérences conservées volontairement pour Génie logiciel/Audiovisuel : ancienne graphie du nom FATEC (« Faculté de Technologies Appliquées ») dans les paragraphes historiques et capitalisation différente ; les six champs de débouchés sont vides. Ces contenus ne sont donc pas déclarés complets. Les intitulés, rattachements et en-têtes utilisent bien les graphies demandées.

Contrôle HTTP additionnel sur la vraie base PostgreSQL locale : les 24 pages répondent en 200 ; aucune des mentions interdites recherchées ni l'ancien domaine de contact n'apparaît dans leur HTML. Les six anciennes références ne sont plus publiques. Candidatures locales : toujours zéro.

## Commande et ordre de déploiement VPS (non exécutés)

Prérequis : code de cette mission validé et livré ; écoles FATEC/ESGA actives et association existante au campus Moribabougou. Ne pas lancer `initialiser_catalogue_ufhob` ni `seed_ufhob_catalogue` après cette commande : ces anciennes commandes portent le référentiel remplacé. Aucun dump local à transférer. Sauvegarder la base UFHOB côté VPS avant mutation.

```bash
cd /srv/ufhob
# Avec le même environnement privé et interpréteur que le service Django :
.venv/bin/python manage.py check
.venv/bin/python manage.py charger_catalogue_fatec_esga --dry-run
.venv/bin/python manage.py charger_catalogue_fatec_esga
.venv/bin/python manage.py charger_catalogue_fatec_esga
.venv/bin/python manage.py collectstatic --noinput
# Redémarrage du seul service UFHOB après autorisation du propriétaire.
```

Aucun `migrate` requis par cette mission. Ne pas appliquer `memoires.0008`. La commande doit recevoir les variables privées du VPS par le mécanisme déjà en place ; ne pas remplacer `.env`.

Migrations actuellement en attente, non appliquées : memoires.0008_portable_private_storage.

## Fichiers de la mission

- `formations/fatec_esga.py`
- `formations/management/commands/charger_catalogue_fatec_esga.py`
- `formations/models.py`
- `formations/views.py`
- `formations/test_fatec_esga.py`
- `formations/templates/formations/scoped_catalogue.html`
- `formations/templates/formations/campaign_detail.html`
- `formations/templates/formations/fragments/_scoped_fees.html`
- `admissions/views.py`
- `core/public_views.py`
- `core/views.py`
- `deploy/MISSION1_CATALOGUE_FATEC_ESGA.md`
