#!/usr/bin/env bash
# Liveness probe for the RQ worker running in THIS container.
#
# Why this exists at all: web, worker and scheduler share one image, so the
# image carries no HEALTHCHECK of its own — a baked-in probe is necessarily
# written for one role and lies about the other two. Each role declares its own
# check in compose instead.
#
# Why not a process check: tini is PID 1 and exits when the worker exits, so
# Docker's restart policy already covers "the process died". The failure a
# process check misses is a worker that is alive but wedged.
#
# So we ask RQ instead. `bench worker` registers itself under rq:workers and
# refreshes its key's expiry on every dequeue loop, with a timeout deliberately
# longer than the refresh interval. A key that still exists therefore means the
# worker checked in recently; a wedged or dead worker stops refreshing and the
# key expires on its own. That is RQ's own liveness contract — reusing it beats
# inventing a heartbeat-age threshold that would drift out of sync with it.
set -euo pipefail

URL="${REDIS_QUEUE:?REDIS_QUEUE must be set}"

# Parse the URL rather than using `redis-cli -u "$URL"`. The URL carries an
# empty username (redis://:pass@host), which redis-cli sends as the 2-arg ACL
# form `AUTH "" pass`; that fails with WRONGPASS against a plain `requirepass`
# server. `-a` sends the 1-arg form this server actually expects.
pass="$(sed -E 's|^redis://:([^@]*)@.*|\1|' <<<"$URL")"
host="$(sed -E 's|^redis://:[^@]*@([^:/]+).*|\1|' <<<"$URL")"

redis() { redis-cli -h "$host" -a "$pass" --no-auth-warning "$@"; }

me="$(hostname)"

# A worker that is shutting down sets `death`; an expired key returns empty for
# every field, so a stale set member simply fails to match our hostname.
for key in $(redis SMEMBERS rq:workers); do
    [[ "$(redis HGET "$key" hostname)" == "$me" ]] || continue
    death="$(redis HGET "$key" death)"
    if [[ -n "$death" ]]; then
        echo "worker $key is shutting down (death=$death)" >&2
        exit 1
    fi
    exit 0
done

echo "no live RQ worker registered under rq:workers for hostname ${me}" >&2
exit 1
