# Bootstrap institutionnel

`institution.json` contient le socle des annexes officielles et inclut
`academic_reference.json`, le catalogue académique institutionnel réel ESFé.
Aucune donnée de démonstration : aucun utilisateur, étudiant, inscription,
année académique, classe, UE ou EC n'est créé.

Chaque entrée future de `objects` suit cette forme :

```json
{
  "id": "annexe.bamako",
  "model": "branches.Branch",
  "lookup": {"code": "BKO"},
  "fields": {"name": "..."}
}
```

Les modèles autorisés appartiennent à `core`, `branches`, `formations` ou
`academics`. Une relation vers un objet déjà créé peut utiliser :

```json
{"$ref": "annexe.bamako"}
```

Le manifeste est appliqué par upsert, dans une transaction :

```powershell
python manage.py bootstrap_institution --dry-run
python manage.py bootstrap_institution
```

Avant une reconstruction locale, exécuter dans cet ordre : backup PostgreSQL,
`reset_business_data`, puis `bootstrap_institution`.

Le reset opérationnel conserve désormais toute l'application `formations` :
cycles, diplômes, filières, programmes, années de cursus, frais, pièces et
contenus. Les identités et les désactivations restent donc intactes, y compris
pour les spécialités ajoutées ultérieurement par l'établissement. Les classes,
années académiques et inscriptions restent des données opérationnelles.
Ne jamais lancer ce reset sur la production.

## Référentiel académique permanent

Installation du seul catalogue, sans modifier les annexes existantes :

```powershell
python manage.py bootstrap_institution --data-file bootstrap/academic_reference.json --dry-run
python manage.py bootstrap_institution --data-file bootstrap/academic_reference.json
```

Les manifestes utilisent les modèles existants et leurs clés naturelles. Les
`aliases` reconnaissent les anciens noms (notamment « Cycle supérieur Licence »).
Une correspondance multiple provoque un refus atomique, sans fusion ni suppression.
`create_fields` initialise les statuts/contenus seulement à la création : une
réexécution ne réactive pas un programme désactivé ou archivé. Les tarifs `strict`
et `fee_labels` refusent une ancienne tarification contradictoire ou des tranches
supplémentaires ; aucun écrasement financier silencieux. Réconcilier ces cas
explicitement avant réexécution. `--dry-run` annule toute la transaction.

Les programmes sont publiables mais les admissions sont fermées à la création :
aucune disponibilité dans une annexe n'est présumée. Le rattachement opérationnel
reste `AcademicClass(programme, branch, academic_year)` ; le bootstrap ne crée
aucune classe pour simuler une offre. Le modèle Fee représente actuellement un
tarif de référence par année de cursus, pas une grille datée par annexe/année
académique. Le dû des inscriptions existantes reste leur montant enregistré.

Les conditions d'accès sont des `ProgrammeQuickFact`, visibles et administrables.
Les cinq pièces communes sont partagées via `ProgrammeRequiredDocument` ; la
preuve du diplôme est conditionnée au niveau d'accès. BAC/Licence/TSS ne sont pas
trois pièces cumulativement obligatoires. Les libellés génériques des diplômes
primaire/secondaire restent à préciser par l'établissement.

Points non inventés : dates calendaires des huit mensualités à confirmer ;
inscription indiquée « À l'inscription » ; conditions d'accès Master à confirmer ;
aucun tarif M2 créé. La structure Master de deux ans reprend le modèle existant.
Une tarification ajoutée ultérieurement sur une année non tarifée par le manifeste
est conservée : l'absence de tarif confirmé n'est pas une interdiction de tarifer.
Les tarifs M1 sont chargés pour les quatre spécialités explicitement communiquées ;
les trois spécialités mises en avant en M2 restent sans tarifs. La mise en avant
de M1/M2 est une donnée `ProgrammeQuickFact`, pas une liste fermée en code.
Un coût total incomplet est affiché « À confirmer », jamais assimilé à la seule M1.

Ne pas utiliser `seed_formations`, `seed_licences`, `seed_masters` ou
`formations/scripts/create_master_programmes.py` pour installer ce référentiel :
ces anciens scripts contiennent des tarifs non confirmés et ne constituent pas
le bootstrap officiel.
