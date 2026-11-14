# UFHOB-MALI — ESF SUP / MASTERS

Rapport du 9 octobre 2026. Base contrôlée : `ufhob_db`. Résultat : vitrine vérifiée ; installation académique **PARTIAL**.

Correction du nom abrégé confirmée par l’utilisateur : **ESFé Sup** (School #4). Appliquée en base et dans l’import pour éviter toute régression. Code ESFÉ, routes et rattachement Moribabougou conservés. Les mentions ESF Sup dans l’audit historique ci-dessous correspondent à l’ancien libellé de la demande.

## Mise à jour après instruction campus

L’utilisateur a confirmé **Moribabougou uniquement** et demandé le retrait temporaire de Djélibougou.

- SchoolBranch #5 créée : ESF Sup #4 → Moribabougou #1, active.
- Djélibougou #2 désactivé ; sa présence EsMed #4 désactivée. Aucun enregistrement supprimé, retrait réversible.
- Sept Masters disponibles à Moribabougou ; zéro à Djélibougou.
- Deuxième application : zéro création, zéro désactivation supplémentaire.
- Contrôles publics : Moribabougou et ESF Sup HTTP 200 ; ancien détail Djélibougou HTTP 404 ; campus retiré de /universite/.
- Année académique toujours absente : classes, semestres, UE et EC restent à créer après confirmation du libellé et des dates. Les lacunes documentaires listées plus bas restent valables.
- Preuves : artifacts/esf_sup_campus_apply_20261009.json, esf_sup_campus_second_run_20261009.json, esf_sup_campus_checks_20261009.json et esf_sup_masters_after_campus_20261009.json.

Les sections « avant/application initiale » ci-dessous conservent l’état historique précédant cette instruction.

## SCHOOL

ESF Sup found : YES — école existante réutilisée.
School ID : 4.
School code : ESFÉ, conservé pour préserver les routes.
School slug : champ absent du modèle réel ; route `/ecoles/esfé/` fondée sur le code.
Active : YES. Public visible : YES (modèle sans champ is_published ; sélection publique par is_active).
Libellé court harmonisé : ESFé Sup → ESF Sup, selon la demande. Nom officiel inchangé.
Campus count : 1. SchoolBranch count : 1 (Moribabougou, présence #5). Logo absent : fallback UFHOB existant utilisé.

**MASTER EXPECTED : 7**

## Architecture réelle inspectée

Institution représente l’université ; School l’école ; Branch le campus physique ; SchoolBranch la présence de l’école sur ce campus. Aucun modèle Campus distinct. Filiere est la famille disciplinaire ; Programme porte School, Cycle et Diploma. ProgrammeYear représente une année de cursus ; AcademicClass nécessite en plus Branch et AcademicYear. Semester dépend de la classe ; UE dépend du semestre ; EC dépend de l’UE.

Références existantes réutilisées : Cycle Master #3, Diploma Master #3, Filiere Sciences de la Santé #1. Aucun nouveau cycle, diplôme, campus ou année universitaire. Aucun modèle ESFé externe utilisé.

Les crédits et coefficients UE sont calculés à partir des EC. EC exige des crédits et coefficients positifs. Le modèle impose aussi une limite de 6 crédits par UE/EC ; plusieurs unités documentaires dépassent cette limite. Aucun contournement, changement de règlement ou migration de schéma effectué.

## DATABASE BEFORE / AFTER

| Donnée ESF Sup / sept Masters | Avant | Après |
|---|---:|---:|
| Master Programmes | 7 | 7 |
| ProgrammeYear / cursus M1-M2 | 14 | 14 |
| Classes | 0 | 0 |
| Semesters | 0 | 0 |
| UE | 0 | 0 |
| EC | 0 | 0 |
| Masters publiés | 0 | 7 |
| Campus / SchoolBranch | 0 | 0 |
| AcademicYear active | 0 | 0 |

Les sept programmes et quatorze années de cursus avaient été créés lors de la mission précédente. Cette exécution les conserve ; elle ne prétend pas les avoir créés à nouveau.

## Audit avant application

Pour chaque ligne : SCHOOL = école #4 ; CYCLE/DIPLOMA = Master #3 ; PROGRAMME_FOUND = YES ; CAMPUS_RELATIONS = [] ; SCHOOLBRANCH_RELATIONS = [] ; ACADEMIC_YEAR = absent ; CLASS_YEAR1/2 = absentes ; SEMESTERS = [] ; UE_COUNT = 0 ; EC_COUNT = 0 ; PUBLIC_VISIBLE avant = NO.

| Formation | Programme ID | ProgrammeYear M1/M2 | ACTION exécutée |
|---|---:|---|---|
| Biologie Médicale | 51 | 125 / 126 | KEEP + FIX_PUBLIC_VISIBILITY |
| Gynécologie Obstétrique | 52 | 127 / 128 | KEEP + FIX_PUBLIC_VISIBILITY |
| Manager en Santé | 53 | 129 / 130 | KEEP + FIX_PUBLIC_VISIBILITY |
| Pédagogie en Santé | 54 | 131 / 132 | KEEP + FIX_PUBLIC_VISIBILITY |
| Épidémiologie | 55 | 133 / 134 | KEEP + FIX_PUBLIC_VISIBILITY |
| Nutrition | 56 | 135 / 136 | KEEP + FIX_PUBLIC_VISIBILITY |
| Santé Environnementale | 57 | 137 / 138 | KEEP + FIX_PUBLIC_VISIBILITY |

CREATE_CLASS / CREATE_SEMESTER / IMPORT_MATRIX restent bloqués par l’absence d’année et de présence campus. Les deux campus existants sont Djélibougou #2 et Moribabougou #1 ; leurs présences existantes concernent d’autres écoles. Les rattacher à ESF Sup sans instruction inventerait une affectation.

## CREATED / UPDATED

Programmes : 0 ; ProgrammeYear/equivalent : 0 ; Campus relations : 0 ; SchoolBranch : 0 ; Classes : 0 ; Semesters : 0 ; UE : 0 ; EC : 0 ; Schools : 0.

Modifications réellement appliquées : sept is_public passés à True ; un libellé court School harmonisé ; sept descriptions administratives issues du précédent audit retirées de la présentation publique. Admissions non ouvertes ; données académiques validées non modifiées.

## MASTER DETAIL

### 1. Biologie Médicale

School : ESF Sup #4.
Cycle : Master #3. Diploma : Master #3.
Programme : #51 — présent et réutilisé.
Campus : Moribabougou #1, SchoolBranch active #5.
1re année : ProgrammeYear #125 présent ; classe M1 absente.
2e année : ProgrammeYear #126 présent ; classe M2 absente.
S1 : absent en base ; référence HIGH ; 4 UE transcrites dans le manifeste ; Master maquette/MPro -BIO bon.pdf (pages 13, 14, 15, 16).
S2 : absent en base ; référence HIGH ; 5 UE transcrites dans le manifeste ; Master maquette/MPro -BIO bon.pdf (pages 13, 14, 15, 16).
S3 : absent en base ; référence HIGH ; 4 UE transcrites dans le manifeste ; Master maquette/MPro -BIO bon.pdf (pages 17, 18).
S4 : absent en base ; référence HIGH ; 4 UE transcrites dans le manifeste ; Master maquette/MPro -BIO bon.pdf (pages 17, 18).
UE : 0 en base. EC : 0 en base.
Sources : voir les références ci-dessus, le manifeste et le registre croisé JSON. La fiche institutionnelle fournie par l’utilisateur confirme seulement formation/cycle/deux années ; elle ne fournit pas de maquette.
Public visible : YES.
Status : PARTIAL.
S4_SOURCE_MISSING : NO pour la référence candidate ; son existence ne prouve pas que les EC sont importables.

### 2. Gynécologie Obstétrique

School : ESF Sup #4.
Cycle : Master #3. Diploma : Master #3.
Programme : #52 — présent et réutilisé.
Campus : Moribabougou #1, SchoolBranch active #5.
1re année : ProgrammeYear #127 présent ; classe M1 absente.
2e année : ProgrammeYear #128 présent ; classe M2 absente.
S1 : absent en base ; référence MEDIUM ; 4 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
S2 : absent en base ; référence MEDIUM ; 4 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
Contrôle : Les notes de bas de tableau documentent ces crédits de stage en plus des crédits UE. Leur répartition par EC n’est pas fournie : aucun EC/UE de stage supplémentaire n’est inventé.
S3 : absent en base ; référence HIGH ; 5 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 21, 22, 23).
Contrôle : Les notes de bas de tableau documentent ces crédits de stage en plus des crédits UE. Leur répartition par EC n’est pas fournie : aucun EC/UE de stage supplémentaire n’est inventé.
S4 : absent en base ; référence HIGH ; 1 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 21, 22, 23).
Contrôle : Les notes de bas de tableau documentent ces crédits de stage en plus des crédits UE. Leur répartition par EC n’est pas fournie : aucun EC/UE de stage supplémentaire n’est inventé.
UE : 0 en base. EC : 0 en base.
Sources : voir les références ci-dessus, le manifeste et le registre croisé JSON. La fiche institutionnelle fournie par l’utilisateur confirme seulement formation/cycle/deux années ; elle ne fournit pas de maquette.
Public visible : YES.
Status : PARTIAL.
S4_SOURCE_MISSING : NO pour la référence candidate ; son existence ne prouve pas que les EC sont importables.

### 3. Manager en Santé

School : ESF Sup #4.
Cycle : Master #3. Diploma : Master #3.
Programme : #53 — présent et réutilisé.
Campus : Moribabougou #1, SchoolBranch active #5.
1re année : ProgrammeYear #129 présent ; classe M1 absente.
2e année : ProgrammeYear #130 présent ; classe M2 absente.
S1 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
S2 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
S3 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 63, 64, 65).
S4 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 63, 64, 65).
UE : 0 en base. EC : 0 en base.
Sources : voir les références ci-dessus, le manifeste et le registre croisé JSON. La fiche institutionnelle fournie par l’utilisateur confirme seulement formation/cycle/deux années ; elle ne fournit pas de maquette.
Public visible : YES.
Status : AMBIGUOUS (sources à confirmer) ; installation PARTIAL.
S4_SOURCE_MISSING : NO pour la référence candidate ; son existence ne prouve pas que les EC sont importables.

### 4. Pédagogie en Santé

School : ESF Sup #4.
Cycle : Master #3. Diploma : Master #3.
Programme : #54 — présent et réutilisé.
Campus : Moribabougou #1, SchoolBranch active #5.
1re année : ProgrammeYear #131 présent ; classe M1 absente.
2e année : ProgrammeYear #132 présent ; classe M2 absente.
S1 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
S2 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
S3 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 80, 81).
S4 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 80, 81).
UE : 0 en base. EC : 0 en base.
Sources : voir les références ci-dessus, le manifeste et le registre croisé JSON. La fiche institutionnelle fournie par l’utilisateur confirme seulement formation/cycle/deux années ; elle ne fournit pas de maquette.
Public visible : YES.
Status : AMBIGUOUS (sources à confirmer) ; installation PARTIAL.
S4_SOURCE_MISSING : NO pour la référence candidate ; son existence ne prouve pas que les EC sont importables.

### 5. Épidémiologie

School : ESF Sup #4.
Cycle : Master #3. Diploma : Master #3.
Programme : #55 — présent et réutilisé.
Campus : Moribabougou #1, SchoolBranch active #5.
1re année : ProgrammeYear #133 présent ; classe M1 absente.
2e année : ProgrammeYear #134 présent ; classe M2 absente.
S1 : absent en base ; référence MEDIUM ; 4 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12); SITE/UPFHOB/AMAQ 2024/UFHOB-MALI/ANNEXES/ANNEXES LIG.docx (pages tableur).
S2 : absent en base ; référence MEDIUM ; 4 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12); SITE/UPFHOB/AMAQ 2024/UFHOB-MALI/ANNEXES/ANNEXES LIG.docx (pages tableur).
Contrôle : Les notes de bas de tableau documentent ces crédits de stage en plus des crédits UE. Leur répartition par EC n’est pas fournie : aucun EC/UE de stage supplémentaire n’est inventé.
S3 : absent en base ; référence HIGH ; 6 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 46, 47); SITE/UPFHOB/AMAQ 2024/UFHOB-MALI/ANNEXES/ANNEXES LIG.docx (pages tableur).
S4 : absent en base ; référence AMBIGUOUS ; 1 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 46, 47); SITE/UPFHOB/AMAQ 2024/UFHOB-MALI/ANNEXES/ANNEXES LIG.docx (pages tableur).
Contrôle : SOURCE_CONFLICT : tableau crédit UE/total 30 ; note de bas de tableau 24 crédits de cours + 6 de stage. Position du coefficient également à clarifier. Aucune ventilation implicite.
UE : 0 en base. EC : 0 en base.
Sources : voir les références ci-dessus, le manifeste et le registre croisé JSON. La fiche institutionnelle fournie par l’utilisateur confirme seulement formation/cycle/deux années ; elle ne fournit pas de maquette.
Public visible : YES.
Status : AMBIGUOUS (sources à confirmer) ; installation PARTIAL.
S4_SOURCE_MISSING : NO pour la référence candidate ; son existence ne prouve pas que les EC sont importables.

### 6. Nutrition

School : ESF Sup #4.
Cycle : Master #3. Diploma : Master #3.
Programme : #56 — présent et réutilisé.
Campus : Moribabougou #1, SchoolBranch active #5.
1re année : ProgrammeYear #135 présent ; classe M1 absente.
2e année : ProgrammeYear #136 présent ; classe M2 absente.
S1 : absent en base ; référence MEDIUM ; 4 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
S2 : absent en base ; référence MEDIUM ; 4 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
Contrôle : Les notes de bas de tableau documentent ces crédits de stage en plus des crédits UE. Leur répartition par EC n’est pas fournie : aucun EC/UE de stage supplémentaire n’est inventé.
S3 : absent en base ; référence HIGH ; 5 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 16, 17); Master maquette/odonto/réleve s4 odonto.xlsx (pages tableur).
S4 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 16, 17); Master maquette/odonto/réleve s4 odonto.xlsx (pages tableur).
UE : 0 en base. EC : 0 en base.
Sources : voir les références ci-dessus, le manifeste et le registre croisé JSON. La fiche institutionnelle fournie par l’utilisateur confirme seulement formation/cycle/deux années ; elle ne fournit pas de maquette.
Public visible : YES.
Status : AMBIGUOUS (sources à confirmer) ; installation PARTIAL.
S4_SOURCE_MISSING : NO pour la référence candidate ; son existence ne prouve pas que les EC sont importables.

### 7. Santé Environnementale

School : ESF Sup #4.
Cycle : Master #3. Diploma : Master #3.
Programme : #57 — présent et réutilisé.
Campus : Moribabougou #1, SchoolBranch active #5.
1re année : ProgrammeYear #137 présent ; classe M1 absente.
2e année : ProgrammeYear #138 présent ; classe M2 absente.
S1 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
S2 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 11, 12).
S3 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 56, 57, 58, 59).
S4 : absent en base ; référence AMBIGUOUS ; 0 UE transcrites dans le manifeste ; Master maquette/DOC-20260423-WA0041..pdf (pages 56, 57, 58, 59).
UE : 0 en base. EC : 0 en base.
Sources : voir les références ci-dessus, le manifeste et le registre croisé JSON. La fiche institutionnelle fournie par l’utilisateur confirme seulement formation/cycle/deux années ; elle ne fournit pas de maquette.
Public visible : YES.
Status : AMBIGUOUS (sources à confirmer) ; installation PARTIAL.
S4_SOURCE_MISSING : NO pour la référence candidate ; son existence ne prouve pas que les EC sont importables.

## Sources inspectées et contrôles

Six documents de Master maquette relus : deux PDF (107 et 34 pages) et quatre classeurs. Empreintes SHA256, pages et en-têtes dans `artifacts/esf_sup_masters_sources_rescanned_20261009.json`. Les textes détaillés et tableaux extraits sont conservés dans les artifacts d’audit du 8 octobre.

Aucun dossier Relever/ trouvé dans le dépôt. SITE/EPSFé et SITE/AMAQ2024 sont vides. Les documents SITE/ANNEXES Word comportent des tableaux historiques dans les suppressions de suivi des modifications : exclus de l’import. Les autres documents techniques/catalogues ne fournissent pas de répartition EC fiable pour ces Masters. Aucun étudiant, note, moyenne, rang ou décision importé.

Biologie : 17 UE ; totaux S1-S4 = 30 chacun ; crédits EC documentés, coefficients EC absents. OOAS tronc commun : S1 = 30 ; S2 = 28 crédits UE + 2 de stage explicitement mentionnés. Gynécologie : S3 = 25 + 5 de stage ; S4 = 24 + 6 de stage. Ces crédits de stage non ventilés ne deviennent pas des UE/EC inventées.

Épidémiologie S3 = 30 ; S4 SOURCE_CONFLICT (tableau 30, note 24+6 et coefficient ambigu), exclu. Nutrition S3 = 30 ; S4 SOURCE_CONFLICT (tableau et total, plus divergences avec le classeur au nom odonto mais en-tête Nutrition), exclu. Les équivalences Manager/Management des services de santé, Pédagogie en Santé/Pédagogie des sciences de santé, Santé Environnementale/Santé et Sécurité au Travail restent AMBIGUOUS ; aucune extrapolation.

À campus/année confirmés, le manifeste permet actuellement 14 semestres et 58 UE en brouillon, sans EC faute de valeurs complètes. Ce résultat a été testé uniquement sur une base de test, pas installé dans ufhob_db. Les totaux documentaires restent dans le manifeste ; une UE vide ne possède pas ses crédits documentaires dans le modèle calculé et ne doit jamais être présentée comme une maquette complète.

## PUBLIC WEBSITE

ESF Sup listed : YES — accueil et page /universite/ : HTTP 200.
ESF Sup detail : YES — /ecoles/esfé/ : HTTP 200, sept Masters.
Programmes shown : YES — sept noms réels affichés, chargés depuis la base.
School filter : YES — ESFÉ retourne uniquement les programmes #51–57 ; école inconnue retourne 404.
Programme detail : YES — sept pages HTTP 200, chacune liée à School #4.
Wrong-school leakage : NO — filtres ESMED, ESGA, FATEC contrôlés.

Contrôles réels avec Django Client sur ufhob_db en transaction de lecture seule ; preuves dans `artifacts/esf_sup_masters_public_checks_20261009.json`. Pas de déploiement distant ni de vérification d’un serveur hébergé effectués.

Corrections ciblées : titres Programme sur cartes et fiches au lieu du nom commun Filiere ; libellé école configurable ; toutes les écoles actives dans le pied de page ; fallback logo UFHOB ; filtre école explicite invalide renvoyant 404. Aucun catalogue statique, nouveau logo, prix ou débouché inventé.

## MISSING SOURCES — documents/informations exactement nécessaires

| Formation | Année | Semestre | Missing | Required source |
|---|---|---|---|---|
| Toutes | M1/M2 | Tous | Campus autorisé et année universitaire absents | Instruction institutionnelle précisant Djélibougou, Moribabougou ou les deux ; libellé de l’année active et dates de début/fin |
| Biologie Médicale | M1/M2 | S1-S4 | Coefficients EC | Maquette/relevé officiel de ce Master avec coefficient de chaque EC |
| Gynécologie Obstétrique | M1/M2 | S1-S4 | Crédits et coefficients EC, ventilation stages | Maquette/relevé de ce Master par semestre détaillant les EC et les stages |
| Épidémiologie | M1/M2 | S1-S4 | Ventilation EC ; contradiction S4 | Maquette/relevé détaillé et tableau S4 validé clarifiant UE/EC/crédits/coefficients |
| Nutrition | M1/M2 | S1-S4 | Ventilation EC ; conflit S4 PDF/tableur | Maquette/relevé détaillé du Master Nutrition et version S4 validée précisant crédits et coefficients |
| Manager en Santé | M1/M2 | S1-S4 | Équivalence avec Management non prouvée, tableau S3 contradictoire | Maquette ESF Sup portant le titre exact ou décision d’équivalence institutionnelle, avec tableaux EC complets corrigés |
| Pédagogie en Santé | M1/M2 | S1-S4 | Équivalence avec Pédagogie des sciences de santé non prouvée | Maquette ESF Sup portant le titre exact ou décision d’équivalence, avec ventilation EC |
| Santé Environnementale | M1/M2 | S1-S4 | Équivalence avec Santé et Sécurité au Travail non prouvée | Maquette ESF Sup portant le titre exact ; document d’équivalence si applicable ; EC/crédits/coefficients |

Une fiche de renseignement ou un document Licence ne peut remplacer ces maquettes Master. Les référentiels régionaux ne prouvent pas à eux seuls l’adoption institutionnelle de toutes les variantes. La limite de 6 crédits du modèle devra également être examinée avec les documents validés avant une importation complète ; aucune migration proposée dans cette mission.

## IDEMPOTENCE

Schools created on second run : 0 ; Programmes : 0 ; ProgrammeYear : 0 ; Campus relations : 0 ; SchoolBranch : 0 ; Classes : 0 ; Semesters : 0 ; UE : 0 ; EC : 0. Modifications sur seconde exécution : 0.

Dry-run, apply et seconde application exécutés. Les fichiers initial_* et final_* distinguent publication initiale et reprise après durcissement du contrôle arithmétique. L’idempotence des structures académiques configurées est également testée sur SQLite ; leur création réelle reste bloquée.

## CHECK / TESTS

manage.py check : PASS — 0 problème.
makemigrations --check --dry-run : PASS — No changes detected. Migrations créées : 0.
Sept tests ciblés : PASS (3,594 s, base SQLite tmp/esf_sup_masters_test.sqlite3, aucune donnée de test dans PostgreSQL). Couverture : absence de doublon School/Cycle, Catalogue 7 Masters, Licence distincte, contexte campus/année, 14 classes et sources autorisées, sources ambiguës exclues, import EC synthétique intégral, conflits et rollback, idempotence, visibilité et isolation publiques.

Suite complète non exécutée : mission ciblée, aucun changement hors périmètre. Avertissements Windows GLib/GIO de découverte d’applications lors de certains processus ; commandes terminées avec code 0. Pour la route accentuée, SQLite ne gère pas la casse Unicode comme PostgreSQL ; test SQLite avec code exact et contrôle live PostgreSQL avec route minuscule.

## Fichiers modifiés/créés pour cette mission

- formations/esf_sup_masters.py : service additif transactionnel.
- formations/management/commands/install_esf_sup_masters.py : dry-run/apply, garde ufhob_db.
- formations/test_esf_sup_masters.py : tests ciblés.
- docs/esf_sup_master_matrix_sources.json : transcription sourcée et exclusions.
- formations/views.py : filtre école explicite.
- formations/templates/formations/detail.html : titres et libellé école.
- templates/cotton/public/programme_card.html : titre Programme.
- templates/cotton/public/footer.html : écoles actives sans troncature.
- templates/public/school_detail.html : fallback logo UFHOB.
- docs/RAPPORT_ESF_SUP_MASTERS_20261009.md et artifacts/esf_sup_masters_*_20261009.json : rapport/preuves.

D’autres modifications étaient déjà présentes dans le dépôt ; elles ont été préservées. Comparaison avant/après : autres écoles, autres programmes, campus, SchoolBranch, cycles, diplômes et données académiques inchangés.

esfe-core touched : NO. esfe_db touched : NO.

**READY_FOR_ESF_SUP_MASTER_DATA: PARTIAL**

**READY_FOR_ESF_SUP_PUBLIC_WEBSITE: YES** (vues locales Django vérifiées).

La mission académique reste incomplète : ni classes ni semestres/UE/EC en base à ce stade. La réponse sur l’année académique et ses dates est nécessaire pour poursuivre la création sans inventer de contexte. Aucun autre chantier de refonte commencé.
