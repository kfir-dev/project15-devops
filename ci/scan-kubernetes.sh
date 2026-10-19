#!/bin/bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo="$(dirname -- "$script_dir")"
source "$script_dir/images.env"

if [[ ! "${CHECKOV_IMAGE:-}" =~ ^(docker\.io/)?bridgecrew/checkov@sha256:[a-f0-9]{64}$ ]]; then
    printf 'STOP: a digest-pinned Checkov image is required.\n' >&2
    exit 1
fi

if [[ "$#" -ne 1 ]]; then
    printf 'Usage: scan-kubernetes.sh REPORT_DIRECTORY\n' >&2
    exit 1
fi

mkdir -p -- "$1"
report_dir="$(realpath -e -- "$1")"
temporary="$(mktemp -d)"

cleanup() {
    rm -f -- "$temporary/manifests.yaml" "$temporary/helm.log"
    rmdir -- "$temporary"
}
trap cleanup EXIT

if ! helm lint "$repo/helm/project15" \
    -f "$repo/helm/project15/values-local.yaml" \
    --set-string database.password= \
    --set-string database.existingSecret=project15-database-external \
    > "$temporary/helm.log" 2>&1; then
    printf 'STOP: Helm lint failed; raw output withheld.\n' >&2
    exit 1
fi

if ! helm template project15 "$repo/helm/project15" \
    --namespace project15 \
    -f "$repo/helm/project15/values-local.yaml" \
    --set-string database.password= \
    --set-string database.existingSecret=project15-database-external \
    > "$temporary/manifests.yaml" 2> "$temporary/helm.log"; then
    printf 'STOP: Helm render failed; raw output withheld.\n' >&2
    exit 1
fi

if grep -Eq '^[[:space:]]*kind:[[:space:]]*Secret[[:space:]]*$' "$temporary/manifests.yaml"; then
    printf 'STOP: rendered Secret objects are not permitted in this scan.\n' >&2
    exit 1
fi

scan_status=0
docker run --rm \
    --user "$(id -u):$(id -g)" \
    --network none \
    --env HOME=/tmp \
    --tmpfs /tmp:rw,nosuid,nodev,mode=1777,size=512m \
    --workdir /tmp \
    --volume "$temporary/manifests.yaml:/scan/manifests.yaml:ro" \
    "$CHECKOV_IMAGE" \
    --file /scan/manifests.yaml \
    --framework kubernetes \
    --skip-download \
    --output json \
    > "$report_dir/checkov-report.json" \
    2> "$report_dir/checkov.log" || scan_status=$?

python3 - "$report_dir/checkov-report.json" <<'VERIFY_CHECKOV'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text())
reports = data if isinstance(data, list) else [data]
passed = failed = skipped = errors = 0
for report in reports:
    summary = report.get("summary", {})
    passed += summary.get("passed", 0)
    failed += summary.get("failed", 0)
    skipped += summary.get("skipped", 0)
    errors += summary.get("parsing_errors", 0)
    for check in report.get("results", {}).get("failed_checks", []):
        print("FAILED:", check.get("check_id"), "|", check.get("resource"))
print(f"Passed: {passed}; Failed: {failed}; Skipped: {skipped}; Parsing errors: {errors}")
if passed + failed == 0 or errors:
    raise SystemExit("STOP: empty scan or manifest parsing errors.")
skipped_checks = [
    (check.get("check_id"), check.get("resource"))
    for report in reports
    for check in report.get("results", {}).get("skipped_checks", [])
]
expected_skip = ("CKV_K8S_40", "Deployment.project15.project15-database")
if skipped_checks != [expected_skip] or skipped != 1:
    raise SystemExit("STOP: unexpected Checkov suppressions.")
if failed:
    raise SystemExit("STOP: Kubernetes checks failed; report retained.")
VERIFY_CHECKOV

if [[ "$scan_status" -ne 0 ]]; then
    printf 'STOP: Checkov returned exit=%s; report retained.\n' "$scan_status" >&2
    exit "$scan_status"
fi

printf 'PASS: Helm lint and Checkov Kubernetes gate passed.\n'
