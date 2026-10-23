#!/bin/bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/images.env"

if [[ ! "${SYFT_IMAGE:-}" =~ ^(docker\.io/)?anchore/syft@sha256:[a-f0-9]{64}$ ]]; then
    printf 'STOP: a digest-pinned Syft image is required.\n' >&2
    exit 1
fi

if [[ "$#" -ne 2 ]]; then
    printf 'Usage: generate-sbom.sh IMAGE REPORT_DIRECTORY\n' >&2
    exit 1
fi

image="$1"
mkdir -p -- "$2"
report_dir="$(realpath -e -- "$2")"
temporary="$(mktemp -d)"
image_id="$(docker image inspect --format '{{.Id}}' "$image")"

cleanup() {
    rm -f -- "$temporary/image.tar"
    rm -f -- "$report_dir/sbom.syft.json"
    rmdir -- "$temporary"
}
trap cleanup EXIT

docker image save --output "$temporary/image.tar" "$image"
rm -f -- "$report_dir/sbom.json" "$report_dir/sbom-binding.json" "$report_dir/sbom.syft.json"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    --env HOME=/tmp \
    --env SYFT_CHECK_FOR_APP_UPDATE=false \
    --tmpfs /tmp:rw,nosuid,nodev,noexec,mode=1777,size=1g \
    --workdir /tmp \
    --volume "$temporary/image.tar:/image.tar:ro" \
    --volume "$report_dir:/reports" \
    "$SYFT_IMAGE" scan docker-archive:/image.tar \
    --output cyclonedx-json=/reports/sbom.json \
    --output syft-json=/reports/sbom.syft.json

if [[ "$(docker image inspect --format '{{.Id}}' "$image")" != "$image_id" ]]; then
    printf 'STOP: image changed during SBOM generation.\n' >&2
    exit 1
fi
python3 "$script_dir/bind-sbom.py" "$temporary/image.tar" \
    "$report_dir/sbom.syft.json" "$report_dir/sbom.json" "$image_id" \
    "$report_dir/sbom-binding.json"

python3 - "$report_dir/sbom.json" <<'VERIFY_SBOM'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text())
components = data.get("components", [])
if data.get("bomFormat") != "CycloneDX" or not components:
    raise SystemExit("STOP: missing or empty CycloneDX component inventory.")

names = {item.get("name", "").lower() for item in components}
if not {"flask", "gunicorn"}.issubset(names):
    raise SystemExit("STOP: expected application dependencies missing from SBOM.")

print("PASS: CycloneDX SBOM generated and parsed.")
print("Components:", len(components))
print("PASS: Flask and Gunicorn present.")
VERIFY_SBOM
