# État du chantier 1 — cloisonnement des données par école (20/11/2026)

Détail de l'audit : `docs/AUDIT_CLOISONNEMENT.md`. Chantiers 2 et 3 : **non commencés** (arrêt demandé).

## Fuites trouvées et corrigées

| # | Endroit | Problème | Correction |
|---|---|---|---|
| F1 | `accounts/services/excel_reports.py` | Rapport Excel du gestionnaire : candidatures et inscriptions comptées par annexe seulement, donc ESGA + FATEC mélangées sur un campus partagé. | `scoped(...)` |
| F2 | `students/views.py` (`class_attendance_summary_view`) | Présence d'une classe d'une autre école ouverte par ID ; aucun contrôle pour un compte sans annexe ; 403 révélait l'existence. | 404 hors périmètre |
| F3 | `students/views.py` (`student_attendance_history_view`) | Historique de présence d'un étudiant d'une autre école. | 404 |
| F4 | `students/views.py` (`mark_student_attendance_view`) | Étudiant ou classe d'une autre école accepté dans le JSON. | 404 |
| F5 | `academics/views.py` (cahier de texte : création et liste) | Classe d'une autre école chargée par ID. | 404 |
| F6 | `portal/services/academic_structure_service.py` | Classes et étudiants d'une autre école visibles et modifiables (même campus). | `scoped(...)` |
| F7 | `students/admin.py` | Admin étudiants et présences sans filtre de périmètre. | `UniversityScopeAdminMixin` |

Mécanisme unique : `accounts.scoping.scoped()` (existant) + `scoped_get_object_or_404()` (ajouté). Le DG et les superutilisateurs voient tout.

## Ce qui reste

- **R2 — décision DG** : caisse, dépenses, paie et honoraires sont rattachés à l'annexe, sans champ école. Ils restent communs aux écoles d'un même campus. Module comptabilité non modifié.
- R1 : `accounts/dashboard_views.py` est du code mort (aucune URL) avec des requêtes non filtrées. À supprimer ou à laisser débranché.
- R3 : `accounts/services/sensitive_actions.py:93` charge un paiement sans `scoped` ; circuit déjà contrôlé en amont.
- R5 : revue ligne à ligne de `portal/views/views.py` (≈ 10 000 lignes) non terminée.
- Liste déroulantes de la modale de candidature : sans objet tant que le chantier 2 n'est pas fait.

## Tests

- `core/test_cloisonnement_ecoles.py` (5 tests, ESGA et FATEC sur le même campus, DG global) : **OK** le 19/11 au soir (5/5).
- Contre-épreuve : sans les corrections, 3/5 échouent (F1, F2/F3, F6). Les tests détectent donc bien les fuites.
- `core.test_brand_seo`, `core.test_public_contact`, `core.test_lancement_final` : OK (19/19) avant ce chantier.
- `students.tests` (réinscription) : erreurs **antérieures** à ce chantier, sans lien avec les fichiers modifiés (`reenrollment_service.py` refuse une « moyenne annuelle saisie manuellement » des données de test).
- Le 20/11, par petits lots (`settings_test_campaign`, `--keepdb`, mémoire libre ≈ 600 Mo) :
  - `core.test_cloisonnement_ecoles` : **5/5 OK** ;
  - `core.test_ufhob_phase2` + `portal.test_university_structure_dashboard` : **29/29 OK** ;
  - `accounts.test_manager_workflows` + `accounts.test_manager_admissions_workspace` : 87 tests, **22 échecs antérieurs**. Le même lot donne exactement 22 échecs sur le code d'origine (sans les corrections du chantier 1). Cause à analyser à part : rendu des sections du tableau de bord gestionnaire.
- Non lancés (mémoire) : `academics`, `students` (complets), `portal.test_monitor_integration`, `portal.test_teacher_supervisor_signature_workflow`.
