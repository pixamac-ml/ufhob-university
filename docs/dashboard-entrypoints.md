# UFHOB — points d'entrée et dette des dashboards authentifiés

Ce document couvre uniquement `ufhob-core` et l'application authentifiée. Le site public et `esfe-core` sont hors périmètre. Le routage de connexion passe par `accounts/services/redirects.py`, puis par la politique existante `portal/permissions.py`; les affectations UFHOB restent validées par `AccessContext` lorsque la politique V2 est activée.

## Shell officiel

- Racine : `templates/portal/staff/director_dashboard.html` → `templates/portal/app_base.html`.
- Composant : `ui_core.app_shell`, `ui/templates/ui_core/layout/app_shell.html`.
- Navigation : `ui_core.app_sidebar` et `ui_core.app_topbar`, avec les groupes construits par `portal/services/certified_dashboard_shell.py`.
- Espace de contenu : `dashboard_shell.workspace_id`, slot `dashboard_content`, drawers/modals partagés. La racine `data-app-shell` porte les tokens de `static/css/app/tokens.css`.
- Rôles servis : étudiant, enseignant, DE, DG, IT, surveillant, gestionnaire, finance, admissions, secrétaire, marketing et superadmin sur leurs vues d'accueil certifiées.

## Carte des entrées

| Rôle | URL canonique | Vue | Template d'accueil | Shell | État |
| --- | --- | --- | --- | --- | --- |
| Étudiant | `/portal/student-dashboard/` | `portal.student.views.dashboard` | `portal/student/dashboard.html` | certifié | OK |
| Enseignant | `/portal/teacher/` | `portal.views.views.teacher_portal` | `portal/staff/director_dashboard.html` | certifié | OK |
| Directeur des études | `/portal/director/` | `portal.views.views.director_portal` | `portal/staff/director_dashboard.html` | certifié | OK, ancienne entrée `/portal/dashboard/` encore valide |
| DG / DG adjoint | `/portal/dg/` | `portal.views.views.dg_portal` | `portal/staff/director_dashboard.html` | certifié | OK, ancienne entrée `/portal/dashboard/` encore valide |
| Informaticien | `/portal/dashboard/` | `portal.views.views.portal_dashboard` | `portal/staff/director_dashboard.html` | certifié | OK ; `/portal/it/` et `/portal/it/v2/` redirigent ici |
| Surveillant académique | `/portal/dashboard/` | `portal.views.views.portal_dashboard` | `portal/staff/director_dashboard.html` | certifié | OK ; `/portal/supervisor/` reste un alias fonctionnel |
| Gestionnaire | `/portal/manager/` | `portal.views.annex_manager.annex_manager_portal` | `portal/staff/director_dashboard.html` | certifié | OK |
| Finance | `/portal/finance/` | `portal.views.views.finance_portal` | `portal/staff/director_dashboard.html` | certifié | OK |
| Admissions | `/portal/admissions/` | `portal.views.views.admissions_portal` | `portal/staff/director_dashboard.html` | certifié | OK |
| Secrétaire | `/portal/secretary/` | `portal.views.views.secretary_portal` | `secretary/dashboard.html` | parent certifié | Accueil OK ; pages secondaires encore sur `secretary/base.html` sans contrat shell |
| Marketing | `/marketing/` | `marketing.views.dashboard` | `marketing/dashboard.html` | parent certifié | Accueil et formulaires sur le même shell ; `marketing/base.html` reste un adaptateur de contenu |
| Superadmin | `/superadmin/` | `superadmin.views.dashboard` | `superadmin/dashboard.html` | certifié | Toutes les sections utilisent `superadmin/unified_base.html` et le même shell |

La régularisation (`/portal/access/regularization/`) reste la destination d'un compte dont l'affectation est incomplète. Elle ne doit pas être remplacée par un dashboard.

## Compatibilité / migration

- `/portal/student/` redirige directement vers `/portal/student-dashboard/`.
- `/portal/staff/` ne rend plus `portal/staff.html` ; il va vers la destination résolue ou la régularisation si elle serait ambiguë.
- `/accounts/dashboard/executive/` redirige vers le dashboard résolu pour l'utilisateur authentifié.
- `/accounts/dashboard/admissions/`, `/accounts/dashboard/finance/` et `/accounts/manager/` redirigent vers les routes `/portal/` correspondantes en conservant la query string.
- `/portal/workflows/reenrollment/`, `/portal/admin/grades/` et `/portal/it/grades/import/` conservent leurs fonctions métier mais rendent désormais le shell certifié. Leurs IDs HTMX et URLs d'action ne changent pas.
- Les pages marketing « annonce », « campagne », « prospect », « média » et « paramètres » ont maintenant le même shell et le même menu que l'accueil marketing. Les formulaires et leurs permissions restent en place.
- `templates/portal/staff/informaticien_dashboard.html` (sans suffixe) a été supprimé après recherche des dépendances et retest : aucun appel de vue, URL, include, composant, script ou test ne le référençait. Sa variante `v2` reste conservée car un test historique la nomme.

## Classification des autres shells

| Fichier | Classe | Justification |
| --- | --- | --- |
| `templates/portal/staff/director_dashboard.html` | OFFICIAL | contrat UI Core certifié |
| `templates/portal/app_base.html` | STILL_REQUIRED | parent de la racine certifiée |
| `secretary/templates/secretary/base.html` | MIGRATE_TO_OFFICIAL | accueil certifié, pages secondaires avec fallback `base_app.html` |
| `marketing/templates/marketing/base.html` | STILL_REQUIRED | adaptateur de contenu marketing sur le shell certifié ; l'ancien HTML `.mk-shell` a été retiré |
| `superadmin/templates/superadmin/unified_base.html` | OFFICIAL | adaptateur de contenu SuperAdmin vers le shell certifié unique |
| `templates/portal/base_portal.html` | LEGACY_REFERENCED | pages/fixtures historiques l'étendent encore ; ne pas supprimer |
| `accounts/templates/accounts/dashboard/base_dashboard.html` | LEGACY_REFERENCED | ancien template executive encore appelé par une vue non câblée ; ne pas supprimer sans audit final |
| `templates/portal/staff/dashboard_shell.html` | LEGACY_REFERENCED | deux templates IT historiques l'étendent ; non routés selon recherche statique |
| `accounts/templates/accounts/portal/base_portal.html` | LEGACY_REFERENCED | wrapper historique de l'ancien portal |

Le template `portal/staff/informaticien_dashboard_v2.html` et certains composants `ui/templates/dashboard/` restent des candidats à auditer, pas `SAFE_TO_REMOVE` : des tests historiques les référencent. Le grand template `portal/dg/dashboard.html` n'a pas de rendu direct repéré, mais il est déjà modifié dans la base de travail et a donc été préservé.

## Dette de couleurs et décision de thème

Le scan des templates authentifiés (`portal/templates/portal`, `accounts/templates/accounts/dashboard`, `secretary`, `marketing`, `superadmin`, `templates/portal`, `ui/templates/ui_core`) est passé de **5 175** à **4 393** occurrences brutes de `bg-white`, `bg-slate-*`, `bg-gray-*`, `text-slate-*`, `text-gray-*`, `border-slate-*`, `border-gray-*`. Le décompte après migration est : `portal/templates/portal` 12, `accounts/templates/accounts/dashboard` 918, `secretary` 7, `marketing` 0, `superadmin` 1 368, `templates/portal` 2 088, `ui_core` 0. Ce total inclut des neutres de statut, des panneaux de marque sombres et des vues historiques : ce n'est pas un nombre de défauts uniques. Les deux vues de notes migrées dans la phase précédente restent à **0** occurrence de ces classes ; leurs états avertissement/erreur sont conservés sous les tokens `warning`/`danger`.

Restent à classifier puis migrer : les pages secondaires secrétaire, d'autres modules métier, les graphiques et les exceptions de marque. Les neutres structurels des écrans officiels DG (modale), superadmin (toutes les sections), surveillant (planning), IT (suivi) et gestionnaire (modales paiement/inscription) ont été migrés ; les couleurs de statut, notamment succès/alerte/erreur, n'ont pas été assimilées à des neutres. Le site public n'est pas inclus dans ce scan et n'a pas été modifié ici.

**READY_FOR_THEME = NO.** L'accueil des rôles, les formulaires marketing et toutes les sections SuperAdmin partagent désormais le shell officiel. Les pages secondaires secrétaire et la dette de couleurs structurelles empêchent encore une activation fiable de Light/Dark/System. Ne pas activer les thèmes avant la migration de leurs vues utiles, la validation HTMX/Alpine et des tests visuels multi-rôles.

La phase suivante a activé le contrôleur Light/Dark/System **sur le shell certifié** avec préférences persistantes ; son scan après deux migrations ciblées est à **4 336** occurrences brutes. Cela ne transforme pas ce verdict de couverture globale en « oui » : les pages secondaires historiques restent hors certification sombre et nécessitent migration et recette visuelle.

## Contrôles HTMX et limites de recette

- Le panneau de compte staff reconstruit maintenant son contexte après l'enregistrement du profil. Le fragment retourné montre donc immédiatement le nouvel avatar ; l'événement `account:profile-updated` transmet son URL au profil et au menu utilisateur, y compris lorsque l'avatar précédent était une vignette d'initiales. Un paramètre de version évite de réutiliser l'image en cache.
- Deux tests HTTP SQLite couvrent le premier upload et le rejet d'un fichier invalide ; ils vérifient le fragment HTML, le statut et l'événement HTMX. Les dix tests sans base sur le routage, les templates et l'adaptateur marketing passent également. `manage.py check`, le build CSS et `makemigrations --check --dry-run` passent.
- La suite historique `UiSystemInteractionTests` reste non exécutable telle quelle avec l'URLconf de production (`ui` est un espace de démonstration non enregistré). Un autre test UI Core attend encore `h-screen`/`lg:sticky` dans une sidebar déjà modifiée avant cette intervention. Ces écarts de tests doivent être traités sans réintroduire une ancienne géométrie par hypothèse.
- Aucun navigateur authentifié instrumenté n'a été disponible pour certifier les interactions Alpine/HTMX ni les largeurs desktop, laptop, tablette et 390 px. Une recette visuelle multi-rôles reste obligatoire avant l'activation des thèmes.
