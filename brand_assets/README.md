# Bibliothèque source de branding

Ce dossier conserve les livrables source validés par l'équipe graphique. Il
n'est pas un dossier `static` Django : aucun fichier placé ici n'est servi par
l'application avant une intégration dédiée.

## Règles communes

- Le SVG est la source maître.
- Les fonds sont transparents.
- Les exports web utilisent RGB / sRGB.
- Ne pas ajouter de marge blanche artificielle autour du logo.
- Préserver le ratio original : jamais d'étirement horizontal ou vertical.
- Les fichiers définitifs sont déposés manuellement avec les noms ci-dessous.

## ESFÉ — fichiers attendus

| Usage | Fichiers attendus |
| --- | --- |
| Source vectorielle | `esfe/source/logo-full.svg`, `esfe/source/logo-mark.svg` |
| PNG général | `esfe/png/logo-full-320.png`, `logo-full-640.png`, `logo-full-1024.png`, `logo-mark-256.png`, `logo-mark-512.png` |
| E-mail | `esfe/email/logo-email-320.png`, `logo-email-640.png` |
| Documents | `esfe/documents/logo-document-600.png`, `logo-document-1200.png` |
| Favicon | `esfe/favicon/favicon-32.png`, `favicon-48.png`, `apple-touch-icon-180.png`, `icon-192.png`, `icon-512.png` |

## Usages prévus

- **E-mail :** PNG 320/640 px ; affichage HTML courant entre 120 et 160 px
  selon le ratio réel. L'export doit mesurer au moins deux fois la taille
  affichée.
- **Site :** SVG prioritaire ; PNG seulement comme fallback.
- **Documents :** SVG si le moteur PDF le rend correctement ; sinon PNG 600 ou
  1200 px.

## Intégration future

Le point d'entrée applicatif est `core.branding.get_branding_assets()` et le
contexte template `branding`. Avant d'activer une nouvelle identité, copier les
exports validés vers les emplacements `static` décidés lors de cette future
mission, puis mettre à jour ce helper. Ne jamais faire pointer un template vers
un fichier absent.

`ufhob/` reprend volontairement la même arborescence pour ses futures sources ;
aucun faux fichier n'y est créé.
