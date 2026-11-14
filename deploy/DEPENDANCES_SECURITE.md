> Mise à jour : voir [la passe de correction](FINALISATION_2026-11-14.md).
> Les résultats initiaux ci-dessous sont conservés comme historique de l’audit.

## Résultat actuel avant publication

Le 14 novembre 2026, `scripts/audit_dependencies.py` a été réexécuté avec le
virtualenv candidat **Python 3.12.16** : **86 distributions interrogées auprès
OSV, aucun avis retourné** (outils inclus, dont git-filter-repo ajouté pour la
purge). Les 16 distributions initialement signalées sont corrigées comme suit.
Le virtualenv principal de développement reste inchangé ; ce résultat concerne
le candidat de livraison, pas ses anciennes dépendances.

| Distribution | Version initiale | Version candidate installée |
|---|---|---|
| anyio | 4.13.0 | 4.16.0 |
| autobahn | 26.7.1 | 26.11.1 |
| brotli | 1.2.0 | 1.2.1 |
| daphne | 4.2.1 | 4.2.3 |
| Django | 6.0.5 | 6.0.10 |
| idna | 3.11 | 3.20 |
| msgpack | 1.1.2 | 1.2.4 |
| pillow | 12.1.0 | 13.0.0 |
| PyMuPDF | 1.26.5 | 1.28.2 |
| pypdf | 6.19.0 | 6.21.4 |
| python-dotenv | 1.2.1 | 1.2.4 |
| sqlparse | 0.5.5 | 0.6.1 |
| Twisted | 26.4.0 | 26.10.0 |
| urllib3 | 2.7.0 | 2.8.0 |
| weasyprint | 66.0 | 70.0 |
| pip | 25.2 | 26.3 |

Le verrou Ubuntu Python 3.12 contient 84 distributions : son contrôle OSV
précédent n’a retourné aucun avis. `pip check` confirme uniquement la cohérence
des dépendances ; il ne prouve pas l’absence de vulnérabilités. Le résultat OSV
est ponctuel et limité à la base d’avis consultée, sans garantie d’absence de
vulnérabilités inconnues. Aucun audit général supplémentaire n’a été relancé.

Les 103 tests Django et 3 tests JavaScript précédents sont conservés ; seul le
compte rendu a changé depuis leur exécution. Les contrôles Django et migrations
sont revérifiés avant commit. Aucune recette native Ubuntu ni aucun accès VPS.

# Dépendances : audit de sécurité du 14 novembre 2026

## Contrôles exécutés

- Le virtualenv UFHOB fonctionne avec Python 3.14.0 et Django 6.0.5.
- `python -m pip check` réussit. Les versions directes de requirements.txt
  correspondent aux distributions installées.
- Leurs métadonnées Requires-Python acceptent Python 3.12.3.
- L'analyse syntaxique de 1 300 fichiers Python avec la grammaire 3.12 n'a
  trouvé aucune erreur au moment de l'inventaire.
- Ces vérifications ne prouvent pas l'installation des bibliothèques natives
  ni la résolution complète des dépendances sur Ubuntu. Une recette Linux reste requise.

## Frontend corrigé sans mise à niveau majeure

L'audit npm initial signalait 16 dépendances vulnérables : 7 high, 7 moderate,
2 low. La dépendance npm `codex`, ancienne bibliothèque non utilisée dans le
code ou les scripts du projet, et sa chaîne obsolète ont été retirées du manifeste.
Ce package n'était pas nécessaire au fonctionnement de l'agent ou de Django.

`npm audit fix --package-lock-only --ignore-scripts` a corrigé le verrou dans
les plages compatibles existantes, sans `--force`. Treize versions du verrou
ont changé et 51 entrées de dépendances obsolètes ont été retirées du verrou.
Le node_modules de travail n'a pas été supprimé ni remplacé.

Une installation neuve du verrou a été faite dans un dossier temporaire ignoré.
Les builds CSS public et applicatif ont réussi avec cet arbre de validation.
Son audit npm signale **zéro vulnérabilité**. Les CSS sources de livraison ont
été recompilés. Le prochain environnement neuf doit utiliser `npm ci` avec ce
verrou. Ce résultat ne constitue pas un audit de toutes les bibliothèques vendor
intégrées manuellement dans static/ ; leur provenance et licences restent à revoir.

## Python : blocage de sécurité à traiter avant exposition

Une requête OSV a contrôlé les noms et versions de 89 distributions installées,
outils compris. Elle signale 16 distributions avec des avis. Les identifiants
GHSA et PYSEC peuvent être des alias d'un même problème : ils ne sont pas
additionnés ici comme des vulnérabilités distinctes. L'applicabilité à un chemin
exposé doit être analysée ; aucun exploit applicatif n'est revendiqué par ce rapport.

| Distribution installée | Avis représentatif à examiner |
|---|---|
| anyio 4.13.0 | GHSA-5p39-cfhj-2xmp |
| autobahn 26.7.1 | GHSA-pjh6-c8mg-3x7m |
| brotli 1.2.0 | GHSA-9v8h-qqgm-4m35, classé critical par la base consultée |
| daphne 4.2.1 | GHSA-rrc9-mx66-ffcm |
| Django 6.0.5 | GHSA-3h9f-r86x-qvjx |
| idna 3.11 | GHSA-65pc-fj4g-8rjx |
| msgpack 1.1.2 | GHSA-6v7p-g79w-8964 |
| pillow 12.1.0 | GHSA-22hg-r758-rrw9 |
| PyMuPDF 1.26.5 | GHSA-cxqh-p2w9-fmr7 |
| pypdf 6.19.0 | GHSA-39mj-jf6j-2qj3 |
| python-dotenv 1.2.1 | GHSA-mf9w-mj56-hr94 |
| sqlparse 0.5.5 | GHSA-3496-9g83-7v6x |
| Twisted 26.4.0 | GHSA-2qrf-pqgx-qh9v |
| urllib3 2.7.0 | GHSA-8988-9cw3-xx77 |
| weasyprint 66.0 | GHSA-983w-rhvv-gwmv |
| pip 25.2, outil d'installation | GHSA-4xh5-x5gv-qwph |

Les réponses et détails sont conservés dans le dossier privé d'audit local.
Pour actualiser l'inventaire sans installation ni modification de paquets :

```powershell
.\.venv\Scripts\python.exe scripts/audit_dependencies.py
```

Cet outil transmet uniquement les noms et versions des distributions à
`https://api.osv.dev/v1/querybatch`, jamais les variables d'environnement ni les données métier.

## Décision de maintenance nécessaire

Les versions Python installées et requirements.txt sont conservées pendant cette
mission : l'ensemble des correctifs n'est pas une simple mise à jour uniforme de
patch. À titre d'exemples documentés, l'avis Pillow ci-dessus indique un correctif
13.0.0 et celui de WeasyPrint un correctif 68.0. Ces montées majeures ne sont pas
autorisées automatiquement par la mission. Les versions citées ne couvrent
qu'un avis chacune et ne sont **pas** un verrou global recommandé.

Après validation : établir une cible corrigée couvrant tous les avis applicables,
la résoudre dans un environnement neuf Python 3.12 Ubuntu, figer ses dépendances
transitives, puis tester PDF, images, uploads, ASGI/WebSockets, accès privés,
authentification et métiers avant de remplacer le virtualenv de travail.
Ne pas annoncer le socle Python actuel comme sécurisé pour une mise en ligne.

Sources : [API OSV](https://osv.dev/docs/),
[avis mainteneur Pillow](https://github.com/python-pillow/Pillow/security/advisories/GHSA-22hg-r758-rrw9),
[avis mainteneur WeasyPrint](https://github.com/Kozea/WeasyPrint/security/advisories/GHSA-983w-rhvv-gwmv).
