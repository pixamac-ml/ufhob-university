> Version corrigée : voir [FINALISATION_2026-11-14.md](FINALISATION_2026-11-14.md).
> Socle cible testé Python 3.12, Django 6.0.10 ; les mentions du socle initial
> sont conservées ci-dessous pour distinguer le virtualenv de développement historique.

# Guide de développement et de déploiement UFHOB

Toutes les commandes Ubuntu ci-dessous sont des procédures pour une opération
ultérieure validée. Cette mission ne se connecte pas au VPS et ne les exécute pas.
Un commit final, un push, une intervention serveur, une restauration ou une
modification de données demandent une validation distincte.

## 1. Isolation et prérequis

Prérequis de toute exécution serveur : traiter les blocages du rapport d’audit,
notamment les avis Python et les données présentes dans le dépôt public. Les
commandes suivantes ne sont pas une invitation à déployer le socle actuel.

| Ressource UFHOB | Valeur cible |
|---|---|
| Dépôt officiel | https://github.com/pixamac-ml/ufhob-university.git |
| Branche distante | main, sans écrasement ni push forcé |
| Application | /srv/ufhob |
| Virtualenv | /srv/ufhob/.venv |
| Service | ufhob.service |
| ASGI | 127.0.0.1:8002 |
| PostgreSQL | ufhob_db, rôle ufhob_app |
| Variables privées | /etc/ufhob/production.env |

Ne jamais agir sur `/srv/esfe`, `esfe_db`, `esfe.service`, le port 8001 ou le
dépôt ESFé. Les commandes Nginx doivent viser uniquement le fichier UFHOB.
Le rechargement de Nginx est partagé par l'hôte : faire un `nginx -t` et valider
l'intervention avant de le recharger, sans modifier aucune configuration ESFé.

Le local utilise Python 3.14.0 et Django 6.0.5. Django 6.0 supporte Python 3.12,
3.13 et 3.14 ; aucune montée de version majeure n'est nécessaire pour Ubuntu.
La présence de Python 3.12.3 ne prouve pas l'installation des dépendances natives
ni l'application des correctifs système Ubuntu. Ces éléments restent à contrôler
sur une recette Ubuntu séparée avant ouverture.

Sources officielles : [compatibilité Django](https://docs.djangoproject.com/en/6.0/faq/install/),
[Daphne](https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/daphne/),
[WeasyPrint 66](https://doc.courtbouillon.org/weasyprint/v66.0/first_steps.html).

## 2. Installation et développement local

Depuis le répertoire UFHOB sous PowerShell :

```powershell
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
```

Pour une nouvelle installation seulement : créer le virtualenv avec l'interpréteur
UFHOB choisi, installer `requirements.txt` via `python -m pip`, copier `.env.example`
en `.env` et renseigner de nouvelles valeurs locales. Ne pas remplacer un `.env`
existant. Vérifier la cible `ufhob_db` avant toute migration locale autorisée.
Le fichier exemple est un exemple de développement, pas la configuration Ubuntu.

```powershell
npm ci --ignore-scripts
npm run build:css
npm run build:css:app
.\.venv\Scripts\python.exe scripts/validate_deployment.py
.\.venv\Scripts\python.exe scripts/audit_release.py --history
```

`validate_deployment.py` génère ses clés en mémoire, interdit les connexions à la
base pendant les contrôles et écrit ses statiques dans un dossier `.tmp-*` ignoré.
Ce contrôle n'est pas un test de connectivité PostgreSQL, Redis, SMTP ou BBB.
`audit_release.py` ne révèle pas les secrets, mais son inventaire peut contenir des
noms de fichiers privés : ne pas publier le rapport JSON local.

## 3. Préproduction

Employer une machine ou un environnement de recette distinct, avec sa propre
base, son Redis, ses médias et ses clés. Le nom de base reste `ufhob_db` dans cet
environnement ; ne pas pointer la recette sur les données de production.
Copier le modèle serveur dans un fichier protégé hors du dépôt et définir :

```text
DJANGO_SETTINGS_MODULE=config.settings_staging
UFHOB_ENVIRONMENT=staging
```

Configurer le domaine HTTPS de recette et les services réellement associés.
Tester l'installation des dépendances, les migrations depuis zéro et une
restauration anonymisée autorisée. Ne pas exporter les comptes ou dossiers
locaux vers une recette publique sans décision explicite.

## 4. Préparation Ubuntu autorisée ultérieurement

Les paquets Python restent dans le virtualenv UFHOB ; ne pas utiliser `sudo pip`.
Prévoir Python 3.12, venv et les bibliothèques natives Pango, PangoFT2, HarfBuzz,
FFmpeg, libpq, polices DejaVu et outils PostgreSQL. Vérifier les noms de paquets
dans Ubuntu 24.04 avant installation et les besoins des roues réellement résolues.
Si des paquets doivent compiler, prévoir les en-têtes Python, libffi et outils C.

Un administrateur prépare le compte `ufhob` sans privilèges, le groupe `ufhob`,
le groupe de lecture Nginx `www-data` et les répertoires suivants :

```bash
sudo install -d -o ufhob -g www-data -m 0750 /srv/ufhob
sudo install -d -o root -g ufhob -m 0750 /etc/ufhob
sudo install -d -o ufhob -g www-data -m 0750 /srv/ufhob/media /srv/ufhob/staticfiles
sudo install -d -o ufhob -g ufhob -m 0700 /srv/ufhob/private_media /srv/ufhob/logs
sudo install -d -o ufhob -g ufhob -m 0700 /var/backups/ufhob
sudo install -d -o root -g www-data -m 0755 /var/lib/ufhob/acme
```

Le répertoire `/srv/ufhob` existe déjà selon l'inventaire fourni : vérifier son
contenu et sa propriété avant toute copie. Ne pas lancer `git clone ... .` dans
un dossier rempli et ne pas utiliser `rsync --delete`.
Après publication validée, récupérer uniquement le dépôt officiel et le SHA validé.

```bash
cd /srv/ufhob
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip==26.3
.venv/bin/python -m pip install --require-hashes -r requirements-ubuntu.lock
.venv/bin/python -m pip check
.venv/bin/python -m weasyprint --info
```

Les dépendances directes sont épinglées ; les contraintes Ubuntu supplémentaires
ne valent validation que si elles ont été effectivement résolues/testées sur
cette plateforme. Ne pas remplacer les versions pour contourner une erreur sans
en analyser la cause. Aucune installation Ubuntu n'a été exécutée depuis Windows.

## 5. Variables et PostgreSQL

Remplir `deploy/production.env.example` dans `/etc/ufhob/production.env` :
propriétaire root, groupe ufhob, mode 0640. Les entrées doivent être de la forme
`KEY='valeur'`, sans `export`, expansion shell ni substitution de commande.
Ne pas copier les secrets locaux. Générer séparément SECRET_KEY et
CARD_SIGNING_KEY, au moins 50 caractères, et encoder les caractères spéciaux
du mot de passe dans DATABASE_URL. Ne jamais mettre ce fichier dans Git.

Le profil impose DEBUG=False, HTTPS, des cookies sécurisés, `ufhob_db`, le rôle
`ufhob_app`, Redis et un SMTP chiffré configuré. Le domaine, SMTP, BBB et les
stockages B2/S3 restent à renseigner. Les modes de test de session et de cours
sont interdits sur serveur. Les préfixes Redis commencent par `ufhob:` et
diffèrent entre préproduction et production. L'exemple emploie Redis DB 2 ;
vérifier sa disponibilité sans modifier une autre application.

La base et le rôle sont annoncés existants ; ne pas les recréer automatiquement.
Vérifier que le rôle UFHOB possède les droits de connexion et de création dans
son schéma public pour les migrations, sans droits sur ESFé. Un administrateur
doit contrôler le propriétaire et les privilèges avant tout GRANT.
DB_SSL_REQUIRE=False n'est approprié que pour PostgreSQL local ou un réseau de
confiance approuvé ; suivre la politique SSL du fournisseur distant.

Après validation d'intervention, l'outil manuel ci-dessous charge le fichier
protégé, vérifie `current_database()` et `current_user` puis exécute la commande :

```bash
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh check
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh check --deploy
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh showmigrations --plan
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh migrate --plan
```

Ne pas écrire DJANGO_SETTINGS_MODULE uniquement dans un `.env` local : la
sélection du profil doit précéder `manage.py` ; systemd et l'outil le font.

## 6. Sauvegardes, migrations et statiques

Sauvegarder avant toute migration et tester la restauration en recette. Utiliser
un fichier `.pgpass` protégé en 0600 ou un gestionnaire de secrets ; ne pas mettre
le mot de passe dans la ligne de commande, les logs ou l'historique du shell.

```bash
pg_dump -h 127.0.0.1 -U ufhob_app -Fc -f /var/backups/ufhob/avant-migration.dump ufhob_db
```

Le nom de sauvegarde doit être unique par opération pour ne pas écraser une
sauvegarde précédente. Sauvegarder aussi `media/`, `private_media/` et les
variables privées dans un emplacement chiffré séparé. Prévoir copie hors VPS,
rétention définie, contrôle d'accès et alertes d'échec. `pg_restore --list` ne
remplace pas un essai de restauration réel. Pour B2/S3 : versionnement,
rétention et restauration propres au fournisseur ; ne pas rendre le bucket public.

Après examen du plan et autorisation de migration uniquement :

```bash
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh migrate
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh migrate --check
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh collectstatic --noinput
```

Ne pas lancer bootstrap, reset, flush ou seed pour déployer. Les migrations
historiques avec chemins Windows doivent être testées sur une base Ubuntu vide,
sans les réécrire. `collectstatic` ne traite pas les médias utilisateurs.
WhiteNoise sert `/static/` depuis `staticfiles/`, avec manifest et compression.
Ne pas utiliser `--clear` lors d'un simple déploiement : conserver les anciennes
empreintes le temps que les pages et navigateurs aient renouvelé leurs références.

## 7. Médias et documents privés

`static/` contient les images et scripts sources ; les nouvelles images de vitrine
placées ici passent par Git puis collectstatic. Les images chargées depuis un
dashboard sont dans `media/` : transfert séparé autorisé via SFTP/rsync sans
suppression distante, puis vérification de leurs références en base.

Ne pas transférer indistinctement les candidatures, reçus ou documents étudiants
pour publier des images de présentation. Conserver les médias institutionnels
locaux et approuver une sélection de transfert. Le déploiement du code ne copie
ni la base locale ni ses comptes. Établir explicitement les données de démarrage
autorisées ; aucune création automatique de comptes par ces fichiers.

Nginx ne sert qu'une liste de chemins de présentation et d'extensions permises.
Les pièces privées et `/private_media/` sont refusées en accès direct ; elles
doivent utiliser les vues Django autorisées ou des URLs privées signées.
La recette doit couvrir les anciennes vues qui dépendent encore directement
de `/media/` : ne pas assouplir le proxy pour contourner un écran cassé.

## 8. Daphne, systemd, Nginx et HTTPS

Daphne est déjà installé et compatible avec l'application ASGI/Channels existante.
Le service écoute uniquement sur 127.0.0.1:8002 et conserve les journaux dans
journald. Le modèle limite les écritures aux médias, documents privés, logs et
cache UFHOB. Il ne lance aucune migration au démarrage.

Après validation de l'administrateur : installer `deploy/ufhob.service` dans
`/etc/systemd/system/ufhob.service`, puis contrôler :

```bash
sudo systemd-analyze verify /etc/systemd/system/ufhob.service
sudo systemctl daemon-reload
sudo systemctl start ufhob.service
sudo systemctl status ufhob.service
sudo journalctl -u ufhob.service -n 100 --no-pager
```

Adapter le domaine confirmé dans les exemples Nginx avant installation. Ne pas
activer le bloc TLS tant que les certificats n'existent pas. Pour la première
émission, utiliser `nginx-http.conf.example`, uniquement pour le challenge ACME,
sans portail HTTP. Installer un fichier nommé UFHOB dans sites-available et son
lien dans sites-enabled, sans remplacer un site existant.

```bash
sudo nginx -t
# Rechargement partage : uniquement apres validation de l'intervention.
sudo systemctl reload nginx
sudo certbot certonly --webroot -w /var/lib/ufhob/acme -d DOMAINE_UFHOB_CONFIRME
```

Installer ensuite le modèle HTTPS avec les chemins de certificats réellement
obtenus, refaire `nginx -t`, puis recharger après validation. Vérifier le
renouvellement avec `certbot renew --dry-run`. Ne pas utiliser le plugin Certbot
Nginx pour modifier automatiquement les autres virtual hosts du serveur.
Le proxy remplace les en-têtes de provenance ; Daphne n'est pas exposé au réseau.
HSTS démarre à 3600 secondes, sans preload ni sous-domaines ; étendre seulement
après validation des domaines. Les avertissements Django W005/W021 sont attendus
pour ce choix initial. SAMEORIGIN est conservé pour les aperçus internes existants.

## 9. Vérification et exploitation

Sur le domaine HTTPS final : vérifier accueil, images, connexion, déconnexion,
changement de mot de passe, SMTP/OTP, pièces privées, reçus, PDF, cours, médias
signés et WebSockets. Tester School + Branch avec deux écoles sur le même campus,
ainsi que les fonctions de direction globale. Vérifier les permissions sur les
documents via des utilisateurs distincts. Contrôler les réponses 400/403/404/500
sans DEBUG et les journaux UFHOB sans recopier d'informations privées.

Si des tâches périodiques sont nécessaires, définir d'abord leur calendrier,
leur caractère idempotent et leur supervision. Aucune tâche cron ou migration
automatique à chaque démarrage/push n'est livrée ici.

## 10. Futures modifications et retour arrière

Cycle manuel : modifier localement → tests → contrôle migrations → compilation
CSS si nécessaire → revue des sources/médias/secrets → commit validé → push
validé → récupération du SHA validé sur Ubuntu → installation des dépendances
éventuellement modifiées → sauvegarde et migration approuvées → collectstatic →
redémarrage uniquement de `ufhob.service` → recette HTTP/journaux.

Avant récupération, vérifier `git status`, `git remote -v`, le SHA déployé et
l'absence de modifications serveur ; consigner le SHA précédent hors du dépôt web.
Utiliser une branche de livraison validée et `git pull --ff-only`, jamais de
fusion implicite, force push, reset --hard ou nettoyage des médias. Un push
n'entraîne aucun déploiement automatique.

En cas d'échec : arrêter uniquement UFHOB si nécessaire et conserver les logs.
Si le schéma reste compatible, revenir au SHA précédent par une opération Git
explicitement approuvée, réinstaller ses dépendances et ses statiques puis
redémarrer UFHOB. Ne pas inverser automatiquement les migrations ni restaurer
une base par réflexe. Une restauration exige validation, maintenance et prise
en compte des données écrites depuis la sauvegarde ; l'exécuter d'abord en recette.

La procédure de restauration validée utilise `pg_restore --exit-on-error` vers
une base UFHOB isolée préparée par l'administrateur. Une restauration destructive
de la production n'est jamais une étape automatique de ce guide. Revalider la
base cible et ses privilèges avant l'opération ; ESFé est toujours exclu.

## 11. Dépannage

| Symptôme | Contrôle |
|---|---|
| Import settings refusé | Variables requises, profil choisi avant manage.py, fichier serveur protégé |
| DisallowedHost/CSRF | Domaine exact, HTTPS, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS, en-têtes proxy |
| 502 Nginx | ufhob.service, port 8002, journald, import ASGI |
| CSS absent/manifest | Build Tailwind, collectstatic, fichiers source, droits staticfiles |
| Média privé en 404 direct | Comportement attendu ; utiliser la vue autorisée, ne pas publier tout media |
| Média public en 404 | Transfert réel, référence base, préfixe/extension autorisés, droits www-data |
| WebSockets absents | Upgrade Nginx, domaine Origin, Redis, préfixes et configuration Channels |
| SMTP/OTP échoue | Identifiants UFHOB, expéditeur autorisé, port/TLS, tests réels validés |
| PDF échoue | Pango/HarfBuzz, polices et bibliothèques natives, essai WeasyPrint |
| BBB échoue | URL et secret UFHOB, connexion API, horaire, affectation et inscription ; ne jamais exposer le secret |
