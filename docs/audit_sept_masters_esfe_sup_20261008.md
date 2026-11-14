# Audit des sept Masters ESFé Sup — 8 octobre 2026

**MASTER PROGRAMMES EXPECTED: 7**

## État vérifié et intervention

Python 3.14.0, environnement virtuel UFHOB, config.settings ; cible et connexion PostgreSQL vérifiées par current_database() = ufhob_db. Avant intervention : 27 programmes, 74 ProgrammeYear, aucune classe, semestre, UE ou EC. Aucun des sept Masters attendus ne figurait dans les programmes, même inactifs ou archivés. Aucune Licence de santé homonyme ne figure dans cette base actuelle ; les rapports historiques ne constituent pas son état actuel.

Création ciblée : 7 Programme et 14 ProgrammeYear. Réutilisation de School #4 ESFÉ / ESFé Sup, Cycle #3 Master, Diploma #3 Master (niveau supérieur), Filiere #1 Sciences de la Santé. Titres stockés « Master — [formation] », durée 2 ans. Aucun diplôme spécialisé supplémentaire inventé. Les programmes sont internes (is_public=False, admissions_open=False) pendant la vérification.

ProgrammeYear = année de cursus ; ce n’est ni une année universitaire ni une classe. Les campus et années universitaires cibles ne sont pas précisés : aucune classe opérationnelle créée. Aucune classe supprimée, aucune UE/EC, note ou donnée validée modifiée. Les 27 programmes préexistants sont inchangés.

| Formation | Programme ID | Cycle / diplôme réel | 1re année ID | 2e année ID | Classes trouvées |
|---|---:|---|---:|---:|---|
| Biologie Médicale | 51 | Master #3 / Master #3 | 125 | 126 | Aucune, tous campus et années |
| Gynécologie Obstétrique | 52 | Master #3 / Master #3 | 127 | 128 | Aucune, tous campus et années |
| Manager en Santé | 53 | Master #3 / Master #3 | 129 | 130 | Aucune, tous campus et années |
| Pédagogie en Santé | 54 | Master #3 / Master #3 | 131 | 132 | Aucune, tous campus et années |
| Épidémiologie | 55 | Master #3 / Master #3 | 133 | 134 | Aucune, tous campus et années |
| Nutrition | 56 | Master #3 / Master #3 | 135 | 136 | Aucune, tous campus et années |
| Santé Environnementale | 57 | Master #3 / Master #3 | 137 | 138 | Aucune, tous campus et années |

## Sources et précautions

Inventaire récursif du dépôt incluant les fichiers ignorés par Git ; lecture textuelle des PDF et XML des DOCX sous SITE, plus Master maquette. Les environnements, dépendances et caches sont exclus. Les reçus et dossiers individuels ne servent pas de maquettes.

Aucun dossier Relever/, Relevé/Relevés ou document explicitement identifié UAS trouvé dans l’arborescence actuelle. Les dossiers SITE/EPSFé et SITE/AMAQ 2024 contiennent des arborescences mais aucun fichier actuel. Les quatre relevés disponibles sont ceux de Master maquette/odonto. Le document OOAS/CEDEAO de février 2017 et le dossier Biologie novembre 2019 sont présents.

La nouvelle fiche est connue par les intitulés et niveaux communiqués par l’utilisateur. Son original n’a pas été fourni ni retrouvé : aucune prétention à une lecture visuelle de cette fiche. Elle confirme le catalogue selon la consigne, pas les matières. Les licences et les doctorats ne sont jamais extrapolés vers les Masters.

Les relevés odonto S1/S2/S3 ne sont pas attribués aux sept Masters : des matières communes ne prouvent pas leur applicabilité. Le S4 est une source candidate Nutrition car l’en-tête nomme Nutrition, mais son nom odonto rend sa provenance ambiguë. Aucun résultat ni identité d’étudiant importé.

FILERES RUSTA-UFHOB-MALI.docx et Filières RUSTA.xlsx sont des références de catalogue, pas des maquettes pédagogiques complètes.

### Annexes Word avec suppressions suivies

ANNEXES LIG, D-FC, DUTIG, L-FC, L-GEA, L-GRH et L-MC, sous SITE/UPFHOB/AMAQ 2024/UFHOB-MALI/ANNEXES, contiennent des références historiques au Master en Épidémiologie et à d’autres formations de santé. Une extraction XML brute lit aussi les textes supprimés. Dans ANNEXES LIG, les tableaux 18–22 portent des lignes w:del et du texte w:delText, avec notamment MGO et FTE2301/MFE2401. Ces versions sont exclues des maquettes validées. Il faut la version finale acceptée ou la maquette approuvée ; le nom d’une annexe technique ou un mot-clé ne suffit pas.

## Résultats obligatoires par année

Les UE/EC ci-dessous sont des éléments trouvés dans les documents, pas installés en base. PARTIAL : source pertinente mais champs ou validation locale manquants. AMBIGUOUS : correspondance, attribution ou valeurs à départager. COMPLETE exige une maquette exacte et vérifiée ; NO_MATRIX_SOURCE signifie aucune source pertinente. Aucune ligne COMPLETE : aucun inventaire trouvé ne fournit toutes les preuves nécessaires à l’installation.

Le tronc commun OOAS M1 est une référence documentée pour la mention Sciences infirmières et obstétricales, pas une attribution automatique à tous les Masters. La Biologie a son propre M1. Manager/Pédagogie demandent confirmation des correspondances d’intitulés ; Santé Environnementale est une option du référentiel dont la spécialité est Santé et sécurité au travail, pas une équivalence prouvée.

| FORMATION | CYCLE | NIVEAU | CLASSES FOUND | SOURCE DOCUMENTS FOUND | SEMESTERS FOUND | UE FOUND | EC FOUND | CREDITS FOUND | COEFFICIENTS FOUND | STATUS |
|---|---|---|---|---|---|---|---|---|---|---|
| Biologie Médicale | Master / Master | 1re année / M1 | 0 | BIO 2019 p. 13,14,15,16 | source S1/S2 ; base 0 | 9 source ; base 0 | 30 source ; base 0 | 30 par semestre ; crédits UE et disciplines explicites (détail ci-dessous). | ABSENTS du dossier. Aucune valeur inventée. | PARTIAL |
| Biologie Médicale | Master / Master | 2e année / M2 | 0 | BIO 2019 p. 17,18 | source S3/S4 ; base 0 | 8 source ; base 0 | 22 source ; base 0 | 30 par semestre ; crédits UE et disciplines explicites (détail ci-dessous). | ABSENTS du dossier. Aucune valeur inventée. | PARTIAL |
| Gynécologie Obstétrique | Master / Master | 1re année / M1 | 0 | OOAS 2017 p. 11,12 | source S1/S2 ; base 0 | 8 source ; base 0 | 21 source ; base 0 | S1 : UE 15/4/6/5, total 30. S2 : UE 7/7/11/3, total 28 enseignements + 2 stage. Répartition EC absente. | S1 : UE 5/4/4/4 ; S2 : UE 3/3/4/2. Coefficients EC absents. | PARTIAL |
| Gynécologie Obstétrique | Master / Master | 2e année / M2 | 0 | OOAS 2017 p. 21,22,23 | source S3/S4 ; base 0 | 6 source ; base 0 | 18 source ; base 0 | S3 : UE 7/4/3/3/8, total 25 + 5 stage ; S4 : 24 + 6 stage. Répartition EC absente. | S3 : PSN 4, SRM 3, SRJ 3, DSR 4 ; SRN non lisible dans extraction, ne pas déduire du total 15. S4 : UE 5. Coefficients EC absents. | PARTIAL |
| Manager en Santé | Master / Master | 1re année / M1 | 0 | OOAS 2017 p. 11,12 | source S1/S2 ; base 0 | 8 source ; base 0 | 21 source ; base 0 | S1 : UE 15/4/6/5, total 30. S2 : UE 7/7/11/3, total 28 enseignements + 2 stage. Répartition EC absente. | S1 : UE 5/4/4/4 ; S2 : UE 3/3/4/2. Coefficients EC absents. | AMBIGUOUS |
| Manager en Santé | Master / Master | 2e année / M2 | 0 | OOAS 2017 p. 63,64,65 | source S3/S4 ; base 0 | 6 source ; base 0 | 21 source ; base 0 | S3 : UE 2/9/3/9/5, total 28 ; note stage 90 h, 45 x 2, mais texte 6 crédits : incohérence. S4 : 24 + 6 stage. Répartition EC absente. | S3 : seconde série 1/4/1/4/3, total 13 ; en-tête ECUE/UE incohérent, statut coefficient à confirmer. S4 : UE 5. Coefficients EC absents. | AMBIGUOUS |
| Pédagogie en Santé | Master / Master | 1re année / M1 | 0 | OOAS 2017 p. 11,12 | source S1/S2 ; base 0 | 8 source ; base 0 | 21 source ; base 0 | S1 : UE 15/4/6/5, total 30. S2 : UE 7/7/11/3, total 28 enseignements + 2 stage. Répartition EC absente. | S1 : UE 5/4/4/4 ; S2 : UE 3/3/4/2. Coefficients EC absents. | AMBIGUOUS |
| Pédagogie en Santé | Master / Master | 2e année / M2 | 0 | OOAS 2017 p. 80,81 | source S3/S4 ; base 0 | 6 source ; base 0 | 15 source ; base 0 | S3 : UE 3/6/6/6/4, total 25 ; stage 225 h, note 4 crédits mais calcul 45 x 5. S4 : 30, note 24 + 6 stage. Répartition EC absente. | S3 : UE 2/4/2/4/3. S4 : UE 5 mais total 30, contradiction. Coefficients EC absents. | AMBIGUOUS |
| Épidémiologie | Master / Master | 1re année / M1 | 0 | OOAS 2017 p. 11,12 | source S1/S2 ; base 0 | 8 source ; base 0 | 21 source ; base 0 | S1 : UE 15/4/6/5, total 30. S2 : UE 7/7/11/3, total 28 enseignements + 2 stage. Répartition EC absente. | S1 : UE 5/4/4/4 ; S2 : UE 3/3/4/2. Coefficients EC absents. | PARTIAL |
| Épidémiologie | Master / Master | 2e année / M2 | 0 | OOAS 2017 p. 46,47 | source S3/S4 ; base 0 | 7 source ; base 0 | 19 source ; base 0 | S3 : UE 3/3/6/5/6/7, total 30 ; S4 : total 30, note 24 + 6 stage, cellule crédit UE peu claire. Répartition EC absente. | S3 : UE 2/2/4/4/4/4. S4 : 30 affiché et total 30, contrôler visuellement. Coefficients EC absents. | PARTIAL |
| Nutrition | Master / Master | 1re année / M1 | 0 | OOAS 2017 p. 11,12 | source S1/S2 ; base 0 | 8 source ; base 0 | 21 source ; base 0 | S1 : UE 15/4/6/5, total 30. S2 : UE 7/7/11/3, total 28 enseignements + 2 stage. Répartition EC absente. | S1 : UE 5/4/4/4 ; S2 : UE 3/3/4/2. Coefficients EC absents. | PARTIAL |
| Nutrition | Master / Master | 2e année / M2 | 0 | OOAS 2017 p. 16,17 ; Excel S4 candidat | source S3/S4 ; base 0 | 6 source ; base 0 | 15 source ; base 0 | S3 : UE 4/7/8/5/6 (CSS535 comprend stage), total 26 + 4 stage. S4 : UE 30, total 24 + 6 stage. Excel S4 candidat : EC 4/6/20. | S3 : UE 2/3/3/2/2. S4 PDF : UE 5 ; Excel candidat : UE 30, EC 4/6/20. Versions différentes. | AMBIGUOUS |
| Santé Environnementale | Master / Master | 1re année / M1 | 0 | OOAS 2017 p. 11,12 | source S1/S2 ; base 0 | 8 source ; base 0 | 21 source ; base 0 | S1 : UE 15/4/6/5, total 30. S2 : UE 7/7/11/3, total 28 enseignements + 2 stage. Répartition EC absente. | S1 : UE 5/4/4/4 ; S2 : UE 3/3/4/2. Coefficients EC absents. | AMBIGUOUS |
| Santé Environnementale | Master / Master | 2e année / M2 | 0 | OOAS 2017 p. 56,57,58,59 | source S3/S4 ; base 0 | 7 source ; base 0 | 30 source ; base 0 | CANDIDATE SST uniquement : S3 UE 2/7/4/2/5/7, total 27 + 3 stage ; S4 : 24 + 6 stage. Équivalence au Master exact non prouvée. | CANDIDATE SST : S3 seconde série 1/4/2/1/3/4 ; S4 UE 5 mais total 30. Coefficients EC absents. | AMBIGUOUS |

Les pages sont physiques PDF. Le JSON associé donne les 14 lignes, identifiants, sources et codes. Les codes source erronés ou atypiques restent signalés, sans correction silencieuse.

## Inventaire des UE/EC documentaires

### M1

UE : S1 : MSS411, SEP412, GDS413, BEB414 ; S2 : ISP421, SPP422, CIA423, MdR424

ECUE : BEB4141, BEB4142, CIA4231, CIA4232, CIA4233, GDS4131, GDS4132, GDS4133, ISP4211, ISP4212, ISP4213, MSS4111, MSS4112, MSS4113, MdR4241, MdR4242, SEP4121, SEP4122, SPP4221, SPP4222, SPP4223

S1 : UE 15/4/6/5, total 30. S2 : UE 7/7/11/3, total 28 enseignements + 2 stage. Répartition EC absente.

S1 : UE 5/4/4/4 ; S2 : UE 3/3/4/2. Coefficients EC absents.

### Gynecologie M2

UE : S3 : PSN531, SRM532, SRN533, SRJ534, DSR535 ; S4 : MFE541

ECUE : DSR5351, DSR5352, DSR5353, MFE5411, MFE5412, MFE5413, PSN5311, PSN5312, PSN5313, SRJ5341, SRJ5343, SRJ5344, SRM5321, SRM5322, SRM5332, SRN5331, SRN5332, SRN5333

S3 : UE 7/4/3/3/8, total 25 + 5 stage ; S4 : 24 + 6 stage. Répartition EC absente.

S3 : PSN 4, SRM 3, SRJ 3, DSR 4 ; SRN non lisible dans extraction, ne pas déduire du total 15. S4 : UE 5. Coefficients EC absents.

### Manager M2

UE : S3 : FTM531, FDM532, GRH533, GFM534, EMP535 ; S4 : MFE541

ECUE : EMP5351, EMP5352, EMP5353, FDM5321, FDM5322, FDM5323, FDM5324, FDM5325, FTM5311, FTM5312, GFM5341, GFM5342, GFM5343, GFM5344, GFM5345, GFM5346, GRH5331, GRH5332, MFE5411, MFE5412, MFE5413

S3 : UE 2/9/3/9/5, total 28 ; note stage 90 h, 45 x 2, mais texte 6 crédits : incohérence. S4 : 24 + 6 stage. Répartition EC absente.

S3 : seconde série 1/4/1/4/3, total 13 ; en-tête ECUE/UE incohérent, statut coefficient à confirmer. S4 : UE 5. Coefficients EC absents.

### Pedagogie M2

UE : S3 : FSP531, EPF532, PEA533, MEA534, EDS535 ; S4 : MFE541

ECUE : EDS5351, EDS5352, EPF5321, EPF5322, FSP5311, FSP5312, MEA5341, MEA5342, MEA5343, MFE5411, MFE5412, MFE5413, PEA5331, PEA5332, PEA5333

S3 : UE 3/6/6/6/4, total 25 ; stage 225 h, note 4 crédits mais calcul 45 x 5. S4 : 30, note 24 + 6 stage. Répartition EC absente.

S3 : UE 2/4/2/4/3. S4 : UE 5 mais total 30, contradiction. Coefficients EC absents.

### Epidemiologie M2

UE : S3 : FTE531, QME532, TEE533, RAE534, GEC535, GDE536 ; S4 : MFE541

ECUE : FTE5311, FTE5312, GDE5361, GDE5362, GDE5363, GEC5351, GEC5352, GEC5353, GEC5354, MFE5411, MFE5412, MFE5413, QME5321, QME5322, RAE5341, RAE5342, RAE5343, TEE5331, TEE5332

S3 : UE 3/3/6/5/6/7, total 30 ; S4 : total 30, note 24 + 6 stage, cellule crédit UE peu claire. Répartition EC absente.

S3 : UE 2/2/4/4/4/4. S4 : 30 affiché et total 30, contrôler visuellement. Coefficients EC absents.

### Nutrition M2

UE : S3 : NUC531, NSA532, IAN533, SEI534, CSS535 ; S4 : MFE541

ECUE : CSS5351, CSS5352, IAN5331, IAN5332, IAN5333, MFE5411, MFE5412, MFE5413, NSA5321, NSA5322, NSA5323, NUC5311, NUC5312, SEI5341, SEI5342

S3 : UE 4/7/8/5/6 (CSS535 comprend stage), total 26 + 4 stage. S4 : UE 30, total 24 + 6 stage. Excel S4 candidat : EC 4/6/20.

S3 : UE 2/3/3/2/2. S4 PDF : UE 5 ; Excel candidat : UE 30, EC 4/6/20. Versions différentes.

### Sante environnementale candidate M2

UE : S3 : FST531, TEP532, SPS533, PTE534, LDS535, SPR536 ; S4 : MFE541

ECUE : FST5311, FST5312, LDS5351, LDS5352, LDS5353, LDS5354, LDS5355, MFE5411, MFE5412, MFE5413, PTE5341, PTE5342, PTE5343, SPR5361, SPR5362, SPR5363, SPR5364, SPR5365, SPR5366, SPS5331, SPS5332, SPS5333, SPS5334, SPS5335, SPS5336, TEP5321, TEP5322, TEP5323, TEP5324, TEP5325

CANDIDATE SST uniquement : S3 UE 2/7/4/2/5/7, total 27 + 3 stage ; S4 : 24 + 6 stage. Équivalence au Master exact non prouvée.

CANDIDATE SST : S3 seconde série 1/4/2/1/3/4 ; S4 UE 5 mais total 30. Coefficients EC absents.

### Biologie Médicale — crédits par discipline

Aucun coefficient de notation explicite identifié. Les crédits ci-dessous viennent du dossier, sans assimiler crédit et coefficient.

| Semestre | UE | Crédits UE | Disciplines et crédits |
|---|---|---:|---|
| S1 | MBIO111 | 9 | Maintenance biomédicale : 2 ; Métrologie : 1 ; Management de la qualité : 2 ; Gestion des laboratoires : 4 |
| S1 | MBIO112 | 6 | Entomologie appliquée : 2.5 ; Changements climatiques : 1.5 ; Santé environnementale : 2 |
| S1 | MBIO113 | 10.5 | Pédagogie : 3 ; Législation de travail : 1.5 ; Genre et leadership : 1 ; Anglais technique : 2 ; Informatique : 3 |
| S1 | MBIO114 | 4.5 | Biostatistique : 3.5 ; Épidémiologie appliquée : 1 |
| S2 | MBIO121 | 15.5 | Bactériologie I : 3 ; Virologie I : 2 ; Parasitologie I : 3 ; Biochimie I : 2 ; Immunologie I : 2.5 ; Hématologie I : 2 ; Immunohistochimie/Immunochimie : 1 |
| S2 | MBIO122 | 5 | Cytologie et histologie : 1 ; Anatomie pathologie : 1.5 ; Biologie de la reproduction : 1 ; Biologie moléculaire I : 1.5 |
| S2 | MBIO123 | 3 | Toxicologie I : 2 ; Pharmacologie : 1 |
| S2 | MBIO124 | 2 | Biosécurité/Biosûreté : 2 |
| S2 | MBIO125 | 4.5 | Projet de Recherche : 4 ; Éthique et déontologie : 0.5 |
| S3 | MBIO231 | 20 | Bactériologie II : 3.5 ; Virologie II : 3.5 ; Parasitologie II : 3.5 ; Biochimie II : 3.5 ; Immunologie II : 2.5 ; Hématologie II : 3.5 |
| S3 | MBIO232 | 4 | Hémobiologie : 2 ; Biologie moléculaire II : 2 |
| S3 | MBIO233 | 4.5 | Mycologie : 2.5 ; Toxicologie II : 2 |
| S3 | MBIO234 | 1.5 | Projet de Recherche : 1.5 |
| S4 | MBIO241 | 12 | Bactériologie III : 2 ; Virologie III : 2 ; Parasitologie III : 2 ; Biochimie III : 2 ; Immunologie III : 2 ; Hématologie III : 2 |
| S4 | MBIO242 | 4 | Hémobiologie II : 2 ; Biologie moléculaire III : 2 |
| S4 | MBIO243 | 4 | Mycologie II : 2 ; Toxicologie III : 2 |
| S4 | MBIO244 | 10 | Stage et rédaction du mémoire : 10 |

M1 : 9 UE, 30 disciplines ; M2 : 8 UE, 22 disciplines. Les titres UE S4 diffèrent entre structuration (VI/VII/VIII) et tableaux (III/IV/V). Les volumes et objectifs figurent dans les extraits sources. Les règles de validation diffèrent entre Biologie (10/20) et OOAS (12/20) ; aucune règle du moteur modifiée.

## Documents précisément nécessaires

1. Original daté de la fiche institutionnelle des sept Masters, et libellés du diplôme délivré par formation si le diplôme générique Master doit être précisé.
2. Biologie Médicale M1/M2 : grille officielle des coefficients EC de S1 à S4 ; confirmation que MPro-BIO 2019 est la version applicable, avec clarification des titres S4.
3. Tronc commun M1 : maquette locale approuvée S1/S2 avec crédits et coefficients EC, stages compris, et liste explicite des formations concernées. Une pièce commune suffit si elle confirme les cinq/six parcours concernés ; les Excel odontologie ne constituent pas cette preuve.
4. Gynécologie Obstétrique M2 : grille S3/S4 par EC et stages ; confirmation du coefficient SRN533 et des codes EC atypiques.
5. Manager en Santé M2 : attestation de correspondance avec Management des services de santé ; grille EC S3/S4 ; clarification de l’en-tête et de la note stage 90 h / 6 crédits / 45 x 2.
6. Pédagogie en Santé M2 : attestation de correspondance avec Pédagogie des sciences de la santé ; grille EC S3/S4 ; correction approuvée du stage 225 h annoncé 4 crédits (calcul 5), et coefficient S4 UE 5 contre total 30.
7. Épidémiologie M1/M2 : version finale acceptée des maquettes S1–S4/rapport ou maquette locale explicitement approuvée ; grille par EC et confirmation des valeurs S4. Les suppressions suivies des annexes techniques ne suffisent pas.
8. Nutrition M2 : modèle certifié S3/S4 ; confirmation de provenance du classeur nommé odonto à en-tête Nutrition ; grille départageant PDF S4 (UE coefficient 5) et Excel (UE 30 ; EC 4/6/20). Le classeur confirmé compléterait S4 uniquement.
9. Santé Environnementale M1/M2 : maquette exacte S1–S4 ; si le parcours est Santé et sécurité au travail, attestation explicite de cette spécialité et grille EC approuvée. Une spécialité voisine ne suffit pas.
10. Liste des campus et années universitaires où ouvrir les classes M1/M2, avec leurs libellés. Les deux ProgrammeYear déjà créés ne remplacent pas ces classes.
11. Sources Relever/ et UAS pour les sept Masters si elles sont les références à appliquer : elles ne sont pas présentes actuellement. Aucun relevé Licence ne peut compléter une année Master.

Inutile de fournir une nouvelle copie de OOAS 2017 ou MPro-BIO 2019 déjà lus ; les pièces demandées comblent les lacunes ou départagent les variantes.

## Architecture et contrôles

Modèles et services inspectés : School/SchoolBranch ; Programme/Cycle/Diploma/ProgrammeYear ; AcademicClass/Semester/UE/EC ; programme_structure_service ; anciennes commandes de catalogue et rapport institutionnel. Un moteur partagé est conservé. Le programme appartient à ESFé Sup ; le campus d’une future classe doit respecter SchoolBranch.

Les validations UE/EC et le service de structure plafonnent actuellement les crédits à 6 ; cela bloque notamment MSS411=15, MBIO231=20 et des mémoires=30. EC impose aussi crédit >= coefficient. Aucune règle contournée ; aucune répartition UE→EC inventée. L’extension du moteur n’est pas réalisée dans cette mission de catalogue et de vérification.

Script ajouté : scripts/ensure_esfe_master_catalogue.py. Lecture seule par défaut ; --apply ajoute uniquement les programmes et cursus absents. Matching accents/casse/ponctuation, alias et petites variantes, recherche Master distincte de Licence ; multiples candidats ou école/diplôme divergent arrêtent la transaction. Aucun bootstrap global, tarif, frais, classe, admission ni note ajouté.

Validation : simulation, application puis nouvelle simulation (7 programmes et 14 années EXIST, aucune création supplémentaire proposée). Contrôle réel : 34 programmes, 88 ProgrammeYear ; 27 programmes antérieurs identiques ; classes/semestres/UE/EC toujours 0. Les niveaux créés sont #125 à #138, programmes #51 à #57.

Vérifications ciblées du matching exécutées avec succès : normalisation accents/casse/préfixes/tirets, correspondance Gynécologie-Obstetrique et exclusion d’une Licence homonyme. Classeur artifacts/audit_sept_masters_esfe_sup_20261008.xlsx : 14 lignes et tous les champs demandés ; aucune note d’étudiant.

python manage.py check : réussi, aucune anomalie. python manage.py makemigrations --check --dry-run : réussi, No changes detected. Aucune migration créée ou appliquée. Messages Windows GLib/UWP sans échec Django. Suites de tests générales non exécutées : contrôle ciblé des écritures réelles et intégrité du catalogue ; aucun moteur métier modifié. Vérification visuelle intégrale des tableaux non réalisée : champs peu clairs signalés pour contrôle avant import.

Fichiers ajoutés : les deux scripts, ce rapport et les artefacts d’inventaire, lecture de base, plan/application/vérification, intégrité, extraits OOAS/Biologie, tableaux historiques Word et 14 lignes structurées dans artifacts/. Les modifications préexistantes ont été préservées.

esfe-core : non touché. esfe_db : non touchée. ufhob_db : +7 Programme, +14 ProgrammeYear uniquement. Aucun secret ni résultat nominatif intégré au tableau final.
