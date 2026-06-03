#!/usr/bin/env bash
# Wire infra endpoints from environment into Frappe's global site config, then
# hand off to the service command. Runs for web, worker and scheduler so every
# process agrees on where MariaDB/Redis live. Idempotent: rewrites the same keys
# each boot, leaves everything else untouched.
set -euo pipefail

# When no site is bound (e.g. gunicorn --preload importing frappe.utils.pdf,
# which sets up the cssutils logger), Frappe resolves its log dir one level
# above the bench: /home/frappe/logs. That dir doesn't exist in the image and
# the web process crashes on a RotatingFileHandler open. Ensure it exists.
mkdir -p /home/frappe/logs /home/frappe/frappe-bench/logs

CONFIG="/home/frappe/frappe-bench/sites/common_site_config.json"

python3 - "$CONFIG" <<'PY'
import json, os, sys

path = sys.argv[1]
try:
    with open(path) as fh:
        cfg = json.load(fh)
except (FileNotFoundError, json.JSONDecodeError):
    cfg = {}

cfg["db_host"] = os.environ["DB_HOST"]
cfg["db_port"] = int(os.environ.get("DB_PORT", "3306"))
cfg["redis_cache"] = os.environ["REDIS_CACHE"]
cfg["redis_queue"] = os.environ["REDIS_QUEUE"]
cfg["redis_socketio"] = os.environ.get("REDIS_SOCKETIO", os.environ["REDIS_QUEUE"])

with open(path, "w") as fh:
    json.dump(cfg, fh, indent=1, sort_keys=True)
PY

exec "$@"
