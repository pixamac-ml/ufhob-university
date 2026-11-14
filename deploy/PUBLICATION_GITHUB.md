> Mise à jour : voir [la passe de correction](FINALISATION_2026-11-14.md).
> Les résultats initiaux ci-dessous sont conservés comme historique de l’audit.

# Publication UFHOB : stratégie à valider avant commit et push

## État constaté le 14 novembre 2026

- Ancien remote local : `pixamac-ml/esfe-core` ; il a été corrigé vers
  `https://github.com/pixamac-ml/ufhob-university.git` pour fetch et push.
- Branche de préparation créée : `prep/ufhob-deployment-20261114`, sans upstream.
- Branche de départ : `refactor/ui-core-foundation`, HEAD `4a53e4a8`.
- Aucun commit créé, aucun push, aucun fetch vers ESFé, aucune branche supprimée.
- Aucun rebase, merge ou autre opération Git inachevée n'a été constaté au départ.
- L'état initial, l'ancien index et la configuration Git locale sont sauvegardés
  dans `.tmp-deployment-audit/`, dossier privé ignoré.

Le dépôt officiel UFHOB est public. Sa branche main distante était
`9946a179a80cee41c5d9e18b2491263af4dd427a`, avec trois commits :
racine `ed2c978892182c70aafc5aff77e4870c0d69236f`, puis `b1f5128c`, puis `9946a179`.
L'historique local hérité a pour racine `a0ec957cce410c01eebe5e4b833225768d314b38`.
Les racines sont distinctes ; les historiques ne doivent pas être fusionnés.

Les références locales `origin/*` et les upstreams des anciennes branches
proviennent encore de l'ancien remote. Changer l'URL ne change pas leur contenu.
Ne pas les interpréter comme un état vérifié du nouveau dépôt officiel, ni
faire `pull` depuis la branche de préparation. Aucun de ces anciens refs n'a été
supprimé ou réécrit pendant cette mission.

## Pourquoi ne pas pousser la branche locale

Le dépôt officiel distant contient déjà `backup.json` : sa lecture a identifié
186 enregistrements Django, dont des modèles de comptes, sessions, candidatures,
inscriptions et paiements. Ces données sont sensibles par nature, même si leur
caractère réel ou fictif n'est pas établi par cet audit. Le dépôt étant public,
le propriétaire doit valider leur retrait et la stratégie de traitement de
l'historique distant. Supprimer seulement le fichier dans un futur commit ne
l'effacera pas des commits précédents. Aucune suppression distante, réécriture
d'historique ou rotation de compte n'a été effectuée ici.

Une archive de sources est aussi présente à la racine distante. Sa lecture en
mémoire, sans extraction, n'a pas retrouvé de signature de secret parmi les
319 entrées texte inspectées. Ce contrôle limité ne constitue pas une revue
exhaustive des données ni une autorisation de republier l'archive.

L'analyse heuristique a retrouvé dans un ancien rapport de l'historique local
une valeur correspondant à un secret SMTP local. Des documents administratifs,
pièces de candidature et reçus figurent aussi dans l'ancien suivi Git.
Retirer ces fichiers de l'index ne les retire pas de l'historique.

Ne pas pousser l'historique hérité, même sur une branche UFHOB secondaire, ni
utiliser `--mirror`, `--all`, `--tags`, `--force` ou `--allow-unrelated-histories`.
Prévoir la rotation du secret concerné auprès de son propriétaire, après
validation et coordination : il peut être partagé avec une application protégée.
Cette mission ne change aucun identifiant de service et ne touche pas ESFé.
Elle ne prétend pas que le secret est déjà public : la constatation porte sur
l'historique local accessible, pas sur une publication distante démontrée.

## Préparation concrète et revue

`scripts/prepare_release.py` copie les sources actuelles dans un dossier de revue
ignoré `.tmp-release-preview-*`. Il ne copie aucun historique Git, refuse les
correspondances de secrets locaux détectées et n'effectue ni commit ni push.
Le manifeste privé donne les empreintes des sources copiées et les fichiers
hors moteur omis. Les candidats littéraux de test restent à examiner ; l'analyse
heuristique n'est pas une preuve exhaustive d'absence de secret ou de donnée personnelle.

Le dossier de revue doit comprendre toutes les applications, migrations,
templates, scripts, tests, sources statiques et configurations nécessaires.
Les archives documentaires, médias utilisateurs, bases, exports et configurations
privées restent hors publication. Vérifier séparément les licences des images,
polices et bibliothèques vendor ainsi que les données institutionnelles destinées
à être publiques ; ne pas publier des documents administratifs par défaut.

Exemple de création locale de l'artefact de revue, sans publication :

```powershell
.\.venv\Scripts\python.exe scripts/prepare_release.py --output .tmp-release-preview-REVISION
```

## Après autorisation du commit et de la publication uniquement

Prérequis : traiter ou faire qualifier par le propriétaire les données déjà
présentes dans le dépôt public. Une nouvelle copie de sources ne résout pas
l'exposition des anciens commits du dépôt officiel. Si un assainissement de
cet historique est nécessaire, il exige une autorisation distincte avant la suite.

1. Revérifier par lecture la branche main du dépôt officiel : elle a pu évoluer.
2. Dans un nouveau répertoire isolé **à l'intérieur de l'espace UFHOB autorisé**,
   cloner uniquement `ufhob-university`, puis créer une branche de livraison
   depuis sa véritable `origin/main`. Ne pas réinitialiser le dépôt de travail actuel.
3. Copier les sources revues de l'artefact, sans `.git`, `.env`, médias ou rapports
   privés. Examiner les anciens fichiers propres au dépôt officiel : leur éventuel
   retrait doit être explicitement validé, jamais obtenu par copie destructive.
4. Refaire les contrôles et tests sur cette copie complète. Examiner la différence
   avec main, les migrations, statiques, fichiers volumineux et secrets de l'index.
5. Présenter le diff et le plan de commit ; créer le commit seulement après accord.
6. Pousser uniquement la branche de livraison vers le dépôt officiel après accord,
   puis faire relire une pull request vers main. Ne pas écraser main.
7. Déployer plus tard le SHA explicitement validé ; aucun automatisme de production.

Cette approche part de la main officielle explicitement validée après traitement
des données distantes, ne fusionne pas les historiques et n'exige aucune
réécriture de l'ancien historique local.
Les branches existantes, le travail local et les données de développement sont préservés.
