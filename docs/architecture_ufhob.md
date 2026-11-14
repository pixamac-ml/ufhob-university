# Architecture technique UFHOB

Cette application Django partage un moteur métier entre les écoles et campus.
Elle n'utilise ni base ni schéma PostgreSQL par école.

## Domaine et autorisations

`core.Institution` représente l'université ; `core.School` une école ;
`branches.Branch` un campus ; `core.SchoolBranch` leur association plusieurs-à-plusieurs.
`formations.Programme` appartient à une école. Sa disponibilité sur un campus
est contrôlée par `formations.availability`, également côté serveur.

`formations.ProgrammeYear` représente une année de cursus. La chaîne académique
est `AcademicYear → AcademicClass → Semester → UE → EC`. La classe référence
le programme, le campus et l'année universitaire ; l'école se déduit du programme.
Admissions (`Candidature`), inscriptions (`Inscription`), étudiants (`Student`)
et inscriptions académiques (`AcademicEnrollment`) conservent l'historique métier.

L'authentification Django existante reste unique. `accounts.Profile`,
`InstitutionalProfile`, le registre des fonctions, `AccessContext` et
`accounts.scoping` séparent le rôle du périmètre GLOBAL/SCHOOL/BRANCH/SCHOOL_BRANCH.
Les tableaux de bord partagent leurs shells et composants. Axes protège les
connexions ; les middlewares gèrent contexte, sessions et changement de mot de passe.

## Applications

| Ensemble | Applications locales |
|---|---|
| Institution et présentation | core, branches, formations, ui, superadmin |
| Admission et scolarité | admissions, inscriptions, students, secretary |
| Enseignement et résultats | academics, academic_cycle, portal |
| Identité, personnel, finances | accounts, payments, shop, coupons |
| Échanges et notifications | communications, notifier, notification_center |
| Contenus | blog, news, community, marketing, memoires |

Les modèles, services, formulaires, politiques, sélecteurs et commandes de ces
applications sont conservés. Les migrations historiques ne sont pas réécrites.
Le répertoire namespace `finance/services/` fournit aussi des services partagés,
notamment `student_clearance.py`, sans être une application Django installée.
Il doit être livré avec les sources ; l'inventaire des seules apps ne suffit pas.
Les incohérences métier encore documentées restent des sujets de recette,
pas une raison de remplacer ces moteurs pendant la préparation du déploiement.

## Exécution

- Entrée de gestion : `manage.py` ; routes principales : `config/urls.py`.
- HTTP et WebSockets : `config.asgi:application`, Channels et Daphne.
- Redis relaie les événements entre processus ; le profil serveur fournit
  également un cache partagé avec un préfixe UFHOB par environnement.
- BigBlueButton : `academics/services/online_class_service.py`, lié aux séances,
  affectations et inscriptions ; secrets et rôles sont déterminés côté serveur.
- SMTP : backends Django et `core.mail_backends.StableSMTPEmailBackend`.
- Stockages privés : communications, mémoires, ressources pédagogiques et
  enregistrements. B2/S3 est optionnel ; les répertoires privés locaux restent sauvegardés.
- PDF : WeasyPrint, ReportLab, PyMuPDF ; FFmpeg pour les usages vidéo existants.
- Frontend : templates Django, django-components, Cotton déjà présent,
  HTMX/Alpine et Tailwind 3 ; aucune nouvelle bibliothèque UI introduite ici.

`academic_cycle/tasks/__init__.py` utilise Celery s'il est installé, sinon
`.delay` s'exécute de façon synchrone. Aucun Celery/Beat ni cron opérationnel
n'a été identifié dans la configuration. Ne pas inventer un worker ou un
planificateur : inventorier et activer individuellement les commandes métier
requises après décision d'exploitation. Le serveur ASGI ne planifie pas ces tâches.

## Environnements et fichiers

- Local : `config.settings`, `.env` privé, virtualenv `.venv`, PostgreSQL `ufhob_db`.
- Préproduction : `config.settings_staging`, mêmes garde-fous que production,
  infrastructure et données séparées, `UFHOB_ENVIRONMENT=staging`.
- Production : `config.settings_production`, variables fournies par systemd,
  PostgreSQL `ufhob_db` avec rôle dédié `ufhob_app`.

Les profils serveur ne complètent pas leurs variables depuis le `.env` local.
`UFHOB_ENV_FILE` permet un fichier explicitement choisi, à garder hors du dépôt.
Les valeurs déjà exportées restent prioritaires sur python-dotenv.

`static/` contient les sources et dépendances frontend nécessaires.
`staticfiles/` est généré par collectstatic. `media/` et `private_media/` sont des
données persistantes non versionnées. Les images de présentation chargées dans
la base nécessitent un transfert de médias et, si nécessaire, de données :
publier le code seul ne les recrée pas.

Guide opératoire : [deploy/GUIDE_UFHOB.md](../deploy/GUIDE_UFHOB.md).
