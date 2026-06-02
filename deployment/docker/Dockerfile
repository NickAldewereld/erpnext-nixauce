# NixFact Dockerfile — multi-stage, hardened.
#
# Production image runs gunicorn directly. Workers and the scheduler use
# the same image with a different CMD (configured in docker-compose.yml).
# `bench start` (Frappe's dev orchestrator that spawns honcho + internal
# redis instances) is intentionally NOT used here — it conflicts with the
# external redis services and breaks session/queue state in production.

ARG PYTHON_IMAGE=python:3.11-slim-bookworm
ARG FRAPPE_BRANCH=version-17
ARG ERPNEXT_BRANCH=version-17
ARG NODE_MAJOR=20

# --------------------------------------------------------------------------
# Stage 1: builder — compiles wheels, fetches Frappe + ERPNext, builds assets.
# --------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

ARG FRAPPE_BRANCH
ARG ERPNEXT_BRANCH
ARG NODE_MAJOR

ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl gnupg \
       git build-essential \
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

RUN bench get-app erpnext --branch ${ERPNEXT_BRANCH}

COPY --chown=frappe:frappe ./nixfact_integration apps/nixfact_integration

RUN bench setup requirements \
    && bench build --app nixfact_integration

# --------------------------------------------------------------------------
# Stage 2: runtime — only what's needed to actually serve traffic.
# --------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/home/frappe/.local/bin:${PATH}" \
    DEBIAN_FRONTEND=noninteractive

# wkhtmltopdf is discontinued upstream and has known CVEs; track Frappe v17
# PDF strategy (chromium / weasyprint) and remove this once available.
# For now we keep a known build, locked to the trixie repo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       libmariadb3 mariadb-client \
       libssl3 libffi8 \
       wkhtmltopdf xvfb \
       redis-tools \
       curl \
       tini \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -ms /bin/bash frappe
USER frappe
WORKDIR /home/frappe

COPY --chown=frappe:frappe --from=builder /home/frappe/.local /home/frappe/.local
COPY --chown=frappe:frappe --from=builder /home/frappe/frappe-bench /home/frappe/frappe-bench

WORKDIR /home/frappe/frappe-bench

COPY --chown=frappe:frappe deployment/docker/entrypoint.sh /entrypoint.sh
COPY --chown=frappe:frappe deployment/docker/init.sh /init.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/method/ping || exit 1

# Use tini as PID 1 for proper signal handling; entrypoint.sh wires
# DB/Redis env into common_site_config.json before exec'ing the CMD.
ENTRYPOINT ["/usr/bin/tini", "--", "/entrypoint.sh"]

# Default CMD = production web. Compose overrides this for worker / scheduler.
CMD ["bash", "-lc", "exec gunicorn --bind 0.0.0.0:8000 --workers 4 --worker-class gthread --threads 4 --timeout 120 --preload frappe.app:application"]
