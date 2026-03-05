#!/usr/bin/env bash
# NIXFact restore script
# Usage: ./restore.sh <backup_file.tar.gz>

set -euo pipefail

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    exit 1
fi

BACKUP_FILE="$1"
TEMP_DIR=$(mktemp -d)

echo "=== NIXFact Restore ==="
echo "Backup: ${BACKUP_FILE}"

# Extract
echo "Extracting backup..."
tar -xzf "${BACKUP_FILE}" -C "${TEMP_DIR}"

# Find the SQL backup
SQL_FILE=$(find "${TEMP_DIR}" -name "*.sql.gz" | head -1)
if [ -z "${SQL_FILE}" ]; then
    echo "ERROR: No SQL backup found in archive"
    rm -rf "${TEMP_DIR}"
    exit 1
fi

# Restore
echo "Restoring database..."
cd /home/frappe/frappe-bench
SITE_NAME=$(ls sites/ | grep -v assets | grep -v common | head -1)

bench --site "${SITE_NAME}" restore "${SQL_FILE}"

# Restore files if present
FILES_BACKUP=$(find "${TEMP_DIR}" -name "*-files.tar.gz" | head -1)
if [ -n "${FILES_BACKUP}" ]; then
    echo "Restoring files..."
    tar -xzf "${FILES_BACKUP}" -C "sites/${SITE_NAME}/"
fi

# Migrate
echo "Running migrations..."
bench --site "${SITE_NAME}" migrate

# Cleanup
rm -rf "${TEMP_DIR}"

echo "Restore complete!"
