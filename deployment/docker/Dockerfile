FROM python:3.11-slim-bookworm

ARG FRAPPE_VERSION=version-17
ARG ERPNEXT_VERSION=version-17
ARG NODE_VERSION=18

ENV PYTHONUNBUFFERED=1 \
    FRAPPE_BRANCH=${FRAPPE_VERSION} \
    ERPNEXT_BRANCH=${ERPNEXT_VERSION}

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget build-essential \
    libmariadb-dev mariadb-client \
    libffi-dev libssl-dev \
    wkhtmltopdf xvfb \
    redis-tools \
    && rm -rf /var/lib/apt/lists/*

# Node.js
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y nodejs \
    && npm install -g yarn

# Create frappe user
RUN useradd -ms /bin/bash frappe
USER frappe
WORKDIR /home/frappe

# Install bench
RUN pip install --no-cache-dir frappe-bench

# Initialize bench
RUN bench init frappe-bench \
    --frappe-branch ${FRAPPE_BRANCH} \
    --skip-redis-config-generation \
    --no-procfile \
    --no-backups

WORKDIR /home/frappe/frappe-bench

# Install ERPNext
RUN bench get-app erpnext --branch ${ERPNEXT_BRANCH}

# Install NIXFact
COPY --chown=frappe:frappe ./nixfact_integration apps/nixfact_integration
RUN bench setup requirements --dev \
    && bench build --app nixfact_integration

EXPOSE 8000 9000

CMD ["bench", "start"]
