#!/usr/bin/env bash
# Hook Certbot borne au certificat UFHOB, sans edition des autres virtual hosts.
set -euo pipefail
if [[ "${RENEWED_LINEAGE:-}" == '/etc/letsencrypt/live/ufhob-mali.ml' ]]; then
    /usr/sbin/nginx -t
    /usr/bin/systemctl reload nginx
fi
