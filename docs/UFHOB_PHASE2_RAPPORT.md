# UFHOB — Rapport de Phase 2

Date de clôture : 9 septembre 2026.

Le moteur partagé est conservé. Le contexte School/Branch est maintenant porté par le profil institutionnel et propagé dans les principaux sélecteurs, vues de dossiers et services académiques. Les règles d'offre des programmes sont validées côté serveur. Aucun nouveau système d'authentification, dashboard, moteur de paiement ou tenant n'a été créé.

## A. Architecture retenue et inspection

Inspection de `temp.txt`, des instructions du dépôt, de l'état Git préexistant, des migrations de Phase 1 et des modèles School, SchoolBranch, Programme, Branch, InstitutionalProfile/Profile, AcademicYear, AcademicCalendar/Entry, AcademicClass/Enrollment, Candidature, Inscription, Student et DirectorTeacherAssignment. Inspection également des permissions, signaux de synchronisation des profils, sélecteurs des dashboards, formulaires d'admission, services de structure académique, calendrier, transferts, réinscription et évaluations.

L'environnement contrôlé utilise le Python 3.14 du `.venv` UFHOB, `config.settings` et PostgreSQL `ufhob_db`. Le nom de la base a aussi été vérifié par `SELECT current_database()`.

Les relations structurantes restent :

```text
Institution → School ← Programme ← AcademicClass / AcademicEnrollment
                 ↕
             SchoolBranch → Branch
Candidature → Programme + Branch
Inscription → Candidature
Student → inscriptions et parcours académiques historiques
```

Les fichiers déjà modifiés par d'autres travaux ont été conservés. Une copie de comparaison du code initial a servi à isoler les changements de cette mission et à reproduire les échecs antérieurs.

## B–D. Modèles, champs et contraintes

| Modèle | Modification |
|---|---|
| InstitutionalProfile | FK nullable `school`, champ `access_scope`, résolution du périmètre et validation de sa cohérence |
| AcademicCalendarEntry | FK nullable `school`, uniquement pour la nouvelle portée `school` |
| Programme | Sélecteur `available_on(branch)` ; protection du changement d'école d'un programme déjà utilisé |
| Candidature | Validation d'offre lors de la création ou du changement Programme/Branch, y compris `save()` |
| AcademicClass | Même validation ; appel de `clean()` dans `save()` |
| AcademicEnrollment | Validation d'offre intégrée au `clean()` déjà appelé par `save()` |
| Inscription | Validation d'offre avant une nouvelle inscription administrative |

Aucun champ School redondant n'a été ajouté aux classes, étudiants, candidatures, inscriptions, paiements ou enseignants. L'année académique reste universitaire.

L'unicité `(School, Branch)` et celle du code School au sein de l'institution existaient en Phase 1 : elles sont conservées et testées. Les nouvelles validations traversant plusieurs tables sont des règles Python du domaine, pas des contraintes SQL prétendument capables de valider une jointure. Aucune migration historique n'a été réécrite.

## E. SchoolBranch et disponibilité

SchoolBranch reste une association plusieurs-à-plusieurs. Une école et son association au campus doivent être actives pour une nouvelle offre d'un programme rattaché à cette école. La même règle est utilisée par les classes, candidatures et inscriptions. Le catalogue d'admission et le formulaire historique filtrent également les possibilités.

La fermeture d'une implantation ne bloque pas la simple mise à jour d'un ancien dossier dont Programme/Branch ne changent pas. Une nouvelle affectation reste contrôlée. Changer l'école d'un programme déjà utilisé est refusé pour éviter de réécrire l'histoire académique par un changement de référentiel.

Les programmes sans School restent admis pour la transition des anciennes données. Ils sont exclus des lectures d'un utilisateur explicitement limité à une école. Aucun rattachement institutionnel n'a été inventé ou attribué automatiquement.

## F–G. AccessContext et périmètres

| Périmètre | Interprétation |
|---|---|
| GLOBAL | Université, sans restriction School/Branch dans le contexte ; les permissions du rôle restent nécessaires |
| SCHOOL | Une école sur ses campus ; Branch absent |
| BRANCH | Un campus ; comportement historique conservé |
| SCHOOL_BRANCH | Intersection d'une école et d'un campus |

`InstitutionalProfile.access_scope` vide conserve la résolution automatique : une école avec campus produit SCHOOL_BRANCH, une école sans campus produit SCHOOL ; en l'absence d'école, le registre des positions conserve son rôle historique. Un périmètre explicite peut être attribué par l'administration centrale. Les permissions de modification des affectations institutionnelles dans l'admin exigent un accès global.

`AccessContext.school` n'est plus un champ toujours vide. Les écoles désactivées et les couples School/Branch invalides rendent le contexte invalide. La policy sait vérifier séparément une ressource School et une ressource Branch. Modifier School ou access_scope sur le profil institutionnel déclenche la révocation de sessions prévue par le mécanisme existant.

`accounts/scoping.py` contient deux contrats distincts :

- `scope_queryset(queryset, context=...)` applique les dimensions du contexte ; il ne donne pas les permissions d'un rôle.
- `scoped(Model, user=...)` ajoute la restriction école aux lectures historiques adaptées. Pour les comptes sans école, les contrôles Branch/rôle existants restent responsables du périmètre historique. Il ne faut pas remplacer une autorisation métier par ce seul appel.

Le middleware AccessContext existant rend le contexte disponible pendant la requête. Un ContextVar est restauré dans un bloc `finally`, y compris lors d'une exception. Les managers ORM ne sont pas remplacés. Les services anciens qui reçoivent seulement Branch peuvent utiliser ce contexte ; les traitements hors requête exécutés au nom d'une personne doivent transmettre l'acteur ou employer explicitement `access_scope(context)`.

Les objets métier détenus directement par un service sont également contrôlés avant les mutations sensibles de structure académique, affectation, réinscription et exécution d'évaluations.

## H. Modules adaptés

- Candidatures, inscriptions, lectures des paiements, détails HTMX et exports des dashboards partagés.
- Classes, semestres, UE/EC, dossiers académiques, sélecteurs DE, informaticien et surveillance.
- Programmes et emploi du temps du DE, affectations et listes d'enseignants, réinscriptions et transferts.
- Sélecteurs étudiants/classes du secrétariat ; filtrage des dossiers liés à un étudiant ou à leur créateur institutionnel.
- Lectures DG des modèles concernés : les contextes globaux conservent leurs agrégations.
- Admin technique des modèles concernés, avec les mêmes sélecteurs pour les listes et relations proposées.

La visibilité d'un enseignant peut provenir de ses affectations de cours, même s'il ne possède pas un School unique sur son profil. Pour un étudiant, le sélecteur de dossier courant utilise `current_academic_enrollment` lorsqu'il existe, avec repli historique sur l'inscription initiale. Les inscriptions académiques restent les sources des lectures historiques.

Les campagnes d'évaluation explicitement limitées à une école utilisent ses classes. Une campagne couvrant plusieurs écoles reste hors du périmètre d'un agent limité à une seule école ; cet agent ne peut pas agir sur une épreuve étrangère en changeant son identifiant. Le calcul des notes n'a pas été réécrit.

### Décision sur le calendrier

Le document de calendrier reste commun au campus et à l'année, avec son versionnement et sa gouvernance existants. Un événement peut maintenant viser une école entière sur ce campus. Les événements visant Programme/Class/Semester continuent de déduire leur école de leur cible.

Les lectures école incluent les événements communs de leurs campus et les événements de leur périmètre. Modifier le document commun, les événements communs ou une autre école exige un périmètre plus large. Les modifications et avenants d'un événement propre à l'école sont contrôlés. Les règles de chevauchement, de blocage des cours et de construction des campagnes comprennent la nouvelle portée School.

Il n'y a pas de nouveau calendrier institutionnel parallèle. La centralisation future d'événements communs à tous les campus reste un besoin distinct du document versionné actuel.

## I. Éléments conservés

DashboardShell, UI Core, navigation, templates publics, Cotton, Tailwind, Course Studio, Student Course Workspace, authentification, calcul des notes, gouvernance des résultats, OTP/reçus, écritures de caisse et règles salaire/honoraires des moniteurs ont été conservés. Les modifications des lectures de paiement concernent le périmètre ; elles ne changent pas le calcul ou l'enregistrement des paiements.

Aucune purge, réinitialisation ou commande de bootstrap n'a été exécutée sur la base applicative. Le bootstrap de Phase 1 apparaît uniquement dans ses tests isolés.

## J. Migrations

- `accounts/migrations/0040_university_access_scope.py`
- `academics/migrations/0047_university_access_scope.py`

Leur présence dans l'historique appliqué de `ufhob_db` et l'existence des nouvelles colonnes ont été vérifiées. Au contrôle final de l'exécuteur, le plan restant pour ces deux migrations était vide. Aucune migration étrangère au périmètre n'a été appliquée par les commandes de cette mission.

## K–N. Tests et contrôles

22 tests de Phase 2 ont été ajoutés dans `core/test_ufhob_phase2.py`. Ils couvrent notamment la matrice A–J, la policy, la conservation de l'historique, le contexte invalide, le nettoyage du contexte après exception, les identifiants HTMX étrangers, le secrétariat via les chemins de scoping, les affectations transversales des enseignants, le calendrier et les campagnes d'évaluation. Le test de disponibilité différé en Phase 1 a été implémenté : il n'est plus skipped.

| Vérification | Résultat |
|---|---|
| Dernière suite ciblée : Phase 1, Phase 2, calendrier, workflows d'évaluation DE, scoping du secrétariat | **75 tests réussis**, aucun skipped |
| Suite élargie antérieure : accès, admissions, inscriptions, programmes, calendrier, gestionnaire, contexte DG, moniteurs, emploi du temps | **137 tests : 134 réussis, 3 échecs antérieurs confirmés** |
| `manage.py check` | OK, aucun problème |
| Dernier `makemigrations --check --dry-run` | OK, `No changes detected` |
| Lecture PostgreSQL de l'historique et des nouvelles colonnes | OK sur `ufhob_db` |
| Analyse syntaxique des fichiers Python modifiés/ajoutés | OK |

Les trois échecs élargis ont été reproduits avec les fichiers du début de mission, sans restaurer ni écraser le dépôt :

1. `AcademicCalendarGovernanceTests.test_revision_clones_entries_and_supersedes_previous_publication` : le test attend une seule entrée alors que trois sont présentes.
2. `DirectorProgrammeWorkflowTests.test_semester_form_rejects_numbers_outside_the_academic_model` : le test attend le refus du semestre 3, accepté par le comportement déjà présent.
3. `ManagerWorkspaceAccessTests.test_finance_manager_is_restricted_to_finance_context` : le test n'attend pas la section de réinscription déjà autorisée à Finance.

Ces tests n'ont été ni supprimés, ni marqués skipped, ni corrigés en modifiant des règles hors mission.

Les tests métier finaux utilisent SQLite en mémoire et les URLs complètes, avec `config.settings_test_ufhob`. Les boucles rapides construisent le schéma courant en désactivant les migrations dans le processus de test ; un rejeu complet des migrations SQLite a aussi été effectué lors du premier lancement. Ce premier lancement utilisait encore la première version incomplète de la fixture Phase 2, corrigée ensuite. Les résultats finaux ci-dessus ne prétendent donc pas être une suite PostgreSQL.

Le compte PostgreSQL n'a pas le droit `CREATEDB`. Aucun test transactionnel n'a été lancé contre les données réelles pour contourner cette limitation, et aucun droit serveur n'a été changé. Les tests PostgreSQL isolés restent à exécuter dans un environnement CI disposant de sa propre base de test.

Commande standard reproductible, avec rejeu des migrations :

```powershell
.\.venv\Scripts\python.exe manage.py test core.test_ufhob_phase1 core.test_ufhob_phase2 academics.test_calendar portal.test_director_evaluation_workflows secretary.tests.ScopeTests --settings=config.settings_test_ufhob --noinput
```

Le contrôle initial signalait la migration hors périmètre `memoires.0005`. Elle est désormais présente dans le dépôt lors du contrôle final ; elle n'a été ni créée ni modifiée par cette mission. Les avertissements GLib liés à des applications Windows sont apparus pendant certains imports ; ils n'ont pas empêché les contrôles Django ou les tests.

## P–Q. Limites et suite recommandée

- Attribuer les écoles et périmètres effectifs au personnel depuis les données officielles. Les anciens comptes sans School restent volontairement en compatibilité Branch ; aucun élargissement ou resserrement arbitraire de leurs affectations n'a été opéré.
- Les APIs `bulk_create`, `QuerySet.update` et le SQL brut contournent les validations de `save()` de Django. Les imports et traitements techniques doivent passer par les règles métier ; les migrations historiques ne sont pas réécrites pour changer ce contrat.
- Les nouvelles vues et tâches doivent reprendre les sélecteurs et transmettre le contexte. Il ne s'agit pas d'une isolation automatique de toutes les requêtes possibles dans l'ORM, ni d'une certification exhaustive de tous les endpoints du dépôt.
- Les objets purement physiques ou administratifs sans lien fiable à un Programme, notamment certains journaux de caisse et documents généraux, conservent leur portée campus. Une ventilation par école de ces données demanderait des règles métier explicites ; aucun School fictif n'y a été ajouté.
- Les audiences de communication et les flux qui ne passent pas par les sélecteurs adaptés nécessitent leur propre revue de périmètre avant un déploiement généralisé multi-écoles.
- Certains workflows d'écriture exigent toujours le choix d'un campus concret. Le périmètre SCHOOL autorise l'agrégation et la sélection sur plusieurs campus ; il ne supprime pas les besoins opérationnels d'une écriture située.
- Corriger séparément les trois tests antérieurs et compléter la validation PostgreSQL isolée.
- La Phase 3 peut consommer School, SchoolBranch, Programme et `available_on(branch)` pour la future vitrine. Le chantier frontend/Cotton reste séparé.

## R–S. Isolation ESFÉ

`C:\Users\HP\PycharmProjects\esfe-core` n'a pas été modifié par cette mission. Aucune connexion de travail n'a ciblé `esfe_db`, aucune migration ou donnée UFHOB n'y a été écrite et aucun reset ESFÉ n'a été effectué. Les tests ont utilisé une base SQLite isolée et les contrôles PostgreSQL ont vérifié explicitement `ufhob_db`.

## O. Fichiers de la mission

La liste ci-dessous distingue les fichiers de cette mission de l'ensemble beaucoup plus large des modifications Git déjà présentes. Les changements des grands fichiers de vues consistent principalement à appeler les sélecteurs contextualisés.

- `academics/admin.py`
- `academics/migrations/0047_university_access_scope.py`
- `academics/models.py`
- `academics/permissions/__init__.py`
- `academics/permissions/calendar_permissions.py`
- `academics/permissions/programme_structure_permissions.py`
- `academics/selectors/academic_readiness_selectors.py`
- `academics/selectors/calendar_selectors.py`
- `academics/selectors/director_monitoring_selectors.py`
- `academics/selectors/timetable_selectors.py`
- `academics/services/calendar_service.py`
- `academics/services/evaluation_campaign_service.py`
- `academics/services/evaluation_execution_service.py`
- `academics/services/programme_structure_service.py`
- `academics/services/teacher_assignment_service.py`
- `accounts/access.py`
- `accounts/access_context.py`
- `accounts/admin.py`
- `accounts/admin_scoping.py`
- `accounts/dashboards/executive_dashboard.py`
- `accounts/dashboards/exports.py`
- `accounts/dashboards/htmx_admissions.py`
- `accounts/dashboards/htmx_caisse.py`
- `accounts/dashboards/htmx_candidatures.py`
- `accounts/dashboards/htmx_finance.py`
- `accounts/dashboards/htmx_global.py`
- `accounts/dashboards/htmx_inscriptions.py`
- `accounts/dashboards/htmx_paiements.py`
- `accounts/dashboards/htmx_utils.py`
- `accounts/dashboards/htmx_widgets.py`
- `accounts/dashboards/manager_dashboard.py`
- `accounts/dashboards/querysets.py`
- `accounts/middleware.py`
- `accounts/migrations/0040_university_access_scope.py`
- `accounts/models.py`
- `accounts/policy_v2.py`
- `accounts/scoping.py`
- `accounts/services/manager_intelligence.py`
- `accounts/signals.py`
- `admissions/admin.py`
- `admissions/forms.py`
- `admissions/models.py`
- `admissions/views.py`
- `config/settings_test_ufhob.py`
- `core/admin.py`
- `core/test_ufhob_phase1.py`
- `core/test_ufhob_phase2.py`
- `formations/admin.py`
- `formations/availability.py`
- `formations/models.py`
- `inscriptions/admin.py`
- `inscriptions/models.py`
- `payments/admin.py`
- `portal/dg/selectors.py`
- `portal/permissions.py`
- `portal/services/director/calendar_mgt_service.py`
- `portal/services/director/deliberation_service.py`
- `portal/services/director/document_workflow_service.py`
- `portal/services/director/exam_session_service.py`
- `portal/services/director/programme_service.py`
- `portal/services/director/tasks_center.py`
- `portal/services/director/teacher_assignment_service.py`
- `portal/services/director/teacher_management_service.py`
- `portal/services/director/teacher_profile_service.py`
- `portal/services/director/timetable_service.py`
- `portal/services/director/transfer_workflow_service.py`
- `portal/services/it_support_service.py`
- `portal/services/reenrollment_service.py`
- `portal/views/admin_grades.py`
- `portal/views/it_grades_import.py`
- `portal/views/it_surveillance.py`
- `portal/views/it_workflows.py`
- `portal/views/reenrollment.py`
- `portal/views/staff_common.py`
- `portal/views/supervisor.py`
- `portal/views/supervisor_cases.py`
- `portal/views/system_profile.py`
- `portal/views/views.py`
- `secretary/selectors.py`
- `docs/UFHOB_PHASE2_RAPPORT.md`
