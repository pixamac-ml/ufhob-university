# UFHOB — recette finale du funnel d’admission

Mission limitée au funnel existant, après lecture intégrale de `AGENTS.md` et `temp.txt`.

## Périmètre et décisions

Inspection du moteur Candidature/CandidatureDocument, des formulaires et vues d’admission, des sélecteurs Programme et relations School/SchoolBranch/Branch, des fragments HTMX/Alpine et des tests existants.

Le moteur partagé est conservé. Aucun modèle dupliqué, aucun champ School redondant, aucune migration créée. Les états existants `submitted` et `to_complete`, ainsi que `completion_message`, portent le résultat et l’engagement explicite du candidat.

Parcours : introduction, identité, informations personnelles, école, campus compatible, cycle réel, programme compatible, documents, récapitulatif, envoi. Une présélection conserve école/cycle/programme et demande un campus compatible sans sauter l’identité.

Les fragments utilisent les champs du formulaire, attendent HTMX et retirent les anciennes options pendant le chargement. Les programmes sont paginés côté serveur, 4 ou 6 par page selon la largeur. Le choix reste dans l’état du formulaire. Les dépendances académiques invalides sont réinitialisées sans effacer l’identité.

La case « Je transmettrai les pièces manquantes ultérieurement » est réelle, décochée par défaut et vérifiée côté serveur. Les pièces obligatoires manquantes bloquent sans engagement. Les fichiers partiels sont conservés et le dossier incomplet est enregistré `to_complete`. Le serveur vérifie aussi école, campus, implantation active, cycle, programme, pièces autorisées, extensions et taille maximale de 10 Mo.

Les retours internes conservent les fichiers en mémoire. Un rechargement conserve les informations et choix dans la session du navigateur, mais demande honnêtement de resélectionner les fichiers : les navigateurs ne permettent pas de restaurer un fichier local depuis une simple sauvegarde de formulaire. Les erreurs de validation JSON ne remplacent pas le formulaire ni les fichiers.

## Fichiers de cette mission

- `admissions/views.py` : filtres, pagination, validation, engagement et soumission JSON compatible avec le POST HTML existant.
- `admissions/templates/admissions/tunnel.html` et `done.html`.
- Fragments sous `admissions/templates/admissions/partials/` : `hero_admission.html`, `step1.html`, `step2.html`, `step3.html`, `campus_options.html`, `cycle_options.html`, `formation_options.html`, `step3_documents.html`, `step4.html`.
- `static/src/css/admission_funnel.css` : présentation institutionnelle isolée, responsive et mouvement réduit.
- `static/public/css/main.css` : sortie Tailwind régénérée.
- `admissions/tests.py` : fixtures adaptées au contexte universitaire et assertions du funnel.
- `admissions/test_funnel_final.py` : régressions ciblées.
- `admissions/check_funnel_browser.cjs` : recette Edge/CDP locale, sans création de candidature réelle.
- Le présent rapport.

Les autres changements déjà présents dans le worktree appartiennent aux travaux antérieurs/concurrents et n’ont pas été nettoyés. Aucune page publique hors admission ni aucun tableau de bord privé n’a été remanié dans cette mission.

## Validation

- Interpréteur UFHOB : `.venv/Scripts/python.exe`, Python 3.14 ; `config.settings` cible `ufhob_db`.
- `manage.py check` : réussi, aucun problème.
- `manage.py test admissions.test_funnel_final.FinalFunnelTests --settings=config.settings_test_ufhob --noinput --verbosity=1` : 22 tests, 21 réussis, 1 ignoré ; base SQLite de test isolée, stockage des fichiers en mémoire.
- Le test ignoré est l’ancien rendu du catalogue public, initialement en échec hors périmètre. Sa page n’a pas été modifiée ; cela ne constitue pas une validation du catalogue.
- Tests métier : absence de consentement, documents partiels/complets, date impossible, fichier trop gros ou étranger au programme, couple école/campus invalide, présélection Doctorat, pagination de 13 programmes et double soumission.
- Recette Edge réelle : parcours ESMED/Djélibougou/Doctorat, changement ESGA/Moribabougou, FATEC avec DUT/Master/Licence issus des données, documents, consentement, retour depuis le récapitulatif, rechargement et lien de présélection. Exécution réussie sans erreur JavaScript.
- Le dernier passage complet a également réussi (`tmp/admission-browser-vkOhLs/`). Des passages intermédiaires ont rencontré une exception générique et un délai dépassé au rechargement ; non reproduits dans le dernier passage, mais à surveiller pendant la recette humaine. La compilation CSS a été terminée avant ce dernier passage.
- Largeurs contrôlées : 1920, 1440, 1366, 1024, 768 et 390 px ; campus, programmes et récapitulatif sans débordement horizontal, boutons de navigation dans la largeur. Captures inspectées sur mobile et ordinateur, disponibles sous `tmp/admission-browser-bIUt1T/`.
- `npm run build:css` : réussi ; avertissement non bloquant Browserslist obsolète.
- `git diff --check -- admissions static/src/css/admission_funnel.css` : réussi, hors avertissements de conversion LF/CRLF.
- `manage.py makemigrations --check --dry-run` : non vierge à cause de la différence préexistante `formations.Fee.Meta.ordering` (`0012_alter_fee_options` proposée). Aucun fichier de migration créé, aucun changement hors mission pour la masquer.

## Limites et sécurité

Pas de soumission sur la base institutionnelle : les créations/validations de candidature ont été testées sur la base isolée. Pas de suite complète de l’application, ni de recette de tous les navigateurs. La recette métier humaine finale reste à effectuer. Les profils/captures temporaires de diagnostic restent dans `tmp`.

`esfe-core` touché : NON. `esfe_db` touchée : NON. Aucun bootstrap, reset ou migration appliquée. Les implantations inactives ne sont pas réactivées artificiellement.

## Verdicts

FUNNEL UFHOB — ORDRE MÉTIER CORRECT : OUI

SCHOOL → CAMPUS FILTRÉ : OUI

CYCLE DYNAMIQUE : OUI

PROGRAMMES DYNAMIQUES : OUI

PRÉSÉLECTION DEPUIS FORMATION : OUI

DOCUMENTS DIFFÉRÉS GÉRÉS : OUI

RÉCAPITULATIF POLI : OUI

DESIGN UFHOB ALIGNÉ : OUI

RESPONSIVE : OUI

PRÊT POUR RECETTE FINALE DU FUNNEL : OUI
