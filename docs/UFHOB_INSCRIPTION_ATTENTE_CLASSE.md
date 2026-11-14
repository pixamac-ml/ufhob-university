# Inscription en attente d’une classe

La règle existante est conservée : une candidature acceptée ne devient une inscription qu’après sélection d’une classe active compatible avec le programme, le campus et l’année académique. Aucun statut ni schéma supplémentaire n’est introduit.

## Affichage

La fenêtre indique « Candidature acceptée », puis « Inscription en préparation — En attente d’une classe compatible ». Elle rappelle le programme, le campus et l’année, invite à solliciter le responsable académique pour créer ou activer la classe et précise que la candidature reste enregistrée. Les boutons « Reprendre plus tard » et « Vérifier les classes disponibles » permettent de reprendre le parcours sans nouvelle acceptation. Une année non configurée dispose d’un message distinct.

Les textes techniques du formulaire ont été remplacés par des indications destinées aux gestionnaires. Aucun accès de création de classe n’est ajouté à leur rôle.

## Fichiers et vérification

- Affichage : `accounts/templates/accounts/dashboard/partials/academic_positioning_body.html`.
- Lien de vérification HTMX : `accounts/dashboards/htmx_utils.py`.
- Corrections déjà réalisées pendant le diagnostic : `accounts/dashboards/htmx_candidatures.py` ouvre l’étape suivante après la fermeture de la précédente ; `accounts/templates/accounts/dashboard/manager_dashboard.html` charge les fenêtres par HTMX pour initialiser les scripts ; `accounts/dashboards/htmx_inscriptions.py` traite une classe invalide comme une erreur de formulaire.
- Régression : `accounts/test_registration_stability.py`, `accounts/check_registration_stability.cjs`.

Trois tests réussis dans SQLite isolé, schéma créé depuis les modèles. Le test Edge headless utilise les réponses HTML produites par Django : ouverture après acceptation, sélection du niveau, affichage des frais, message d’absence de classe, absence de bouton de soumission dans ce cas, puis vérification des classes et reprise du formulaire. Il ne constitue pas une démonstration intégrale sur des données réelles.

`manage.py check` réussit. `makemigrations accounts admissions --check --dry-run` ne détecte aucun changement. Aucune migration créée ou appliquée. La suite complète n’a pas été relancée pour cet ajustement visuel. Lors du diagnostic initial, 46/47 tests métier avaient réussi ; l’échec concernait l’affichage d’un coupon sur la vue d’ensemble, hors de la demande visuelle finalement retenue.

La lecture de `ufhob_db` avait confirmé l’absence de classe active, avec l’année 2026–2027 et les frais configurés. Aucune donnée opérationnelle n’a été modifiée, aucune classe n’a été créée. `esfe-core` et `esfe_db` n’ont pas été touchés. Les modifications préexistantes ont été préservées.
