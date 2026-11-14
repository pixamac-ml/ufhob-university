# Réparation de la gestion des implantations — 11 septembre 2026

1. **Cause constatée.** La réparation déjà présente était incomplète : le formulaire global de rattachement lisait une relation `school` non renseignée puis utilisait `move_to_end` sur un dictionnaire ; son filtre pouvait exclure un campus réactivable lorsque d'autres écoles y étaient actives. Les vues École du Superadmin appelaient `sync_school_branches` sans import. Ses vues Campus n'enregistraient pas les implantations et validaient directement les paramètres POST sans ModelForm.

2. **Fichiers complétés ou créés pendant cette intervention.** Les modifications antérieures ont été conservées ; aucun commit ni nettoyage Git n'a été effectué.

   - `core/services/implantations.py` : transactions, verrouillage et protection de la création concurrente d'un même lien.
   - `portal/dg/forms.py` : sauvegarde atomique du formulaire Campus existant.
   - `portal/dg/university_forms.py` : formulaire global fonctionnel, filtre des liens réactivables et sauvegarde atomique des écoles.
   - `portal/dg/university_views.py` : validation du choix d'école dans le périmètre autorisé et actualisation du choix des campus.
   - `templates/portal/dg/modals/branch_admin.html` et `templates/portal/dg/modals/university_editor.html` : sélections à hauteur limitée et textes métier.
   - `superadmin/forms.py` : adaptation du formulaire Campus partagé, validation du code école et conservation des liens vers des campus inactifs.
   - `superadmin/views.py` et `superadmin/urls.py` : raccordement au service partagé et éditeur explicite des implantations.
   - `superadmin/templates/superadmin/branches/editor.html` : formulaire Campus validé avec sélection des écoles.
   - `superadmin/templates/superadmin/public_site/schools/form.html` : tableau des implantations et actions.
   - `superadmin/templates/superadmin/public_site/schools/implantation.html` : modification et réactivation d'une implantation.
   - `portal/test_implantation_management.py` : 14 régressions ciblées.
   - Le présent rapport.

3. **DG.** Réparation existante complétée : campus sans école en contexte global, école du contexte conservée, sélection multiple, rattachement explicite et réactivation historique. Le mécanisme existant d'actualisation des fragments et de conservation du contexte reste utilisé ; aucun nouveau système de navigation.

4. **Superadmin.** Création/modification des écoles et campus raccordées à la même synchronisation. Tableau et éditeur d'implantations avec statut, code local et dates. Les paramètres POST passent par les formulaires Django.

5. **Création Campus + SchoolBranch : OUI.** Transaction atomique, y compris annulation du campus si la synchronisation échoue.
6. **Modification des implantations : OUI.** Désactivation et réactivation sans suppression des enregistrements historiques.
7. **Campus multi-écoles : OUI.** Modèle existant préservé.
8. **École multi-campus : OUI.** Modèle existant préservé.
9. **Doublons empêchés : OUI.** Validation, réutilisation des liens inactifs et contrainte d'unicité existante.
10. **Funnel School → Campus : OUI.** Vérification des campus issus des liens actifs ; moteur Programme et design du tunnel inchangés.
11. **`manage.py check` : OK**, aucune anomalie.
12. **Migrations.** Aucune migration créée ou appliquée à `ufhob_db`. Le contrôle ciblé `makemigrations core branches portal --check --dry-run` passe. Le contrôle global échoue sur une différence préexistante de `formations.Fee.Meta.ordering` (`amount` → `programme_year`, `label`), laissée hors périmètre.
13. **Tests.** Première exécution : 18 tests réussis. Exécution finale : **20/20 tests réussis**, avec `config.settings_test_ufhob` et une base SQLite en mémoire. Modules : `portal.test_implantation_management.ImplantationManagementTests` et `portal.test_university_structure_dashboard`. Suite générale et recette dans un navigateur non exécutées. Les tests ne constituent pas une validation de la concurrence PostgreSQL en charge.
14. **Isolation ESFÉ.** `esfe-core` et `esfe_db` non touchés. Aucune donnée métier écrite dans `ufhob_db` ; consultations uniquement. Environnement vérifié : interpréteur `.venv` UFHOB, Python 3.14, paramètres `config.settings`, cible PostgreSQL `ufhob_db`.

## État réel des données consultées

Lors du contrôle, `ufhob_db` contenait 4 écoles actives, 2 campus actifs et **3 implantations actives**, et non 4. Le lien ESMED ↔ Moribabougou existe mais est inactif, avec une ouverture au 10 août 2026 et une fermeture au 30 septembre 2027. Il n'a pas été réactivé automatiquement : cette décision reste accessible dans l'éditeur. Le tunnel doit donc l'exclure tant que le lien reste inactif.

Les modèles School, Branch, SchoolBranch, les règles de disponibilité Programme et les mécanismes de contexte/permissions ont été inspectés. Aucun nouveau champ, aucune duplication d'architecture et aucune donnée institutionnelle inventée.

GESTION SCHOOL ↔ SCHOOLBRANCH ↔ CAMPUS OPÉRATIONNELLE : OUI, selon les vérifications serveur et tests ciblés.

BACKEND PRÊT POUR REPRENDRE LE FUNNEL CANDIDATURE : OUI. La migration globale préexistante et l'état des implantations ci-dessus restent à prendre en compte.
