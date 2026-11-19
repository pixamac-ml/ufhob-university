# UFHOB — ufhob-mali.ml — Ubuntu 24.04

Préparation locale uniquement, aucune commande exécutée sur le VPS. Ne lancer
ces étapes qu'après autorisation d'intervention serveur. PR #3 non fusionnée.
Code validé : `77aef83799acb000a20d6af5aa5fa3e445fd4350` ; les modèles de domaine
ci-joints sont un complément local non inclus dans ce commit. Transférer l'archive
préparée séparément et l'extraire sous `/tmp` (pas dans le dépôt applicatif).

Paramètres restant à fournir : IP publique IPv4 du VPS (IPv6 seulement si servie),
adresse de contact ACME, nouvelles clés SECRET_KEY et CARD_SIGNING_KEY distinctes,
mot de passe du rôle existant ufhob_app, SMTP UFHOB et expéditeur vérifié.
Confirmer Redis local DB 2 et son authentification/ACL si requise ; ne modifier
aucune configuration Redis existante. BBB_API_URL et BBB_SECRET sont nécessaires
uniquement pour activer la visioconférence distante ; stockage B2/S3 facultatif.
Aucun `www` n'est demandé. Médias institutionnels autorisés à transférer séparément.

## 1. DNS, installation et récupération du code

Exécuter dans une session Bash administrateur, sans `set -x`. Les entrées DNS A
doivent désigner l'IPv4 fournie ; toute entrée AAAA doit réellement servir ce site.
Les ports publics 80/443 doivent être autorisés, jamais 8002 ou Redis/PostgreSQL.
Le rechargement Nginx affecte le processus partagé, sans modifier les autres sites.

```bash
set -euo pipefail
sudo apt-get update
sudo apt-get install -y python3.12-venv postgresql-client redis-tools certbot dnsutils \
  libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libpq5 ffmpeg fonts-dejavu-core
dig +short A ufhob-mali.ml
dig +short AAAA ufhob-mali.ml
# Comparer aux adresses du VPS avant de poursuivre.
id ufhob >/dev/null 2>&1 || sudo useradd --system --user-group --home-dir /srv/ufhob --shell /usr/sbin/nologin ufhob
sudo install -d -o ufhob -g www-data -m 0750 /srv/ufhob
cd /srv/ufhob
if [[ ! -d .git ]]; then
  test -z "$(find . -mindepth 1 -maxdepth 1 -print -quit)"
  sudo -u ufhob git init
  sudo -u ufhob git remote add origin https://github.com/pixamac-ml/ufhob-university.git
fi
test "$(sudo -u ufhob git remote get-url origin)" = 'https://github.com/pixamac-ml/ufhob-university.git'
test -z "$(sudo -u ufhob git status --porcelain)"
sudo -u ufhob git fetch --no-tags origin livraison/ufhob-securisation-20261114
sudo -u ufhob git cat-file -e 77aef83799acb000a20d6af5aa5fa3e445fd4350^{commit}
sudo -u ufhob git switch --detach 77aef83799acb000a20d6af5aa5fa3e445fd4350
test -x .venv/bin/python || sudo -u ufhob python3.12 -m venv .venv
sudo -u ufhob .venv/bin/python -m pip install --upgrade pip==26.3
sudo -u ufhob .venv/bin/python -m pip install --require-hashes -r requirements-ubuntu.lock
sudo -u ufhob .venv/bin/python -m pip check
```

Si `/srv/ufhob` contient déjà des fichiers hors dépôt, la procédure s'arrête :
inspecter ces fichiers, sans les supprimer ni les écraser pour continuer.

## 2. Variables, PostgreSQL, Redis, migrations et statiques

Après transfert de `ufhob-hostinger-20261114.tar.gz` sous `/tmp`, vérifier son SHA256
contre le fichier fourni puis extraire. Le fichier de variables doit rester
compatible Bash et systemd : `KEY='valeur'`, sans expansion ni substitution shell.
Encoder le mot de passe PostgreSQL dans DATABASE_URL. Ne pas reprendre le .env local.

```bash
cd /tmp
sha256sum -c ufhob-hostinger-20261114.tar.gz.sha256
tar -xzf ufhob-hostinger-20261114.tar.gz
ufhob_cfg=/tmp/ufhob-hostinger-20261114/deploy
sudo install -d -o root -g ufhob -m 0750 /etc/ufhob
if ! sudo test -e /etc/ufhob/production.env; then
  sudo install -o root -g ufhob -m 0640 "$ufhob_cfg/production.env.example" /etc/ufhob/production.env
fi
sudoedit /etc/ufhob/production.env
# Garder ALLOWED_HOSTS=ufhob-mali.ml et CSRF_TRUSTED_ORIGINS=https://ufhob-mali.ml.
sudo install -d -o ufhob -g www-data -m 2750 /srv/ufhob/media /srv/ufhob/staticfiles
sudo install -d -o ufhob -g ufhob -m 0700 /srv/ufhob/private_media /srv/ufhob/logs /var/backups/ufhob
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh check --deploy
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh migrate --plan
# L'outil verifie la base ufhob_db ET l'utilisateur ufhob_app avant chaque commande.
# Avec .pgpass UFHOB en 0600 : sauvegarde avant la premiere ecriture.
sudo -u ufhob pg_dump -h 127.0.0.1 -U ufhob_app -Fc -f "/var/backups/ufhob/avant-$(date +%Y%m%d-%H%M%S).dump" ufhob_db
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh migrate
sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh collectstatic --noinput
```

Le rôle et la base existent : ne pas les recréer. Si les privilèges UFHOB sont
insuffisants, faire corriger uniquement ceux de ufhob_db par l'administrateur.
Redis doit rester privé. `redis-cli -h 127.0.0.1 -p 6379 -n 2 PING` doit retourner
PONG si l'accès sans authentification est autorisé ; sinon utiliser `--askpass`
et l'utilisateur ACL autorisé, jamais le secret dans la ligne de commande.
Les préfixes imposés par le code sont `ufhob:production` (cache) et
`ufhob:production:channels` (Channels), indépendamment de l'index Redis choisi.
Ne lancer aucune commande FLUSH, CONFIG SET ou redémarrage Redis partagé.

## 3. HTTP ACME, certificat, puis TLS et démarrage

Avant installation, vérifier qu'aucun autre virtual host ne déclare ufhob-mali.ml
et que le port 8002 est disponible : `sudo ss -ltnp 'sport = :8002'`.
L'édition ne concerne que `/etc/nginx/sites-available/ufhob` et ufhob.service.
Ne pas installer le modèle TLS avant que les deux fichiers certificat existent.

```bash
sudo install -d -o root -g www-data -m 0755 /var/lib/ufhob/acme
test ! -L /etc/nginx/sites-available/ufhob
if [[ -e /etc/nginx/sites-available/ufhob ]]; then
  sudo cp -a /etc/nginx/sites-available/ufhob "/etc/nginx/sites-available/ufhob.avant-$(date +%Y%m%d-%H%M%S)"
fi
sudo install -m 0644 "$ufhob_cfg/nginx-http.conf.example" /etc/nginx/sites-available/ufhob
if [[ -e /etc/nginx/sites-enabled/ufhob || -L /etc/nginx/sites-enabled/ufhob ]]; then
  test "$(readlink -f /etc/nginx/sites-enabled/ufhob)" = /etc/nginx/sites-available/ufhob
else
  sudo ln -s /etc/nginx/sites-available/ufhob /etc/nginx/sites-enabled/ufhob
fi
sudo nginx -t
sudo systemctl reload nginx
read -r -p 'Adresse email de contact Let’s Encrypt : ' ufhob_acme_email
sudo certbot certonly --webroot -w /var/lib/ufhob/acme --cert-name ufhob-mali.ml \
  -d ufhob-mali.ml --email "$ufhob_acme_email" --agree-tos --non-interactive
sudo test -s /etc/letsencrypt/live/ufhob-mali.ml/fullchain.pem
sudo test -s /etc/letsencrypt/live/ufhob-mali.ml/privkey.pem
sudo install -m 0644 "$ufhob_cfg/nginx.conf.example" /etc/nginx/sites-available/ufhob
sudo nginx -t
sudo systemctl reload nginx
sudo install -d -o root -g root -m 0755 /etc/letsencrypt/renewal-hooks/deploy
sudo install -m 0755 "$ufhob_cfg/renew-ufhob-certificate.sh" /etc/letsencrypt/renewal-hooks/deploy/ufhob-nginx
sudo certbot renew --cert-name ufhob-mali.ml --dry-run
systemctl list-timers --all certbot.timer
sudo install -m 0644 "$ufhob_cfg/ufhob.service" /etc/systemd/system/ufhob.service
sudo systemctl daemon-reload
sudo systemctl enable --now ufhob.service
sudo systemctl status ufhob.service --no-pager
sudo journalctl -u ufhob.service -n 80 --no-pager
sudo ss -ltnp 'sport = :8002'
```

Daphne doit écouter **127.0.0.1:8002**, sous l'utilisateur ufhob, avec variables
dans /etc/ufhob/production.env. Aucune écoute publique sur 8002. Si le certificat
échoue, conserver le virtual host HTTP (503 hors challenge). Vérifier le timer
de renouvellement ; s'il est absent, faire préparer sa planification. Le hook
ne recharge Nginx qu'après renouvellement du certificat UFHOB.

## 4. Recette fonctionnelle

```bash
curl -I http://ufhob-mali.ml/                     # 301 vers HTTPS
curl -I https://ufhob-mali.ml/                    # accueil, sans erreur 5xx
curl -I https://ufhob-mali.ml/accounts/login/     # formulaire de connexion
curl -I https://ufhob-mali.ml/static/public/css/main.css
curl -I https://ufhob-mali.ml/media/candidatures/interdit.pdf  # 404
```

Dans le navigateur, avec un compte de production habilité : connexion et
déconnexion, parcours CSRF/OTP SMTP, dashboard, images de la vitrine et ouverture
d'un PDF réel autorisé. Tester séparément le refus d'accès à ce PDF sans session
et avec un rôle non habilité. Les médias utilisateurs ne sont pas livrés par Git ;
transférer seulement les médias institutionnels validés, sans export des dossiers locaux.

Dans Réseau → WS, vérifier `wss://ufhob-mali.ml/ws/notifications/` : réponse **101**
avec une session autorisée, réception d'une notification de test consentie et refus
sans session. Les messages utilisent `/ws/messages/<conversation_id>/` : vérifier
l'appartenance, sans lire une conversation non autorisée. Le namespace Redis doit
être UFHOB ; vérifier les préfixes dans Django sans afficher les URL contenant des secrets.
La visioconférence nécessite les véritables paramètres BBB et une recette séparée.

En cas d'échec : consulter uniquement journalctl -u ufhob.service et les erreurs
du virtual host UFHOB ; ne pas migrer en arrière sans restauration validée.
La purge des anciennes références publiques via GitHub Support reste prioritaire.

Sources : [Certbot webroot](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot),
[HTTP-01 sur le port 80](https://letsencrypt.org/docs/challenge-types/),
[bibliothèque HarfBuzz Ubuntu 24.04](https://packages.ubuntu.com/noble/libharfbuzz-subset0).
