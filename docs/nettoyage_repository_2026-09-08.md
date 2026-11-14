# Nettoyage récupérable du dépôt ESFE Core — 8 septembre 2026

Mission exécutée après lecture intégrale de `AGENTS.md` et `temp.txt`, examen de l'état Git, du diff et de la taille du dépôt. Aucun clonage Université, changement de branding ou modification métier n'a été effectué.

## Résultat physique

Les tailles ci-dessous sont exprimées en Mo décimaux (1 Mo = 1 000 000 octets), arrondies au dixième.

| Mesure | Taille |
|---|---:|
| Dépôt avant nettoyage, Git et environnements compris | 2 193,7 Mo |
| Dépôt après nettoyage, hors `VIDAGE_COMPLET` | 1 396,2 Mo |
| Réduction nette de l'arborescence active | 797,5 Mo |
| Fichiers effectivement déplacés | 797,6 Mo |
| `VIDAGE_COMPLET`, avec inventaires, manifestes et validations | Environ 831,1 Mo |

6 647 fichiers ont été déplacés, sans suppression définitive. Les 6 647 empreintes SHA-256 des copies archivées correspondent aux empreintes des originaux avant déplacement. Sept résidus Office ont été conservés par prudence. La légère différence entre volume déplacé et réduction nette tient aux fichiers générés ou modifiés pendant l'intervention dans cet espace de travail actif.

Le déplacement reste sur le même volume : il ne libère pas encore d'espace disque. Le propriétaire doit déplacer manuellement l'archive vers un autre emplacement après validation. Aucun compactage ou changement de l'historique Git n'a été réalisé.

## Principaux responsables du poids initial

| Élément | Taille initiale | Traitement |
|---|---:|---|
| `.git/` | 659,4 Mo | Historique conservé |
| `.venv/` | 524,1 Mo | Conservé : deux processus Python actifs l'utilisent |
| `media/` | 329,0 Mo | Téléversements et documents générés archivés |
| `SITE/` | 327,2 Mo | Documents EPSFé archivés ; UPFHOB et résidus Office conservés |
| `esfe-core.zip` | 63,2 Mo | Archivé |
| `node_modules/` | 55,5 Mo | Conservé : un processus Node actif l'utilise |
| `staticfiles/` | 51,3 Mo | Contenu généré archivé ; régénération vérifiée |
| `static/` | 37,6 Mo | Sources et assets applicatifs conservés |

L'inventaire des 30 fichiers et des 30 entrées de premier niveau les plus volumineux est fourni dans `VIDAGE_COMPLET/_nettoyage/top30-files.csv` et `top30-directories.csv`. La taille initiale exacte mesurée était de 2 193 698 392 octets.

## Catégories déplacées

| Catégorie | Fichiers | Octets |
|---|---:|---:|
| Médias téléversés et générés (`media`) | 3 381 | 329 008 201 |
| Médias privés et rendus (`private_media`) | 1 156 | 2 210 142 |
| Documents historiques, présentations, captures et maquettes | 470 | 228 069 270 |
| Bases SQLite QA et journaux associés | 27 | 90 282 168 |
| Archive ZIP, dump et sorties locales | 8 | 63 315 344 |
| Résultat de `collectstatic` | 264 | 51 318 128 |
| Anciennes preuves de recette (`_audit`) | 96 | 15 570 121 |
| Artefacts de tests (`test_artifacts`) | 14 | 2 494 253 |
| Caches Python hors environnements actifs | 1 228 | 9 459 332 |
| Sauvegardes PostgreSQL locales | 3 | 5 868 407 |
| **Total** | **6 647** | **797 595 366** |

Les bases SQLite et leurs journaux ont fait l'objet d'une vérification groupée : une famille en cours d'utilisation ou modifiée depuis l'inventaire devait rester en place. PostgreSQL lui-même n'a subi aucune mutation.

Les maquettes et scripts historiques de `mockups/` et `mocukp/`, ainsi que les HTML isolés à la racine, ont été examinés et recherchés dans les références applicatives. Aucun template applicatif n'a été retiré sur la seule base de son nom ou de l'absence d'une référence statique.

## Conservation et travail concurrent

La classification complète A/B/C/D est enregistrée dans `classification-reviewed.csv` : source obligatoire, source/asset utilisé, artefact à archiver, élément incertain ou protégé.

Sont conservés :

- applications Django, modèles, services, accès, URLs, migrations et tests, y compris tous les nouveaux fichiers et changements concurrents ;
- templates applicatifs, composants UI, sources CSS/JS, polices, logos, bibliothèques statiques embarquées et CSS compilé utilisé par les pages ;
- `manage.py`, configuration, dépendances, lockfile, bootstrap institutionnel et documentation technique/déploiement ;
- `AGENTS.md`, `temp.txt`, `bbb.txt`, `devin.txt`, ainsi que `temp1.txt` et `img_3.png`, déjà présents dans le travail concurrent ;
- `.env` local, ignoré et non suivi par Git, et `.env.example` ;
- `.git/`, `.idea/`, `.junie/`, `.devin/` et les outils de diagnostic dont l'usage actuel ne justifiait pas le retrait.

Au contrôle final, 250 fichiers de la liste protégée ont conservé leur SHA-256. Le seul changement de cette liste est `.gitignore`, modifié dans cette mission. L'index Git est identique à l'index enregistré avant nettoyage : aucune opération `add`, commit, reset, restore, stash, clean ou revert n'a été effectuée. Les suppressions et autres modifications qui existaient déjà avant la mission ont été laissées telles quelles.

Éléments volontairement laissés en place :

- `.venv/` et `node_modules/` : des processus concurrents les utilisent encore. Les déplacer aurait interrompu les serveurs ou le compilateur. `requirements.txt` reste disponible ; la cohérence de `package.json` avec le lockfile a été vérifiée. Le retrait de ces environnements reste différé tant qu'ils sont utilisés.
- `SITE/UPFHOB/` (105,8 Mo) : documents de la future mission et activité Office constatée. Aucun traitement Université n'a été entrepris.
- `SITE/AMAQ 2024/` : sept résidus Office et système, conservés par prudence.
- `price.txt`, `configuration`, `HANDOFF_OTP_CASH_RESERVE.md` et `ESFE_Dashboard_Gestionnaire_Evolution_Metier.txt` : références locales ou métier potentiellement actuelles.
- Certains répertoires désormais vides (`staticfiles`, `backups`, `_audit`, `test_artifacts`, `mocukp`) restent verrouillés par Windows. Les arbres vides `mockups` et `audits_dashboards` ont été déplacés sous `_repertoires_vides/`. Les racines de stockage `media` et `private_media` restent disponibles pour l'application.

## Modifications actives

- `.gitignore` : ajout de `VIDAGE_COMPLET/`, `backups/`, `logs/`, journaux SQLite, couverture et caches Mypy/Ruff ; correction de l'exception `!.env.example` ; retrait d'une fin de fichier corrompue contenant des octets NUL et un doublon de règle.
- `tailwind.config.js` : exclusion explicite de `VIDAGE_COMPLET` du parcours des templates, pour éviter que les archives influencent les prochaines compilations CSS.
- Ce rapport de nettoyage. Tous les scripts d'intervention, inventaires et sorties de validation sont rangés dans l'archive.

Aucun modèle, schéma, workflow métier ou configuration de stockage n'a été modifié. Aucune migration n'a été créée ni appliquée.

## Validations exécutées

| Validation | Résultat |
|---|---|
| `python manage.py check` avant et après | PASS — aucun problème, sortie 0 |
| `python manage.py makemigrations --check --dry-run` avant et après | PASS — `No changes detected`, sortie 0 |
| Analyse syntaxique des sources Python après nettoyage | PASS — 1 178 fichiers |
| Chargement de 8 templates essentiels | PASS — base, accueil, connexion, shell de direction, étudiant, enseignant, DG, gestionnaire |
| Recherche de 19 assets par les finders Django | PASS — CSS, JS, logos, polices et CKEditor |
| Import de `config.urls`, `config.wsgi`, `config.asgi` | PASS |
| Démarrage HTTP isolé sur port local éphémère, lecture du CSS réel | PASS — HTTP 200 |
| `python manage.py collectstatic --dry-run --noinput --verbosity 0` | PASS — sortie 0 |
| `node --check tailwind.config.js` et contrôle du lockfile | PASS |
| Compilation Tailwind vers `VIDAGE_COMPLET/_nettoyage/css-validation.css` | PASS — sans écraser le CSS concurrent |
| `git diff --check -- .gitignore tailwind.config.js` | PASS |
| Empreintes SHA-256 des fichiers déplacés | PASS — 6 647 fichiers vérifiés, aucune différence |
| Comparaison de l'index Git | PASS — identique |

Conformément à la mission, aucune grande suite de tests n'a été lancée. Les commandes ont produit quelques avertissements GLib/Windows et Browserslist ; leurs sorties finales sont néanmoins valides. Les vérifications Django ont été exécutées avec le moteur PostgreSQL configuré, sans réinitialisation de données.

## Récupération et précautions avant déplacement de l'archive

Le manifeste `VIDAGE_COMPLET/_nettoyage/moves.csv` contient les colonnes `Path`, `Destination`, `Bytes`, `SHA256`, `Result`. Pour une ligne `MOVED`, remettre le fichier de `Destination` à `Path`, après avoir vérifié qu'aucun fichier plus récent n'existe à cet emplacement. Les documents de travail sont préfixés par `documents_travail/` ; les autres chemins relatifs sont conservés directement.

L'archive contient des documents privés, des données de test, des sauvegardes, un ancien `.env.txt` et un diff de travail. Elle doit rester privée et ne doit pas être versionnée ou publiée.

Les médias déplacés ne sont plus accessibles par leurs anciennes URL locales. Leur récupération ou transfert vers le stockage de déploiement sera nécessaire pour conserver l'accès aux pièces jointes des données existantes. Les écritures de nouveaux médias restent possibles dans les racines de stockage actives.

Les déplacements de fichiers suivis apparaissent comme des suppressions non indexées dans Git. Un clonage Git du dernier commit reproduirait encore son contenu antérieur : le propriétaire devra intégrer les changements retenus dans une étape ultérieure de préparation de release. Aucun commit ni clonage n'a été effectué dans cette mission.

Le propriétaire peut déplacer manuellement `VIDAGE_COMPLET` après consultation de ce rapport et de `VIDAGE_COMPLET/LIRE_AVANT_DEPLACEMENT.md`. Aucune autre transformation ne sera engagée sans sa prochaine instruction.
