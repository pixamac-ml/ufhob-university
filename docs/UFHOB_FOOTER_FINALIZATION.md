# UFHOB — FOOTER FINALIZATION

Audit ciblé du 2 octobre 2026. **READY_FOR_UFHOB_FOOTER_PRODUCTION: NO**.

La mise en forme et la centralisation sont réalisées. Il manque la confirmation du téléphone public actuel et du domaine canonique de production. Les questions ont été transmises ; aucune réponse n'a été présumée.

## EMAIL

- Public : `universite@univ-fhb-mali.org`.
- Source unique : `Institution.email`, administrable sans modifier les templates.
- Mise à jour exécutée sur la ligne Institution 1 de **ufhob_db**, avec contrôle explicite du nom de base et de l'ancienne valeur. Ancienne valeur : `contact@univ-fhb-mali.org`.
- Footer, Contact, Mentions légales, Confidentialité, Conditions d'utilisation et données structurées consomment cette source. Aucun email officiel ajouté en dur dans les templates.
- Les identifiants SMTP, expéditeurs techniques et workflows d'envoi n'ont pas été modifiés.
- Cette modification de donnée locale doit être reportée dans l'Institution de la base effectivement déployée si elle diffère de cette base. Pas de migration de données ni de bootstrap exécuté.

## PHONE — inventaire et qualification

Les dates documentaires ci-dessous sont des dates de fichier/métadonnées, sauf mention contraire. Elles ne prouvent pas qu'un numéro reste actif en 2026.

| NUMBER | SOURCE | DATE | CURRENT_USAGE | STATUS |
| --- | --- | --- | --- | --- |
| +223 95 33 75 01 | Institution.phone ; footer/Contact avant intervention | Institution mise à jour le 11/09/2026 | Configuré ; désormais masqué publiquement dans les surfaces corrigées | TO_CONFIRM |
| +223 76 37 88 66 | BE UPFHOB-MALI.docx ; RAE L_GRHREFERENCE_28_05_2025.docx ; Livret de l'étudiant 2025.pdf p.3 ; lettre de stage PDF p.1 | 15/07/2025 ; 28/05/2025 ; 16/01/2025 ; 21/11/2024 | Principal documentaire récurrent, non publié faute de validation actuelle | PROBABLE |
| +223 66 37 88 66 | BE UPFHOB-MALI.docx ; RAE ; Livret 2025 p.3 | 2025 | Secondaire documentaire, non publié | TO_CONFIRM |
| +223 72 73 94 94 | Attestation de Préinscription UFHOB-MALI.docx ; personne chargée du dossier dans BE UPFHOB-MALI.docx | 12/11/2024 ; 15/07/2025 | Ancien contact/document et suivi nominatif ; statut public actuel inconnu | TO_CONFIRM |
| +223 76 41 08 93 | LETTRE DE MISE EN STAGE UFHOB-MALI - Copie.docx | 14/07/2025 | Document Word différent du PDF daté 2024, non publié | CONFLICT |
| +223 78 22 13 24 | Branch.phone des campus Djélibougou et Moribabougou | Constat base au 02/10/2026 | Téléphone campus, pas principal universitaire ; retiré des cartes Contact en attente de validation | TO_CONFIRM |
| 76 88 24 11 | Ancien footer dans templates/base.html et composant hérité | Non daté | Donnée ESFÉ héritée, retirée du footer public actif | OLD |
| +223 97 67 20 87 | Ancien footer et raccourcis WhatsApp de templates/base.html | Non daté | Coordonnée ESFÉ héritée, retirée des liens actifs de cette base | OLD |
| +223 70 00 00 00 | Valeur de secours du composant footer hérité | Non daté | Placeholder ; composant désormais non appelé par le footer de base | OLD |

- Principal publié : aucun tant qu'il n'est pas confirmé.
- Secondaire publié : aucun tant qu'il n'est pas confirmé.
- Les valeurs institutionnelles/campus stockées ont été conservées. Aucun remplacement automatique par un numéro documentaire.
- `PUBLIC_CONTACT_PHONES_CONFIRMED=false` par défaut empêche de publier les numéros institutionnels dans le footer, Contact, les encarts juridiques et les données structurées. Ce réglage est un verrou de publication, pas une deuxième source de numéros.
- Après validation : renseigner Institution.phone avec le ou les numéros confirmés (séparateur `/` pour deux numéros), puis activer `PUBLIC_CONTACT_PHONES_CONFIRMED=true` dans l'environnement déployé. Les liens sont normalisés en `tel:+223…`.
- Les fiches campus indépendantes n'ont pas été remaniées ; elles peuvent encore présenter leur propre contact campus. Ne pas confondre cette donnée avec un contact institutionnel confirmé.

## LOCATION

- Affichée : **Moribabougou, Bamako, Mali**.
- Source : Institution.address/city/country, concordante avec les documents institutionnels.
- Libellé : « Localisation ». Aucune qualification comme siège juridique ni comme campus principal inventée.
- Même valeur dans footer, Contact et encarts juridiques.
- « Campus » conservé dans le footer moderne ; aucun « Annexe » ajouté.

## DOMAIN

- Domaine documentaire : `www.univ-fhb-mali.org`, notamment Livret 2025 p.3 et BE 2025.
- Configuration constatée : BASE_URL pointe vers un hôte HTTP de développement ; ALLOWED_HOSTS ne confirme pas un déploiement sur le domaine UFHOB et conserve une entrée héritée ESFÉ.
- Domaine affiché dans le footer : aucun en attendant confirmation/configuration réelle.
- URL canonique de production : **à confirmer** entre `https://www.univ-fhb-mali.org` et `https://univ-fhb-mali.org`.
- Le footer utilisera BASE_URL lorsqu'il correspond à l'une de ces origines HTTPS. Aucun sous-domaine créé, aucun changement DNS ou déploiement effectué.
- Consultation de https://www.univ-fhb-mali.org : accès 403 via l'outil de consultation ; cela ne démontre ni un lien cassé ni la configuration du futur déploiement.

## SOCIAL NETWORKS

SiteConfiguration est absent de la base examinée : aucun compte social public n'est actuellement configuré.

| Réseau | URL actuelle configurée | Éléments retrouvés | Action/statut |
| --- | --- | --- | --- |
| Facebook | Aucune | https://www.facebook.com/ufhobml/ dans Livret 2025 p.3 | TO_CONFIRM ; consultation bloquée par Facebook, pas de preuve de compte cassé ; non ajouté |
| Instagram | Aucune | esfe_officiel dans ancien footer de base | Ancien compte ESFÉ retiré du footer actif ; aucun compte UFHOB inventé |
| TikTok | Aucune | esfe_officiel dans ancien footer de base | Même action |
| YouTube | Aucune | @esfe_tv dans ancien footer de base | Même action |
| LinkedIn | Aucune | Placeholder du composant hérité | Non publié |
| WhatsApp | Aucune | Numéro ESFÉ historique dans base.html | Retiré ; raccourcis conditionnés à la configuration institutionnelle |

Les cartes « Coordonnée à renseigner », liens vides et placeholders ne sont plus publiés. Les liens configurés doivent être validés institutionnellement avant leur saisie. Le filtre technique de liens ne prétend pas vérifier la propriété d'un compte.

## FOOTER / CONTACT PAGE

- Design Cotton existant conservé, logo officiel local conservé (57 × 56 pixels rendus, ratio respecté).
- Identité textuelle issue d'Institution.name.
- Liens université, écoles, formations, admissions, campus et Contact conservés.
- Mentions légales, Confidentialité et Conditions d'utilisation publiées conservées ; bouton Cookies ouvre le gestionnaire existant.
- Le template de base réutilise maintenant ce footer existant : suppression du second footer actif avec coordonnées ESFÉ indépendantes.
- Email responsive, cellules sans débordement, identité flexible et focus visible. Les contacts restent lisibles sans dépendance aux polices distantes.
- Contact : même email, même localisation et même règle de publication des téléphones. Formulaire et workflow inchangés.

## LEGACY DATA

| Adresse | Classement | Action |
| --- | --- | --- |
| contact@univ-fhb-mali.org | Ancien PUBLIC_CONTACT | Remplacée dans Institution |
| ufhobmali@gmail.com | LEGACY documentaire (attestation 2024, BE/RAE/livret 2025) | Documents conservés, non publiée dans les surfaces corrigées |
| ufhbmali@gmail.com | Non retrouvée dans les sources ciblées | Aucun remplacement spéculatif |
| inscription@univ-fhb-mali.org | Adresse spécialisée dans fiche d'inscription 2024-2025 | Document conservé ; pas adoptée comme contact principal |
| esfeho@… | Document Word du livret, mélange de données héritées | Non adoptée ; document conservé |
| esfereseaux@gmail.com | Ancien footer ESFÉ | Supprimée de la configuration du footer actif dans base.html |
| contact@esfe.edu.ml | Ancien script core/seed_legal.py | TECHNICAL/LEGACY ; script non exécuté, non modifié |

Audit limité au footer, aux pages et modèles institutionnels, à la configuration et aux documents UFHOB pertinents de SITE/UPFHOB. Aucun audit global ni remplacement massif. Les anciens composants/scripts non appelés restent dans le dépôt ; leur présence n'est pas assimilée à un affichage public actif. Un document .docx non lisible comme archive Word a été écarté ; aucune coordonnée n'en a été déduite.

## FILES MODIFIED

- core/public_contact.py : présentation commune des coordonnées et filtrage des liens sociaux.
- core/context_processors.py : exposition globale, cohérence des données structurées et WhatsApp.
- config/settings.py, .env.example : verrou de publication des téléphones. **.env réel non modifié.**
- templates/cotton/public/footer.html : contacts centralisés, suppression placeholders, Cookies, identité.
- templates/base.html : réutilisation du footer Cotton et suppression des destinations WhatsApp héritées actives.
- core/templates/core/contact.html : coordonnées communes, retrait des téléphones campus non vérifiés de cette page.
- templates/legal_notice.html, templates/privacy_policy.html, templates/terms_of_service.html : encarts centralisés et liens mailto/tel.
- static/src/css/input.css, static/public/css/main.css : responsive/focus ciblés, CSS public recompilé.
- core/test_public_contact.py : tests ciblés.
- docs/UFHOB_FOOTER_FINALIZATION.md : présent rapport.
- tmp/footer-qa/ : script de recette, résultats JSON, captures desktop/tablette/mobile (artefacts locaux).

Les modifications préexistantes nombreuses du dépôt ont été conservées. Le diff Git global contient donc aussi du travail antérieur à cette mission.

## TESTS / CHECK / MIGRATIONS

- Environnement vérifié : dossier ufhob-core, son .venv, Python 3.14.0, Django 6.0.5, config.settings, PostgreSQL ufhob_db.
- `python manage.py check` : OK, aucune anomalie.
- `python manage.py makemigrations --check --dry-run` : OK, No changes detected. **Aucune migration créée/exécutée.**
- `python manage.py test core.test_public_contact --settings=config.settings_test_ufhob` : 3 tests OK, SimpleTestCase sans création de base ; masquage numéros non confirmés, normalisation de deux liens tel, mailto rendu, filtrage placeholders.
- GET `/`, `/contact/`, `/mentions-legales/`, `/confidentialite/`, `/conditions-utilisation/` : HTTP 200 ; email officiel et footer présents ; aucun des anciens emails recherchés ; aucun téléphone non confirmé rendu.
- Rendu isolé du footer par défaut de base.html : email officiel, absence des anciens contacts et comptes ESFÉ dans le footer ; anciens liens WhatsApp flottants retirés.
- Edge headless/Playwright : accueil + Contact aux largeurs 320, 390, 768 et 1440 ; absence de débordement horizontal ; aucun élément du footer hors écran ; logo chargé et non déformé ; ouverture Cookies réussie.
- Les ressources HTTPS externes ont été bloquées lors de la recette visuelle pour éviter les attentes réseau. CSS, images, JS du site servis localement ; polices de repli utilisées. Cela ne certifie pas les performances réseau de production.
- `npm run build:css` : OK. Avertissement Browserslist préexistant (données anciennes), non bloquant.
- Playwright et pypdf installés uniquement dans le .venv UFHOB pour cette recette ; aucune installation globale ni changement du manifeste applicatif.
- Aucun envoi de formulaire/email, appel téléphonique ou test d'envoi transactionnel ; pas de suite métier globale, hors périmètre.
- Avertissements Windows GLib/UWP locaux sans impact sur les résultats.
- `git diff --check` signale des espaces/fins de ligne CRLF dans des fichiers déjà largement modifiés avant cette mission (notamment settings et CSS) ; aucun nettoyage global effectué pour préserver les changements concurrents.

## RISQUES / DÉPLOIEMENT

1. Confirmer le téléphone principal et un éventuel secondaire avant publication ; ne pas simplement activer le verrou sans validation.
2. Confirmer l'origine HTTPS et configurer BASE_URL/ALLOWED_HOSTS/CSRF_TRUSTED_ORIGINS lors du déploiement. Aucune configuration locale sensible écrasée.
3. Aucun réseau UFHOB actuel validé dans la configuration ; laisser les réseaux absents jusqu'à confirmation.
4. Les pages juridiques répondent mais leur contenu CMS est minimal : notamment « Informations institutionnelles à compléter avant publication définitive ». La finalisation juridique ne fait pas partie de cette correction des coordonnées.
5. Les anciens éléments hors footer, les fiches campus et documents historiques ne sont pas certifiés par cet audit ciblé. Le rendu intégral du template hérité révèle aussi un compte social ESFÉ hors footer ; le footer et les pages modernes testées n'en contiennent plus. Pas de refonte de navigation engagée.

**esfe-core : non touché. esfe_db : non touchée.** Aucun moteur métier, compte, architecture École/Campus, document académique, bootstrap ou migration historique modifié.

**READY_FOR_UFHOB_FOOTER_PRODUCTION: NO** — confirmations téléphone et domaine encore nécessaires.
