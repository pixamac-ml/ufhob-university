# Finalisation et livraison UFHOB

État courant : [FINALISATION_2026-11-14.md](FINALISATION_2026-11-14.md).

# Préparation et déploiement UFHOB

Documentation de référence : [GUIDE_UFHOB.md](GUIDE_UFHOB.md).
Architecture : [docs/architecture_ufhob.md](../docs/architecture_ufhob.md).
Stratégie Git : [PUBLICATION_GITHUB.md](PUBLICATION_GITHUB.md).
Résultats de la mission : [AUDIT_2026-11-14.md](AUDIT_2026-11-14.md).

Cible exclusivement UFHOB : `/srv/ufhob`, `ufhob_db`, rôle `ufhob_app`,
`ufhob.service`, Daphne `config.asgi:application` sur `127.0.0.1:8002`.
Le domaine et les secrets de production restent à renseigner.

Fichiers disponibles :

- `production.env.example` : exemple serveur sans véritables secrets.
- `ufhob.service` : service dédié, variables dans `/etc/ufhob/production.env`.
- `nginx-http.conf.example` : challenge ACME initial, sans portail HTTP.
- `nginx.conf.example` : HTTPS, WebSockets et liste de médias publics autorisés.
- `manage-ufhob.sh` : commandes manuelles après contrôle de la base et du rôle.
- `../scripts/validate_deployment.py` : validation locale isolée sans connexion base.
- `../scripts/audit_release.py` : inventaire heuristique, rapport privé.
- `../scripts/prepare_release.py` : copie de sources pour revue, sans historique Git.

Aucune migration, installation serveur ou publication n'est déclenchée par ces
fichiers. Les instructions Ubuntu sont destinées à une intervention ultérieure
explicitement validée. Aucun déploiement automatique au push n'est configuré.

Le socle Python corrigé est isolé et validé sous Python 3.12 ; le traitement
des données déjà publiques reste soumis à autorisation avant publication.
