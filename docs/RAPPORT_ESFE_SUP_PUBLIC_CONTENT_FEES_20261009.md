# UFHOB-MALI — ESFé SUP / PUBLIC CONTENT + FEES

Mission P0 du 9 octobre 2026. Modifications réellement appliquées à `ufhob_db`. Vitrine et tarifs prêts ; le chantier académique demeure PARTIAL et n’a pas été modifié.

## SCHOOL

Canonical name : **ESFé Sup**.

School ID : **4**. Code technique : ESFÉ, inchangé. Campus : **Moribabougou**, issu de SchoolBranch active #5 / Branch #1.

PUBLIC SCHOOL PAGE : **PASS**. Présentation institutionnelle, domaines de formation, orientations pédagogiques, informations pratiques, programmes, perspectives professionnelles et campus affichés à partir des données DB. Aucun chiffre, partenaire, accréditation ou équipement ajouté.

## PROGRAMMES

| Programme | Description / objectifs / compétences / débouchés | Frais M1 | Frais M2 | Public |
|---|---|---:|---:|---|
| #51 Biologie Médicale | Enrichis et persistés | 810 000 | 810 000 | PASS |
| #52 Gynécologie Obstétrique | Enrichis et persistés | 810 000 | 810 000 | PASS |
| #53 Manager en Santé | Enrichis et persistés | 810 000 | 810 000 | PASS |
| #54 Pédagogie en Santé | Enrichis et persistés | 810 000 | 810 000 | PASS |
| #55 Épidémiologie | Enrichis et persistés | 810 000 | 1 200 000 | PASS |
| #56 Nutrition | Enrichis et persistés | 810 000 | 1 200 000 | PASS |
| #57 Santé Environnementale | Enrichis et persistés | 810 000 | 1 200 000 | PASS |

Montants en XOF / F CFA. Les sept Programme et leurs quatorze ProgrammeYear ont été réutilisés. Durée affichée depuis Programme.duration_years ; années triées sur year_number. Objectifs dans learning_outcomes ; trois compétences par formation dans les modèles CompetenceBlock/CompetenceItem existants ; domaines professionnels possibles dans career_opportunities ; organisation générale dans program_structure.

Les orientations éditoriales sont celles autorisées par l’utilisateur, y compris le complément Épidémiologie/Nutrition/Santé Environnementale. Elles ne constituent pas une maquette pédagogique ni une promesse d’emploi. Les perspectives sont liées au parcours préalable et aux conditions propres aux fonctions concernées ; aucun droit automatique à exercer un acte réglementé n’est attribué au diplôme.

Aucune condition d’admission spécifique n’a été créée. Les pièces existantes restent utilisées ; pour les parcours non EsMed sans conditions détaillées, le texte public invite à vérifier les conditions auprès de l’école. Admissions des sept Masters toujours fermées ; les boutons de candidature ne sont pas affichés pour ces programmes. La page école propose la consultation des Masters.

## FEES

pricing model used : **formations.Fee → ProgrammeYear → Programme → School**.

records created : **42 Fee**. records updated : **0 Fee**.

Group A M1 total : **810000**.

Group A M2 total : **810000**.

Group B M1 total : **810000**.

Group B M2 total : **1200000**.

| Groupe / année | Inscription | Janvier | Mars | Total calculé |
|---|---:|---:|---:|---:|
| A — 1re année | 410 000 | 200 000 | 200 000 | 810 000 |
| A — 2e année | 410 000 | 200 000 | 200 000 | 810 000 |
| B — 1re année | 410 000 | 200 000 | 200 000 | 810 000 |
| B — 2e année | 600 000 | 300 000 | 300 000 | 1 200 000 |

Source : fiche institutionnelle tarifaire communiquée explicitement par l’utilisateur dans cette mission. « Inscription » ne reçoit pas un mois civil inventé : due_month = « À l’inscription ». Janvier et Mars conservent les mois fournis. Le modèle existant utilise déjà les francs CFA et ne nécessite pas AcademicYear. Pas de nouvelle structure de tarification ou de devise ; le manifeste opérationnel précise XOF.

Les totaux ne sont pas enregistrés comme valeurs indépendantes : la vue calcule la somme des Fee. Aucune table de prix dans les vues ou templates. Les montants du manifeste sont utilisés uniquement par la commande d’installation ; la vitrine lit la DB. Les échéances sont ordonnées numériquement : inscription en premier, puis mois calendaires ; en cas d’autres libellés existants, tri stable par libellé/id. Un tarif absent affiche « Tarifs non renseignés », jamais zéro ni un prix inventé.

Le modèle existant est également consulté par le catalogue/admissions pour les coûts. Aucun paiement, facture, écriture comptable ou plan de prélèvement créé. Aucun moteur de paiement ou règle comptable modifié.

## ORDER

M1 before M2 : **PASS** — test de réponse HTML avec ProgrammeYear 2 créé avant ProgrammeYear 1. Cartes tarifaires identifiées par data-cursus-year, ordre 1 puis 2 ; libellés 1re année puis 2e année.

S1 before S2 before S3 before S4 : **NON APPLICABLE à ces fiches publiques**. Aucun semestre n’est publié/créé dans cette passe. Le modèle Semester possède déjà le tri numérique par academic_class puis number ; aucun tri textuel ou contenu S4 inventé. La mission académique reste PARTIAL.

School : ordre configuré existant préservé. Programme : ordre stable existant préservé. ProgrammeYear : year_number ascendant explicitement préchargé par la vue. Fee : inscription, puis ordre numérique des mois.

## PUBLIC

School detail : **PASS** — `/ecoles/esfé/` et `/universite/` HTTP 200.

Programme cards : **PASS** — nom Programme exact, école, cycle, durée DB et lien détail ; résumé limité, aucun tarif complet ajouté aux cartes.

Programme detail : **PASS** — sept pages HTTP 200, présentation, objectifs, compétences, débouchés, organisation, durée, diplôme, école et campus.

Fee display : **PASS** — format « 410 000 F CFA », échéances exactes et total annuel calculé. Composant partagé réutilisé pour toutes les écoles ; toutes les années disposant de frais peuvent être affichées.

Responsive : **PASS** — navigateur réel Microsoft Edge headless avec Playwright ; huit pages (école + sept Masters), chacune à 390, 768, 1024 et 1440 px : **32 cas sans débordement horizontal**. Bornes des cartes de frais vérifiées et ordre 1/2 contrôlé dans le DOM. Captures disponibles aux quatre largeurs. Mise en page verticale sur mobile, deux colonnes à partir du breakpoint adapté.

OTHER SCHOOLS REGRESSION : **PASS** — pages des écoles EsMed/ESGA/FATEC accessibles ; leurs 3/12/12 programmes publics ont tous été consultés ; les totaux affichés correspondent à leurs propres Fee. Aucun prix ESFé Sup, nouveau texte ou nouvelle formation écrit dans les autres écoles. Le test isolé vérifie également qu’un tarif différent reste affiché tel quel après import ESFé Sup.

SEO : title, meta description, H1 et hiérarchie H2 vérifiés sur les neuf routes principales. Résumés publics issus des champs éditoriaux réels ; pas de mots-clés artificiels.

Contrôles sur les vues locales du projet et `ufhob_db` ; aucun déploiement distant effectué. Les dépendances web externes sont bloquées pendant le contrôle navigateur ; CSS/JS locaux utilisés et animations neutralisées uniquement pour la capture, sans changement du comportement de production.

## IMAGES

Official ESFé Sup images installed : **NO — awaiting user-provided assets**.

Fallback working : **YES** — logo UFHOB existant. Hero/illustration conditionnels : aucune balise src vide, aucun visuel stock ou IA, aucun téléchargement. Les champs School.hero_image, School.logo et Programme.illustration restent prêts pour l’intégration ultérieure des visuels officiels.

## INSTALLATION / IDEMPOTENCE

Dry-run : 42 Fee à créer, sept programmes et une école à enrichir, sept blocs et 21 compétences à créer ; aucune écriture persistée.

Apply : résultats correspondants réellement appliqués.

Seconde application : **0** Fee créée/modifiée, **0** programme modifié, **0** école modifiée, **0** bloc/compétence créé/modifié. Aucun doublon. Les frais supplémentaires non documentés provoquent une erreur et un rollback, sans suppression silencieuse.

## TESTS / CHECK / MIGRATIONS

Tests ciblés : **10 tests PASS** — formations.test_esfe_sup_public et formations.test_esf_sup_masters, SQLite séparée tmp/esf_sup_masters_test.sqlite3. Vérification des montants individuels et totaux des sept formations, dry-run, idempotence, ordre HTML malgré création inversée, contenus, absence de nouvelle année/classes/semestres/UE/EC, rollback sur conflit tarifaire, visibilité et autres écoles.

Contrôles live : neuf routes principales et les 27 programmes publics des autres écoles via Django Client ; transaction READ ONLY pour les contrôles DB. Navigateurs : 32 cas PASS, preuves et captures dans artifacts/esfe_sup_public_p0/.

manage.py check : **PASS — 0 problème**.

makemigrations --check --dry-run : **PASS — No changes detected**.

Migrations : **0**. Aucun changement de schéma nécessaire.

npm run build:css : **PASS**, CSS public recompilé avec les composants existants. Avertissement Browserslist/caniuse-lite ancien, sans échec ; aucune dépendance mise à jour. Avertissements Windows GLib/GIO lors de certains processus, sans échec des validations.

Suite globale non exécutée : tests ciblés et contrôle des pages réellement concernées réalisés. Aucune donnée de test ajoutée dans PostgreSQL.

## FICHIERS ET PREUVES

- docs/esfe_sup_public_content.json : tarifs institutionnels et contenus autorisés, source d’import.
- formations/esfe_sup_public.py : service transactionnel idempotent, réutilisation des modèles.
- formations/management/commands/install_esfe_sup_public.py : dry-run/apply limité à ufhob_db.
- formations/test_esfe_sup_public.py : tests tarifaires, ordre, publics et préservation.
- formations/templatetags/formation_display.py : montants F CFA et libellés d’année.
- formations/templates/formations/fragments/_fees.html : cartes tarifaires partagées.
- formations/views.py : tri des échéances et préchargement des compétences.
- formations/templates/formations/detail.html : section frais partagée, compétences/organisation, durée et illustration conditionnelle.
- core/public_views.py : état des candidatures de l’école calculé depuis les programmes.
- templates/public/school_detail.html : absence d’image gérée, campus issu des relations actives, CTA conforme à l’état des admissions.
- templates/cotton/public/programme_card.html : école et cycle explicites.
- static/public/css/main.css : sortie du build CSS.
- artifacts/esfe_sup_public_dry_run_20261009.json, artifacts/esfe_sup_public_apply_20261009.json, artifacts/esfe_sup_public_second_run_20261009.json : résultats d’installation.
- artifacts/esfe_sup_public_p0/checks.json et captures school-*/fees-* : vérifications et responsive.

Les modifications antérieures/concurrentes du dépôt ont été conservées. Aucun nouveau School, Programme, ProgrammeYear, Campus ou SchoolBranch. Aucun changement à AcademicYear, AcademicClass, Semester, UE ou EC (tous toujours absents dans la base opérationnelle). ESFé Sup conserve son nom canonique, son code historique et son unique campus Moribabougou. Djélibougou demeure désactivé.

esfe-core touched : **NO**. esfe_db touched : **NO**.

**READY_FOR_ESFE_SUP_PUBLIC_CONTENT: YES**

**READY_FOR_ESFE_SUP_FEES: YES**

Mission arrêtée après cette passe. Images officielles à intégrer séparément quand l’utilisateur les fournira ; chantier académique non débloqué artificiellement.
