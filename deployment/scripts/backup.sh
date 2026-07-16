#!/usr/bin/env bash
# NixFact backup script.
#
# An archive holds the full DB dump plus bench's own site_config_backup.json,
# which carries the site's encryption_key and db_password. The encryption_key
# decrypts every Mollie / Ponto credential stored at rest, so treating an
# archive as plaintext is a privacy disaster.
#
# It is the per-site site_config.json that holds the key — not
# common_site_config.json, which this script also bundles but which contains
# only db_host, redis URLs and ports. This header used to name the wrong file;
# verified against a real archive on 2026-07-16. The distinction matters
# because the wrong version invites the conclusion that encryption is optional.
#
# Modes (set NIXFACT_BACKUP_ENCRYPTION):
#   age   — pipe through age -r "$NIXFACT_AGE_RECIPIENT" (recommended)
#   gpg   — symmetric AES256 with a passphrase file at NIXFACT_GPG_PASSFILE
#   none  — explicit opt-out; UMASK 0077 still applies
#
# Usage:  ./backup.sh [backup_dir]

set -euo pipefail
umask 077

BACKUP_DIR="${1:-/opt/nixfact/backups}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
STAGING_DIR="${BACKUP_DIR}/.staging-${TIMESTAMP}"
BENCH_DIR="${NIXFACT_BENCH:-/home/frappe/frappe-bench}"
ENC_MODE="${NIXFACT_BACKUP_ENCRYPTION:-age}"

mkdir -p "${BACKUP_DIR}" "${STAGING_DIR}"
trap 'rm -rf "${STAGING_DIR}"' EXIT

echo "=== NixFact Backup — ${TIMESTAMP} ==="

# --- DB + files via bench ---
cd "${BENCH_DIR}"
echo "Dumping database + files..."
# Tell bench where to write instead of working out where it wrote.
#
# This previously ran the dump and then parsed bench's summary for paths, with
# a datestamp glob as fallback. It never produced a single backup. bench prints
#   Database: /path/to/dump.sql.gz 1.1MiB
# — size last — while the grep anchored the extension at end of line, so it
# matched nothing and returned 1. Under `set -o pipefail` that killed the
# script before the fallback could run, and the EXIT trap wiped the staging
# dir on the way out, leaving no trace beyond a failed unit. (Had the grep
# matched, `awk '{print $NF}'` would have yielded "1.1MiB" rather than a path.)
#
# The lesson is not "fix the regex": bench's summary is a human-readable
# display format, not an interface, and parsing it would break again on the
# next upstream wording change. --backup-path is the interface.
bench --site all backup --with-files --compress --backup-path "${STAGING_DIR}"

# Never trust a zero exit code alone — verify the artefacts exist. A silent
# empty backup is the failure mode that matters here.
if ! compgen -G "${STAGING_DIR}/*" >/dev/null; then
    echo "bench exited 0 but wrote nothing to ${STAGING_DIR}" >&2
    exit 1
fi

# --- Site config (contains encryption_key — encrypt mode is mandatory) ---
echo "Including common_site_config.json..."
cp "${BENCH_DIR}/sites/common_site_config.json" "${STAGING_DIR}/"

# --- Compress ---
ARCHIVE="${BACKUP_DIR}/nixfact_backup_${TIMESTAMP}.tar.gz"
echo "Compressing..."
tar -czf "${ARCHIVE}" -C "${STAGING_DIR}" .
chmod 600 "${ARCHIVE}"

# --- Encrypt ---
case "${ENC_MODE}" in
    age)
        : "${NIXFACT_AGE_RECIPIENT:?Set NIXFACT_AGE_RECIPIENT to your age recipient (age1...)}"
        echo "Encrypting with age..."
        age -r "${NIXFACT_AGE_RECIPIENT}" -o "${ARCHIVE}.age" "${ARCHIVE}"
        rm -f "${ARCHIVE}"
        FINAL="${ARCHIVE}.age"
        ;;
    gpg)
        : "${NIXFACT_GPG_PASSFILE:?Set NIXFACT_GPG_PASSFILE to the passphrase file}"
        echo "Encrypting with gpg..."
        gpg --symmetric --cipher-algo AES256 \
            --batch --passphrase-file "${NIXFACT_GPG_PASSFILE}" \
            -o "${ARCHIVE}.gpg" "${ARCHIVE}"
        rm -f "${ARCHIVE}"
        FINAL="${ARCHIVE}.gpg"
        ;;
    none)
        echo "WARNING: NIXFACT_BACKUP_ENCRYPTION=none — backup is plaintext." >&2
        FINAL="${ARCHIVE}"
        ;;
    *)
        echo "Unknown NIXFACT_BACKUP_ENCRYPTION='${ENC_MODE}'" >&2
        rm -f "${ARCHIVE}"
        exit 2
        ;;
esac

chmod 600 "${FINAL}"

# --- Retention with safety guard ---
# Refuse to prune if there is suspiciously little to keep (suggests
# repeated backup failure).
existing_count="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'nixfact_backup_*' -type f | wc -l)"
if (( existing_count >= 2 )); then
    find "${BACKUP_DIR}" -maxdepth 1 -name 'nixfact_backup_*' -type f -mtime +30 -delete
else
    echo "Skipping retention: only ${existing_count} backup(s) present." >&2
fi

echo "Backup complete: ${FINAL}"
