#!/usr/bin/env bash
# NixFact update script.
#
# Updates only to **signed** released tags. Uses `git verify-tag` so a
# compromised upstream cannot push arbitrary code into operator VPSes.
#
# Set NIXFACT_TAG before running, e.g.:
#     NIXFACT_TAG=v0.1.1 ./update.sh
#
# A pre-update backup with files is taken first; if migration fails the
# script aborts WITHOUT calling `restart` so the operator can recover.

set -euo pipefail
umask 077

: "${NIXFACT_TAG:?Set NIXFACT_TAG to the release tag to update to (e.g. v0.1.1)}"

BENCH_DIR="${NIXFACT_BENCH:-/home/frappe/frappe-bench}"
NIXFACT_APP_DIR="${BENCH_DIR}/apps/nixfact_integration"

echo "=== NixFact Update — target tag: ${NIXFACT_TAG} ==="

cd "${BENCH_DIR}"

echo "Pre-update backup (with files)..."
bench --site all backup --with-files --compress

echo "Updating Frappe / ERPNext..."
bench update --pull --no-backup

echo "Verifying NixFact tag signature..."
cd "${NIXFACT_APP_DIR}"
git fetch --tags origin
if ! git verify-tag "${NIXFACT_TAG}"; then
    echo "ERROR: tag ${NIXFACT_TAG} signature did not verify. Aborting." >&2
    exit 6
fi
git checkout "${NIXFACT_TAG}"

cd "${BENCH_DIR}"
echo "Building assets..."
bench build --app nixfact_integration

echo "Running migrations..."
if ! bench --site all migrate; then
    echo "ERROR: migration failed. Investigate before restarting; backup is in sites/*/private/backups/." >&2
    exit 7
fi

echo "Restarting services..."
# Prefer systemctl when running under systemd; otherwise fall back to bench restart.
# The operator must have set up systemd units (deployment/systemd/*.service).
if command -v systemctl >/dev/null 2>&1 && systemctl is-active --quiet nixfact.service; then
    systemctl restart \
        nixfact.service \
        nixfact-scheduler.service \
        'nixfact-worker@short.service' 'nixfact-worker@long.service'
else
    bench restart
fi

echo "Update complete: nixfact at ${NIXFACT_TAG}."
