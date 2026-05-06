#!/usr/bin/env bash
# NixFact backup script.
#
# Backups contain the full DB dump *and* common_site_config.json (which
# stores Frappe's encryption_key, used to decrypt every Mollie / Ponto
# password at rest). Treating these as plaintext is a privacy disaster.
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
backup_output="$(bench --site all backup --with-files --compress)"

# bench prints absolute paths; fish them out.
echo "${backup_output}" | grep -E 'sql\.gz$|files\.tar$|files\.tar\.gz$|private-files\.tar$' | \
    awk '{print $NF}' | while read -r f; do
        if [[ -f "$f" ]]; then
            cp -- "$f" "${STAGING_DIR}/"
        fi
    done

# Fallback: glob match if grep above didn't catch anything (older bench).
shopt -s nullglob
for f in "${BENCH_DIR}"/sites/*/private/backups/*"$(date +%Y%m%d)"*; do
    cp -n -- "$f" "${STAGING_DIR}/"
done
shopt -u nullglob

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
