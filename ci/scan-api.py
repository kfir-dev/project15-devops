import argparse
from collections import Counter
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlsplit
import uuid

EXPECTED = {"/health/live", "/health/ready", "/api/products"}
REPORTS = ("zap-report.json", "zap-report.html", "zap-coverage.json")
REPO = Path(__file__).resolve().parents[1]

def require(condition, message):
    if not condition:
        raise RuntimeError(message)

def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=40)
    require(result.returncode == 0, "Preflight command failed; raw output withheld.")
    return result.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report_directory")
    args = parser.parse_args()
    require(os.getuid() != 0, "Run the scanner as the regular WSL agent user.")

    reports = Path(args.report_directory).expanduser().resolve()
    reports.mkdir(parents=True, exist_ok=True)
    for name in REPORTS + ("zap-summary.json",):
        require(not (reports / name).exists(), "Use a fresh report directory.")

    specification = REPO / "ci/zap/api-readonly.openapi.json"
    hook = REPO / "ci/zap/coverage-hook.py"
    spec = json.loads(specification.read_text())
    require(spec["servers"] == [{"url": "http://project15.local"}],
            "Unexpected scan server.")
    require(set(spec["paths"]) == EXPECTED, "Unexpected scan paths.")
    require(all(set(item) == {"get"} for item in spec["paths"].values()),
            "Scan definition must contain GET operations only.")
    require("$ref" not in specification.read_text(),
            "External or indirect API definitions require review.")
    require(hook.is_file(), "Coverage hook is missing.")

    pins = [
        line.split("=", 1)[1]
        for line in (REPO / "ci/images.env").read_text().splitlines()
        if line.startswith("ZAP_IMAGE=")
    ]
    require(len(pins) == 1, "Expected one ZAP image pin.")
    image = pins[0]
    require(re.fullmatch(r"ghcr\.io/zaproxy/zaproxy@sha256:[0-9a-f]{64}", image),
            "ZAP image must be digest-pinned.")
    inspected = json.loads(command(["docker", "image", "inspect", image]))[0]
    require(image in inspected.get("RepoDigests", []), "Local ZAP digest mismatch.")

    node = json.loads(command(["docker", "inspect", "minikube"]))[0]
    require(node["State"]["Running"], "Minikube container is not running.")
    network = node["NetworkSettings"]["Networks"].get("minikube")
    require(network is not None, "Minikube Docker network is missing.")
    address = str(ipaddress.IPv4Address(network["IPAddress"]))

    probe = "import json, sys\nfrom urllib.request import Request, ProxyHandler, build_opener\ntry:\n    opener = build_opener(ProxyHandler({}))\n    paths = json.loads(sys.argv[1])\n    for endpoint in paths:\n        request = Request('http://project15.local' + endpoint, method='GET')\n        with opener.open(request, timeout=10) as response:\n            if response.status != 200:\n                raise ValueError('Unexpected HTTP status.')\n            if 'application/json' not in response.headers.get('Content-Type', ''):\n                raise ValueError('Unexpected content type.')\n            if not isinstance(json.loads(response.read(2_000_000)), dict):\n                raise ValueError('Unexpected response shape.')\n    print(json.dumps({'ok': True, 'paths': paths}))\nexcept Exception as exc:\n    print(json.dumps({'ok': False, 'error': type(exc).__name__}))\n    sys.exit(1)"
    checked = subprocess.run(
        ['docker', 'run', '--rm', '--network', 'minikube',
         '--add-host', 'project15.local:' + address,
         '--user', str(os.getuid()) + ':' + str(os.getgid()),
         '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
         '--memory', '128m', '--cpus', '1',
         '--entrypoint', 'python3', image,
         '-c', probe, json.dumps(sorted(EXPECTED))],
        capture_output=True, text=True, timeout=60,
    )
    require(checked.returncode == 0,
            'Docker-network endpoint preflight failed; raw output withheld.')
    checked_data = json.loads(checked.stdout)
    require(checked_data.get('ok') is True
            and set(checked_data['paths']) == EXPECTED,
            'Docker-network preflight coverage differs.')
    print('PASS: three scoped GET endpoints reachable through Ingress.', flush=True)

    state = Path.home() / ".local/state/project15-zap"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(state, 0o700)
    fd, log_path = tempfile.mkstemp(prefix="scan-", suffix=".log", dir=state)
    os.fchmod(fd, 0o600)
    name = "project15-zap-" + uuid.uuid4().hex[:12]
    print("Protected scanner log:", log_path, flush=True)

    with tempfile.TemporaryDirectory(prefix="project15-zap-") as temporary:
        work = Path(temporary)
        docker = [
            "docker", "run", "--rm", "--init", "--name", name,
            "--network", "minikube",
            "--add-host", "project15.local:" + address,
            "--user", f"{os.getuid()}:{os.getgid()}",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--memory", "1g", "--cpus", "1",
            "--env", "PYTHONDONTWRITEBYTECODE=1",
            "--volume", str(work) + ":/zap/wrk:rw",
            "--volume", str(specification) + ":/zap/wrk/api.openapi.json:ro",
            "--volume", str(hook) + ":/zap/wrk/coverage-hook.py:ro",
            image, "zap-api-scan.py",
            "-t", "/zap/wrk/api.openapi.json", "-f", "openapi",
            "-S", "-T", "3", "-s",
            "-J", "zap-report.json", "-r", "zap-report.html",
            "--hook", "/zap/wrk/coverage-hook.py",
            "-z", "-silent -Xmx512m",
        ]
        process = None
        try:
            with os.fdopen(fd, "w") as log:
                process = subprocess.Popen(
                    docker, stdout=log, stderr=subprocess.STDOUT
                )
                started = time.monotonic()
                while True:
                    try:
                        code = process.wait(timeout=15)
                        break
                    except subprocess.TimeoutExpired:
                        elapsed = int(time.monotonic() - started)
                        print("Passive ZAP scan running:", elapsed, "seconds.", flush=True)
                        require(elapsed < 480, "ZAP scan exceeded the overall time limit.")
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name],
                capture_output=True, text=True, timeout=30,
            )
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=30)
            for filename in REPORTS:
                origin = work / filename
                if origin.is_file():
                    target = reports / filename
                    shutil.copyfile(origin, target)
                    target.chmod(0o600)

    print("ZAP exit code:", code, flush=True)
    require(code in (0, 2), "ZAP execution failed; inspect the protected scanner log.")
    require(all((reports / filename).is_file()
                and (reports / filename).stat().st_size > 0 for filename in REPORTS),
            "A required ZAP report is missing or empty.")

    coverage = json.loads((reports / "zap-coverage.json").read_text())
    require("error" not in coverage, "Coverage hook failed.")
    successful = {
        item["path"] for item in coverage["observed"]
        if item["method"] == "GET" and item["status"] == 200
    }
    require(successful == EXPECTED, "ZAP did not observe all three successful GETs.")
    require(coverage["unsafe_method_count"] == 0
            and coverage["unexpected_path_count"] == 0,
            "Unexpected target operation observed.")
    require(coverage["active_scan_count"] == 0, "An active scan was unexpectedly started.")
    require(coverage["passive_records_remaining"] == 0,
            "Passive scanning did not finish.")

    report = json.loads((reports / "zap-report.json").read_text())
    sites = report.get("site")
    require(isinstance(sites, list) and sites, "ZAP report contains no sites.")
    counts = Counter({str(level): 0 for level in range(4)})
    findings = []
    for site in sites:
        require(urlsplit(site.get("@name", "")).hostname == "project15.local",
                "Unexpected site in ZAP report.")
        alerts = site.get("alerts")
        require(isinstance(alerts, list), "Malformed ZAP alerts.")
        for alert in alerts:
            risk = str(alert.get("riskcode"))
            require(risk in counts, "Unknown ZAP risk classification.")
            counts[risk] += 1
            findings.append({
                "rule": str(alert.get("pluginid", "")),
                "name": alert.get("name", ""),
                "riskcode": risk,
                "instances": len(alert.get("instances", [])),
            })

    summary = {
        "mode": "passive",
        "scope": sorted(EXPECTED),
        "image": image,
        "specification_sha256": hashlib.sha256(specification.read_bytes()).hexdigest(),
        "scanner_exit_code": code,
        "coverage_verified": True,
        "rule_counts": {
            "HIGH": counts["3"], "MEDIUM": counts["2"],
            "LOW": counts["1"], "INFORMATIONAL": counts["0"],
        },
        "findings": findings,
        "gate": "pass" if counts["3"] == 0 else "fail",
    }
    target = reports / "zap-summary.json"
    target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    target.chmod(0o600)
    print("PASS: three GET endpoints observed; passive scanning completed.")
    for risk, count in summary["rule_counts"].items():
        print(risk + ":", count)
    require(counts["3"] == 0, "ZAP HIGH security gate failed; reports retained.")
    print("PASS: passive ZAP HIGH gate passed for the defined scope.")
    print("Reports saved:", reports)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit("STOP: " + str(exc))
