# UFHOB — Passe finale d’intégration

Mission du 10 septembre 2026, selon `temp.txt`. Modifications antérieures conservées.

- **A. Structure** : sous-sections compactes Écoles, Campus, Implantations et Programmes. Campus sans école visibles dans la vue universitaire ; statuts, compteurs et actions séparés.
- **B. Création Campus** : depuis une école, création du campus et de son implantation dans une transaction ; depuis la vue globale, création du campus seul.
- **C. Rattachement** : seuls les campus encore non rattachés sont proposés pour un nouveau lien. Les liens existants se modifient ou se réactivent, sans duplication ni suppression d’historique.
- **D–E. Formulaires RH** : recrutement et réaffectation partagent les champs Périmètre, École et Campus. Contexte prérempli, campus dépendants de l’école, identifiants falsifiés refusés. École et scope sont enregistrés dans InstitutionalProfile. Postes globaux conservés selon le registre ; affectations pédagogiques transversales et salaires préservés.
- **F–G. Components / menus** : champs RH partagés, filtre compact ; menu partagé positionné hors des conteneurs susceptibles de le couper, borné à l’écran, fermeture extérieure/Échap, actions HTMX et filtrage des options explicitement non autorisées. Les sélecteurs natifs des filtres sont conservés.
- **H. Densité** : cartes plus courtes, sous-sections distinctes, remarques de régularisation repliables, libellé Direction générale et tableau RH École / Campus.
- **I. Filtering** : inspection des sélecteurs et des mutations ; relations SchoolBranch et scoping existants réutilisés. Paramètres école/campus/année conservés dans les requêtes DG. Sous-section Structure conservée après action et pagination.
- **K. Recette manuelle** : création Campus globale puis depuis une école ; rattachement d’un campus existant à une deuxième école ; recrutement et réaffectation dans les quatre scopes ; refus d’un campus incompatible ; menus en bord d’écran et dans les modales ; navigation HTMX, pagination et affichage du personnel créé. Vérifier également les dashboards des différents rôles avec leurs affectations réelles.
- **L. Contrôles** : `manage.py check` sans anomalie ; syntaxe JS et expression Alpine du menu OK ; compilation des sept templates concernés OK ; contrôle d’espaces Git OK. Aucun test suite exécuté. La recette navigateur n’est pas revendiquée.

Python 3.14 du virtualenv UFHOB, settings et cible `ufhob_db` vérifiés. Aucune migration, donnée opérationnelle, invitation réelle ou configuration d’environnement modifiée. `esfe-core` et `esfe_db` non touchés. Avertissements GLib/GIO Windows sans blocage.

## J. Fichiers modifiés

- `portal/dg/forms.py`
- `portal/dg/rh_service.py`
- `portal/dg/services.py`
- `portal/dg/navigation.py`
- `portal/dg/university.py`
- `portal/dg/university_forms.py`
- `portal/views/views.py`
- `static/src/js/portal/dg_dashboard.js`
- `templates/portal/dg/partials/university.html`
- `templates/portal/dg/partials/staff_scope_fields.html` (nouveau)
- `templates/portal/dg/partials/settings_ui_core.html`
- `templates/portal/dg/modals/recruitment.html`
- `templates/portal/dg/modals/staff_action.html`
- `templates/portal/dg/modals/branch_admin.html`
- `ui/components/ui_core/navigation/dropdown_menu.py`
- `ui/templates/ui_core/navigation/dropdown_menu.html`
- `ui/templates/ui_core/forms/filter_bar.html`
- `docs/UFHOB_INTEGRATION_FINALE_DASHBOARDS.md` (ce rapport)

Les dashboards académiques, étudiants, enseignants, moniteurs et administratifs conservent les mécanismes universitaires des missions précédentes. Cette passe complète l’intégration des formulaires et composants ; elle ne constitue pas une certification fonctionnelle exhaustive de chaque écran.
