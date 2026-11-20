# Audit du cloisonnement école / annexe — UFHOB-Mali (nuit du 19/11/2026)

Périmètre : branche `livraison/ufhob-securisation-20261114`, dossier `.local-delivery`, code local uniquement.

## 1. Cartographie réelle

| Objet | Modèle | Rattachement école | Rattachement annexe |
|---|---|---|---|
| Université | `core.Institution` | — | — |
| École | `core.School` (`is_active`, `is_public`) | — | via `core.SchoolBranch` |
| Annexe / campus | `branches.Branch` | via `core.SchoolBranch` (une annexe peut accueillir plusieurs écoles) | — |
| Année académique | `academics.AcademicYear` | **globale** (créée une fois, partagée par toutes les écoles) | — |
| Programme | `formations.Programme` | `school` | `available_on(branch)` |
| Candidature | `admissions.Candidature` | `programme.school` | `branch` |
| Pièces | `admissions.CandidatureDocument` | `candidature.programme.school` | `candidature.branch` |
| Inscription / dossier | `inscriptions.Inscription` | `candidature.programme.school` | `candidature.branch` |
| Paiement | `payments.Payment`, `CashPaymentSession` | `inscription.candidature.programme.school` | idem `branch` |
| Étudiant | `students.Student` | inscription académique courante, sinon candidature | idem |
| Classe | `academics.AcademicClass` | `programme.school` | `branch` |
| Utilisateur | `accounts.Profile` (poste, annexe historique) + `accounts.InstitutionalProfile` (`school`, `branch`, `access_scope` GLOBAL / SCHOOL / BRANCH / SCHOOL_BRANCH) | `InstitutionalProfile.school` | `InstitutionalProfile.branch` |
| Finances d'annexe | `BranchExpense`, `BranchWallet`, `BranchCashMovement`, `PayrollEntry`, `TeacherHonorariumEntry` | **aucun champ école** | `branch` |

Rattachement d'un utilisateur : `accounts.access_context.build_access_context(user)` construit le contexte (école, annexe, périmètre, validité). Le middleware `accounts.middleware` le pose pour toute la requête (`access_scope`). Le DG (`executive_director`, périmètre GLOBAL) et les superutilisateurs n'ont pas de restriction.

## 2. Mécanisme unique de filtrage (existant, conservé et complété)

- `accounts.scoping.scoped(Model, user=…)` : queryset limité à l'école et à l'annexe de l'utilisateur. La table `SCOPE_PATHS` donne le chemin école/annexe de chaque modèle. Un modèle absent de la table est **vide** pour un utilisateur local (refus par défaut).
- `accounts.scoping.scoped_get_object_or_404(queryset, user=…, pk=…)` (**ajouté cette nuit**) : chargement par identifiant dans le périmètre. Un objet d'une autre école répond **404**, comme un objet inexistant.
- `accounts.dashboards.querysets.get_base_queryset(user, type)` : tableau de bord gestionnaire, construit sur `scoped`.
- `accounts.admin_scoping.UniversityScopeAdminMixin` : admin Django (listes et listes déroulantes de clés étrangères).

## 3. Fuites et risques trouvés

| # | Fichier : ligne (avant correction) | Gravité | Scénario | État |
|---|---|---|---|---|
| F1 | `accounts/services/excel_reports.py:316-327` | **Élevée** | Rapport Excel du gestionnaire : candidatures et inscriptions filtrées par annexe seulement. À Moribabougou, un gestionnaire ESGA comptait aussi les dossiers FATEC. | Corrigé (`scoped`) |
| F2 | `students/views.py:143` `class_attendance_summary_view` | **Élevée** | Résumé de présence d'une classe par ID : contrôle d'annexe seulement. Un compte ESGA ouvrait une classe FATEC du même campus. Un compte sans annexe (périmètre école) n'avait **aucun** contrôle. Réponse 403, qui révélait l'existence. | Corrigé : 404 |
| F3 | `students/views.py:156` `student_attendance_history_view` | **Élevée** | Historique de présence d'un étudiant d'une autre école (même campus) par ID. | Corrigé : 404 |
| F4 | `students/views.py:77,82` `mark_student_attendance_view` | Moyenne | Saisie de présence avec un `student_id` / `academic_class_id` d'une autre école dans le JSON. | Corrigé : 404 |
| F5 | `academics/views.py:811` (cahier de texte, création) et `:878` (`class_lesson_logs_view`) | Moyenne | Classe d'une autre école chargée par ID ; contrôle d'annexe seulement. | Corrigé : 404 |
| F6 | `portal/services/academic_structure_service.py:54,80,183,195,236,240` | Moyenne | Structure académique (classes, étudiants à affecter, archivage, semestres, affectation) filtrée par annexe seulement : classes et étudiants FATEC visibles et modifiables par l'ESGA sur un campus partagé. | Corrigé (`scoped`) |
| F7 | `students/admin.py` (Student, présences, alertes) | Faible | Admin Django sans le mixin de périmètre (accès admin réservé au staff technique). | Corrigé (mixin) |
| R1 | `accounts/dashboard_views.py` (≈ 40 requêtes non filtrées) | Faible | Ancien module **non relié à aucune URL** (code mort). Dangereux s'il était rebranché. | Signalé, non modifié |
| R2 | Finances d'annexe (`BranchExpense`, caisse, portefeuilles, paie, honoraires) | **Structurel** | Ces enregistrements n'ont pas de champ école : sur un campus partagé, la caisse et les dépenses sont communes aux écoles. Conforme au fonctionnement actuel « par annexe », mais contraire à la règle « un comptable d'école ne voit que son école ». | **Décision DG nécessaire.** Module comptabilité non modifié par prudence. |
| R3 | `accounts/services/sensitive_actions.py:93` | Faible | Paiement chargé par `target_id` sans `scoped`. L'identifiant vient d'un circuit déjà contrôlé (correction de paiement). | Signalé (module finance) |
| R4 | `marketing/selectors/dashboard.py:43` | Faible | Liste de toutes les classes pour le responsable marketing (rôle université). | Conforme si le marketing reste un rôle université |
| R5 | `portal/views/views.py` (≈ 10 000 lignes) | À compléter | Les sections DG passent par `resolve_dg_context` (filtrage école/annexe choisi). Revue ligne à ligne non terminée cette nuit. | À poursuivre |

Points vérifiés **sans fuite** : liste, détail, actions et pièces des candidatures du gestionnaire (`get_base_queryset`) ; exports CSV candidatures et paiements (`exports.py`) ; détail d'inscription gestionnaire (`scoped` + annexe) ; admin Candidature, Pièce, Inscription, Paiement, Session de caisse (mixin) ; rapports PDF de classe (`can_view_academic_class`).

## 4. Tests d'isolation

`core/test_cloisonnement_ecoles.py` (ESGA et FATEC sur **le même campus**, DG global) :
- le sélecteur central ne compte que sa propre école ; un ID étranger donne 404 ; le DG voit les deux ;
- liste des candidatures, détail, action « en analyse » et export CSV : rien de l'autre école ;
- rapport Excel : seules les candidatures de l'école sont comptées ;
- présence d'une classe et historique d'un étudiant de l'autre école : 404 ;
- structure académique : classes de l'autre école absentes.

Contre-épreuve : sans les corrections, 3 tests sur 5 échouent (F1, F2/F3, F6).
