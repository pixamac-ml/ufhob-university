# Finalisation UFHOB — 14 novembre 2026

Cette passe corrige les constats précédents ; elle ne relance pas l’audit général.

## Corrections

- Clone officiel isolé ; branche `livraison/ufhob-securisation-20261114` issue
  de `origin/main` (nouvelle base assainie `8d94dafd`). Sources validées intégrées ; fichiers distants
  légitimes conservés. Deux migrations exclusives au prototype `schools`,
  incompatibles avec le moteur courant, archivées dans la sauvegarde privée.
- `backup.json`, archive et note locale exclus de la prochaine version, copies
  locales conservées. Export retiré des 7 commits et des 3 branches officielles ;
  références de fusion des 2 PR et anciens SHA encore accessibles, à faire traiter
  par GitHub Support. Les données exposées doivent rester considérées compromises.
- Secret SMTP : localisé dans l’ancien rapport local ; aucune correspondance
  exacte dans les 565 blobs de l’historique officiel, archives inspectées comprises.
  Aucune révocation exécutée. Rotation à décider par le propriétaire si cet
  ancien rapport a été diffusé ailleurs ; aucun identifiant d’un autre projet changé.
- Dépendances ciblées corrigées dans un virtualenv CPython 3.12.16 isolé :
  Django 6.0.10, Daphne 4.2.3, Pillow 13.0.0, WeasyPrint 70.0, PyMuPDF 1.28.2,
  ainsi que les dépendances affectées recensées. Typing Extensions ajusté pour
  satisfaire AnyIO corrigé. Virtualenv principal conservé intact.
- Audit OSV de l’environnement corrigé : 85 distributions, zéro signalement.
  Audit npm : zéro vulnérabilité. Verrou Linux 3.12/glibc 2.39 avec hachages :
  84 distributions, zéro signalement OSV.
- Stockage des mémoires sérialisé par fonction stable, sans chemin machine ni
  clé S3 dans les nouvelles migrations. Migration `0008_portable_private_storage`
  ajoutée ; anciennes migrations conservées, aucun déplacement de médias.
  Aucune migration appliquée à la base de développement.

## Validation

- pip check, contrôle Django et absence de migrations manquantes : réussis.
- Production isolée : contrôle, statiques, ASGI, PDF et 1 196 templates réussis.
- 3 tests JavaScript réussis.
- Sélection Django finale : **103 tests réussis**, dont les 85 tests initiaux,
  5 contrôles des bibliothèques/stockage et 13 tests mémoires. Une fixture de
  formulaire a été complétée avec le champ obligatoire existant type_travail ;
  aucune règle métier affaiblie. Base de test SQLite isolée détruite après exécution.
- Exécution native : Python 3.12 sur Windows. Le verrou est résolu pour Linux
  x86_64 compatible Ubuntu 24.04 ; aucune exécution Ubuntu/VPS revendiquée.
  Prévoir Pango et libharfbuzz-subset0 sur Ubuntu. Le PDF Windows fonctionne avec
  le repli FontTools, signalé comme déprécié par WeasyPrint pour une version future.

## Publication et installation ultérieure

Purge publique explicitement autorisée, exécutée et vérifiée : les trois branches
UFHOB ont été actualisées atomiquement avec contrôle de leurs anciens SHA.
Le script privé préparé `reprendre-purge.ps1` a été réutilisé. Authentification
GitHub CLI `pixamac-ml`, dépôt vérifié `pixamac-ml/ufhob-university` uniquement.
Nouvelle `main` : `8d94dafd04faa26c18276862340a4e8e020a63f3`.

Les sept nouveaux arbres ont été contrôlés sur GitHub : aucun `backup.json` ni
blob de cet export. Seul l’export a été retiré ; auteurs, messages, dates et tous
les autres fichiers sont préservés. Bundle privé inchangé, empreinte vérifiée.

**Risque résiduel confirmé** : les deux références de fusion `refs/pull/*/merge`
contiennent encore l’export ; les sept anciens commits restent accessibles par
SHA. Les têtes des deux PR sont assainies. Un brouillon privé de demande à GitHub
Support est préparé, non envoyé. Aucune PR ni référence gérée par GitHub n’a été
modifiée hors des trois branches autorisées. Les copies déjà téléchargées ne
peuvent pas être retirées par cette opération. Les responsables devront évaluer
l’invalidation des accès/sessions concernés dans le système source ; aucune
révocation ni modification de données métiers n’a été effectuée ici.

Branche applicative `livraison/ufhob-securisation-20261114` resynchronisée sur la
nouvelle `main` dans le clone isolé ; arbre de l’index strictement préservé.
Le transfert réseau Git s’étant bloqué, les objets assainis ont été récupérés
depuis le miroir local vérifié, avec comparaison indépendante des SHA GitHub.
Aucun commit applicatif final ni push applicatif exécuté ; aucun accès VPS.
Les résultats des 103 tests Django et 3 tests JavaScript précédents sont conservés,
le code applicatif n’ayant pas été modifié par la purge. Les contrôles de reprise
et leurs preuves privées sont dans `.tmp-ufhob-finalisation/private/`.
Après purge : `pip check`, contrôle Django et contrôle des migrations réussis.
Les 2 711 fichiers de l’index ont été revérifiés : aucun secret local connu,
aucune signature de jeton/clé privée, aucun export Django ni fichier > 5 Mio.
Un signalement heuristique correspond à une constante fictive dans un test BBB
avec domaine example.test, examiné et classé sans secret réel.

Les commandes suivantes ne seront exécutées qu’après publication validée et
accord d’intervention Hostinger, avec le SHA réellement approuvé :

```bash
cd /srv/ufhob
git status --short
git remote get-url origin
git fetch origin livraison/ufhob-securisation-20261114
ufhob_release_sha='SHA_DU_FUTUR_COMMIT_VALIDE'
git switch --detach "$ufhob_release_sha"
test -x .venv/bin/python || python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip==26.3
.venv/bin/python -m pip install --require-hashes -r requirements-ubuntu.lock
.venv/bin/python -m pip check
sudo -u ufhob bash deploy/manage-ufhob.sh check --deploy
sudo -u ufhob bash deploy/manage-ufhob.sh migrate --plan
# Sauvegarde, verification de la base cible et accord avant les ecritures :
sudo -u ufhob bash deploy/manage-ufhob.sh migrate
sudo -u ufhob bash deploy/manage-ufhob.sh collectstatic --noinput
sudo systemctl restart ufhob.service
sudo journalctl -u ufhob.service -n 100 --no-pager
```

Première installation sur une base UFHOB vide : ne pas appliquer cette intégration
à une base du prototype `schools` déjà remplie sans plan de reprise distinct.
Ne pas recréer un virtualenv serveur existant à l’aveugle ; le préparer uniquement
si absent, ou utiliser un nouvel environnement validé pour une mise à jour.
Configuration existante : `/srv/ufhob`, `ufhob_db`, `ufhob_app`, `ufhob.service`,
Daphne `127.0.0.1:8002`. Aucun changement d’ESFé, aucune donnée locale supprimée.

Version préparée : **2 711 fichiers suivis**, dont **2 428 chemins modifiés,
ajoutés ou retirés** par rapport à la main officielle. Commit français préparé,
non créé. Les quatre suppressions de suivi restantes concernent deux fichiers exclus
et deux migrations du prototype archivées ; backup.json est déjà absent de la
nouvelle base. Aucun effacement des copies privées.
