#!/usr/bin/env bash
# Outil manuel Ubuntu. N'installe, ne migre et ne redemarre rien spontanement.
set -euo pipefail
readonly app_dir=/srv/ufhob
readonly env_file=/etc/ufhob/production.env
if [[ $# -eq 0 || ! -r "$env_file" ]]; then
    echo 'Usage: sudo -u ufhob bash /srv/ufhob/deploy/manage-ufhob.sh <commande Django>' >&2
    exit 2
fi
case "$1" in
    check|showmigrations|makemigrations|migrate|collectstatic|initialiser_catalogue_ufhob|charger_catalogue_fatec_esga|charger_identite_ecoles|charger_frais_esmed|masquer_esfe_public|masquer_ecole_public) ;;
    *) echo 'Commande non autorisee par cet outil de deploiement.' >&2; exit 2 ;;
esac
# Fichier de confiance root:ufhob, syntaxe KEY='valeur', compatible systemd.
set -a
source "$env_file"
set +a
[[ "${DJANGO_SETTINGS_MODULE:-}" == 'config.settings_production' ]] || exit 2
[[ "${UFHOB_ENVIRONMENT:-}" == 'production' ]] || exit 2
cd "$app_dir"
"$app_dir/.venv/bin/python" - <<'PY'
import django
django.setup()
from django.conf import settings
from django.db import connection
db = settings.DATABASES['default']
if db['NAME'] != 'ufhob_db' or db.get('USER') != 'ufhob_app':
    raise SystemExit('Cible PostgreSQL UFHOB invalide.')
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database(), current_user')
    if cursor.fetchone() != ('ufhob_db', 'ufhob_app'):
        raise SystemExit('Identite de connexion PostgreSQL UFHOB invalide.')
print('Cible verifiee : ufhob_db / ufhob_app.')
PY
exec "$app_dir/.venv/bin/python" manage.py "$@"
