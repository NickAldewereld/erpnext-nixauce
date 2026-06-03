#!/usr/bin/env bash
# Wire infra endpoints from environment into Frappe's global site config, then
# hand off to the service command. Runs for web, worker and scheduler so every
# process agrees on where MariaDB/Redis live. Idempotent: rewrites the same keys
# each boot, leaves everything else untouched.
set -euo pipefail

# The container's PID-1 cwd ends up at / (Dockerfile WORKDIR isn't honored once
# tini is PID 1), and Frappe resolves sites_path and its log dir RELATIVE TO THE
# CWD. From / that means /sites (empty -> every site 404s) and /home/frappe/logs.
# Anchoring to the bench dir here fixes web, workers and scheduler in one place.
cd /home/frappe/frappe-bench

# frappe.app reads sites_path from $SITES_PATH (default "."), so the bare
# gunicorn web looks for sites at <cwd>/<site> instead of <cwd>/sites/<site>
# and 404s "<site> does not exist" — even though the site is valid (bench works,
# because bench sets sites_path to "sites"). Point it at the real sites dir;
# this also fixes the /assets and /files middleware (same _sites_path).
export SITES_PATH=/home/frappe/frappe-bench/sites

# Belt-and-suspenders for the cssutils logger path resolved before a site binds.
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
