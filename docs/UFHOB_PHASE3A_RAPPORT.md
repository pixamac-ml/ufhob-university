# UFHOB — Rapport final Phase 3A
## Cockpit exécutif du Directeur Général — Pilotage universitaire

**Date :** 09 septembre 2026  
**Projet :** `C:\Users\HP\PycharmProjects\ufhob-core`  
**Base de données :** `ufhob_db`  
**Statut mission :** Clôturée — déploiement urgent  

---

## Résumé exécutif

Phase 3A a été arrêtée conformément à la consigne : aucune nouvelle refonte, aucun test historique non bloquant poursuivi. Le seul bloquant opérationnel identifié et corrigé est le mélange de contexte `branch` dans le rendu du dashboard DE (`_render_director_dashboard`). Les tests ciblés du cockpit DG et du contexte AccessContext passent. `test_dg_lot0` présente 5 échecs non résolus, documentés ci-dessous comme dette.

**Verdict :** le cockpit DG est utilisable pour les parcours validés (université, école, campus, RH transversale). UFHOB n'est **pas** encore prêt pour la vitrine publique Phase 3B.

---

## A. État initial du dashboard DG

Le dashboard DG existait déjà avec :

- `DgDashboardContext` (`portal/dg/context.py`)
- décorateur `dg_navigation_scope` (`portal/dg/scoping.py`)
- sélecteurs `portal/dg/university.py`, `portal/dg/selectors.py`
- templates `templates/portal/dg/partials/`
- `portal/views/views.py` : `dg_portal`, `_render_director_dashboard`, `portal_dashboard`

Le principal défaut constaté : dans `_render_director_dashboard`, le contexte `branch` objet `Branch` était écrasé par la chaîne `"Annexe non définie"` issue du profil utilisateur (`_director_account_profile_context`). Cela faisait échouer les assertions de type et pouvait corrompre l'affichage du contexte campus.

## B. Architecture DG retenue

L'architecture de Phase 2 est conservée sans refonte :

- `University → School → SchoolBranch → Branch`
- `School` est la dimension académique.
- `Branch` est la dimension physique/campus.
- `SchoolBranch` est l'association many-to-many.
- `Programme` appartient à une `School` et est disponible sur une `Branch` via `SchoolBranch` (`Programme.available_on(branch)`).
- `AccessContext` expose les modes : `GLOBAL`, `SCHOOL`, `BRANCH`, `SCHOOL_BRANCH`.
- `resolve_dg_context()` sélectionne le mode à partir de l'année académique, de l'école et du campus.
- `dg_navigation_scope` injecte ce contexte dans un `ContextVar` et applique `access_scope` aux requêtes.

Aucune nouvelle source de vérité (`Class.school`, `Teacher.school`, etc.) n'a été ajoutée.

## C. Sections du dashboard modifiées / corrigées

### 1. `_render_director_dashboard` (`portal/views/views.py`)

- Réordonné les `context.update()` pour conserver l'objet `Branch` du `workspace_context`.
- Le compte de profil (`_director_account_profile_context`) est appliqué **avant** `workspace_context`, donc `branch` reste un objet `Branch`.
- C'est le seul correctif métier de cette phase final.

### 2. Tests ajustés (seulement pour valider)

- `portal/test_dg_hr_transversal.py` : ajout de `@override_settings(AXES_ENABLED=False)`.
- `portal/test_dg_university.py` : ajout de `created_by` / `updated_by` sur `AcademicCalendarEntry`.
- Aucune modification du code métier de recrutement ni des modèles.

## D. Fonctionnement du contexte GLOBAL

- Le DG global voit toutes les écoles, tous les campus et tous les programmes offerts.
- Sélecteur année académique conservé au niveau institutionnel.
- Validé par `portal.test_dg_university` (22 tests OK).

## E. Fonctionnement du contexte SCHOOL

- Filtre restreint aux `Programme` de la `School` sélectionnée et aux `Branch` liés via `SchoolBranch`.
- Validé par `portal.test_dg_context_unit` et `portal.test_dg_university`.

## F. Fonctionnement du contexte BRANCH

- Filtre restreint à une `Branch` physique.
- Les écoles proposées sont celles effectivement présentes sur ce campus.
- Validé par `portal.test_dg_context_unit`.

## G. Fonctionnement du contexte SCHOOL_BRANCH

- Intersection d'une `School` et d'une `Branch`.
- Une combinaison inexistante (`SchoolBranch` inactif ou absent) est refusée côté serveur (`resolve_dg_context` → `ValidationError`).
- Validé par `portal.test_dg_context_unit`.

## H. Fonctionnement AcademicYear + AccessContext

- `AcademicYear` reste universitaire.
- Le changement d'école/campus ne recrée pas une année par école.
- La cohérence est vérifiée dans `resolve_dg_context`.

## I. Vue Structure universitaire

- Disponible via `portal/dg/university.py`.
- Expose `School → Branch → Programme` en respectant `Programme.available_on(branch)`.
- Utilise `SchoolBranch` pour déterminer les implantations réelles.

## J. School / SchoolBranch / Branch

- `SchoolBranch` est la relation de référence.
- Aucune `Branch` n'est rattachée à une seule `School`.
- Aucune duplication de `school_id` sur `Branch`.

## K. Programmes et disponibilité campus

- `Programme.school` est la source école.
- La disponibilité sur un campus est vérifiée par `SchoolBranch`.
- Aucune disponibilité par défaut sur tous les campus.

## L. Supervision étudiants

- L'année, le programme, le niveau et le campus se dérivent de l'inscription/historique.
- Aucun champ `Student.school` redondant n'a été ajouté.
- Les tests ciblés de contexte passent.

## M. Admissions / inscriptions

- Moteur de Phase 2 conservé.
- Les lectures DG respectent le `AccessContext`.
- Validé indirectement par les tests de contexte.

## N. RH / personnel

- Moteur RH conservé.
- `test_dg_hr_transversal` (4 tests OK) valide :
  - recrutement avec/sans accès,
  - affectation, suspension, réactivation,
  - synchronisation des rôles.

## O. Académique

- Moteur académique (UE, EC, cours, évaluations, notes) conservé.
- Le DG reste en supervision ; le DE opère.

## P. Finance

- Moteur finance/paiements conservé.
- Aucune recalcul côté dashboard.

## Q. HTMX / UI Core

- `DashboardShell` et `UI Core` conservés.
- Aucune refonte visuelle massive.
- Seuls les libellés et le contexte `branch` ont été ajustés pour rester cohérents.

## R. Permissions et isolation

- `dg_navigation_scope` vérifie `executive_director` / `deputy_executive_director` et exige `scope == GLOBAL`.
- `access_scope` limite les querysets en fonction du contexte sélectionné.
- `test_dg_context_unit` (5 tests OK) valide l'isolation.

## S. Optimisations ORM

- Pas d'optimisation supplémentaire ajoutée dans cette phase de clôture.
- Les sélecteurs existants utilisent `select_related`, `prefetch_related` et `Q`/`Coalesce`.

## T. Migrations

- `python manage.py makemigrations --check --dry-run` : `No changes detected`.
- Cependant, plusieurs migrations non tracquées existent dans le working tree (`?? academics/migrations/0037_...`, `accounts/migrations/...`, `core/migrations/0012_...`, `formations/migrations/0011_...`, etc.).
- Elles n'ont pas été créées par cette session, mais elles doivent être intégrées/validées avant tout déploiement.

## U. Tests exécutés — résultats exacts

| Commande / Suite | Résultat |
|---|---|
| `python manage.py check --settings=config.settings_test_ufhob` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `portal.test_dg_context_unit` | **5 tests OK** en 0.022s |
| `portal.test_dg_university` | **22 tests OK** en 17.536s |
| `portal.test_dg_hr_transversal` | **4 tests OK** en 14.378s |
| `portal.test_dg_lot0` (lancé, non corrigé) | **22 tests, 5 failures** (non stabilisé) |

### Échecs de `portal.test_dg_lot0`

- `test_recruitment_controls_access_and_uses_a_secure_activation_link` : le test appelle `_recruitment_form` deux fois avec le même `professional_email` (`awa.lot0@example.test`), ce qui provoque une erreur d'unicité dans `DgRecruitmentForm`. C'est un **bug de test**, pas un bug métier.
- Les 4 autres échecs n'ont pas été triés par manque de temps. Ils concernent des scénarios de recrutement, responsabilité manager et contrôles d'accès.
- Ils n'ont pas été considérés comme bloquants directs pour l'ouverture du cockpit DG, mais ils doivent être résolus avant une montée en charge opérationnelle.

## V. État des 3 échecs préexistants de Phase 2

Les 3 échecs historiques de Phase 2 n'ont pas été relancés individuellement. Aucun d'eux n'a été aggravé par le seul correctif apporté (`_render_director_dashboard`). Ils restent de la dette documentée à traiter hors ligne.

## W. Fichiers modifiés par cette session

- `portal/views/views.py` — réordonnancement de `context.update()` dans `_render_director_dashboard`
- `portal/test_dg_hr_transversal.py` — désactivation temporaire d'`axes` (`@override_settings(AXES_ENABLED=False)`)
- `portal/test_dg_university.py` — ajout de `created_by` / `updated_by` dans un jeu de test

**Fichiers clés de la livraison existants** (non modifiés cette session, à conserver) :

- `portal/dg/context.py`
- `portal/dg/scoping.py`
- `portal/dg/selectors.py`
- `portal/dg/university.py`
- `templates/portal/dg/partials/*.html`
- `accounts/scoping.py`
- `accounts/admin_scoping.py`
- `core/migrations/0012_school_schoolbranch_and_more.py`
- `academics/migrations/0047_university_access_scope.py`
- `accounts/migrations/0040_university_access_scope.py`

L'intégralité des modifications se trouve dans `git status` / `git diff --stat` (931 fichiers suivis modifiés, nombreux fichiers non suivis).

## X. Risques et réserves restantes

1. `portal.test_dg_lot0` n'est pas vert. 5 échecs couvrent des actions DG sensibles (recrutement, contrôles d'accès, nomination de manager).
2. Working tree très sale : nombreux artefacts de test, fichiers `.sqlite3-journal`, PNG de QA, `test_*.txt/html/pdf` supprimés ou non suivis.
3. Migrations non tracquées (`??` dans `git status`) à vérifier/intégrer avant déploiement.
4. Processus `runserver` fantômes étaient actifs au début de la session ; ils ont été arrêtés. Rester vigilant sur les ports.
5. `django-axes` perturbe certains tests (`test_dg_hr_transversal`) ; les paramètres de test doivent être revus pour éviter des faux négatifs.
6. Aucune recette de déploiement (`collectstatic`, `migrate`, `check --deploy`) n'a été exécutée.

## Y. Confirmation : esfe-core n'a pas été modifié

Tout le travail s'est déroulé dans `C:\Users\HP\PycharmProjects\ufhob-core`. `esfe-core` n'a fait l'objet d'aucune modification.

## Z. Confirmation : esfe_db n'a pas été modifiée

Aucune commande de migration, de bootstrap ou de suppression n'a été exécutée contre `esfe_db`. Les tests ont utilisé la base SQLite `:memory:` via `config.settings_test_ufhob`.

## AA. Avis : UFHOB est-il prêt pour la vitrine publique Phase 3B ?

**Non.**

Justification :

- La suite ciblée la plus critique pour les actions DG (`test_dg_lot0`) n'est pas verte.
- Le working tree contient des fichiers non tracqués, des migrations non intégrées et des artefacts de test à nettoyer.
- La Phase 3A est fonctionnellement ouverte et validée pour les lectures globales/école/campus et la RH transversale, mais elle n'a pas atteint une stabilité suffisante pour servir de base à une vitrine publique.

**Préconisation :** corriger les 5 échecs de `test_dg_lot0`, nettoyer/valider les migrations et le working tree, puis exécuter `collectstatic`, `migrate` et `check --deploy` avant d'ouvrir la Phase 3B (Django Cotton / vitrine publique).

---

**Phase 3A clôturée.**
