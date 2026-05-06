#!/usr/bin/env bash
# NixFact restore script.
#
# Safety-first defaults:
#   - Requires explicit site argument when more than one site is present.
#   - Takes a pre-flight backup (full + files) BEFORE touching anything.
#   - Refuses to run unless the operator types RESTORE.
#   - Decrypts age/gpg archives transparently.
#
# Usage:
#   ./restore.sh <backup_file> [--site <site_name>]

set -euo pipefail
umask 077

if [[ -z "${1:-}" ]]; then
    cat >&2 <<EOF
Usage: $0 <backup_file> [--site <site_name>]
       backup_file: .tar.gz, .tar.gz.age (age), or .tar.gz.gpg (gpg symmetric)
EOF
    exit 1
fi

BACKUP_FILE="$1"
shift || true

BENCH_DIR="${NIXFACT_BENCH:-/home/frappe/frappe-bench}"
SITE_NAME=""
while (( $# )); do
    case "$1" in
        --site) SITE_NAME="${2:-}"; shift 2 ;;
        *)      echo "Unknown arg: $1" >&2; exit 2 ;;
    esac
done

# Resolve site if not explicit.
mapfile -t SITES < <(find "${BENCH_DIR}/sites" -maxdepth 1 -mindepth 1 \
    -type d -not -name assets -printf '%f\n' 2>/dev/null || true)
if [[ -z "${SITE_NAME}" ]]; then
    if (( ${#SITES[@]} == 1 )); then
        SITE_NAME="${SITES[0]}"
    elif (( ${#SITES[@]} == 0 )); then
        echo "No sites found under ${BENCH_DIR}/sites; cannot restore." >&2
        exit 3
    else
        echo "Multiple sites present (${SITES[*]}); pass --site <name>." >&2
        exit 3
    fi
fi

echo "=== NixFact Restore ==="
echo "Site:    ${SITE_NAME}"
echo "Archive: ${BACKUP_FILE}"
echo
read -rp "Type RESTORE to confirm overwrite of ${SITE_NAME}: " ack
[[ "${ack}" == "RESTORE" ]] || { echo "Aborted."; exit 1; }

TEMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TEMP_DIR}"' EXIT

# --- Pre-flight backup of current state ---
PREFLIGHT_DIR="${BENCH_DIR}/sites/${SITE_NAME}/private/backups/pre-restore-$(date +%s)"
mkdir -p "${PREFLIGHT_DIR}"
echo "Taking pre-flight backup..."
( cd "${BENCH_DIR}" && bench --site "${SITE_NAME}" backup --with-files --compress )
# Move the just-created backup files into our pre-restore dir.
find "${BENCH_DIR}/sites/${SITE_NAME}/private/backups" -maxdepth 1 -type f \
    -newer "${PREFLIGHT_DIR}" -exec mv {} "${PREFLIGHT_DIR}/" \; || true
echo "Pre-restore backup at: ${PREFLIGHT_DIR}"

# --- Decrypt if needed ---
case "${BACKUP_FILE}" in
    *.tar.gz.age)
        : "${NIXFACT_AGE_IDENTITY:?Set NIXFACT_AGE_IDENTITY to your age private key file}"
        DECRYPTED="${TEMP_DIR}/decrypted.tar.gz"
        age -d -i "${NIXFACT_AGE_IDENTITY}" -o "${DECRYPTED}" "${BACKUP_FILE}"
        ARCHIVE="${DECRYPTED}"
        ;;
    *.tar.gz.gpg)
        : "${NIXFACT_GPG_PASSFILE:?Set NIXFACT_GPG_PASSFILE to the passphrase file}"
        DECRYPTED="${TEMP_DIR}/decrypted.tar.gz"
        gpg --decrypt --batch --passphrase-file "${NIXFACT_GPG_PASSFILE}" \
            -o "${DECRYPTED}" "${BACKUP_FILE}"
        ARCHIVE="${DECRYPTED}"
        ;;
    *.tar.gz)
        ARCHIVE="${BACKUP_FILE}"
        ;;
    *)
        echo "Unsupported archive extension; expected .tar.gz, .tar.gz.age, .tar.gz.gpg" >&2
        exit 4
        ;;
esac

# --- Extract ---
tar -xzf "${ARCHIVE}" -C "${TEMP_DIR}"

# --- Find SQL backup deterministically ---
mapfile -t SQL_FILES < <(find "${TEMP_DIR}" -name '*.sql.gz' -type f | sort -V)
if (( ${#SQL_FILES[@]} == 0 )); then
    echo "ERROR: No .sql.gz found in archive." >&2
    exit 5
elif (( ${#SQL_FILES[@]} > 1 )); then
    echo "Multiple .sql.gz files found; using newest: ${SQL_FILES[-1]}"
fi
SQL_FILE="${SQL_FILES[-1]}"

# --- Restore ---
cd "${BENCH_DIR}"
echo "Restoring database from ${SQL_FILE}..."
bench --site "${SITE_NAME}" restore "${SQL_FILE}"

# --- Files (private + public if present) ---
for FILES_BACKUP in "${TEMP_DIR}"/*-files.tar.gz \
                    "${TEMP_DIR}"/*private-files.tar.gz; do
    [[ -f "${FILES_BACKUP}" ]] || continue
    echo "Restoring ${FILES_BACKUP##*/}..."
    tar -xzf "${FILES_BACKUP}" -C "sites/${SITE_NAME}/"
done

echo "Running migrations..."
bench --site "${SITE_NAME}" migrate

echo "Restore complete."
echo "Pre-restore backup retained at: ${PREFLIGHT_DIR}"
