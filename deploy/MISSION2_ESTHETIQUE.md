# Mission 2 — Rapport (Claude Code) — 18 novembre 2026

> Aucun commit, aucun push, aucun déploiement. Serveur de dev non coupé.
> Migration `memoires.0008` non appliquée. Aucune migration créée.

---

## 1. Ce qui s'est passé

1. J'ai d'abord appliqué la charte visuelle du prompt : bannières SVG, bleu nuit `#05254A`, orange `#EE9A22`, coin arrondi unique, couleurs propres aux écoles.
2. Tu as jugé ces consignes visuelles fausses et m'as demandé de tout annuler.
3. **Tout ce volet visuel a été retiré.** L'accueil, les couleurs et les pages écoles sont revenus à leur état d'origine.
4. Seules les 6 corrections que tu as autorisées sont conservées (section 2).

---

## 2. Ce qui est conservé (et seulement ça)

| # | Correction | Fichiers |
|---|---|---|
| 1 | **/plan-du-site/ : erreur 500 corrigée.** Le tri utilisait `display_order`, qui n'existe pas ; le champ réel est `order`. La page répond maintenant en 200. | `core/views.py` |
| 2 | **Bouton WhatsApp** : rond et plus petit sur mobile, zone sûre de l'iPhone respectée (`safe-area-inset`), espace réservé en bas du pied de page. Il était déjà masqué dans le tunnel d'admission. | `templates/public/base.html`, `static/src/css/input.css` (classe `whatsapp-float`) |
| 3 | **Compteurs du pied de page à 320 px** : « COMPOSANTES » et « FORMATIONS » ne sont plus coupés. La grille passe sur 2 colonnes sur petit écran. | `templates/cotton/public/footer.html` |
| 4 | **Sections vides masquées** : Actualités (accueil, pied de page, menu), campus, écoles et formations quand elles sont vides, bloc « Informations à venir », grille d'images vide de « Vie universitaire ». | `templates/home.html`, `footer.html`, `navbar.html`, `core/context_processors.py` |
| 5 | **Contacts valides uniquement** : +223 76 88 24 79, www.ufhob-mali.ml et @ufhob_officiel, depuis une source unique (settings + `core/public_contact.py`). Les anciens numéros de l'institution et l'e-mail sur l'ancien domaine ne sont plus publiés. Les liens Instagram, YouTube et TikTok **ESFé** codés en dur dans `base.html` ont été retirés : les réseaux sociaux viennent maintenant de la configuration du site, et une URL vide masque le lien. | `config/settings.py`, `core/public_contact.py`, `core/context_processors.py`, `templates/base.html`, `footer.html`, `core/templates/core/contact.html` |
| 6 | **Logos et descriptions FATEC/ESGA** : logo et description sous le nom officiel sur `/ecoles/fatec/` et `/ecoles/esga/`, dans le gabarit d'origine. Logo sur les cartes écoles de l'accueil. Le logo UFHOB de repli n'apparaît plus pour ces deux écoles. | `core/school_identity.py`, `core/templatetags/school_identity.py`, `templates/public/partials/ecole_identite.html`, `templates/cotton/public/school_card.html`, `formations/templates/formations/scoped_catalogue.html` (1 ligne d'include ajoutée, rien d'autre), `static/images/institution/{fatec,esga}-logo[-blanc].svg` |

**Commande ajoutée :** `python manage.py charger_identite_ecoles [--dry-run] [--force]`
- Elle écrit la description de FATEC et ESGA uniquement.
- Elle n'écrase jamais un texte existant sans `--force`.
- Elle a été exécutée en local : 2 descriptions écrites. Un second passage n'a rien modifié.

---

## 3. Ce qui a été retiré (retour à l'origine)

- **Accueil :** le cinematic-hero d'origine est revenu (photo, overlay, animation, barre de progression, menu révélé après la bannière).
- **Couleurs :** les tokens d'origine sont restaurés : `#1D5761`, `#00E9E0`, `#F5A72B`, ivoire `#FFFDF3`, rayons 0.125rem. Le CSS a été recompilé.
- **Boutons :** retour à l'orange d'origine `#f58220`.
- **Polices :** retour aux Google Fonts d'origine.
- **Pages écoles :** plus de bannière ni de couleurs propres.
- **Fichiers supprimés :** les bannières SVG/WebP de `static/`, le composant `campaign_hero.html`, les polices auto-hébergées.

---

## 4. ⚠️ Décisions à prendre

1. **Descriptions FATEC et ESGA :** ce sont les textes du prompt. Ce sont des **propositions** qui doivent être validées par la direction.
   - Une fois validées, rien à faire.
   - Sinon, modifie-les dans l'admin Django (École → Description), ou dans `core/school_identity.py` puis relance `charger_identite_ecoles --force`.
2. **Adresse e-mail publique :** l'e-mail de l'institution (`universite@univ-fhb-mali.org`) est sur l'**ancien domaine**. Il est donc masqué partout.
   - Si une adresse valide existe, ajoute dans `.env` : `PUBLIC_CONTACT_EMAIL=adresse@...`. Elle réapparaîtra automatiquement.
3. **URL des réseaux sociaux :** aucune URL n'est configurée, donc aucun lien n'est affiché. Le compte @ufhob_officiel figure en texte dans les contacts.
   - Pour afficher les liens, renseigne les URL Facebook, Instagram, TikTok et YouTube dans l'admin (Configuration du site). Je n'ai inventé aucune URL.
4. **Photo de l'accueil :** elle est revenue comme demandé, mais l'enseigne du bâtiment montre les **anciens numéros, l'ancienne boîte postale et l'ancien site `univ-fhb-mali.org`**.
   - C'est en contradiction avec la règle « contacts valides uniquement ».
   - Il faudrait une autre photo, ou accepter ce point.
5. **Chevauchement mobile « Notre signature » / « Découvrir l'université »** (audit P1) :
   - Je l'avais corrigé, mais la correction a été annulée avec l'accueil.
   - Le défaut est revenu. Faut-il le recorriger ?
6. **Test navigateur instable** (bouton « Suivant » ambigu pendant la transition Alpine) :
   - Je l'avais corrigé, mais la correction a été annulée.
   - Faut-il la réappliquer ? Elle ne touche que le fichier de test.
7. **Fichier de Codex `formations/fatec_esga.py`** : il remplace les contacts et vide les réseaux sociaux sur les pages FATEC, ESGA et `/formations/`.
   - Ses valeurs sont aujourd'hui identiques aux miennes, mais cela fait une deuxième source de vérité.
   - Il faudrait que Codex supprime ce remplacement. Je n'ai pas touché à son fichier.

---

## 5. Production : `www.ufhob-mali.ml` (préparé, PAS déployé)

**Cause probable, constatée dans le dépôt :**
- `deploy/nginx.conf.example` et `deploy/nginx-http.conf.example` : `server_name ufhob-mali.ml;` seulement, sans www.
- `deploy/production.env.example` : `ALLOWED_HOSTS=ufhob-mali.ml` et `CSRF_TRUSTED_ORIGINS=https://ufhob-mali.ml`, sans www.
- `deploy/HOSTINGER_UFHOB.md` : le certificat est demandé avec `-d ufhob-mali.ml` seulement.
- L'erreur « upstream connect error » sur www indique aussi que le **DNS `www` pointe ailleurs**, probablement vers le proxy Hostinger, et pas vers le VPS.

**Choix recommandé :** `www.ufhob-mali.ml` comme adresse canonique, puisque les publicités l'affichent. Le domaine nu redirige en 301 vers www.

Je n'ai modifié aucun fichier de déploiement : c'est à décider. Commandes à lancer sur le VPS :

```bash
# 1. DNS chez Hostinger (panneau DNS du domaine) :
#    enregistrement A    www  -> <IP du VPS>   (même IP que @)
#    supprimer tout CNAME/redirection Hostinger existant sur www
dig +short www.ufhob-mali.ml     # doit renvoyer l'IP du VPS
dig +short ufhob-mali.ml

# 2. Certificat couvrant les deux noms
sudo certbot certonly --webroot -w /var/lib/ufhob/acme --cert-name ufhob-mali.ml \
  -d ufhob-mali.ml -d www.ufhob-mali.ml --expand \
  --email "$ufhob_acme_email" --agree-tos --non-interactive

# 3. nginx : dans /etc/nginx/sites-available/ufhob
#    - bloc 80  : server_name ufhob-mali.ml www.ufhob-mali.ml;
#                 location / { return 301 https://www.ufhob-mali.ml$request_uri; }
#    - bloc 443 pour le domaine nu : server_name ufhob-mali.ml;
#                 return 301 https://www.ufhob-mali.ml$request_uri;
#    - bloc 443 principal : server_name www.ufhob-mali.ml;  (proxy vers Django)
sudo nginx -t && sudo systemctl reload nginx

# 4. Variables Django (/etc/ufhob/… fichier d'environnement privé)
BASE_URL=https://www.ufhob-mali.ml
ALLOWED_HOSTS=www.ufhob-mali.ml,ufhob-mali.ml
CSRF_TRUSTED_ORIGINS=https://www.ufhob-mali.ml,https://ufhob-mali.ml
#   puis redémarrer le seul service UFHOB (après ton accord)

# 5. Vérification
curl -sI http://ufhob-mali.ml        | head -3   # 301 -> https://www...
curl -sI https://ufhob-mali.ml       | head -3   # 301 -> https://www...
curl -sI https://www.ufhob-mali.ml   | head -3   # 200
```

**Après le déploiement de ce code :**
- `python manage.py collectstatic --noinput` : les nouveaux logos et le CSS recompilé doivent être copiés.
- `python manage.py charger_identite_ecoles --dry-run`, puis la même commande sans `--dry-run`.

---

## 6. Vérification

- **Captures après** : `.tmp-mission2/final-accueil-390.png`, `final-accueil-1366.png`, `final-fatec-390.png`, `final-fatec-1366.png`.
- **Captures avant** (audit de Codex) : `.tmp-revue-locale/page-00-*.png` (accueil) et `page-02-*.png` (FATEC).
- **Mesures sur les 4 captures finales :**
  - HTTP 200 ;
  - 0 erreur JavaScript ;
  - 0 réponse HTTP ≥ 400 ;
  - aucun débordement horizontal ;
  - couleur primaire mesurée `#1d5761` ;
  - cinematic-hero présent sur l'accueil.
- **`manage.py check`** : aucun problème.
- **Tests :**
  - Avant le retour en arrière, 11 tests sur 12 de la mission passaient.
  - **Après le retour en arrière, les tests n'ont pas pu être confirmés** : l'exécution s'est bloquée sans rien afficher (base SQLite de test) et je l'ai arrêtée.
  - **La suite complète n'a pas été lancée.** À faire avant toute mise en production.

---

## 7. `git diff --stat` : à lire avec prudence

Le dépôt contenait déjà de très nombreuses modifications non commitées avant cette mission, et la plupart des gabarits publics ne sont **pas suivis par git**. `git diff --stat` mélange donc mon travail et l'existant : par exemple, il affiche plus de 800 lignes pour `home.html`. **Ces chiffres ne mesurent pas cette mission.**

Liste exacte des fichiers touchés par la mission (tous du site public) :

**Modifiés**
`core/views.py` · `core/public_contact.py` · `core/context_processors.py` · `config/settings.py` · `templates/base.html` · `templates/home.html` · `templates/public/base.html` · `templates/cotton/public/footer.html` · `templates/cotton/public/navbar.html` · `templates/cotton/public/school_card.html` · `core/templates/core/contact.html` · `formations/templates/formations/scoped_catalogue.html` · `core/test_public_contact.py` · `static/src/css/input.css` · `static/public/css/main.css` (recompilé)

**Ajoutés**
`core/school_identity.py` · `core/templatetags/school_identity.py` · `core/management/commands/charger_identite_ecoles.py` · `core/test_mission2_public.py` · `templates/public/partials/ecole_identite.html` · `static/images/institution/fatec-logo.svg` · `fatec-logo-blanc.svg` · `esga-logo.svg` · `esga-logo-blanc.svg` · `deploy/MISSION2_ESTHETIQUE.md`

**Remis à l'état d'origine** (touchés puis restaurés)
`tailwind.config.js` · `templates/cotton/public/programme_card.html` · `school_programme_card.html` · `formations/templates/formations/campaign_detail.html` · `static/src/css/admission_funnel.css` · `formations/test_campaign_launch.py` · `formations/test_campaign_mobile.py`
