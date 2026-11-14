# Référentiel académique permanent ESFé — rapport d'exécution

Mission courante de `temp.txt`, exécutée le 8 septembre 2026.

## 1. Résultat installé

Le catalogue académique était vide en PostgreSQL avant intervention. Le seul
manifeste académique a été installé, sans réappliquer les coordonnées des annexes.

| Référentiel | Nombre installé |
|---|---:|
| Cycles | 4 |
| Programmes | 22 |
| Années de cursus (`ProgrammeYear`) | 50 |
| Frais / tranches (`Fee`) | 312 |
| Pièces partagées (`RequiredDocument`) | 5 |

Première exécution : **537 objets créés** au total, relations et contenus inclus.
Seconde exécution : **0 création**, mêmes identifiants pour tous les modèles de
`formations`. Les compteurs des modèles opérationnels `branches`, `students`,
`inscriptions`, `payments`, `academics`, `accounts` et `auth` sont inchangés.
Aucun étudiant, inscription, paiement, classe ou année académique n'a été créé.

## 2. Architecture réutilisée et schéma

Modèles réutilisés : `Cycle`, `Filiere`, `Diploma`, `Programme`, `ProgrammeYear`,
`Fee`, `ProgrammeQuickFact`, `RequiredDocument`, `ProgrammeRequiredDocument`.

Aucune nouvelle table, aucun nouveau champ, aucune migration nécessaire.
Les conditions d'accès et l'année Master mise en avant sont stockées dans les
informations structurées administrables `ProgrammeQuickFact`, et affichées sur
la fiche. Les durées restent sur `Programme.duration_years`.

Le calcul annuel utilise toujours `Programme.get_inscription_amount_for_year()`
et les montants entiers CFA de `Fee`. L'inscription conserve son propre dû
enregistré : le bootstrap ne réécrit pas les montants des inscriptions.

## 3. Cycles et programmes

Les quatre libellés officiels sont `Cycle primaire`, `Cycle secondaire`,
`Cycle Licence` et `Cycle Master`. L'ancien nom `Cycle supérieur Licence` est
reconnu et normalisé en conservant l'identité de la ligne. Des correspondances
multiples sont refusées, jamais fusionnées arbitrairement.

### Cycle primaire — accès DEF ou BEPC

| Programme | Durée | Total annuel CFA |
|---|---:|---:|
| Employé de Pharmacie | 2 ans | 200 000 |
| Agent de Santé Communautaire | 2 ans | 200 000 |
| Matrone | 2 ans | 100 000 |
| Aide Soignant | 1 an | 100 000 |

### Cycle secondaire — accès DEF ou BEPC

| Programme | Durée | Total annuel CFA |
|---|---:|---:|
| Infirmier Santé Publique | 3 ans | 310 000 |
| Infirmière Santé Maternelle et Infantile | 3 ans | 310 000 |
| Technicien de Labo-Pharmacie | 3 ans | 310 000 |
| Technicien Santé Communautaire | 3 ans | 310 000 |
| Auxiliaire Infirmier | 2 ans | 225 000 |
| Auxiliaire Puériculture | 2 ans | 225 000 |

### Cycle Licence — accès BAC ou diplôme TS ou BT + 3 ans

| Programme | Durée | Total annuel CFA |
|---|---:|---:|
| Infirmier d'État | 3 ans | 410 000 |
| Sage-Femme | 3 ans | 410 000 |
| Biologie Médicale | 3 ans | 410 000 |
| Nutrition | 2 ans | 510 000 |
| Santé Environnementale | 2 ans | 510 000 |

La plage du cycle Licence est 2–3 ans, sans imposer trois années à tous les
programmes. Un ancien rattachement d'Infirmier d'État au secondaire est reconnu
et corrigé sans remplacer le programme ni ses relations.

### Cycle Master

La structure de cursus de deux ans reprend celle du code existant ; la mission
ne fournit pas de nouvelle durée ni de conditions d'accès Master confirmées.

| Programme | Structure | Mise en avant | Tarif installé |
|---|---|---|---|
| Biologie Médicale | 2 ans | M1 | M1 : 810 000 CFA |
| Gynécologie Obstétrique | 2 ans | M1 | M1 : 810 000 CFA |
| Manager en Santé | 2 ans | M1 | M1 : 810 000 CFA |
| Pédagogie en Santé | 2 ans | M1 | M1 : 810 000 CFA |
| Épidémiologie | 2 ans | M2 | Aucun tarif confirmé chargé |
| Nutrition | 2 ans | M2 | Aucun tarif confirmé chargé |
| Santé Environnementale | 2 ans | M2 | Aucun tarif confirmé chargé |

Aucun tarif M2 n'est inventé, et le tarif M1 n'est pas extrapolé aux trois
spécialités communiquées uniquement pour M2. L'accès Master est explicitement
indiqué « À confirmer par l'établissement ». L'ajout d'autres spécialités reste
possible via les modèles et l'administration existants, sans modification de code.

## 4. Plans financiers

| Parcours | Inscription CFA | Échéancier | Total annuel CFA |
|---|---:|---|---:|
| Primaire, pharmacie / santé communautaire | 100 000 | 8 × 12 500 | 200 000 |
| Primaire, matrone / aide soignant | 20 000 | 8 × 10 000 | 100 000 |
| Secondaire, trois ans | 110 000 | 8 × 25 000 | 310 000 |
| Secondaire, deux ans | 85 000 | 8 × 17 500 | 225 000 |
| Licence, trois ans | 130 000 | 8 × 35 000 | 410 000 |
| Licence, deux ans | 210 000 | Janvier 150 000 + mars 150 000 | 510 000 |
| Master 1, quatre spécialités communiquées | 410 000 | Janvier 200 000 + mars 200 000 | 810 000 |

Chaque échéance est une ligne `Fee`, rattachée à l'année du programme. Les huit
mensualités sont numérotées ; leurs mois calendaires ne sont pas inventés.
L'échéance d'inscription est indiquée « À l'inscription ».

La fiche ne présente plus un M1 connu comme le coût total d'un Master de deux ans.
Une année sans frais est affichée « Tarif à confirmer », pas comme une année
gratuite. Le traitement administratif existant refuse une inscription dont le
montant calculé n'est pas strictement positif.

## 5. Pièces du dossier

Cinq objets partagés, reliés aux programmes sans duplication : demande timbrée,
naissance/jugement supplétif, copie légalisée du diplôme d'accès, certificat de
fréquentation et quatre photos. La mention BAC/Licence/TSS est incluse dans les
conditions de la preuve du diplôme, et non transformée en trois pièces
cumulativement obligatoires. La condition d'accès propre au programme reste
visible. Les relations existantes permettent d'ajouter des pièces spécifiques.

## 6. Bootstrap et sécurité

`bootstrap/institution.json` inclut `bootstrap/academic_reference.json` via le
service officiel `core.services.institution_bootstrap`.

Commande exécutée sur PostgreSQL, d'abord en simulation puis deux fois réellement :

```powershell
python manage.py bootstrap_institution --data-file bootstrap/academic_reference.json --dry-run
python manage.py bootstrap_institution --data-file bootstrap/academic_reference.json
```

Le service conserve les statuts et contenus d'exploitation grâce aux valeurs
d'initialisation `create_fields`, reconnaît les anciens noms via `aliases` et
refuse les tarifs contradictoires ou tranches supplémentaires. Tout refus annule
la transaction entière. Les tarifs ajoutés ultérieurement sur une année laissée
non tarifée par le manifeste sont conservés.

Le bootstrap et le reset utilisent le même verrou transactionnel PostgreSQL.
Les inclusions restent dans le dossier du manifeste ; les cycles d'inclusion
sont refusés. Un contrôle explicite des longueurs protège aussi les bases SQLite
de test contre les valeurs que PostgreSQL refuserait. La simulation PostgreSQL
a précisément permis de détecter et corriger un slug trop long avant installation.

## 7. Reset, activation et annexes

Le reset opérationnel exclut désormais l'application `formations`, qui contient
le catalogue permanent, ses tarifs de référence et ses contenus. Il préserve
identifiants, désactivations, archives et spécialités ajoutées par l'établissement.
Les classes, années académiques et inscriptions restent opérationnelles.

Le reset a été exécuté **uniquement dans les tests isolés**, jamais sur la base
réelle. Le test vérifie qu'une classe opérationnelle disparaît mais que son
programme et tous les frais de référence subsistent.

La désactivation d'un cycle ou d'une filière est respectée par le selector public
des programmes. Le bootstrap ne réactive pas les entrées désactivées/archivées.

Les nouveaux programmes sont actifs et publics, mais leurs admissions sont
fermées à la création. Aucune offre universelle par annexe n'est présumée.
`AcademicClass(programme, branch, academic_year)` reste le rattachement
opérationnel existant ; aucune classe fictive n'a été créée pour alimenter l'UI.

## 8. Validations

- `python manage.py check` : aucune erreur.
- `python manage.py makemigrations --check --dry-run` : aucun changement de schéma.
- Tests ciblés : **40 tests réussis**, exécution du groupe en 47,828 s.
- Après ajout de l'alias historique « Infirmier d’État », réexécution du test
  de normalisation/rattachement : **1 test réussi**, 13,186 s.
- Simulation PostgreSQL : 537 créations prévues, transaction annulée.
- Installation PostgreSQL puis réexécution : 537 puis 0 créations, identités stables.
- Contrôle des compteurs opérationnels avant/après : inchangés.
- Inspection des diffs ciblés et `git diff --check` : pas d'erreur d'espacement.

Commande de tests :

```powershell
python manage.py test formations.test_institutional_reference formations.tests core.test_business_data_management admissions.tests --settings=config.settings_test_local --keepdb --noinput -v 1
```

`ESFE_TEST_DB_NAME` désignait une base SQLite isolée dans le dossier temporaire
Windows. Aucune grosse suite complète n'a été lancée. Des avertissements Windows
GLib/UWP sans lien avec le résultat Django apparaissent dans l'environnement.

Couverture : quatre cycles, 22 rattachements et durées, accès, montants détaillés,
totaux annuels, huit mensualités, janvier/mars, Licence de deux ans, bootstrap
sur base propre, idempotence, reset, activation/archivage, alias historiques,
ambiguïtés, conflits tarifaires, rollback, absence de double comptage,
compléments Master ultérieurs, affichage des tarifs inconnus et longueurs SQL.

## 9. Fichiers de cette mission

- `bootstrap/academic_reference.json` — ajouté, données officielles.
- `bootstrap/institution.json` — inclusion académique ajoutée au manifeste existant.
- `bootstrap/README.md` — installation, règles et limites documentées.
- `core/services/institution_bootstrap.py` — extensions de l'upsert officiel.
- `core/services/business_data_reset.py` — catalogue permanent exclu du reset.
- `formations/models.py` — prise en compte des cycles/filières inactifs.
- `formations/views.py` — tarifs incomplets et cycles primaire/secondaire.
- `formations/templates/formations/detail.html` — accès, pièces et échéances visibles.
- `formations/test_institutional_reference.py` — nouveaux tests ciblés.
- `docs/referentiel_academique_esfe_2026-09-08.md` — présent rapport.

Les changements préexistants/concurrents ont été conservés, notamment dans le
manifeste des annexes et le reset. Aucun reset Git, restore, stash, revert ou
suppression de fichier n'a été effectué. Aucun clonage Université ni autre
chantier n'a été commencé.

## 10. Points métier à confirmer et limites existantes

- Tarifs M2, et éventuels tarifs M1 des trois spécialités annoncées uniquement en M2.
- Conditions d'accès Master ; durée Master de deux ans reprise du code existant.
- Mois calendaires exacts des huit mensualités.
- Intitulés officiels des diplômes délivrés, notamment primaire/secondaire : les
  libellés génériques nécessaires au modèle `Diploma` restent administrables.
- Offre réelle par annexe/année, avant ouverture des admissions.
- `Fee` ne possède pas de dimension annexe/année académique : les montants chargés
  sont des tarifs de référence par année de cursus. Aucun moteur parallèle ni
  fausse grille historique n'a été ajouté pour masquer cette limite existante.

Les anciens `seed_formations`, `seed_licences`, `seed_masters` et
`formations/scripts/create_master_programmes.py` contiennent encore des données
et tarifs anciens non confirmés. Ils n'ont pas été exécutés et ne sont pas la
source du référentiel permanent ; utiliser exclusivement le bootstrap officiel.
