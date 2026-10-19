#!/bin/bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/images.env"

if [[ ! "${GRYPE_IMAGE:-}" =~ ^(docker\.io/)?anchore/grype@sha256:[a-f0-9]{64}$ ]]; then
    printf 'STOP: a digest-pinned Grype image is required.\n' >&2
    exit 1
fi

if [[ "$#" -ne 1 ]]; then
    printf 'Usage: scan-sbom.sh REPORT_DIRECTORY\n' >&2
    exit 1
fi

report_dir="$(realpath -e -- "$1")"
if [[ ! -s "$report_dir/sbom.json" ]]; then
    printf 'STOP: sbom.json is missing or empty.\n' >&2
    exit 1
fi

cache_dir="$HOME/.cache/project15-grype"
mkdir -p -- "$cache_dir"
rm -f -- "$report_dir/grype-report.json"

scan_status=0
docker run --rm \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --env GRYPE_DB_CACHE_DIR=/cache \
    --env GRYPE_CHECK_FOR_APP_UPDATE=false \
    --tmpfs /tmp:rw,nosuid,nodev,noexec,mode=1777,size=512m \
    --workdir /tmp \
    --volume "$report_dir/sbom.json:/input/sbom.json:ro" \
    --volume "$report_dir:/reports" \
    --volume "$cache_dir:/cache" \
    "$GRYPE_IMAGE" sbom:/input/sbom.json \
    --output json \
    --file /reports/grype-report.json \
    --fail-on critical || scan_status=$?

if [[ ! -s "$report_dir/grype-report.json" ]]; then
    printf 'STOP: Grype did not produce a report.\n' >&2
    exit 1
fi

python3 - "$report_dir/grype-report.json" <<'VERIFY_GRYPE'
from collections import Counter
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text())
if not isinstance(data.get("matches"), list):
    raise SystemExit("STOP: unexpected Grype report structure.")

counts = Counter(
    item["vulnerability"]["severity"].upper()
    for item in data["matches"]
)
for severity in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "NEGLIGIBLE", "UNKNOWN"):
    print(severity + ": " + str(counts[severity]))
print("PASS: Grype JSON report saved and parsed.")
VERIFY_GRYPE

if [[ "$scan_status" -ne 0 ]]; then
    printf 'Grype failed or the CRITICAL gate blocked the scan; exit=%s.\n' "$scan_status" >&2
    exit "$scan_status"
fi

printf 'PASS: Grype CRITICAL gate passed.\n'
