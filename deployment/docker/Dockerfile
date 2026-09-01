# NixFact Dockerfile — multi-stage, hardened.
#
# Production image runs gunicorn directly. Workers and the scheduler use
# the same image with a different CMD (configured in docker-compose.yml).
# `bench start` (Frappe's dev orchestrator that spawns honcho + internal
# redis instances) is intentionally NOT used here — it conflicts with the
# external redis services and breaks session/queue state in production.

# Frappe's develop line (frappe 17.0.0.dev0) pins Python >=3.14,<3.15.
ARG PYTHON_IMAGE=python:3.14-slim-bookworm
# Frappe 17 has no cut `version-17` branch yet; the v17 dev line lives on
# `develop` upstream (latest released branch is version-16). nixfact_integration
# requires frappe >=17.0.0-dev, so we track `develop`. Pin to a tag/commit once
# version-17 is cut. Override at build time with --build-arg if needed.
ARG FRAPPE_BRANCH=develop
ARG ERPNEXT_BRANCH=develop
# Frappe CRM — the SPA served at /crm, on this same site and database, so it
# shares Customer/Contact/Lead with ERPNext instead of duplicating them.
# Upstream's own installer targets `main` against frappe version-15; on the v17
# dev line only `develop` tracks along, so it follows the same rule as above.
ARG CRM_BRANCH=develop
# A branch name is not a version. Tracking `develop` by name means every rebuild
# silently picks up whatever upstream happened to push, so an image can neither
# be reproduced nor rolled back — on an unreleased line that is a live hazard,
# not a theoretical one. bench only understands branches, so we clone the branch
# and then check out these exact commits. Bump them deliberately; never drift.
ARG FRAPPE_REF=6e3d89f7ffc3e986995c5604064101b75bf4c034
ARG ERPNEXT_REF=ac68db3fa6cdfcaa900a856568d977e8e1de2356
ARG CRM_REF=66165cb1dae46bd02f5899baeb30f05df7b6098e
# Frappe develop requires Node >=24.
ARG NODE_MAJOR=24

# --------------------------------------------------------------------------
# Stage 1: builder — compiles wheels, fetches Frappe + ERPNext, builds assets.
# --------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

ARG FRAPPE_BRANCH
ARG ERPNEXT_BRANCH
ARG CRM_BRANCH
ARG FRAPPE_REF
ARG ERPNEXT_REF
ARG CRM_REF
ARG NODE_MAJOR

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl gnupg \
       git build-essential pkg-config \
       libmariadb-dev mariadb-client \
       libffi-dev libssl-dev libpq-dev \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
       | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
       > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g yarn \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash frappe
USER frappe
WORKDIR /home/frappe

RUN pip install --no-cache-dir --user frappe-bench

ENV PATH="/home/frappe/.local/bin:${PATH}"

RUN bench init frappe-bench \
    --frappe-branch ${FRAPPE_BRANCH} \
    --skip-redis-config-generation \
    --no-procfile \
    --no-backups

WORKDIR /home/frappe/frappe-bench

# Pin to the exact commits. bench clones shallow and names the remote
# `upstream`, so fetch the bare SHA (GitHub serves these) rather than
# unshallowing the entire history just to reach one commit.
# `bench init` ran yarn install against develop HEAD, so node_modules belongs to
# whatever upstream pushed today — not to FRAPPE_REF. The pin covered the code
# and left the dependencies drifting, which surfaces as a missing esbuild plugin
# the moment the build cache no longer hides it. Re-resolve against the pinned
# package.json so code and node_modules describe the same commit.
RUN cd apps/frappe \
    && git fetch --depth=1 upstream ${FRAPPE_REF} \
    && git checkout --detach FETCH_HEAD \
    && yarn install

RUN bench get-app erpnext --branch ${ERPNEXT_BRANCH}

RUN cd apps/erpnext \
    && git fetch --depth=1 upstream ${ERPNEXT_REF} \
    && git checkout --detach FETCH_HEAD \
    && yarn install

# get-app also runs yarn install + the asset build for the app's Vue frontend.
# Node's default heap is too small for that inside this container's memory
# budget, hence the explicit bump.
ENV NODE_OPTIONS=--max-old-space-size=3072

RUN bench get-app crm --branch ${CRM_BRANCH}

RUN cd apps/crm \
    && git fetch --depth=1 upstream ${CRM_REF} \
    && git checkout --detach FETCH_HEAD

COPY --chown=frappe:frappe ./nixfact_integration apps/nixfact_integration

# bench treats every dir under apps/ as a git repo (git.Repo(app_path)); the
# COPY above is plain files, so `bench setup requirements` raises
# InvalidGitRepositoryError. Init a throwaway repo so bench's app tooling
# accepts it, and register it in apps.txt for requirements/build/install.
RUN cd apps/nixfact_integration \
    && git init -q \
    && git add -A \
    && git -c user.email=build@nixfact.local -c user.name=build \
       commit -qm "vendored nixfact_integration" \
    && cd /home/frappe/frappe-bench \
    && (grep -qxF nixfact_integration sites/apps.txt 2>/dev/null \
        || echo nixfact_integration >> sites/apps.txt)

# Build assets AFTER every app sits on its pinned commit. get-app builds them
# at branch HEAD, which for a pinned app is the wrong tree; rebuilding here is
# what makes the pins mean anything for the shipped bundles.
RUN bench setup requirements \
    && bench build --app erpnext \
    && bench build --app nixfact_integration \
    && bench build --app crm

# --------------------------------------------------------------------------
# Stage 2: runtime — only what's needed to actually serve traffic.
# --------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/home/frappe/.local/bin:/home/frappe/frappe-bench/env/bin:${PATH}" \
    DEBIAN_FRONTEND=noninteractive

# wkhtmltopdf is discontinued upstream and has known CVEs; track Frappe v17
# PDF strategy (chromium / weasyprint) and remove this once available.
# For now we keep a known build, locked to the trixie repo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       git \
       libmariadb3 mariadb-client \
       libssl3 libffi8 \
       wkhtmltopdf xvfb \
       redis-tools \
       curl \
       tini \
       age \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash frappe

# node-runtime voor de socketio-service (realtime, o.a. Frappe CRM). De
# node_modules (socket.io e.a.) komen al mee via de bench-copy hieronder;
# alleen het binary zelf bleef in de builder-stage hangen.
COPY --from=builder /usr/bin/node /usr/bin/node

USER frappe
WORKDIR /home/frappe

COPY --chown=frappe:frappe --from=builder /home/frappe/.local /home/frappe/.local
COPY --chown=frappe:frappe --from=builder /home/frappe/frappe-bench /home/frappe/frappe-bench

# Stash the built assets OUTSIDE the sites/ volume mount. At runtime the
# sites_data volume shadows sites/assets, so without a re-sync the volume can
# drift from the app baked into this image (stale asset manifest -> bundle 404s
# -> unstyled site). entrypoint.sh mirrors this stash into the volume each boot.
RUN cp -a /home/frappe/frappe-bench/sites/assets /home/frappe/frappe-bench/assets-image

WORKDIR /home/frappe/frappe-bench

COPY --chown=frappe:frappe deployment/docker/entrypoint.sh /entrypoint.sh
COPY --chown=frappe:frappe deployment/docker/init.sh /init.sh
# WSGI wrapper that adds Frappe's /assets + /files static middleware (no nginx
# sidecar in this stack). Lives in the bench root so gunicorn --pythonpath finds
# it; it can't go under sites/ (that path is a mounted volume at runtime).
COPY --chown=frappe:frappe deployment/docker/nixfact_wsgi.py /home/frappe/frappe-bench/nixfact_wsgi.py
COPY --chown=frappe:frappe deployment/docker/healthcheck-worker.sh /healthcheck-worker.sh
# The backup runs where bench lives: inside this image, invoked from the host's
# systemd timer via `docker compose exec`. age is installed above so the archive
# is encrypted before it ever touches the host's disk.
COPY --chown=frappe:frappe deployment/scripts/backup.sh /backup.sh

EXPOSE 8000

# NO HEALTHCHECK here on purpose. This image serves three roles (web, worker,
# scheduler) and a baked-in probe applies to all of them, so any check written
# for one lies about the other two. It used to curl 127.0.0.1:8000 — correct for
# web, meaningless for worker and scheduler, which never listen on a port and
# consequently sat "unhealthy" forever while working fine. Each role declares
# its own check in docker-compose.yml, next to the CMD that defines that role.

# Use tini as PID 1 for proper signal handling; entrypoint.sh wires
# DB/Redis env into common_site_config.json before exec'ing the CMD.
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]

# Default CMD = production web. Compose overrides this for worker / scheduler.
# Use `bash -c` (NOT `-lc`): a login shell re-sources /etc/profile and resets
# PATH to the system default, dropping the bench venv so `gunicorn` isn't found.
# NO --preload: importing frappe.app in the gunicorn master (no site bound)
# leaves frappe.local in a state the forked workers don't re-init per request,
# so every request 404s "<site> does not exist". 2 workers fits the ~1.5g limit.
CMD ["bash", "-c", "exec gunicorn --bind 0.0.0.0:8000 --workers 2 --worker-class gthread --threads 4 --timeout 120 --pythonpath /home/frappe/frappe-bench nixfact_wsgi:application"]
