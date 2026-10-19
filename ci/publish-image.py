import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

os.umask(0o077)

if len(sys.argv) != 5:
    raise SystemExit("Usage: publish-image.py IMAGE REPORT_DIRECTORY COMMIT BUILD")

image, directory, commit, build = sys.argv[1:]
if not re.fullmatch(r"[a-f0-9]{40}", commit) or not build.isdigit():
    raise SystemExit("STOP: invalid commit or build number.")

reports = Path(directory).resolve(strict=True)
trivy = json.loads((reports / "scan-report.json").read_text())
grype = json.loads((reports / "grype-report.json").read_text())
sbom = json.loads((reports / "sbom.json").read_text())

if not trivy.get("Results") or not isinstance(grype.get("matches"), list):
    raise SystemExit("STOP: required vulnerability reports are incomplete.")
if sbom.get("bomFormat") != "CycloneDX" or not sbom.get("components"):
    raise SystemExit("STOP: valid SBOM required.")

trivy_critical = any(
    item.get("Severity", "").upper() == "CRITICAL"
    for section in trivy["Results"]
    for item in (section.get("Vulnerabilities") or [])
)
grype_critical = any(
    item["vulnerability"]["severity"].upper() == "CRITICAL"
    for item in grype["matches"]
)
if trivy_critical or grype_critical:
    raise SystemExit("STOP: CRITICAL findings block publication.")

username = os.environ.get("GHCR_USERNAME")
token = os.environ.pop("GHCR_TOKEN", None)
if username != "kfir-dev" or not token:
    raise SystemExit("STOP: required GHCR credentials are unavailable.")

def run(arguments, action, *, input_text=None, timeout=60, environment=None):
    try:
        result = subprocess.run(
            arguments, input=input_text, capture_output=True,
            text=True, timeout=timeout, env=environment
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(f"STOP: {action} timed out; raw output withheld.")
    if result.returncode:
        raise SystemExit(
            f"STOP: {action} failed; exit={result.returncode}; raw output withheld."
        )
    return result.stdout

metadata = json.loads(run(
    ["docker", "image", "inspect", image], "local image inspection"
))[0]
labels = metadata.get("Config", {}).get("Labels") or {}
if labels.get("org.opencontainers.image.revision") != commit:
    raise SystemExit("STOP: image revision label does not match source commit.")
if labels.get("org.opencontainers.image.source") != "https://github.com/kfir-dev/project15-app":
    raise SystemExit("STOP: image source label is missing or unexpected.")

repository = "ghcr.io/kfir-dev/project15-app"
remote_tag = f"{repository}:sha-{commit}-build-{build}"

with tempfile.TemporaryDirectory(prefix="project15-ghcr-") as temporary:
    environment = os.environ.copy()
    environment["DOCKER_CONFIG"] = temporary
    run(
        ["docker", "login", "ghcr.io", "--username", username, "--password-stdin"],
        "GHCR authentication", input_text=token + "\n", environment=environment
    )
    token = None
    print("PASS: GHCR authentication completed.", flush=True)

    run(["docker", "tag", image, remote_tag], "image tagging", environment=environment)
    print("Publishing the checked image to GHCR...", flush=True)
    run(
        ["docker", "push", remote_tag], "image publication",
        timeout=600, environment=environment
    )
    published = json.loads(run(
        ["docker", "image", "inspect", remote_tag],
        "published image inspection", environment=environment
    ))[0]

    if published["Id"] != metadata["Id"]:
        raise SystemExit("STOP: local image identity changed during publication.")

    references = [
        value for value in (published.get("RepoDigests") or [])
        if re.fullmatch(re.escape(repository) + r"@sha256:[a-f0-9]{64}", value)
    ]
    if len(set(references)) != 1:
        raise SystemExit("STOP: could not identify one published digest.")
    reference = references[0]

(reports / "image-reference.txt").write_text(reference + "\n")
(reports / "image-publication.json").write_text(json.dumps({
    "source_commit": commit,
    "build": build,
    "tag": remote_tag,
    "image_reference": reference,
    "local_image_id": metadata["Id"],
}, indent=2) + "\n")

print("PASS: image published; digest and source metadata saved.")
print("Temporary Docker credentials removed.")
