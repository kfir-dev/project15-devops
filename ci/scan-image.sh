#!/bin/bash
set -euo pipefail
umask 077

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/images.env"

if [[ ! "${TRIVY_IMAGE:-}" =~ ^(docker\.io/)?aquasec/trivy@sha256:[a-f0-9]{64}$ ]]; then
    printf 'STOP: a digest-pinned Trivy image is required.\n' >&2
    exit 1
fi

if [[ "$#" -ne 2 ]]; then
    printf 'Usage: scan-image.sh IMAGE REPORT_DIRECTORY\n' >&2
    exit 1
fi

image="$1"
mkdir -p -- "$2"
report_dir="$(realpath -e -- "$2")"
cache_dir="$HOME/.cache/project15-trivy"
mkdir -p -- "$cache_dir"
temporary="$(mktemp -d)"

cleanup() {
    rm -f -- "$temporary/image.tar"
    rmdir -- "$temporary"
}
trap cleanup EXIT

docker image save --output "$temporary/image.tar" "$image"
rm -f -- "$report_dir/scan-report.json"

trivy() {
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        --env HOME=/tmp \
        --workdir /tmp \
        --volume "$temporary/image.tar:/image.tar:ro" \
        --volume "$report_dir:/reports" \
        --volume "$cache_dir:/cache" \
        "$TRIVY_IMAGE" image \
        --input /image.tar \
        --cache-dir /cache \
        --scanners vuln \
        --ignorefile /dev/null \
        --ignore-unfixed=false \
        --timeout 10m \
        --no-progress \
        "$@"
}

trivy --severity HIGH,CRITICAL --format json \
    --output /reports/scan-report.json --exit-code 0

printf 'Vulnerability report saved. Checking CRITICAL gate.\n'
trivy --severity CRITICAL --format table --exit-code 1

printf 'PASS: no CRITICAL vulnerabilities found.\n'
