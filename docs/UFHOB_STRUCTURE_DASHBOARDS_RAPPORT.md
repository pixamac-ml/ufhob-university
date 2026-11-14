# UFHOB — Structure universitaire dans les dashboards

Mission de `temp.txt`, exécutée le 10 septembre 2026. Inspection ciblée des rapports Phase 2, Phase 3A et alignement, des modèles, permissions, formulaires, services, vues, templates et changements Git préexistants.

| Point | Livraison |
|---|---|
| A. DG / écoles | Création, consultation de l’identité et des programmes, modification et activation/désactivation depuis Structure universitaire. Code contrôlé, institution existante réutilisée, aucune donnée officielle inventée. |
| B. Campus | Création/édition existantes accessibles depuis la structure, tableau des campus et de leurs écoles, vocabulaire Campus dans la navigation DG. |
| C. SchoolBranch | Rattachement à un campus existant, configuration du code local et des dates, activation/désactivation du couple. Doublons refusés, liens historiques conservés, aucune duplication de campus. Plusieurs campus se rattachent successivement depuis une école. |
| D. Programmes | Catalogue accessible depuis chaque école. École obligatoire pour un nouveau programme ; anciennes données sans école conservées. Mutations DG soumises au contexte serveur. Gouvernance DG/catalogue et DE/structure académique conservée. |
| E. Navigation | Université → école → implantation, liens vers les données correspondantes, retour global. Les sélecteurs consomment les implantations et sélecteurs métier existants. |
| F. DE | École, campus et année dans la présentation. Les DE SCHOOL disposent du sélecteur de campus autorisé pour les workflows nécessitant un campus physique. |
| G. Étudiant | École, campus, programme, classe et année du parcours consulté dans le bandeau et le shell. Historique préservé. |
| H–I. Enseignant / moniteur | Contexte par classe dans les tableaux, ressources, planning, Course Studio, détail et cahier. Affectations transversales conservées ; règles salariales et honoraires inchangées. |
| J. Surveillant | Contexte du shell enrichi ; sélecteur opérationnel et scoping existants conservés. |
| K. Gestionnaire / finance | Contexte du shell enrichi et sélection de campus pour les affectations SCHOOL. Paiements dérivés du dossier ; aucune ventilation scolaire fictive des caisses ou dépenses. |
| L. Secrétaire | Même présentation et sélection de campus autorisé ; dossiers et choix continuent de passer par les sélecteurs existants. |
| M. Informaticien | Présentation commune enrichie ; périmètre serveur, sélection de campus et restrictions d’import existants conservés. |
| N. Autres rôles | Admissions et agent de paiement utilisent le shell/contextes partagés. Marketing et superadministration gardent leur gouvernance globale existante et son contrôle des affectations locales. |
| O. Formulaires | Nouveaux formulaires School et SchoolBranch ; adaptation du formulaire Campus et du choix School des programmes. Validation des identifiants, codes, doublons, dates et activation côté serveur. |
| P. Templates | Structure administrable, formulaires dans la modale existante, contexte étudiant et contexte pédagogique réutilisable. Aucun second shell. |
| Q. HTMX | Navigation hiérarchique, erreurs de formulaire dans la modale, légende du contexte synchronisée, année conservée au changement de campus. La fermeture d’un périmètre sélectionné renvoie explicitement au parent ; les identifiants de sous-objets sont effacés lors des changements de périmètre. |
| S. Recette manuelle | Tester les actions DG et les quatre contextes, la navigation HTMX/historique navigateur, chaque rôle SCHOOL sur deux campus, les parcours étudiants historiques et Course Studio sur les affectations transversales. Vérifier les vrais KPI, recherches, exports et imports avec les données institutionnelles. |
| T. Validation | `manage.py check` : aucun problème. Syntaxe des deux scripts JS : OK. Six tests ciblés des mutations/contexte : OK ; quatre tests existants des rôles, historique étudiant et affectations enseignant/moniteur : OK. Contrôle des espaces du diff : OK. |

Les tests ont utilisé SQLite isolé via le lanceur existant `.git/phase2_fast_tests.py`. Dix tests distincts validés, sans campagne générale de régression. Les refus HTTP 403 attendus sont testés. Des avertissements GLib/GIO Windows non bloquants apparaissent durant les imports. Recette navigateur, suite complète, migration dry-run et tests PostgreSQL non exécutés conformément au mode de validation demandé. Aucun résultat de tests historiques n’est présenté comme un résultat de cette mission.

Aucune migration créée ou appliquée. Aucun bootstrap, reset, flush, commit ou changement de `.env`. Python 3.14 du virtualenv UFHOB et `config.settings` vérifiés ; connexion PostgreSQL confirmée sur `ufhob_db` en lecture. `esfe-core` et `esfe_db` non touchés. Les modifications préexistantes ont été conservées.

## R. Fichiers de cette mission

- `accounts/operational_context.py`
- `portal/dg/forms.py`
- `portal/dg/navigation.py`
- `portal/dg/university.py`
- `portal/dg/university_forms.py`
- `portal/dg/university_views.py`
- `portal/services/certified_dashboard_shell.py`
- `portal/services/director_dashboard_presentation.py`
- `portal/services/teacher_dashboard_service.py`
- `portal/student/views.py`
- `portal/views/views.py`
- `portal/urls.py`
- `portal/test_university_structure_dashboard.py`
- `static/src/js/portal/certified_dashboard_shell.js`
- `static/src/js/portal/dg_dashboard.js`
- `templates/portal/dg/partials/university.html`
- `templates/portal/dg/modals/branch_admin.html`
- `templates/portal/dg/modals/university_editor.html`
- `templates/portal/staff/shared/university_context.html`
- `templates/portal/staff/shared/academic_class_context.html`
- `templates/portal/staff/director/partials/context_bar.html`
- `templates/portal/partials/teacher_class_detail.html`
- `templates/portal/partials/teacher_support_workspace.html`
- `templates/portal/partials/teacher_lesson_log_panel.html`
- `ui/templates/dashboard/teacher_supports_section.html`
- `ui/templates/dashboard/teacher_overview_section.html`
- `docs/UFHOB_STRUCTURE_DASHBOARDS_RAPPORT.md` (ce rapport)

Les protections et moteurs déjà livrés par les phases précédentes sont réutilisés. Cette livraison est prête à être vérifiée depuis les dashboards ; les contrôles ciblés ne constituent pas une certification de chaque route, export et interaction navigateur du dépôt.

ARCHITECTURE UNIVERSITAIRE CORRECTEMENT TRADUITE DANS LES DASHBOARDS :
OUI

DASHBOARDS PRÊTS POUR RECETTE MANUELLE :
OUI

