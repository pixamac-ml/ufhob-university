# UFHOB — Alignement transversal des dashboards

Mission du 9 septembre 2026, définie par `temp.txt` modifié à 13:14. Les phases 1, 2 et 3A constituent le point de départ. Ce rapport distingue les corrections de cette mission des nombreuses modifications déjà présentes dans le dépôt.

## A. Architecture auditée

Lecture d’`AGENTS.md`, de `temp.txt`, des rapports des phases 2 et 3A, des modèles et tests universitaires. Inspection du registre des positions, d’InstitutionalProfile, d’AccessContext, des permissions, des routes, formulaires, services, sélecteurs et templates concernés.

Architecture conservée : une université, une base, une authentification, des moteurs partagés. Programme fournit School ; SchoolBranch représente l’implantation plusieurs-à-plusieurs sur les campus. Aucun champ School ajouté aux dossiers ou aux classes. Aucun moteur, shell ou système de permissions dupliqué.

## B. Dashboards découverts

DG/DGA, DE, gestionnaire d’annexe, responsable financier, agent de paiement, admissions, secrétariat, IT, enseignant, moniteur/monitrice, surveillance, étudiant, marketing et superadministration. Les positions enseignantes partagent le même moteur ; les positions financières réutilisent le contrat du workspace gestionnaire.

## C. Matrice rôle/scope

Voir [la matrice initiale](UFHOB_DASHBOARDS_MATRICE_AUDIT.md), rédigée avant les corrections. Les sources d’autorisation restent distinctes des filtres de navigation. Le contexte opérationnel d’une école peut être restreint à un campus autorisé sans modifier l’affectation institutionnelle enregistrée.

## D. DG

Conservation de la phase 3A : GLOBAL, SCHOOL, BRANCH et SCHOOL_BRANCH, année, sélection mémorisée, exports et refus des couples invalides. La suite `portal.test_dg_university` est incluse dans la régression. Pas de nouvelle refonte DG dans cette mission.

## E. DE

Formulaires de classes, programmes, semestres, UE, EC et évaluations reliés aux querysets contextualisés. Les affectations pédagogiques directes à un semestre, une UE ou un EC sont également reconnues par le scoping partagé. Les synthèses de planning filtrent School ; la détection de conflits de ressources reste transversale aux écoles. Un enseignant ou une salle ne peut pas être réservé deux fois simplement parce que les cours appartiennent à deux écoles.

## F. Gestionnaire / finance / admissions

Paiements et candidatures continuent à dériver School du dossier. L’export CSV des paiements reconnaît désormais la capacité existante `view_payments` du contrat gestionnaire, et utilise le même queryset autorisé. Recette avec un paiement de l’école locale, un d’une autre école sur le même campus et un de la même école sur un autre campus.

Les écritures de caisse, dépenses et mouvements physiques restent des données de campus lorsqu’aucune ventilation académique fiable n’existe. Aucun montant n’est artificiellement attribué à une école. Aucune modification des reçus, OTP, règles salariales ou calculs comptables.

## G. Secrétaire

Les choix de personnel sont filtrés par l’acteur, y compris hors middleware. Les recherches d’étudiants utilisent l’inscription académique courante, avec repli pour les dossiers anciens. Correction du chemin de relation des inscriptions dans la recherche par classe.

Les pièces, visites, rendez-vous, tâches et historiques préchargés dans une fiche étudiant utilisent leurs sélecteurs autorisés. Un campus enregistré ou une personne liée ne peut pas être remplacé par un simple OR sur le campus de l’auteur. Un identifiant de personnel d’une autre école est refusé par la validation du formulaire.

## H. Informaticien

Correction des recherches de comptes, choix de classes et EC, diagnostics, tickets, journaux, cartes étudiantes et de personnel, ainsi que leurs vérifications QR. La fenêtre de compte et son historique passent par le contrôle commun de la cible. Les services de suspension, réactivation, déblocage et changement d’adresse contrôlent aussi leur acteur avant mutation.

Une affectation SCHOOL permet de choisir un campus actif parmi les SchoolBranch autorisés. Le choix persiste entre requêtes, sans élargir l’école. Un identifiant invalide est refusé. La configuration technique commune à tout le campus est protégée contre les modifications d’un acteur limité à une école ; le formulaire explique cette restriction.

## I. Enseignant

Le campus du profil reste un rattachement principal. Les campus des cours, créneaux et affectations pédagogiques actifs sont accessibles par sélection. L’école principale RH ne supprime plus les affectations transversales. Les classes et EC accessibles restent déterminés par les affectations réelles de l’enseignant.

Les affectations directes à Class, Semester, UE ou EC alimentent les classes visibles, les matières et les indicateurs. Un campus non affecté est refusé côté serveur. Chaque classe conserve son année ; aucun faux filtre annuel global n’est affiché.

## J. Moniteur / Monitrice

Même navigation pédagogique que l’enseignant, y compris un second campus affecté. Statut salarié et distinction salaire/honoraires préservés. Les tests d’intégration moniteur et de suivi des services font partie de la régression.

## K. Surveillant

Les classes, événements, présences, cahiers de texte, alertes et dossiers de suivi sont filtrés dans les sources communes des indicateurs et workspaces. Les agrégats ne comptent plus toutes les écoles du campus. Une affectation SCHOOL peut sélectionner un campus autorisé.

L’accès au propre profil de l’utilisateur repose sur son identité, et non sur son affectation RH au campus sélectionné : cela évite une tentative de création d’un second Profile pendant la navigation sur un autre campus.

## L. Étudiant

École et campus affichés sont dérivés du parcours académique consulté. Recette après passage d’un ancien parcours ESMED/campus B à un parcours ESGA/campus A : sélectionner l’année antérieure conserve l’ancien contexte. L’accès direct à un EC d’un autre étudiant est refusé.

## M. Templates HTML

Indicateur universitaire discret dans le shell existant et dans les workspaces étudiant/enseignant remplacés par HTMX. Identité UFHOB sur le libellé du shell partagé. Aucun remplacement massif des anciennes chaînes ESFÉ, aucune modification de la vitrine publique.

## N. HTMX

Le campus enseignant est transmis dans les requêtes et dans l’URL canonique de réponse. Les campus opérationnels IT/surveillance utilisent les événements HTMX du shell commun et une sélection du contenu du workspace, sans injecter un second shell dans le premier.

Les fragments étudiants reconstruisent leur contexte historique. Le widget financier imbriqué conserve également ce contexte sans ajouter un second bandeau de navigation. Les contrôles serveur restent applicables lorsque les paramètres sont falsifiés.

## O. Formulaires

Querysets de choix restreints pour les structures académiques, évaluations et relations de personnel du secrétariat. Le contrôle de ModelChoiceField refuse les identifiants étrangers soumis manuellement. La permission d’import de notes est vérifiée avant de lire le fichier.

## P. Querysets et sélecteurs

Extension d’`accounts.scoping`, réutilisée par les services IT, surveillance, présences, cahiers de texte, synthèses et formulaires. Les contextes SYSTEM invalides donnent un queryset vide. Les managers ORM globaux et les relations historiques ne sont pas remplacés ; les tâches sans requête doivent transmettre explicitement leur acteur/contexte lorsqu’elles agissent pour une personne.

## Q. Navigation et indicateurs

Bandeau School / Campus / année ou indication explicite de la source de l’année. Sélecteurs de campus pour les enseignants et les postes opérationnels SCHOOL IT/surveillance. Les menus conservent leur architecture et leurs capacités existantes.

Marketing et superadministration conservent leurs opérations institutionnelles. Une affectation explicitement locale n’autorise pas l’administration de campagnes, paramètres ou données globales. Le marketing local n’est pas présenté comme une fonctionnalité nouvelle : il est refusé tant qu’un workflow local complet n’existe pas.

## R. Exports

CSV de paiements testé en contexte gestionnaire ; exports DG et leur cohérence avec l’année/parcours couverts par la suite universitaire existante. Les modèles XLSX des notes continuent à passer par la permission de classe et le semestre. Aucune réécriture des moteurs PDF/XLSX. La recette ne prétend pas avoir rendu chaque variante de document de l’application.

## S. Recherche

Personnel IT, diagnostic étudiant, classes/EC IT, recherche étudiant/classe au secrétariat, listes des workspaces de surveillance et matières des enseignants suivent leur contexte métier. Les recherches directes et les identifiants d’URL sont contrôlés côté serveur.

## T. Logs / audit

Les journaux IT suivent la cible du compte ; un auteur central ne rend pas une cible étrangère visible à une école locale. Les vérifications de cartes suivent les personnes autorisées. Sessions et événements de sécurité sont lus après validation du compte cible. Notifications et messagerie restent personnelles.

## U. Historique

L’inscription courante sert au répertoire opérationnel. Les parcours historiques restent des enregistrements AcademicEnrollment et sont sélectionnés par année pour l’étudiant et le DG. Les historiques associés à une fiche du secrétariat sont restreints avant préchargement. Aucun historique supprimé ou réécrit.

## V. Isolation School

Scénario de référence : ESMED et ESGA sur le même campus. L’utilisateur ESMED ne peut pas récupérer les comptes, classes, dossiers, paiements et éléments de surveillance ESGA par changement d’identifiant.

## W. Isolation Branch

Le campus reste une dimension distincte. Un gestionnaire du campus A ne reçoit pas les paiements du campus B. Un enseignant n’accède à un autre campus que par son rattachement ou ses affectations actives. Les choix opérationnels SCHOOL sont contrôlés contre les implantations actives.

## X. Isolation SchoolBranch

La combinaison est appliquée aux données métier. SchoolBranch reste plusieurs-à-plusieurs et unique par couple. Les tests des phases 1 et 2 vérifient sa cohérence et la disponibilité des programmes. Aucun `Branch.school_id` introduit.

## Y. AcademicYear

Année institutionnelle conservée. DG : contexte annuel existant. Étudiant : année du parcours dans les liens, paramètres et fragments. Enseignant : année de chaque classe. Finance : périodes métier et inscription concernée. Les bandeaux n’inventent pas une année active lorsqu’un module n’en fournit pas.

## Z. Tests exécutés

Lanceur : `.venv/Scripts/python.exe .git/phase2_fast_tests.py <labels>`. Il charge `config.settings_test_ufhob` et crée une base SQLite de test isolée. Les labels exécutés sont :

- `portal.test_university_dashboard_alignment` : **22 tests réussis sur 22**, dernier passage après vérification positive de la fiche étudiant du secrétariat et du paiement visible à l’écran gestionnaire.
- `core.test_ufhob_phase2` : 22 tests réussis, exécutés avec la recette avant ses deux derniers ajouts (42/42 réussis à ce stade).
- `portal.test_teacher_sections`, `portal.test_monitor_integration`, `portal.test_supervisor_planner`, `portal.test_teacher_service_monitoring`, `secretary.tests`, `accounts.test_manager_finance_workspace`, `portal.test_dg_university`, `core.test_ufhob_phase1`, `academics.tests.AcademicScheduleServiceTests`, `academics.tests.LessonLogServiceTests`, `academics.tests.AcademicResultCalculationTests`, `superadmin.tests.SuperadminAccessPolicyTests` : **226 tests, 214 réussis, 10 échecs et 2 erreurs**.
- Comparaison sur la copie initiale, via `.git/alignment_baseline_tests.py` : 15 tests liés aux dix premiers échecs, puis 44 tests académiques. Les **12 anomalies sont reproduites avant les modifications**.
- `.venv/Scripts/python.exe manage.py check` ; `.venv/Scripts/python.exe manage.py makemigrations --check --dry-run` : réussis.
- `node --check static/src/js/portal/certified_dashboard_shell.js` et `node --check static/src/js/portal/teacher_certified_dashboard.js` : réussis.

Recette réelle par Client Django : connexion des rôles, rendu des pages, requêtes HTMX, contrôles de contenu, listes autorisées, identifiants étrangers, parcours historique, sélection de campus, import XLSX valide et export CSV. Aucune capture navigateur n’est revendiquée.

## AA. Réussites, échecs et exclusions

Les échecs de régression sont conservés et comparés à une copie des fichiers prise avant cette mission. Aucun test existant n’est supprimé ou désactivé pour obtenir un résultat vert. Les journaux de travail sont conservés sous `.git/alignment-*.log`.

Anomalies préexistantes reproduites :

1. Enseignant sans campus : le test attend HTTP 200, le routage existant renvoie 302 vers l’affectation.
2. Huit tests du planning surveillant attendent des opérations/écrans désormais refusés par la gouvernance (403).
3. Fixture du secrétariat : création d’un groupe déjà existant (`auth_group.name` unique).
4. Publication annuelle : le test tente de finaliser avant traitement de chaque dossier par le jury.
5. Widget de notes publiées : attente `14.00/20`, résultat existant `Non disponible`.

Ces anomalies empêchent de présenter la suite générale comme entièrement verte. Elles n’ont pas été masquées par des modifications de permissions ou de tests.

Bilan des ensembles distincts exécutés : **270 tests, 258 réussis, 12 anomalies préexistantes reproduites**, aucun test déclaré skipped dans ces ensembles. Les passages de comparaison sur le code initial ne sont pas ajoutés une seconde fois à ce total.

Avertissements d’environnement : messages GLib/GIO concernant des applications Windows installées et avertissements Git LF/CRLF. Ils n’empêchent pas les résultats ci-dessus. Le contrôle d’espaces Git passe en tenant compte des fins de ligne Windows (`core.whitespace=trailing-space,space-before-tab,cr-at-eol`).

Les tests utilisent SQLite isolé avec synchronisation des modèles (`MIGRATION_MODULES` neutralisé par le lanceur local), les vraies URLs et les vrais templates. Ils ne constituent pas un rejeu PostgreSQL des migrations. Suite exhaustive de tout le dépôt, recette navigateur et envoi réel de courriels/SMS non exécutés.

## AB. Migrations

Aucune migration créée ou appliquée. `manage.py makemigrations --check --dry-run` : **No changes detected**. `manage.py check` : **aucune anomalie**. Base configurée et connexion vérifiées : `ufhob_db` ; Python 3.14.0 du virtualenv UFHOB.

## AC. Fichiers modifiés

39 fichiers existants modifiés et 6 fichiers créés pendant cette mission. Comparaison avec la copie initiale ; les travaux antérieurs du `git diff` ne sont pas attribués à cette mission.

- `academics/permissions/__init__.py`
- `academics/services/analytics_service.py`
- `academics/services/lesson_log_service.py`
- `academics/services/schedule_service.py`
- `academics/services/session_service.py`
- `accounts/access_context.py`
- `accounts/dashboards/exports.py`
- `accounts/dashboards/helpers.py`
- `accounts/scoping.py`
- `marketing/permissions.py`
- `portal/forms.py`
- `portal/permissions.py`
- `portal/selectors/informaticien.py`
- `portal/services/informaticien_workflows.py`
- `portal/services/it_dashboard_service.py`
- `portal/services/it_support_service.py`
- `portal/services/supervisor_dashboard_service.py`
- `portal/services/supervisor_service.py`
- `portal/services/supervisor_workspace_service.py`
- `portal/services/teacher_dashboard_service.py`
- `portal/student/services.py`
- `portal/student/views.py`
- `portal/student/widgets/academics.py`
- `portal/views/it_workflows.py`
- `portal/views/supervisor.py`
- `portal/views/views.py`
- `secretary/forms.py`
- `secretary/selectors.py`
- `static/src/js/portal/certified_dashboard_shell.js`
- `static/src/js/portal/teacher_certified_dashboard.js`
- `students/services/attendance_service.py`
- `students/services/case_service.py`
- `superadmin/superadmin_views_complete.py`
- `superadmin/views.py`
- `superadmin/views/utils.py`
- `templates/portal/informaticien/workflows/branch_settings_workspace.html`
- `templates/portal/staff/director_dashboard.html`
- `templates/portal/student/section_workspace.html`
- `templates/portal/teacher/v2/workspace.html`

Fichiers créés :

- `accounts/operational_context.py`
- `portal/services/teaching_scope.py`
- `portal/test_university_dashboard_alignment.py`
- `templates/portal/staff/shared/university_context.html`
- `docs/UFHOB_DASHBOARDS_MATRICE_AUDIT.md`
- `docs/UFHOB_DASHBOARDS_ALIGNEMENT_RAPPORT.md`

## AD. Réserves

Les données historiques sans School fiable ne sont pas attribuées arbitrairement à une école. Les comptes sans affectation et les ressources communes nécessitent un traitement institutionnel explicite. Les tests de rendu Django ne valident pas l’exécution JavaScript dans un navigateur ; la syntaxe des scripts modifiés est vérifiée avec Node.

## AE. Dette restante

Aligner les anciennes attentes de tests avec les règles de gouvernance actuelles, et traiter leurs fixtures défectueuses, sans ouvrir des permissions pour les faire passer. Une future évolution du marketing local nécessitera un vrai périmètre d’audience et de publication ; elle ne doit pas réutiliser implicitement les opérations globales. La ventilation financière par école ne doit être ajoutée que sur une source comptable fiable.

## AF. Isolation du dépôt ESFÉ

`C:\Users\HP\PycharmProjects\esfe-core` **non modifié**. Toutes les modifications de cette mission se trouvent dans `ufhob-core`.

## AG. Isolation de la base ESFÉ

`esfe_db` **non modifiée**. Aucun bootstrap, flush, reset, migration ou jeu de données de test exécuté sur une base opérationnelle. Les fixtures sont confinées à SQLite de test.

## AH. Verdict sur les dashboards

**DASHBOARDS UFHOB ALIGNÉS SUR LA NOUVELLE ARCHITECTURE : OUI**

Pour les parcours et contextes opérationnels audités : moteurs partagés, isolation école/campus côté serveur, affectations pédagogiques transversales et parcours historiques. Les 22 tests spécifiques sont verts et aucune anomalie nouvelle n’a été observée dans les suites de régression exécutées. Ce verdict ne constitue pas une certification de chaque variante d’export, de chaque route du dépôt ou d’un déploiement sans réserve ; les limites de recette et les anomalies préexistantes restent explicites ci-dessus.

## AI. Verdict sur la vitrine Django Cotton

**PRÊT POUR LA VITRINE PUBLIQUE DJANGO COTTON : NON**

Les bases universitaires nécessaires sont en place, mais une déclaration de préparation globale sans réserve serait prématurée : les anomalies académiques et de gouvernance de la suite générale doivent être traitées ou explicitement arbitrées. La compatibilité et la recette du futur frontend Cotton restent à faire lors de sa mission dédiée. Django Cotton n’a pas été installé ; aucune vitrine n’a été reconstruite pendant cette mission.
