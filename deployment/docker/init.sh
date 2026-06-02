#!/usr/bin/env bash
# One-shot, idempotent first-run bootstrap. Safe to re-run: if the site already
# exists it only re-asserts the current-site and scheduler. Invoked via
#   docker compose run --rm -e ADMIN_PASSWORD=... nixfact /init.sh
# entrypoint.sh has already written common_site_config.json by the time this
# runs, so bench can reach MariaDB/Redis by service name.
set -euo pipefail

cd /home/frappe/frappe-bench
SITE="${SITE_NAME:?SITE_NAME must be set}"

if [[ ! -d "sites/${SITE}" ]]; then
    echo "Creating site ${SITE}..."
    bench new-site "${SITE}" \
        --db-host "${DB_HOST}" \
        --db-root-password "${DB_ROOT_PASSWORD}" \
        --admin-password "${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set for first init}" \
        --install-app erpnext
    bench --site "${SITE}" install-app nixfact_integration
else
    echo "Site ${SITE} already exists — skipping creation."
fi

bench use "${SITE}"
bench --site "${SITE}" enable-scheduler || true
echo "Init complete for ${SITE}."
