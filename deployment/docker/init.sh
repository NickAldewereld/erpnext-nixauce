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
else
    echo "Site ${SITE} already exists — skipping creation."
fi

# Assert the apps on every run, not only when the site is created. An existing
# site is not the same as a site with the apps installed: if a first run dies
# between new-site and install-app, the site survives and every later run would
# take the skip branch and never install anything.
installed="$(bench --site "${SITE}" list-apps 2>/dev/null | awk '{print $1}')"
for app in erpnext nixfact_integration; do
    if grep -qx "${app}" <<<"${installed}"; then
        echo "App ${app} already installed on ${SITE}."
    else
        echo "Installing ${app} on ${SITE}..."
        bench --site "${SITE}" install-app "${app}"
    fi
done

# Sync the site's schema with the code in this image. Nothing else does this:
# `bench new-site` only syncs at creation, so from the first image rebuild
# onwards the DocType definitions in the database drift behind the JSON on
# disk. The drift is invisible until something reads a field that exists in
# code but not in the database — e.g. any Single whose validate() compares
# get_doc_before_save().<new_field>, which raises AttributeError rather than
# reporting a stale schema. That is what blocked ERPNext's setup wizard here;
# this site turned out to be 30 patches behind.
#
# Migrate is idempotent: with nothing to apply it is a no-op, so it belongs on
# every boot rather than in a runbook someone has to remember.
echo "Migrating ${SITE}..."
bench --site "${SITE}" migrate

bench use "${SITE}"
bench --site "${SITE}" enable-scheduler || true
echo "Init complete for ${SITE}."
