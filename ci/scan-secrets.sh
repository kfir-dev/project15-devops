#!/bin/bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "$script_dir/images.env"

if [[ ! "${GITLEAKS_IMAGE:-}" =~ ^ghcr\.io/gitleaks/gitleaks@sha256:[a-f0-9]{64}$ ]]; then
    printf 'STOP: a digest-pinned GitLeaks image is required.\n' >&2
    exit 1
fi

if [[ "$#" -ne 2 ]]; then
    printf 'STOP: exactly two repository paths are required.\n' >&2
    exit 1
fi

for repository in "$@"; do
    repository="$(realpath -e -- "$repository")"
    if [[ "$(git -C "$repository" rev-parse --is-shallow-repository)" != "false" ]]; then
        printf 'STOP: full Git history is required.\n' >&2
        exit 1
    fi

    printf 'Scanning Git history: %s\n' "$(basename -- "$repository")"
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        --env HOME=/tmp \
        --volume "$repository:/repo:ro" \
        --workdir /repo \
        "$GITLEAKS_IMAGE" \
        --redact --no-banner git --log-opts='--all' /repo
done

printf 'PASS: both repository histories passed GitLeaks.\n'
