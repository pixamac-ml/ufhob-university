# Correction urgente du catalogue — 18 novembre 2026

## Modifications

Le catalogue retrouve `formations/list.html` et son fragment d’origine : en-tête, filtres HTMX et sélection de toutes les écoles actives (ESMed, ESGA, FATEC, ESFé Sup sur la base locale). Seule la branche FATEC/ESGA utilise le regroupement par filière, puis DUT/Licence/Master. La présentation provient de Filiere.description et apparaît une seule fois ; le composant de carte existant masque sa description uniquement quand ce paramètre lui est passé. Les autres cartes gardent leur comportement.

Tous les détails repassent par `formations/detail.html`, avec leurs sections et illustrations existantes. Les données de frais, pièces et conditions y sont injectées. Le gabarit de campagne distinct n’est plus utilisé par cette vue. Aucun texte « à confirmer » ou « annualité » n’est ajouté au HTML public. Les réserves métier de périodicité restent dans la documentation.

Génie logiciel et Audiovisuel multimédia reçoivent exactement les descriptions et débouchés fournis pour les trois niveaux, par la commande idempotente. Les descriptions de filière sont administrables sans répétition des trois cartes.

Aucun fichier CSS, aucune définition de couleur, aucun fichier de core hors vues n’a été modifié par cette correction. Le composant partagé de carte a reçu uniquement la condition de masquage du texte. Le travail parallèle de présentation est conservé.

## Contrôles locaux

`check` réussi ; `makemigrations --check --dry-run` : aucun changement. Aucun nouveau schéma ou migration applicative. Exécution locale du chargeur : 14 mises à jour éditoriales (6 programmes, 8 présentations de filière), puis zéro création et zéro mise à jour au passage suivant. Les autres programmes et les associations campus ne sont pas réinitialisés.

## PostgreSQL neuf et vide

Cluster PostgreSQL 18 temporaire créé avec initdb, indépendant du service PostgreSQL habituel : écoute 127.0.0.1:55439, données `.tmp-correction-catalogue/pgdata`. Base `test_ufhob_catalogue_vide`, profil `config.settings_test_postgres_catalogue`. Aucun secret de connexion principal imprimé. Le compte habituel n’avait pas CREATEDB ; aucun privilège ne lui a été ajouté.

Séquence exécutée sur ce cluster isolé :

```powershell
.\.venv\Scripts\python.exe manage.py migrate --settings=config.settings_test_postgres_catalogue --noinput
.\.venv\Scripts\python.exe manage.py preparer_catalogue_fatec_esga --settings=config.settings_test_postgres_catalogue
.\.venv\Scripts\python.exe manage.py preparer_catalogue_fatec_esga --settings=config.settings_test_postgres_catalogue
.\.venv\Scripts\python.exe manage.py charger_catalogue_fatec_esga --settings=config.settings_test_postgres_catalogue
.\.venv\Scripts\python.exe manage.py charger_catalogue_fatec_esga --settings=config.settings_test_postgres_catalogue
```

La préparation crée seulement l’institution, FATEC, ESGA, Moribabougou et les deux SchoolBranch manquants ; elle conserve les références déjà présentes. Aucun élève, utilisateur métier, candidature, paiement ni année académique avec des dates inventées. Pour recevoir des dossiers, une année académique active avec ses dates officielles doit également être configurée.

La permission du chargeur pour le test est limitée aux bases `test_ufhob_catalogue_*` et exige le drapeau du profil de test. La base opérationnelle autorisée reste `ufhob_db`.

### Séquence VPS après validation (non exécutée)

Avec le virtualenv et l’environnement privé du service UFHOB déjà chargés, sur une **base neuve** :

```bash
cd /srv/ufhob
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py preparer_catalogue_fatec_esga
.venv/bin/python manage.py charger_catalogue_fatec_esga --dry-run
.venv/bin/python manage.py charger_catalogue_fatec_esga
.venv/bin/python manage.py charger_catalogue_fatec_esga
.venv/bin/python manage.py check
```

Ne pas employer le profil de test sur le VPS. Sur un serveur déjà en exploitation, examiner séparément son plan de migrations avant tout migrate. Aucune migration, notamment memoires.0008, n’a été appliquée à la base locale opérationnelle pendant cette correction ; les migrations intégrales de cette preuve concernent uniquement le cluster neuf.

## Tests

Preuve PostgreSQL : **24 pages en HTTP 200** après passage de zéro à 24 programmes. Deux préparations et deux chargements ; second chargement sans création/mise à jour. Écoles créées : ESGA, FATEC. Preuves détaillées : `.tmp-correction-catalogue/postgres-empty-proof.json`.

Journal de suite complète : `.tmp-correction-catalogue/full-suite-pg-final.log`. Résultat final : échecs — voir journal.

Les anciens tests des six offres sans cycle ont été remplacés par le contrat des huit Licences et des alias. Le scénario navigateur utilise la nouvelle commande et cible l’étape active pour éviter les collisions pendant les transitions Alpine.

Une tentative sur le vieux SQLite réutilisé a rencontré un index de migration news absent ; elle n’est pas présentée comme une validation de migration vierge. La preuve de création à neuf et la suite complète utilisent PostgreSQL.

### Bilan final des suites

Suite globale : **1 457 tests exécutés, 143 échecs, 145 erreurs, 18 ignorés**. Elle n’est pas verte. Exemple confirmé : `NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join` dans les tests de délibération annuelle académiques. Aucun correctif hors catalogue n’a été tenté pour masquer ces erreurs.

Suite complète formations + admissions : **73 tests, 2 échecs, 1 erreur, 1 ignoré**. Les trois problèmes restants portent sur ESFé Sup et le référentiel historique : frais de cursus absents dans un test ESFé, ancienne attente « Tarif à confirmer », ancienne attente « DEF ou BEPC ». Ces tests n’ont pas été affaiblis ni ignorés pour rendre artificiellement le résultat vert. Les 21 tests des modules `formations.test_fatec_esga`, `formations.test_campaign_launch`, `formations.test_campaign_mobile` et `admissions.tests` passent dans cette exécution, y compris le scénario navigateur d’enregistrement.

La demande de suite globale verte reste donc non satisfaite. Une correction des moteurs et contrats historiques concernés dépasse la restauration urgente du catalogue. Les résultats sont ceux de l’état courant du dépôt ; aucun passage comparatif sur un checkout antérieur ne permet d’attribuer tous les échecs à un état préexistant.

## Captures navigateur

| Page | 390 px | 1366 px |
|---|---|---|
|Catalogue original|`.tmp-correction-catalogue/capture-0-390.png`|`.tmp-correction-catalogue/capture-0-1366.png`|
|Catalogue FATEC|`.tmp-correction-catalogue/capture-1-390.png`|`.tmp-correction-catalogue/capture-1-1366.png`|
|Catalogue ESGA|`.tmp-correction-catalogue/capture-2-390.png`|`.tmp-correction-catalogue/capture-2-1366.png`|
|Détail Licence Génie logiciel|`.tmp-correction-catalogue/capture-3-390.png`|`.tmp-correction-catalogue/capture-3-1366.png`|

8 vues HTTP 200 ; débordements : 0 ; vues contenant les mentions retirées : 0. Les quatre écoles sont présentes dans chaque contrôle du catalogue.

## Git et limites

Aucun commit, push ou déploiement. Le dépôt contient des modifications préexistantes et du travail parallèle : le diff Git total ne représente pas exclusivement cette correction. Statistiques capturées dans `.tmp-correction-catalogue/git-diff-stat.txt` ; fichiers non suivis à examiner séparément.

Fichiers de correction : formations/views.py, formations/fatec_esga.py, formations/management/commands/charger_catalogue_fatec_esga.py, formations/management/commands/preparer_catalogue_fatec_esga.py, formations/templates/formations/detail.html, formations/templates/formations/fragments/_programme_list.html, templates/cotton/public/programme_card.html (condition de contenu seulement), formations/test_campaign_launch.py, formations/test_campaign_mobile.py, config/settings_test_postgres_catalogue.py et ce rapport.