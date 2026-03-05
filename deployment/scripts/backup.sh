#!/usr/bin/env bash
# NIXFact backup script
# Usage: ./backup.sh [backup_dir]

set -euo pipefail

BACKUP_DIR="${1:-/opt/nixfact/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${TIMESTAMP}"

mkdir -p "${BACKUP_PATH}"

echo "=== NIXFact Backup - ${TIMESTAMP} ==="

# Database backup
echo "Backing up database..."
cd /home/frappe/frappe-bench
bench --site all backup --with-files
cp -r sites/*/private/backups/*"$(date +%Y%m%d)"* "${BACKUP_PATH}/" 2>/dev/null || true

# Config backup
echo "Backing up configuration..."
cp sites/common_site_config.json "${BACKUP_PATH}/"

# Compress
echo "Compressing..."
tar -czf "${BACKUP_DIR}/nixfact_backup_${TIMESTAMP}.tar.gz" -C "${BACKUP_DIR}" "${TIMESTAMP}"
rm -rf "${BACKUP_PATH}"

# Retention: keep last 30 days
find "${BACKUP_DIR}" -name "nixfact_backup_*.tar.gz" -mtime +30 -delete

echo "Backup complete: ${BACKUP_DIR}/nixfact_backup_${TIMESTAMP}.tar.gz"
