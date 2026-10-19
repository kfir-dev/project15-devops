import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

directory = Path(__file__).resolve().parent
repo = directory.parent
lock = json.loads((directory / "chart-lock.json").read_text())
archive = Path.home() / ".cache/project15-charts" / lock["archive"]

if hashlib.sha256(archive.read_bytes()).hexdigest() != lock["sha256"]:
    raise SystemExit("STOP: chart checksum differs.")

images = [
    line.split("=", 1)[1].strip()
    for line in (repo / "ci/images.env").read_text().splitlines()
    if line.startswith("CHECKOV_IMAGE=")
]
if len(images) != 1 or not re.fullmatch(
    r"(docker\.io/)?bridgecrew/checkov@sha256:[a-f0-9]{64}", images[0]
):
    raise SystemExit("STOP: pinned YAML inspection image missing.")

arguments = [
    "-f", str(directory / "values-local.json"),
    "--kube-version", "1.37.0",
]
lint = subprocess.run(
    ["helm", "lint", str(archive), *arguments],
    capture_output=True, text=True
)
if lint.returncode:
    raise SystemExit("STOP: Helm lint failed; raw output withheld.")
print("PASS: chart checksum and Helm lint verified.", flush=True)

render = subprocess.run(
    ["helm", "template", "project15-monitoring", str(archive),
     "--namespace", "monitoring", "--include-crds", *arguments],
    capture_output=True, text=True
)
if render.returncode:
    raise SystemExit("STOP: Helm rendering failed; raw output withheld.")

result = subprocess.run(
    ["docker", "run", "--rm", "-i", "--network", "none",
     "--user", f"{os.getuid()}:{os.getgid()}",
     "--env", "PYTHONDONTWRITEBYTECODE=1",
     "--volume", f"{directory / 'verify-render.py'}:/audit.py:ro",
     "--entrypoint", "python", images[0], "/audit.py"],
    input=render.stdout, capture_output=True, text=True
)
print(result.stdout.strip())
if result.returncode:
    raise SystemExit("STOP: monitoring render audit failed; raw stderr withheld.")
print("PASS: monitoring configuration audit completed.")
print("No secret values displayed; no cluster changes.")
