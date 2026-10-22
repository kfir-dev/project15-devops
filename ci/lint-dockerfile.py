import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("application_directory")
    args = parser.parse_args()
    app = Path(args.application_directory).resolve()
    dockerfile = app / "Dockerfile"
    source = dockerfile.read_text()
    reports = app / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    report = reports / "hadolint.json"
    report.unlink(missing_ok=True)

    repo = Path(__file__).resolve().parents[1]
    images = [
        line.split("=", 1)[1].strip()
        for line in (repo / "ci/images.env").read_text().splitlines()
        if line.startswith("HADOLINT_IMAGE=")
    ]
    if len(images) != 1 or not re.fullmatch(
        r"hadolint/hadolint@sha256:[0-9a-f]{64}", images[0]
    ):
        raise RuntimeError("Pinned Hadolint image configuration invalid.")

    state = Path.home() / ".local/state/project15-hadolint"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, log = tempfile.mkstemp(prefix="lint-", suffix=".log", dir=state)
    name = "project15-hadolint-" + uuid.uuid4().hex[:12]
    command = [
        "docker", "run", "--rm", "-i", "--name", name,
        "--network", "none", "--read-only",
        "--user", f"{os.getuid()}:{os.getgid()}",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges:true",
        "--memory", "512m", "--cpus", "1",
        images[0], "hadolint", "--format", "json",
        "--failure-threshold", "warning", "--disable-ignore-pragma", "-",
    ]
    try:
        with os.fdopen(descriptor, "w") as stream:
            result = subprocess.run(
                command, input=source, stdout=subprocess.PIPE,
                stderr=stream, text=True, timeout=120,
            )
    finally:
        subprocess.run(
            ["docker", "rm", "-f", name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )

    print("Hadolint exit code:", result.returncode)
    print("Protected diagnostic log:", log)
    try:
        findings = json.loads(result.stdout)
    except ValueError:
        raise RuntimeError("Hadolint did not produce a valid JSON report.") from None
    if not isinstance(findings, list) or any(
        not isinstance(item, dict)
        or item.get("level") not in {"error", "warning", "info", "style"}
        or not isinstance(item.get("code"), str)
        for item in findings
    ):
        raise RuntimeError("Unexpected Hadolint report structure.")

    report.write_text(json.dumps(findings, indent=2) + "\n", encoding="utf-8")
    report.chmod(0o600)
    print("Hadolint findings:", len(findings))
    blocking = sum(item["level"] in {"error", "warning"} for item in findings)
    if result.returncode != 0 or blocking:
        raise RuntimeError("Hadolint gate failed; report retained.")
    print("PASS: Dockerfile lint gate passed; hadolint.json saved.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit("STOP: " + str(exc))
