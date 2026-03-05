#!/usr/bin/env bash
# NIXFact update script
# Usage: ./update.sh

set -euo pipefail

echo "=== NIXFact Update ==="

cd /home/frappe/frappe-bench

# Backup first
echo "Creating pre-update backup..."
bench --site all backup

# Pull updates
echo "Pulling latest code..."
bench update --pull --no-backup

# Install NIXFact updates
echo "Updating NIXFact..."
cd apps/nixfact_integration
git pull origin main
cd ../..

# Build and migrate
echo "Building assets..."
bench build --app nixfact_integration

echo "Running migrations..."
bench --site all migrate

echo "Restarting services..."
sudo supervisorctl restart all 2>/dev/null || bench restart

echo "Update complete!"
