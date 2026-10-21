#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:?Usage: scan-python-sca.sh APP_DIR}"
cd "$APP_DIR"
mkdir -p reports

.venv/bin/python -m pip install pip-audit==2.10.1
.venv/bin/python -m pip_audit --local --progress-spinner off --format json --output reports/pip-audit.json
