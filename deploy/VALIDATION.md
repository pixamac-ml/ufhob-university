> Mise à jour : voir [la passe de correction](FINALISATION_2026-11-14.md).
> Les résultats initiaux ci-dessous sont conservés comme historique de l’audit.

# Validation locale du 14 novembre 2026

Voir le rapport complet [AUDIT_2026-11-14.md](AUDIT_2026-11-14.md), notamment
les échecs initiaux corrigés, les limites et les blocages de publication.

## Résultats finaux sur le projet local

- Python 3.14.0, Django 6.0.5 ; base locale ufhob_db vérifiée.
- pip check : réussi ; versions directes conformes au requirements.txt.
- manage.py check : réussi ; makemigrations --check --dry-run : No changes detected.
- 85 tests Django sélectionnés : réussis sur une base SQLite isolée détruite après test.
- 3 tests JavaScript d'apparence : réussis.
- Production isolée : contrôles, collectstatic, manifest, import ASGI, compilation
  des 1 239 templates et rendu PDF réussis, sans connexion base ni secret local.
- W005/W021 HSTS restent attendus ; W019 SAMEORIGIN préexistant reste ignoré.
- Deux builds CSS avec le verrou npm corrigé : réussis dans un arbre temporaire neuf.
- Audit de cet arbre npm : zéro vulnérabilité.
- Syntaxe du script Ubuntu via Git Bash : réussie.
- Aucun changement de schéma ni aucune migration dans ufhob_db.

Commande de la sélection Django :

```powershell
.\.venv\Scripts\python.exe manage.py test config.test_production config.test_release_templates academics.test_online_class academics.test_calendar core.test_ufhob_phase1 core.test_ufhob_phase2 --settings=config.settings_test_ufhob --noinput
```

Le test de production isolé est reproductible avec :

```powershell
.\.venv\Scripts\python.exe scripts/validate_deployment.py
```

L'audit des dépendances est reproductible avec :

```powershell
.\.venv\Scripts\python.exe scripts/audit_dependencies.py --npm
```

Sa sortie non nulle est actuellement attendue : 16 distributions Python portent
encore des avis de sécurité. Cela constitue un blocage et n'est pas masqué par
les tests fonctionnels réussis. Aucune montée majeure de dépendance Python n'a
été appliquée sans décision.

Aucune validation sur le VPS : PostgreSQL Ubuntu vide, bibliothèques natives,
Nginx, systemd, HTTPS, Redis/SMTP/BBB/B2/S3 réels et restauration restent à tester
après autorisation. Les tests locaux ne prouvent pas l'exploitabilité des avis
ni l'aptitude actuelle à exposer l'application en production.

## Copie des sources vérifiée

`.tmp-release-preview-20261114-v2` : 2 680 fichiers sources, empreintes vérifiées,
1296 fichiers Python acceptés par la grammaire 3.12. Contrôles de production,
manifest, import ASGI, PDF et compilation de 1 187 templates réussis depuis cette
copie. Aucun .git ni .env local copié ; aucun média utilisateur copié. Les
répertoires privés vides créés par l’import applicatif restent ignorés.
