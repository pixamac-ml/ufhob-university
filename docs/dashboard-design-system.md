# Design system des espaces authentifiés UFHOB

## Périmètre et chargement

Le site public n'utilise pas ces tokens. Les espaces authentifiés chargent
`static/app/css/main.css` (construit par `npm run build:css:app`) à la place
de `static/public/css/main.css` ; le public garde son asset. La configuration
`tailwind.app.config.js` emploie `darkMode: 'class'` afin qu'aucune variante
`dark:` héritée ne suive automatiquement le système. Les thèmes sont pilotés
par les variables scoped, sans classe `.dark` globale.
`static/css/app/tokens.css` est chargé par
`templates/portal/app_base.html`, `templates/base_app.html`,
`templates/workspace_base.html` et l'ancien
`templates/portal/staff/dashboard_shell.html`. Les variables sont définies
uniquement sous `[data-app-shell]`. Le shell certifié est délimité par
`templates/portal/staff/director_dashboard.html` et par sa racine composant
`ui/templates/ui_core/layout/app_shell.html` ; les autres layouts ont
leur propre racine. Ne pas ajouter ces variables au `:root` public.

La palette claire conserve les valeurs `ui` initiales. Les contrôles
d'apparence sont visibles dans le composant de préférences du shell certifié.
Les anciens basculeurs propres à l'enseignant et à l'informaticien restent
masqués ; le champ enseignant `dark_mode` demeure historique et
`UserPreference.theme` est l'unique source de vérité visuelle.

## Thèmes et taille du texte

`UserPreference.theme` utilise `LIGHT`, `DARK`, `SYSTEM` ; `font_scale` utilise
`SM`, `MD`, `LG`, `XL`. Le shell officiel rend ces valeurs directement dans
`data-theme` et `data-font-scale` avant le premier affichage. `SYSTEM`
s'appuie sur `color-scheme: light dark` et `light-dark()` dans `tokens.css` ;
le CSS suit donc l'OS même sans JavaScript. La valeur serveur prévaut sur
le cache local.

Le script précoce dans `templates/portal/app_base.html` fixe la couleur de
fond du document avant le chargement CSS. `static/src/js/app/appearance.js`
synchronise ensuite le stockage local par utilisateur, les autres onglets,
les changements système et les graphiques Chart.js. Il ne s'exécute pas sur
le site public. Le POST HTMX `accounts:appearance_update` retourne `204` et
`account:preferences-updated` sans remplacer le shell. Les contrôles sont
des groupes radio natifs, utilisables au clavier.

La taille du texte passe par `--app-font-scale` et des règles scoped sur les
utilitaires typographiques courants, sans toucher aux icônes ni aux largeurs.
Les nouveaux composants doivent employer les classes `ui-*`/tokens et éviter
`bg-white`, `text-black` ou les neutres hardcodés pour la structure.

## Carte des composants

| Groupe | Source | Utilisation | État |
| --- | --- | --- | --- |
| Shell certifié, sidebar, topbar, navigation mobile | `ui/templates/ui_core/layout/app_shell.html`, `navigation/app_sidebar.html`, `navigation/app_topbar.html` | DG, DE, étudiant, enseignant, staff via `templates/portal/staff/director_dashboard.html` | partagé, tokens raccordés |
| Panels, page header, breadcrumbs, grilles | `ui/templates/ui_core/layout/` | espaces certifiés et système UI | partagé, classes `ui-*` raccordées |
| Form fields, filtres | `ui/templates/ui_core/forms/` | formulaires UI Core | partagé, classes `ui-*` raccordées |
| Table, lignes, statuts, KPI, graphiques | `ui/templates/ui_core/data_display/` | tableaux et widgets UI Core | partagé, couleurs structurelles raccordées ; séries graphiques à auditer |
| Alertes, toasts, chargement | `ui/templates/ui_core/feedback/` | retours transversaux | partagé, statuts conservés |
| Modale, drawer, dropdown, tabs | `ui/templates/ui_core/overlays/`, `navigation/` | HTMX/Alpine, interactions partagées | partagé, couleurs raccordées sans modifier le DOM |
| Profil, préférences, notifications | `ui/templates/account/`, `ui/templates/notifications/` | espaces authentifiés | partagé, déjà en classes `ui-*` |
| Shell staff historique | `templates/portal/staff/dashboard_shell.html` | anciens écrans staff | racine isolée, variables structurelles principales raccordées ; classes slate restantes |
| Shell legacy comptes | `accounts/templates/accounts/dashboard/base_dashboard.html` | ancien dashboard comptes | racine isolée ; couleurs historiques restantes |
| Sidebars héritées | `ui/templates/dashboard/` | `teacher_sidebar` dans `portal/teacher/v2/dashboard.html` ; `secretary_sidebar` enregistrée mais sans appel trouvé | non mutualisées avec UI Core ; la seconde est potentiellement orpheline |
| Public | `templates/public/`, `ui/templates/blog/`, `ui/templates/news/`, cartes publiques | vitrine | hors périmètre, ne pas modifier |

`ui/components/ui_core/` contient les classes Python enregistrées dans
django_components ; les templates associés sont dans `ui/templates/ui_core/`.
Les familles account/notifications sont dans `ui/components/account/` et
`ui/components/notifications/`. Les composants métier propres à un seul
dashboard ne doivent pas devenir des primitives par simple similitude visuelle.

## Tokens et règles

Les tokens structurels sont `--app-bg`, `--surface*`, `--text-*`,
`--border*`, `--input-*`, `--shadow-color`, `--sidebar-*` et `--navbar-*`.
Les tokens d'action et d'état sont `--primary*`, `--success*`, `--warning*`,
`--danger*`, `--info*`, `--accent*` et `--focus-ring`.

Créer une nouvelle surface avec `bg-ui-surface` ou un token de surface, pas
avec `bg-white`. Utiliser `text-ui-text`/`text-ui-text-muted` pour la
hiérarchie et `border-ui-border` pour les séparateurs. Un paiement validé
emploie `success`, une erreur `danger`, une attente `warning` ; ne pas
transformer un statut métier en gris structurel. Les couleurs de marque,
logos, séries graphiques et états académiques doivent être évalués séparément.
Garder les classes Tailwind de géométrie et les contrats HTMX/Alpine existants.

Les classes `ui-*` compilées par Tailwind gardent les valeurs claires de
secours ; dans `[data-app-shell]`, le CSS scoped les relie aux variables.
L'ordre est important : charger `tokens.css` après `app/css/main.css`.
Pour un nouveau composant partagé, choisir une classe `ui-*` existante avant
d'ajouter une utility. Les variantes de hover/focus doivent aussi suivre le
token ; vérifier l'état disabled et le contraste.

## Dette de migration constatée

Scan initial des familles authentifiées ciblées (`ui/templates/ui_core`,
`ui/templates/dashboard`, `templates/portal/staff`, `templates/portal/student`,
`accounts/templates/accounts`) : environ **2 564** occurrences de classes
blanc/gris/slate dans **86** fichiers. `ui/templates/ui_core` en contient
**0** ; l'ancien `dashboard_shell.html` est passé de **58** à **2**
(transparences blanches volontaires sur la sidebar). Après migration, le même
scan en trouve environ **2 509**. Les fichiers
account/notifications de django_components n'en contiennent également **0**.
Un second scan des templates applicatifs et du JS portal a trouvé environ
**136** occurrences `#hex`/`rgb()`/`rgba()`/`hsl()` : elles incluent la palette
inline historique, des couleurs de marque et des états. Les icônes UI Core
n'ont pas de `fill`/`stroke` noir explicite ; les logos restent hors migration.
Ces occurrences ne sont pas toutes interchangeables : certaines sont des
états métier ou des tableaux legacy. Aucune substitution globale ne doit être
appliquée. Les couleurs directes d'anciennes vues, les graphiques et les
composants propres à un rôle restent à examiner écran par écran.

L'activation actuelle couvre le shell certifié et les composants UI Core
tokenisés. Elle ne certifie pas les pages secondaires secrétaire/superadmin
qui gardent leur conteneur historique, les couleurs hardcodées de vues métier,
ni les éditeurs tiers. Il reste à migrer et recetter ces écrans, puis à
comparer visuellement desktop/tablette/mobile avant de déclarer tous les
espaces authentifiés compatibles sombre.

Le scan large de phase 1.5 est passé de **4 393** à **4 336** occurrences
brutes : les neutres structurels du workspace DE et de la modale du règlement
étudiant ont été migrés après lecture de leur contexte ; les couleurs d'état
ont été conservées. Cette phase a aussi raccordé les variantes opacifiées
des tokens, sans remplacement mécanique des classes métier.
`ui/templates/ui_core`, `ui/templates/account` et
`ui/templates/notifications` comptent **0** classe neutre historique dans
ce scan. `templates/portal/staff` en compte environ **736** (dont des
variantes `dark:` et des écrans historiques), `templates/portal/student`
environ **27**, et `superadmin/templates/superadmin` environ **1 368**.
Ces valeurs ne sont pas des défauts uniques ; les neutres structurels encore
visibles sur les routes officielles, notamment des vues de planning, sont
`TO_FIX` avant certification complète du mode sombre. Les couleurs d'état
métier, de marque et de graphiques restent à classifier individuellement.
