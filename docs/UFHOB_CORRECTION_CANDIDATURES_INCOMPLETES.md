# Candidatures incomplètes — gestionnaire d’annexe

## Diagnostic et correction

Inspection du modèle de candidature et de ses documents, des formulaires, des vues HTMX, de la présentation du tableau, de la fenêtre de détail, des permissions, du filtrage universitaire et des tests existants.

Le statut `to_complete` excluait le dossier des actions de décision, côté interface et serveur. Le détail affichait les pièces sans permettre leur ajout ou leur validation.

Les candidatures à compléter disposent maintenant des actions de traitement, dont l’acceptation sans attendre les pièces. Le détail liste les pièces manquantes et permet leur ajout puis leur validation. La validation enregistre son auteur et sa date dans les champs existants. L’ajout de pièces conserve le statut de candidature et l’inscription éventuelle.

Le moteur partagé, les permissions `manage_admissions`, le filtrage École/Campus et les contrôles de disponibilité des programmes sont conservés. Les nouveaux téléversements acceptent les mêmes extensions et la même limite de 10 Mo que le parcours public. Ils sont limités aux pièces configurées pour le programme, sans doublon ni remplacement implicite des pièces existantes.

## Fichiers concernés

- `accounts/dashboards/htmx_candidatures.py`
- `accounts/services/manager_dashboard_presentation.py`
- `accounts/services/manager_admission_documents.py` (nouveau formulaire)
- `accounts/templates/accounts/dashboard/partials/candidature_modal.html`
- `accounts/urls.py`
- `accounts/test_manager_admission_documents.py` (nouveaux tests)

## Validation

- `manage.py check` : aucune erreur.
- `manage.py makemigrations accounts admissions --check --dry-run` : aucun changement.
- Vérification globale des migrations : écart préexistant sur les options Meta de `formations.Fee`, laissé intact. Aucune migration créée ni appliquée.
- Tests ciblés : 10/10 réussis (`accounts.test_manager_admission_documents` et `accounts.test_manager_workflows.ManagerCandidatureWorkflowTests`). La dernière exécution a créé le schéma SQLite depuis les modèles, avec `MIGRATION_MODULES` désactivé dans le processus de test uniquement, pour éviter de reconstruire les 224 fichiers de migrations.
- Première exécution avec migrations : 14/16 réussis. Une erreur de fixture du nouveau test (nom d’annexe dupliqué) a été corrigée puis vérifiée dans les 10 tests ci-dessus. L’autre échec, dans `accounts.test_manager_admissions_workspace`, porte sur une assertion préexistante de navigation : le menu contient désormais `messagerie` et `mon-salaire`. Il est extérieur à la correction et laissé intact. Les cinq autres tests de ce module ont réussi.
- Vérification interactive dans un navigateur et suite complète non exécutées.

Environnement vérifié : interpréteur UFHOB Python 3.14, paramètres applicatifs `config.settings`, base PostgreSQL `ufhob_db`. Tests exécutés avec `config.settings_test_ufhob`, dans SQLite en mémoire, avec stockage temporaire des pièces dans le dépôt.

Les modifications préexistantes du dépôt ont été préservées. `esfe-core` et `esfe_db` n’ont pas été touchés. Aucune donnée opérationnelle n’a été modifiée.
