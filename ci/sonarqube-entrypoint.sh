#!/bin/bash
set -eu
SONAR_JDBC_PASSWORD="$(cat /run/secrets/sonar_db_password)"
export SONAR_JDBC_PASSWORD
exec /opt/sonarqube/docker/entrypoint.sh "$@"
