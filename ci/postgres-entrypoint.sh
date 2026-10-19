#!/bin/bash
set -eu
POSTGRES_PASSWORD="$(cat /run/secrets/sonar_db_password)"
export POSTGRES_PASSWORD
exec /usr/local/bin/docker-entrypoint.sh "$@"
