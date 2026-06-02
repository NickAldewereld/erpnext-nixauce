# NixFact Production Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run ERPNext + the `nixfact_integration` app as a production instance in an unprivileged Docker-in-LXC container on Proxmox host `pro`, published at `https://erp.aldewereldconsultancy.nl` via Caddy + Authentik OIDC on the Hostinger VPS over the existing Tailscale subnet route, with borgmatic-captured nightly backups.

**Architecture:** A single `--with-docker` LXC (192.168.178.218, VMID 218) runs the repo's `deployment/docker/docker-compose.yml` stack (MariaDB, two Redis, web, one worker, scheduler). Caddy on the VPS terminates TLS and reverse-proxies over the Tailscale-advertised `192.168.178.0/24` route to the container's LAN IP. Authentik provides OIDC SSO into Frappe.

**Tech Stack:** Proxmox VE 9, LXC (Debian 12), Docker Compose, Frappe/ERPNext v17, MariaDB 10.11, Redis 7, Caddy, Authentik (OIDC), borgmatic.

**Reference spec:** `docs/superpowers/specs/2026-06-02-nixfact-production-deployment-design.md`

**Conventions (host `pro`):** code/config/docs in English; owner comms in Dutch; secrets in `/root/.secrets/*.env` on `pro`; SSD root disk + HDD (`/mnt/pve/wd1tb`) for bulk; all containers unprivileged. Source of truth for infra: `/root/CLAUDE.md` on `pro`.

---

## File Structure (created/modified)

In this repo:
- **Create** `deployment/docker/entrypoint.sh` — wires `DB_HOST`/`REDIS_*` env into Frappe's `common_site_config.json` on container start, then execs the service command. Closes gap #1 (compose passes infra env that nothing currently consumes).
- **Create** `deployment/docker/init.sh` — idempotent first-run bootstrap: create the site, install `erpnext` + `nixfact_integration`, enable scheduler. Closes gap #2.
- **Modify** `deployment/docker/Dockerfile` — `COPY` the two scripts; route `ENTRYPOINT` through `entrypoint.sh`.
- **Modify** `deployment/docker/docker-compose.yml` — trim mem limits, merge to one worker, parameterise the web port bind (`BIND_HOST`).
- **Modify** `deployment/docker/.env.example` — add `BIND_HOST`, `ADMIN_PASSWORD`, `REDIS_SOCKETIO`; document them.
- **Modify** `docs/installation.md` — replace the stale version-15 / `bench start` instructions with the compose flow (out of scope to rewrite fully; add a pointer to this plan).

On host `pro` (no repo): the LXC, a `git clone` of this repo inside it, `/root/.secrets/nixfact.env`, and a borgmatic source-dir addition on LXC 200.

On the VPS: one Caddyfile site block; Authentik OIDC Provider + Application + group.

---

## Phase 0 — Make the image deployable (on the dev box)

> The current Dockerfile builds the bench but never creates a site and nothing
> consumes the `DB_HOST`/`REDIS_*` env vars. Phase 0 fixes that and proves the
> stack boots end-to-end locally on the dev box (Docker 27.5.1 confirmed
> usable) before touching `pro`.

### Task 0.1: Add the config-wiring entrypoint

**Files:**
- Create: `deployment/docker/entrypoint.sh`

- [ ] **Step 1: Write `deployment/docker/entrypoint.sh`**

```bash
#!/usr/bin/env bash
# Wire infra endpoints from environment into Frappe's global site config, then
# hand off to the service command. Runs for web, worker and scheduler so every
# process agrees on where MariaDB/Redis live. Idempotent: rewrites the same keys
# each boot, leaves everything else untouched.
set -euo pipefail

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
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x deployment/docker/entrypoint.sh && ls -l deployment/docker/entrypoint.sh`
Expected: mode shows `-rwxr-xr-x`.

- [ ] **Step 3: Commit**

```bash
git add deployment/docker/entrypoint.sh
git commit -m "[deploy] Add entrypoint that wires DB/Redis env into site config"
```

### Task 0.2: Add the idempotent site-init script

**Files:**
- Create: `deployment/docker/init.sh`

- [ ] **Step 1: Write `deployment/docker/init.sh`**

```bash
#!/usr/bin/env bash
# One-shot, idempotent first-run bootstrap. Safe to re-run: if the site already
# exists it only re-asserts the current-site and scheduler. Invoked via
#   docker compose run --rm -e ADMIN_PASSWORD=... nixfact /init.sh
# entrypoint.sh has already written common_site_config.json by the time this
# runs, so bench can reach MariaDB/Redis by service name.
set -euo pipefail

cd /home/frappe/frappe-bench
SITE="${SITE_NAME:?SITE_NAME must be set}"

if [[ ! -d "sites/${SITE}" ]]; then
    echo "Creating site ${SITE}..."
    bench new-site "${SITE}" \
        --db-host "${DB_HOST}" \
        --db-root-password "${DB_ROOT_PASSWORD}" \
        --admin-password "${ADMIN_PASSWORD:?ADMIN_PASSWORD must be set for first init}" \
        --install-app erpnext
    bench --site "${SITE}" install-app nixfact_integration
else
    echo "Site ${SITE} already exists — skipping creation."
fi

bench use "${SITE}"
bench --site "${SITE}" enable-scheduler || true
echo "Init complete for ${SITE}."
```

- [ ] **Step 2: Make it executable**

Run: `chmod +x deployment/docker/init.sh && ls -l deployment/docker/init.sh`
Expected: mode shows `-rwxr-xr-x`.

> Note for the executor: exact `bench new-site` flags can differ across Frappe
> v17 point releases. If Step (Task 0.6) fails on an unknown flag, the likely
> fixes are: `--db-root-password` → `--mariadb-root-password`, or splitting
> `--install-app erpnext` into a separate `bench --site … install-app erpnext`
> call. Adjust here, re-run, then commit the working version.

- [ ] **Step 3: Commit**

```bash
git add deployment/docker/init.sh
git commit -m "[deploy] Add idempotent site bootstrap (new-site + install apps)"
```

### Task 0.3: Route the Dockerfile entrypoint through the wiring script

**Files:**
- Modify: `deployment/docker/Dockerfile:103-106`

- [ ] **Step 1: Copy the scripts into the runtime image**

Add after `WORKDIR /home/frappe/frappe-bench` (runtime stage, around line 95), before `EXPOSE 8000`:

```dockerfile
COPY --chown=frappe:frappe deployment/docker/entrypoint.sh /entrypoint.sh
COPY --chown=frappe:frappe deployment/docker/init.sh /init.sh
```

- [ ] **Step 2: Change ENTRYPOINT to chain tini → entrypoint.sh**

Replace line 103:

```dockerfile
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]
```

(Leave the `CMD [...gunicorn...]` line unchanged; `entrypoint.sh` execs it.)

- [ ] **Step 3: Commit**

```bash
git add deployment/docker/Dockerfile
git commit -m "[deploy] Chain entrypoint.sh in image so env wiring runs for all services"
```

### Task 0.4: Trim compose for RAM and parameterise the port bind

**Files:**
- Modify: `deployment/docker/docker-compose.yml`

- [ ] **Step 1: Parameterise the web port bind**

Replace the `nixfact` service `ports:` block (line ~105-106):

```yaml
    ports:
      - "${BIND_HOST:-127.0.0.1}:${HTTP_PORT:-8080}:8000"
```

(Default `127.0.0.1` keeps the dev smoke test local; in the LXC we set `BIND_HOST=0.0.0.0` so Caddy can reach it over the subnet route.)

- [ ] **Step 2: Trim mem limits to fit the 4 GB LXC cap**

Set these `mem_limit` values: `mariadb` → `1g`; `redis-cache` → `192m`; `redis-queue` → `192m`; `nixfact` (web) → `1500m`; `scheduler` → `256m`.

- [ ] **Step 3: Merge the two workers into one**

Delete the `worker-long` service. Rename `worker-short` to `worker`, set `mem_limit: 768m`, and change its command to process both queues:

```yaml
    command: ["bench", "worker", "--queue", "short,long"]
```

- [ ] **Step 4: Validate compose syntax**

Run: `cd deployment/docker && cp .env.example .env.tmp && docker compose --env-file .env.tmp config >/dev/null && echo OK && rm .env.tmp`
Expected: `OK` (no schema errors).

- [ ] **Step 5: Commit**

```bash
git add deployment/docker/docker-compose.yml
git commit -m "[deploy] Trim compose mem limits, single worker, parameterised bind"
```

### Task 0.5: Extend `.env.example` with the new variables

**Files:**
- Modify: `deployment/docker/.env.example`

- [ ] **Step 1: Add variables under the `--- Site ---` block**

```bash
# --- Site ---
SITE_NAME=nixfact.localhost
HTTP_PORT=8080
# 127.0.0.1 for local/dev; 0.0.0.0 in the LXC so the VPS Caddy can reach it
# over the Tailscale subnet route.
BIND_HOST=127.0.0.1
NIXFACT_TAG=local

# Admin password is consumed ONLY by the one-shot init (docker compose run …
# /init.sh). Not needed for normal runtime. Leave blank here; pass at init time.
ADMIN_PASSWORD=

# Defaults to REDIS_QUEUE if unset.
# REDIS_SOCKETIO=
```

- [ ] **Step 2: Commit**

```bash
git add deployment/docker/.env.example
git commit -m "[deploy] Document BIND_HOST/ADMIN_PASSWORD/REDIS_SOCKETIO in .env.example"
```

### Task 0.6: Local smoke test — build, init, boot, verify

**Files:** none (runtime verification on the dev box)

- [ ] **Step 1: Generate a local .env**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
./deployment/scripts/generate_env.sh > deployment/docker/.env
chmod 600 deployment/docker/.env
```

- [ ] **Step 2: Build the image**

Run: `cd deployment/docker && docker compose build`
Expected: image `nixfact:local` builds successfully (Frappe + ERPNext v17 + nixfact_integration; first build is slow, ~minutes).

- [ ] **Step 3: Start the data services**

Run: `docker compose up -d mariadb redis-cache redis-queue`
Then: `docker compose ps`
Expected: all three become `healthy` within ~30s.

- [ ] **Step 4: Run the one-shot site init**

```bash
docker compose run --rm -e ADMIN_PASSWORD=smoketest-admin nixfact /init.sh
```
Expected: ends with `Init complete for nixfact.localhost.` If it fails on a `bench new-site` flag, apply the fix noted in Task 0.2 Step 2, re-commit, re-run.

- [ ] **Step 5: Start web + worker + scheduler**

Run: `docker compose up -d` then `docker compose ps`
Expected: `nixfact` becomes `healthy` (its HEALTHCHECK hits `/api/method/ping`).

- [ ] **Step 6: Verify the desk and assets load**

```bash
curl -fsS http://127.0.0.1:8080/api/method/ping
curl -fsS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/app
curl -fsS -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8080/assets/frappe/dist/css/website.bundle.css" 2>/dev/null || true
```
Expected: `ping` returns `{"message":"pong"}`; `/app` returns `200` or `302` (redirect to login); assets return `200`. If assets 404, record it — it means gunicorn isn't serving static and an nginx/whitenoise sidecar is needed (carry into Phase 6 known-limitations, not a Phase 0 blocker).

- [ ] **Step 7: Confirm NixFact doctypes are installed**

```bash
docker compose exec nixfact bench --site nixfact.localhost list-apps
```
Expected: lists `frappe`, `erpnext`, `nixfact_integration`.

- [ ] **Step 8: Tear down the smoke test**

```bash
docker compose down -v
rm -f deployment/docker/.env
```
Expected: containers and the test volumes removed. (`.env` is gitignored; confirm with `git status` showing a clean tree.)

- [ ] **Step 9: Push the branch**

```bash
cd /mnt/nvme1tb/projects/erpnext-nixauce
git push -u origin nixfact-production-deployment
```
Expected: branch pushed (so the LXC can `git clone`/`pull` it). Confirm the remote/credentials first.

---

## Phase 1 — Provision the LXC on `pro`

> All `pro` commands run as root over SSH (via the Tailscale route). Follow the
> existing `lxc-factory` paved road.

### Task 1.1: Create the container

**Files:** none (Proxmox state)

- [ ] **Step 1: Confirm the next IP is still free**

Run on `pro`: `/root/scripts/pro-toolkit.sh lxc next-ip`
Expected: `192.168.178.218` (if different, use the reported IP and matching VMID throughout).

- [ ] **Step 2: Dry-run the creation**

Run on `pro`:
```bash
/root/scripts/pro-toolkit.sh lxc --dry-run create nixfact 192.168.178.218 \
  --with-docker --ram 4096 --disk 30 --cores 4 --id 218
```
Expected: a preview with `nesting=1`, `keyctl=1`, Debian 12 template, 30 GB on `local-lvm`, no errors.

- [ ] **Step 3: Create the container**

Run on `pro` (same command without `--dry-run`):
```bash
/root/scripts/pro-toolkit.sh lxc create nixfact 192.168.178.218 \
  --with-docker --ram 4096 --disk 30 --cores 4 --id 218
```
Expected: container 218 created and started; Docker CE installed inside.

- [ ] **Step 4: Verify Docker works inside the LXC**

Run on `pro`: `pct exec 218 -- docker run --rm hello-world`
Expected: the "Hello from Docker!" message (proves nesting/keyctl are correct).

- [ ] **Step 5: Add a swap allowance and confirm onboot**

Run on `pro`:
```bash
pct set 218 --swap 2048 --onboot 1
pct config 218 | grep -E 'memory|swap|onboot|features'
```
Expected: `memory: 4096`, `swap: 2048`, `onboot: 1`, `features: keyctl=1,nesting=1`.

### Task 1.2: Add the HDD-backed backup bind-mount

**Files:** none (Proxmox state)

- [ ] **Step 1: Create the host backup dir and bind-mount it**

Run on `pro`:
```bash
mkdir -p /mnt/pve/wd1tb/nixfact/backups
pct set 218 --mp0 /mnt/pve/wd1tb/nixfact,mp=/mnt/nixfact
pct config 218 | grep mp0
```
Expected: `mp0: /mnt/pve/wd1tb/nixfact,mp=/mnt/nixfact`.

- [ ] **Step 2: Verify the mount inside the container**

Run on `pro`: `pct exec 218 -- sh -c 'mkdir -p /mnt/nixfact/backups && touch /mnt/nixfact/backups/.probe && ls -la /mnt/nixfact/backups'`
Expected: `.probe` created (HDD path writable from inside).

---

## Phase 2 — Deploy the stack inside the LXC

### Task 2.1: Clone the repo and generate production env

**Files:** none (container state)

- [ ] **Step 1: Install git and clone the branch**

Run on `pro`:
```bash
pct exec 218 -- bash -lc 'apt-get update && apt-get install -y git && \
  git clone -b nixfact-production-deployment https://github.com/NickAldewereld/erpnext-nixauce /opt/nixfact'
```
Expected: repo cloned to `/opt/nixfact` inside the container. (If the repo is private, configure a deploy token/SSH key first.)

- [ ] **Step 2: Generate the production .env**

Run on `pro`:
```bash
pct exec 218 -- bash -lc 'cd /opt/nixfact && \
  ./deployment/scripts/generate_env.sh > deployment/docker/.env && \
  chmod 600 deployment/docker/.env'
```
Expected: `.env` created with random secrets.

- [ ] **Step 2b: Set production values in .env**

Run on `pro`:
```bash
pct exec 218 -- bash -lc 'cd /opt/nixfact/deployment/docker && \
  sed -i "s/^SITE_NAME=.*/SITE_NAME=erp.aldewereldconsultancy.nl/" .env && \
  sed -i "s/^BIND_HOST=.*/BIND_HOST=0.0.0.0/" .env && \
  sed -i "s/^HTTP_PORT=.*/HTTP_PORT=8080/" .env && \
  grep -E "^(SITE_NAME|BIND_HOST|HTTP_PORT)=" .env'
```
Expected: `SITE_NAME=erp.aldewereldconsultancy.nl`, `BIND_HOST=0.0.0.0`, `HTTP_PORT=8080`.

- [ ] **Step 3: Copy the generated secrets to `/root/.secrets` on `pro`**

Run on `pro`:
```bash
mkdir -p /root/.secrets
pct exec 218 -- cat /opt/nixfact/deployment/docker/.env > /root/.secrets/nixfact.env
chmod 600 /root/.secrets/nixfact.env
```
Expected: `/root/.secrets/nixfact.env` exists (backup of the generated secrets, per convention).

### Task 2.2: Build, init, and bring up the stack

**Files:** none (container state)

- [ ] **Step 1: Build the image inside the LXC**

Run on `pro`: `pct exec 218 -- bash -lc 'cd /opt/nixfact/deployment/docker && docker compose build'`
Expected: `nixfact:local` builds (slow on the R220; be patient).

- [ ] **Step 2: Start data services**

Run on `pro`: `pct exec 218 -- bash -lc 'cd /opt/nixfact/deployment/docker && docker compose up -d mariadb redis-cache redis-queue && sleep 30 && docker compose ps'`
Expected: all three `healthy`.

- [ ] **Step 3: Run the one-shot site init with a strong admin password**

Run on `pro` (replace with a real strong password; store it in `/root/.secrets/nixfact.env`):
```bash
pct exec 218 -- bash -lc 'cd /opt/nixfact/deployment/docker && \
  docker compose run --rm -e ADMIN_PASSWORD="<STRONG-ADMIN-PW>" nixfact /init.sh'
```
Expected: `Init complete for erp.aldewereldconsultancy.nl.`

- [ ] **Step 4: Bring up web + worker + scheduler**

Run on `pro`: `pct exec 218 -- bash -lc 'cd /opt/nixfact/deployment/docker && docker compose up -d && sleep 20 && docker compose ps'`
Expected: `nixfact` `healthy`, worker + scheduler `running`.

- [ ] **Step 5: Verify reachable on the LAN IP**

Run on `pro`: `curl -fsS http://192.168.178.218:8080/api/method/ping`
Expected: `{"message":"pong"}` (proves `BIND_HOST=0.0.0.0` exposes it on the subnet route).

- [ ] **Step 6: Record host RAM headroom**

Run on `pro`: `free -h | head -2`
Expected: host still has comfortable free+available memory with the stack running. If tight, reduce `nixfact` web `mem_limit` and gunicorn `--workers` (in the CMD) and note it.

---

## Phase 3 — Publish via Caddy on the VPS

> The VPS already fronts `sign.` (docuseal) and `foto.` (immich) with the same
> pattern. SSH to the VPS: `ssh root@88.222.220.64`. Find the Caddyfile the way
> the existing blocks are configured (inspect the running Caddy config /
> `/opt/docker/.../Caddyfile`).

### Task 3.1: Add the `erp.` site block

**Files:** the VPS Caddyfile (location per existing `sign.`/`foto.` blocks)

- [ ] **Step 1: Confirm DNS already resolves**

Run anywhere: `dig +short erp.aldewereldconsultancy.nl`
Expected: `88.222.220.64`.

- [ ] **Step 2: Verify the VPS can reach the container over Tailscale**

Run on the VPS: `curl -fsS http://192.168.178.218:8080/api/method/ping`
Expected: `{"message":"pong"}` (subnet route works VPS→container).

- [ ] **Step 3: Add the Caddy site block**

Add to the VPS Caddyfile (mirror the `sign.` block's header set):

```caddy
erp.aldewereldconsultancy.nl {
    encode zstd gzip

    header {
        Strict-Transport-Security "max-age=63072000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        -Server
    }

    reverse_proxy 192.168.178.218:8080 {
        header_up X-Forwarded-Proto https
        header_up X-Forwarded-Host {host}
    }
}
```

> Deliberately no strict CSP / X-Frame-Options here — they break the ERPNext
> desk (the repo's nginx.conf set a CSP for a different topology; do not copy it
> into Caddy).

- [ ] **Step 4: Reload Caddy**

Run on the VPS: reload Caddy the way the other blocks are managed (e.g. `docker exec <caddy> caddy reload --config /etc/caddy/Caddyfile` or `caddy reload`). Then:
`curl -fsS -o /dev/null -w "%{http_code}\n" https://erp.aldewereldconsultancy.nl/api/method/ping`
Expected: `200` over valid TLS (Caddy auto-issues the certificate on first hit).

- [ ] **Step 5: Tell Frappe its public host**

Run on `pro`:
```bash
pct exec 218 -- bash -lc 'cd /opt/nixfact/deployment/docker && \
  docker compose exec -T nixfact bench --site erp.aldewereldconsultancy.nl set-config host_name "https://erp.aldewereldconsultancy.nl"'
```
Expected: config set; reloading `https://erp.aldewereldconsultancy.nl/app` shows the ERPNext login.

---

## Phase 4 — Authentik OIDC SSO

> Reuse the same Authentik that already fronts the VPS Nextcloud installs. Two
> sides: create the provider in Authentik, then register it as a Social Login
> Key in Frappe.

### Task 4.1: Create the Authentik OIDC provider, application, and group

**Files:** none (Authentik state)

- [ ] **Step 1: Create an access group**

In Authentik admin → Directory → Groups → create `erp-users`; add your user.

- [ ] **Step 2: Create an OAuth2/OIDC Provider**

Authentik → Applications → Providers → Create → OAuth2/OpenID Provider:
- Name: `ERPNext`
- Authorization flow: implicit/explicit consent (match your Nextcloud setup)
- Client type: Confidential
- Redirect URIs: `https://erp.aldewereldconsultancy.nl/api/method/frappe.integrations.oauth2_logins.custom/authentik`
- Signing key: your default; record the generated **Client ID** and **Client Secret**.

- [ ] **Step 3: Create the Application and bind the group**

Authentik → Applications → Create:
- Name `ERPNext`, slug `erpnext`, provider `ERPNext`.
- Bind a policy/group binding so only `erp-users` may access.

- [ ] **Step 4: Note the OIDC endpoints**

From the provider's metadata (`https://auth.aldewereldconsultancy.nl/application/o/erpnext/.well-known/openid-configuration`) record `authorization_endpoint`, `token_endpoint`, `userinfo_endpoint`. Store Client ID/Secret in `/root/.secrets/nixfact.env` on `pro`.

### Task 4.2: Register Authentik as a Social Login Key in Frappe

**Files:** none (Frappe data)

- [ ] **Step 1: Create the Social Login Key**

In the ERPNext desk (logged in as Administrator) → search "Social Login Key" → New:
- Enable Social Login: yes
- Provider Name: `Authentik`
- Client ID / Client Secret: from Task 4.1
- Base URL: `https://auth.aldewereldconsultancy.nl`
- Authorize URL / Access Token URL / Redirect URL / API Endpoint (userinfo): from the well-known metadata
- Auth URL Data: `{"response_type": "code", "scope": "openid email profile"}`

- [ ] **Step 2: Verify the login button and flow**

Open an incognito window → `https://erp.aldewereldconsultancy.nl/login`.
Expected: a "Login with Authentik" button; clicking it bounces to Authentik, and after auth lands back logged in as your user (auto-created/matched by email).

- [ ] **Step 3: Lock down local signup**

Desk → "Website Settings" / "System Settings": disable signup; keep `Administrator` for break-glass.
Expected: only Authentik users in `erp-users` (plus Administrator) can get in.

---

## Phase 5 — Backups via existing borgmatic

> Pattern mirrors DocuSeal: write backup artifacts to the HDD bind-mount, then
> have LXC 200's borgmatic pull them into the encrypted repo.

### Task 5.1: Nightly `bench backup` into the bind-mount

**Files:** none (container state)

- [ ] **Step 1: Add a cron inside the LXC**

Run on `pro` — create `/etc/cron.d/nixfact-backup` inside container 218:
```bash
pct exec 218 -- bash -lc 'cat >/etc/cron.d/nixfact-backup <<"CRON"
# Nightly Frappe backup (DB + files) into the HDD bind-mount for borgmatic pickup
30 2 * * * root cd /opt/nixfact/deployment/docker && /usr/bin/docker compose exec -T nixfact bench --site erp.aldewereldconsultancy.nl backup --with-files >/var/log/nixfact-backup.log 2>&1 && cp -f /var/lib/docker/volumes/docker_sites_data/_data/erp.aldewereldconsultancy.nl/private/backups/* /mnt/nixfact/backups/ 2>>/var/log/nixfact-backup.log
CRON
systemctl restart cron 2>/dev/null || service cron restart'
```
> Note: the volume path `docker_sites_data` depends on the compose project name;
> confirm with `pct exec 218 -- docker volume ls`. Simpler robust alternative —
> bind-mount the host backup dir straight into the web container by adding
> `- /mnt/nixfact/backups:/home/frappe/frappe-bench/sites/erp.aldewereldconsultancy.nl/private/backups` won't work (overlays the site dir), so prefer copying out as above, or run the repo's `deployment/scripts/backup.sh` with `NIXFACT_BACKUP_ENCRYPTION=none` writing to `/mnt/nixfact/backups`.

- [ ] **Step 2: Run the backup once manually and verify an artifact lands**

Run on `pro`:
```bash
pct exec 218 -- bash -lc 'cd /opt/nixfact/deployment/docker && docker compose exec -T nixfact bench --site erp.aldewereldconsultancy.nl backup --with-files'
pct exec 218 -- ls -la /mnt/nixfact/backups/
```
Expected: a `*-database.sql.gz` (and files tar) present under `/mnt/nixfact/backups/` (copy step may need the volume-path fix from Step 1's note).

### Task 5.2: Add the path to LXC 200's borgmatic

**Files:** LXC 200 borgmatic config + its bind-mounts (per `/root/CLAUDE.md`)

- [ ] **Step 1: Bind-mount the backup dir read-only into LXC 200**

Run on `pro` (mirror the docuseal read-only bind on LXC 200):
```bash
pct set 200 --mp1 /mnt/pve/wd1tb/nixfact/backups,mp=/mnt/nixfact-backups,ro=1
pct config 200 | grep nixfact
```
Expected: `mp1: .../nixfact/backups,mp=/mnt/nixfact-backups,ro=1`. (Use the next free `mpN` index on 200.)

- [ ] **Step 2: Add to borgmatic source_directories**

Edit LXC 200's borgmatic config (the file driving `/root/backup-pull.sh`) and add `/mnt/nixfact-backups` to `source_directories`.

- [ ] **Step 3: Verify it appears in the next archive**

Run on `pro`:
```bash
pct exec 200 -- bash -lc "BORG_PASSCOMMAND='cat /root/.borg/passphrase' borgmatic create --verbosity 1"
pct exec 200 -- bash -lc "BORG_PASSCOMMAND='cat /root/.borg/passphrase' borg list /mnt/backups/vps-borg-repo --last 1"
```
Expected: a fresh archive that includes `mnt/nixfact-backups/`.

---

## Phase 6 — Acceptance, hardening, and known limitations

### Task 6.1: Run the acceptance checklist

**Files:** none

- [ ] **Step 1: TLS + desk**

`curl -fsS -o /dev/null -w "%{http_code}\n" https://erp.aldewereldconsultancy.nl/app` → `200`/`302` over valid TLS.

- [ ] **Step 2: OIDC single-login** — incognito login via Authentik works in one step; non-`erp-users` users are rejected; Administrator break-glass works.

- [ ] **Step 3: NixFact present** — desk search finds "NixFact Instellingen"; `docker compose exec nixfact bench --site erp.aldewereldconsultancy.nl list-apps` shows `nixfact_integration`.

- [ ] **Step 4: Scheduler + workers** — `pct exec 218 -- bash -lc 'cd /opt/nixfact/deployment/docker && docker compose exec -T nixfact bench --site erp.aldewereldconsultancy.nl doctor'` reports scheduler active and workers consuming queues.

- [ ] **Step 5: Reboot survival** — `pct reboot 218`; after boot, `curl https://erp.aldewereldconsultancy.nl/api/method/ping` → `pong` (restart policies + `onboot` bring the stack back).

- [ ] **Step 6: Backup artifact** — confirm `/mnt/nixfact/backups/` has a dated artifact and the borgmatic archive contains it (Phase 5).

### Task 6.2: Record known limitations and follow-ups

**Files:**
- Modify: `docs/superpowers/specs/2026-06-02-nixfact-production-deployment-design.md` (append a "Post-deploy notes" section)

- [ ] **Step 1: Document the socketio gap**

The compose has no socketio/node service, so **Frappe realtime (live notifications, progress bars, list auto-refresh) does not work**. The desk is fully usable without it. Follow-up (out of this plan's scope): add a `socketio` service (requires node in the runtime image) + a Caddy `/socket.io` websocket route. Record this explicitly so it is not mistaken for "everything works."

- [ ] **Step 2: Record the assets result** from Task 0.6 Step 6 (served by gunicorn, or needs an nginx/whitenoise sidecar).

- [ ] **Step 3: Credential hygiene** — confirm the plaintext Proxmox/VPS passwords shared during planning have been rotated and SSH-key auth is in use; confirm `/opt/nixfact/deployment/docker/.env` is `chmod 600` and not committed.

- [ ] **Step 4: Commit the notes**

```bash
git add docs/superpowers/specs/2026-06-02-nixfact-production-deployment-design.md
git commit -m "[docs] Post-deploy notes: socketio/assets limitations + follow-ups"
```

---

## Self-review notes (for the author, not a task)

- **Spec coverage:** placement/substrate → Phase 1; docker-compose stack → Phase 0/2; public access via Caddy → Phase 3; Authentik OIDC → Phase 4; borgmatic backups → Phase 5; acceptance criteria → Phase 6; the three spec "open items" (site-init, ERPNext version, port bind) → resolved in Phase 0 (init.sh + confirmed `version-17` in the Dockerfile + `BIND_HOST`).
- **Scope:** still sub-project A only; B/C/D untouched.
- **Known deviation from pure TDD:** this is an ops deployment, so "tests" are verification curls/checks with expected output rather than unit tests — appropriate for the domain.
