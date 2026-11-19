# Livraison campagne UFHOB-Mali — 17 novembre 2026

## Audit ciblé

- Dépôt : UFHOB uniquement. Branche initiale `prep/ufhob-deployment-20261114` ; branche de livraison `lancement/catalogue-public-20261117`.
- Environnement local vérifié : `.venv/Scripts/python.exe`, Python 3.14.0, Django 6.0.5, `config.settings`, PostgreSQL `ufhob_db`.
- Architecture réutilisée : Institution → School → SchoolBranch → Branch ; Programme ; Candidature et tunnel Alpine/HTMX existant en quatre étapes. Aucun second moteur d'admission.
- Écoles ESGA/FATEC et campus Moribabougou déjà présents localement. Les anciennes formations sont déclinées en DUT/Licence/Master ; les rattachements historiques ne sont pas réécrits pour correspondre à la publicité.
- La base locale ne contenait aucune candidature au moment de l'audit. Aucun enregistrement supprimé. Les autres données, dont les données de démonstration éventuelles, sont conservées faute de qualification certaine.
- Une migration `memoires.0008_portable_private_storage` était déjà en attente avant cette mission ; elle n'a pas été appliquée à la base PostgreSQL locale par cette mission.
- Les anciennes commandes `seed_ufhob_catalogue` et `seed_ufhob_academic_year` contiennent prix, diplômes ou données de démonstration ; ne pas les utiliser pour ce lancement.

## Choix d'architecture

Les six offres utilisent le modèle Programme existant. Cycle, diplôme et durée deviennent facultatifs afin de ne pas inventer de qualification académique. Les relations historiques existantes sont conservées. L'affectation académique précise devra être validée avant la création d'une inscription et d'une classe ; la réception des candidatures reste possible.

Le marqueur `campaign_published` donne la priorité aux six offres sur l'accueil et leur attribue les URLs avec école. Les anciennes URLs restent accessibles. Les données de présentation restent administrables sur Programme. La publication des frais historiques est désactivée ; les lignes Fee restent intactes.

Les UTM sont limités aux cinq clés demandées, à 255 caractères par valeur, conservés en session et dans des champs cachés du formulaire, transmis dans les redirections et enregistrés dans `Candidature.campaign_tracking`. Ce suivi n'installe aucun pixel publicitaire tiers.

Le contact provisoire est configurable avec `PUBLIC_CAMPAIGN_PHONE`, `PUBLIC_WHATSAPP_URL`, `ESGA_CONTACT_PHONE`, `FATEC_CONTACT_PHONE`, `ESMED_CONTACT_PHONE`. Aucun fichier `.env` n'a été modifié. Les champs de contact institutionnels peuvent rester vides sur une base neuve plutôt que d'inventer une adresse ou un email.

## Migrations de la mission

- `core.0021_alter_institution_address_alter_institution_city_and_more`
- `formations.0013_programme_campaign_published_and_more`
- `admissions.0005_candidature_campaign_tracking`

## Initialisation

```bash
python manage.py initialiser_catalogue_ufhob --dry-run
python manage.py initialiser_catalogue_ufhob
python manage.py initialiser_catalogue_ufhob --require-ready
```

`--campus SLUG` associe explicitement les deux écoles à un campus existant, actif et ouvert aux candidatures ; l'option est répétable. Pour une base entièrement neuve, `--campus SLUG --campus-name NOM --campus-code CODE` crée le campus à partir des seules valeurs explicitement fournies, sans adresse ni ville inventée. `--year-start AAAA-MM-JJ --year-end AAAA-MM-JJ` crée l'année 2026-2027 à partir de ses dates officielles ; les mêmes arguments peuvent être réexécutés sans doublon. Une année existante différente n'est pas écrasée et une autre année active n'est pas désactivée.

La commande ne réactive pas une présence SchoolBranch désactivée. Elle préserve les informations éditoriales déjà renseignées et les données académiques/financières ; une référence ambiguë, archivée ou rattachée à une autre école fait échouer toute la transaction.

`--require-ready` interdit de conclure au succès si l'année active n'est pas 2026-2027 ou si une école n'a aucun campus de candidature. Sur une production vide, ces références doivent d'abord être fournies avec leurs valeurs officielles. Aucun campus, calendrier, diplôme ou prix n'est deviné.

## URLs publicitaires

1. https://ufhob-mali.ml/formations/esga/finance-comptabilite/
2. https://ufhob-mali.ml/formations/esga/informatique-de-gestion/
3. https://ufhob-mali.ml/formations/esga/gestion-des-entreprises-et-administration/
4. https://ufhob-mali.ml/formations/fatec/reseaux-telecommunications/
5. https://ufhob-mali.ml/formations/fatec/marketing-communication/
6. https://ufhob-mali.ml/formations/fatec/gestion-des-ressources-humaines/

Écoles : `/ecoles/esga/` et `/ecoles/fatec/`. Tunnel : `/admissions/?formation=SLUG`.

## Validation reproductible

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test formations.test_campaign_launch admissions.tests --settings=config.settings_test_campaign --keepdb --noinput
.\.venv\Scripts\python.exe manage.py test formations.test_campaign_mobile --settings=config.settings_test_campaign --keepdb --noinput
```

Le test navigateur nécessite Playwright et Microsoft Edge sur le poste de validation. Il vérifie les six pages à 320 et 390 pixels, le titre, le bouton orange dans le premier écran, l'absence de débordement horizontal et le parcours réel en quatre étapes jusqu'à la création d'une candidature dans SQLite isolé. Captures locales : `.tmp-campaign-browser/`. Les fichiers SQLite et captures ne sont pas à versionner.

Résultats constatés : `check` sans erreur, `makemigrations --check --dry-run` sans changement. Suite complète : **22 tests réussis**, dont le navigateur réel et la double initialisation d'une base vide avec références explicites. L'initialisation PostgreSQL locale a été exécutée deux fois : deuxième passage, zéro création et zéro mise à jour. Les suites des modules internes sans rapport avec le lancement n'ont pas été exécutées.

Le contrôle Git des espaces porte aussi sur le travail préexistant et signale des espaces de fin de ligne dans `config/settings.py` ; ces lignes étrangères à la mission n'ont pas été nettoyées.

## Git

Le dépôt contenait de très nombreuses modifications et suppressions préexistantes, y compris des suppressions déjà indexées. L'index n'est pas modifié par cette mission afin de préserver ce travail. Ne pas lancer `git add .` ni un commit global.

Message proposé : `Finaliser le catalogue public UFHOB et le suivi des candidatures publicitaires`.

```bash
git status --short
git diff -- formations admissions core templates config deploy
# Après revue du travail préexistant, indexer uniquement les changements voulus.
git add -p -- formations admissions core templates config deploy
# Les nouveaux fichiers doivent également être ajoutés explicitement après revue.
git diff --cached --stat
git diff --cached
# Ne poursuivre que si l'index ne contient aucune suppression/modification étrangère
# à la livraison revue : certaines suppressions étaient déjà indexées avant la mission.
git commit -m "Finaliser le catalogue public UFHOB et le suivi des candidatures publicitaires"
git push -u origin lancement/catalogue-public-20261117
```

Le patch local `.tmp-campaign-baseline/mission.patch` isole les changements de cette mission par rapport à l'état trouvé au début ; il ne représente pas nécessairement un patch directement applicable à HEAD, car le travail préexistant est une dépendance de la livraison. Ne pas exporter de base opérationnelle dans Git.

## Déploiement VPS — à exécuter seulement après autorisation

Ces chemins proviennent des fichiers de déploiement du dépôt : `/srv/ufhob`, `/etc/ufhob/production.env`, service `ufhob.service`. Ils n'ont pas été revérifiés sur le VPS pendant cette mission. Aucun déploiement, push ou redémarrage n'a été effectué.

Après publication et revue du commit, dans une session Bash administrateur :

```bash
set -euo pipefail
cd /srv/ufhob
test -z "$(sudo -u ufhob git status --porcelain)"
sudo -u ufhob git fetch origin lancement/catalogue-public-20261117
sudo -u ufhob git switch --detach origin/lancement/catalogue-public-20261117
# Sauvegarde uniquement UFHOB, conservée côté serveur.
sudo install -d -o postgres -g postgres -m 0700 /var/backups/ufhob-campaign
sudo -u postgres pg_dump -Fc -d ufhob_db -f "/var/backups/ufhob-campaign/avant-catalogue-$(date +%Y%m%d-%H%M%S).dump"
sudo -u ufhob bash deploy/manage-ufhob.sh check
sudo -u ufhob bash deploy/manage-ufhob.sh migrate --noinput
sudo -u ufhob bash deploy/manage-ufhob.sh initialiser_catalogue_ufhob --dry-run
# Base entièrement neuve : après confirmation du campus et des dates officielles,
# utiliser les options --campus-name, --campus-code, --year-start et --year-end.
# Si les présences SchoolBranch existent déjà :
sudo -u ufhob bash deploy/manage-ufhob.sh initialiser_catalogue_ufhob --require-ready
# Si Moribabougou est confirmé et existe sous ce slug, employer à la place :
# sudo -u ufhob bash deploy/manage-ufhob.sh initialiser_catalogue_ufhob --campus moribabougou --require-ready
sudo -u ufhob bash deploy/manage-ufhob.sh initialiser_catalogue_ufhob --require-ready
sudo -u ufhob bash deploy/manage-ufhob.sh collectstatic --noinput
sudo -u ufhob bash deploy/manage-ufhob.sh check --deploy
sudo systemctl restart ufhob.service
sudo systemctl is-active ufhob.service
for path in \
  / /ecoles/esga/ /ecoles/fatec/ \
  /formations/esga/finance-comptabilite/ \
  /formations/esga/informatique-de-gestion/ \
  /formations/esga/gestion-des-entreprises-et-administration/ \
  /formations/fatec/reseaux-telecommunications/ \
  /formations/fatec/marketing-communication/ \
  /formations/fatec/gestion-des-ressources-humaines/ \
  '/admissions/?formation=finance-comptabilite&utm_source=verification'; do
  curl --fail --silent --output /dev/null --write-out '%{http_code} %{url_effective}\n' "https://ufhob-mali.ml$path"
done
```

Le CSS critique des pages publicitaires et des boutons est livré directement dans les templates, sans dépendre d'une compilation Tailwind. Aucune modification Nginx n'est nécessaire. Ne créer aucune candidature fictive sur le VPS.

## Limites avant ouverture

- Vérifier l'année active et les implantations réelles avec `--require-ready` ; les dates officielles ne sont pas inventées.
- Les anciennes formations et contenus institutionnels restent conservés. Les six nouvelles pages ne publient ni frais ni reconnaissance État/CAMES ; tout ancien texte éditorial réutilisé doit rester validé par la direction.
- Les logos actuels et les champs de configuration sont conservés ; les fichiers SVG futurs ne sont pas encore fournis.
- Le site de production n'a pas pu être lu par l'outil web de cette session. La validation HTTPS finale doit être réalisée après déploiement.
- `esfe-core` et `esfe_db` n'ont pas été touchés.

## Inventaire précis des fichiers de mission

- `admissions/admin.py`
- `admissions/migrations/0005_candidature_campaign_tracking.py`
- `admissions/models.py`
- `admissions/templates/admissions/partials/formation_options.html`
- `admissions/templates/admissions/tunnel.html`
- `admissions/tracking.py`
- `admissions/views.py`
- `config/settings.py`
- `config/settings_test_campaign.py`
- `core/context_processors.py`
- `core/migrations/0021_alter_institution_address_alter_institution_city_and_more.py`
- `core/models.py`
- `core/public_contact.py`
- `core/public_views.py`
- `core/views.py`
- `deploy/LANCEMENT_CAMPAGNE_2026-11-17.md`
- `deploy/manage-ufhob.sh`
- `formations/admin.py`
- `formations/campaign_catalogue.py`
- `formations/management/commands/initialiser_catalogue_ufhob.py`
- `formations/migrations/0013_programme_campaign_published_and_more.py`
- `formations/models.py`
- `formations/templates/formations/campaign_detail.html`
- `formations/templates/formations/detail.html`
- `formations/test_campaign_launch.py`
- `formations/test_campaign_mobile.py`
- `formations/urls.py`
- `formations/views.py`
- `static/src/css/admission_funnel.css`
- `templates/cotton/public/footer.html`
- `templates/cotton/public/programme_card.html`
- `templates/cotton/public/school_programme_card.html`
- `templates/home.html`
- `templates/public/base.html`
- `templates/public/school_detail.html`
