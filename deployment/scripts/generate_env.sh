#!/usr/bin/env bash
# Generate a populated .env from .env.example by replacing every
# __GENERATE_ME__ sentinel with a fresh random secret.
#
# Usage:    ./generate_env.sh > .env
#           chmod 600 .env

set -euo pipefail
umask 077

EXAMPLE="${1:-deployment/docker/.env.example}"

if [[ ! -f "${EXAMPLE}" ]]; then
    echo "Cannot read ${EXAMPLE}" >&2
    exit 1
fi

while IFS= read -r line; do
    if [[ "${line}" == *"__GENERATE_ME__"* ]]; then
        secret="$(openssl rand -base64 32 | tr -d '\n=' | tr '/+' '_-')"
        line="${line//__GENERATE_ME__/${secret}}"
    fi
    printf '%s\n' "${line}"
done < "${EXAMPLE}"
