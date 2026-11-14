# Création de classes par la Direction générale

Le cockpit DG possède maintenant un bouton « Créer une classe » dans la sous-section Classes. Le formulaire reprend les champs académiques existants : école, campus, programme, année, niveau et seuil de validation facultatif.

L’action est réservée au contexte exécutif global du DG. Les choix sont validés côté serveur : le programme doit appartenir à l’école, l’école doit être active sur le campus choisi et les filtres du contexte DG ne peuvent pas être contournés. La création appelle `save_academic_class`, le service partagé des directeurs d’études ; il réactive une classe historique équivalente ou en crée une nouvelle, active les deux semestres et applique les contrôles existants.

Après succès, le modal se ferme, la liste des classes est rafraîchie et un message indique que les inscriptions peuvent désormais être positionnées.

La fiche ouverte depuis une ligne propose également « Modifier la classe » et « Supprimer la classe ». La suppression est volontairement un archivage réversible : la classe disparaît des listes actives, tandis que les inscriptions, semestres et autres traces historiques restent intactes.

Vérifications : `manage.py check` réussi, compilation Python réussie et test DG de filtrage des classes réussi. `makemigrations --check --dry-run` signale uniquement l’écart préexistant de `formations.Fee`. Aucune migration, classe ou donnée opérationnelle n’a été créée dans `ufhob_db`. `esfe-core` et `esfe_db` n’ont pas été touchés.
