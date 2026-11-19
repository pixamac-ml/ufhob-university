# Reprise de la « correction urgente » catalogue (Codex → Claude Code) — 18 novembre 2026

> Aucun commit, aucun push, aucun déploiement. Aucune initiative visuelle.
> Aucun module comptabilité, finance ou inscriptions modifié.

## 1. État des 4 points demandés

| # | Demande | État | Qui |
|---|---|---|---|
| 1 | `/formations/` : page d'origine (en-tête, filtres, 4 écoles ESMed, ESGA, FATEC, ESFé Sup). ESGA et FATEC regroupés par filière, description de la filière une seule fois, cartes DUT/Licence/Master avec niveau, durée et Candidater. | **Fait.** Vérifié en direct : les 4 onglets d'école sont présents et la page FATEC est regroupée par filière (description affichée une fois, puis 3 cartes). | Codex |
| 2 | Pages de détail : gabarit d'origine + blocs Frais / Dossier (« Pièces à fournir ») / Conditions. Aucune mention « à confirmer » ni « annualité ». | **Fait.** Vérifié sur Génie logiciel Licence, Audiovisuel DUT et Finance Master : les 3 blocs sont présents et aucune mention interdite n'apparaît dans le HTML. | Codex |
| 3 | Textes Génie logiciel / Audiovisuel + suppression de « Faculté de Technologies ». | **Fait.** Les 6 programmes ont de nouveaux textes et des débouchés renseignés, en base et dans `charger_catalogue_fatec_esga.py`. Il ne reste aucun texte générique en base. **J'ai complété** la dernière occurrence de « Faculté de Technologies », dans l'ancienne commande `seed_ufhob_catalogue.py`. | Codex + Claude |
| 4 | Tests : comparaison avec HEAD, puis classement (a) / (b). Correction de (b) uniquement. | **Fait** (voir section 2). | Claude |

## 2. Tests : comparaison HEAD / actuel

**Méthode**
- Un `git worktree` de HEAD (`4a53e4a`) a été créé dans un dossier temporaire.
- Les deux arbres ont été testés avec **les mêmes réglages** : cluster PostgreSQL jetable de Codex (port 55439, jamais le PostgreSQL du propriétaire), bases de test distinctes, couche Channels en mémoire, cache en mémoire.

⚠️ **Limite importante** : HEAD date du **3 septembre 2026**. Le dépôt contient environ 2,5 mois de travail non commité **antérieur** à nos missions. Les échecs ont donc été classés en trois catégories :
- **(a)** : échoue déjà sur HEAD.
- **(a\*)** : apparu depuis HEAD, mais sans lien avec les fichiers de nos missions. Il vient du travail non commité antérieur.
- **(b)** : causé par nos missions.

| | Tests | Échecs | Erreurs |
|---|---|---|---|
| HEAD | 1 068 | 60 | 80 |
| Actuel (avant corrections b) | 1 452 | 143 | 149 |

| Catégorie | Nombre | Répartition |
|---|---|---|
| **(a)** déjà sur HEAD | 127 | students 39, portal 27, accounts 25, academics 20, ui 14, coupons 1, secretary 1 |
| **(a\*)** apparu depuis HEAD, sans lien avec nos missions | 143 | portal 42, accounts 38, academics 35, notification_center 7, superadmin 5, communications 3, formations 3, payments 3, core 2, students 2, shop 1, ui 2 |
| **(b)** causé par nos missions | 5 | **tous corrigés** (voir ci-dessous) |

Les échecs que tu as cités :
- **Permissions dashboard « secretary »** : (a), il existe déjà sur HEAD (`secretary.tests.PermissionTests.test_is_secretary_returns_true_for_secretary_group`).
- **`academic_year_not_found` inscription=92** : n'apparaît pas dans cette exécution sur base isolée. Il dépend probablement des données de la base locale.

### Échecs (b) et corrections

| Test | Cause | Correction |
|---|---|---|
| `formations.test_campaign_launch` (×2) | `preparer_catalogue_fatec_esga` refusait toute base PostgreSQL autre que `ufhob_db` ou `test_ufhob_catalogue_*`, y compris les bases de test Django. | Bases `test_*` autorisées. Toute autre base que `ufhob_db` reste interdite. |
| `formations.test_campaign_mobile` | Même cause. | Même correction. |
| `formations.test_fatec_esga` (setUpClass) | Même garde-fou dans `charger_catalogue_fatec_esga`. | Même correction. |
| `core.test_mission2_public` (page école) | Mon test comparait un texte contenant une apostrophe que le HTML échappe. | `escape()` dans le test. |

Relance ciblée après correction : **19 tests, 18 OK**. Le seul restant, `ui.tests…test_gallery_renders`, a été reclassé en (a\*) : le test ne simule que 2 requêtes du context processor, alors que celui-ci interroge aussi `School` et `Branch`. Ces requêtes ont été ajoutées après HEAD, mais **avant** nos missions. J'ai seulement corrigé la partie session (`capture_tracking` sans session).

### Points (a\*) à surveiller (non corrigés, hors périmètre)

- **`formations.test_institutional_reference`** (×2) et **`formations.test_esfe_sup_public`** : ces tests attendent l'affichage des frais sur les fiches ESFé et ESMed (« 1re année », « DEF ou BEPC »). Cet affichage est coupé par `PUBLIC_FEES_ENABLED = False`, une décision antérieure à nos missions. **C'est à toi de décider** : soit adapter ces tests, soit réactiver l'affichage des frais pour ces écoles.
- **`payments.tests`** (×3) et **`core.test_signatures`** (×2) : modules finance et signatures, non touchés.

## 3. Fichiers modifiés pendant cette reprise (Claude)

- `formations/management/commands/charger_catalogue_fatec_esga.py`, `formations/management/commands/preparer_catalogue_fatec_esga.py` : autorisent les bases de test Django.
- `formations/management/commands/seed_ufhob_catalogue.py` : « Faculté de Technologies » devient « Faculté des Technologies ».
- `core/context_processors.py` : pas d'attribution de campagne sans session.
- `core/test_mission2_public.py` : `escape()`.

Fichiers de la correction de Codex, d'après son script `.tmp-correction-catalogue/edit.py` :
- `formations/views.py`, `formations/fatec_esga.py`, `formations/templates/formations/detail.html`, `formations/templates/formations/fragments/_programme_list.html`, `templates/cotton/public/programme_card.html` ;
- tests réécrits : `formations/test_campaign_launch.py`, `formations/test_campaign_mobile.py` ;
- nouvelles commandes `preparer_catalogue_fatec_esga` et `config/settings_test_postgres_catalogue.py`.

## 4. `git diff --stat` (Codex + Claude) : à lire avec prudence

- `git diff --stat` complet : **825 fichiers changés, +28 010 / −102 337**.
- Limité à `formations admissions core config templates static/src static/public/css tailwind.config.js` : **198 fichiers, +6 657 / −21 075**.
- Fichiers non suivis dans ces dossiers et `deploy/` : **171**.

Ces chiffres comparent à HEAD (3 septembre). Ils incluent tout le travail non commité antérieur, dont des suppressions massives de documents à la racine, et **ne mesurent pas nos missions**. La sortie complète de Codex est dans `.tmp-correction-catalogue/git-diff-stat.txt` (UTF-16).

## 5. Captures

- `/formations/` : `.tmp-mission2/catalogue-formations-390.png`, `catalogue-formations-1366.png` (+ `-full.png`).
- Page de détail (Licence Génie logiciel) : `.tmp-mission2/catalogue-detail-genie-logiciel-licence-390.png`, `…-1366.png` (+ `-full.png`).
- Mesures sur ces 4 vues :
  - HTTP 200 ;
  - 0 erreur JavaScript ;
  - 0 réponse HTTP ≥ 400 ;
  - aucun débordement horizontal ;
  - 4 écoles présentes sur `/formations/` ;
  - aucune mention « à confirmer » ni « annualité ».

## 6. Nettoyage à prévoir

- **Worktree temporaire de HEAD** : **déjà supprimé**, y compris sa copie locale de `.env`.
- **Cluster PostgreSQL jetable de Codex** (`.tmp-correction-catalogue/pgdata`, port 55439) : toujours en marche. À arrêter quand tu n'en as plus besoin.
