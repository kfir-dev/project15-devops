import copy
import os
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parent.parent
KUBE = ["kubectl", "--context=minikube", "-n", "project15"]
HELM = ["--kube-context", "minikube", "--namespace", "project15"]

def run(arguments, *, source=None, timeout=90):
    result = subprocess.run(
        arguments, input=source, capture_output=True, text=True, timeout=timeout
    )
    if result.returncode:
        raise SystemExit("STOP: deployment preflight failed; raw output withheld.")
    return result.stdout

def objects(source):
    output = run([
        "kubectl", "--context=minikube", "create",
        "--dry-run=client", "--validate=false", "-f", "-", "-o", "json"
    ], source=source)
    decoder = json.JSONDecoder()
    remaining = output.strip()
    resources = {}
    while remaining:
        document, end = decoder.raw_decode(remaining)
        remaining = remaining[end:].lstrip()
        items = document.get("items", []) if document.get("kind") == "List" else [document]
        for item in items:
            metadata = item["metadata"]
            key = (item["kind"], metadata.get("namespace", ""), metadata["name"])
            if key in resources:
                raise SystemExit("STOP: duplicate resource in render.")
            resources[key] = item
    return resources

def pvc_snapshot():
    claims = json.loads(run(KUBE + ["get", "pvc", "-o", "json"]))
    by_name = {item["metadata"]["name"]: item for item in claims["items"]}
    snapshot = {}
    for name in ("project15-database", "project15-security-reports"):
        claim = by_name[name]
        if claim["status"]["phase"] != "Bound" or not claim["spec"].get("volumeName"):
            raise SystemExit("STOP: required PVC is not Bound.")
        snapshot[name] = {
            "uid": claim["metadata"]["uid"],
            "spec": claim["spec"],
        }
    return snapshot

def prepare(reports, override):
    reference = (reports / "image-reference.txt").read_text().strip()
    if not re.fullmatch(
        r"ghcr\.io/kfir-dev/project15-app@sha256:[a-f0-9]{64}", reference
    ):
        raise SystemExit("STOP: unexpected deployment image reference.")

    publication = json.loads((reports / "image-publication.json").read_text())
    if publication.get("image_reference") != reference:
        raise SystemExit("STOP: publication metadata does not match image reference.")

    status = json.loads(run(["helm", "status", "project15", *HELM, "-o", "json"]))
    if status["info"]["status"] != "deployed":
        raise SystemExit("STOP: Helm release is not deployed.")

    claims = pvc_snapshot()
    repository, digest = reference.split("@", 1)
    override.write_text(json.dumps({
        "app": {"image": {
            "repository": repository,
            "digest": digest,
            "pullPolicy": "Always",
        }}
    }))

    installed = objects(run(["helm", "get", "manifest", "project15", *HELM]))
    proposed = objects(run([
        "helm", "template", "project15", str(REPO / "helm/project15"),
        "--namespace", "project15",
        "-f", str(REPO / "helm/project15/values-local.yaml"),
        "-f", str(override),
    ]))

    if set(installed) != set(proposed):
        raise SystemExit("STOP: resource inventory differs.")

    expected = copy.deepcopy(installed)
    application = expected[("Deployment", "project15", "project15-app")]
    containers = application["spec"]["template"]["spec"]["containers"]
    matches = [item for item in containers if item["name"] == "app"]
    if len(matches) != 1:
        raise SystemExit("STOP: unexpected application container structure.")
    matches[0]["image"] = reference

    if expected != proposed:
        raise SystemExit("STOP: rendered changes exceed the application image field.")

    return reference, status["version"], claims

def secret_snapshot():
    snapshot = {}
    for name in ("project15-database-external", "project15-ghcr-pull"):
        secret = json.loads(run(KUBE + ["get", "secret", name, "-o", "json"]))
        snapshot[name] = {
            "uid": secret["metadata"]["uid"],
            "type": secret["type"],
            "data": secret.get("data", {}),
        }
    return snapshot

def database_spec():
    deployment = json.loads(run(
        KUBE + ["get", "deployment", "project15-database", "-o", "json"]
    ))
    return deployment["spec"]

def execute(reports, override, reference, previous_revision, claims):
    os.umask(0o077)
    (reports / "deployment.json").unlink(missing_ok=True)
    secrets_before = secret_snapshot()
    database_before = database_spec()

    state = Path.home() / ".local/state/project15-deployments"
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    state.chmod(0o700)

    descriptor, filename = tempfile.mkstemp(
        prefix="before-helm-", suffix=".dump", dir=state
    )
    backup = Path(filename)
    with os.fdopen(descriptor, "wb") as output:
        result = subprocess.run(
            KUBE + [
                "exec", "deployment/project15-database", "--", "sh", "-c",
                'pg_dump -w -U "${POSTGRES_USER:-postgres}" -d project15 -Fc'
            ],
            stdout=output, stderr=subprocess.PIPE, timeout=120
        )
    if result.returncode or backup.stat().st_size == 0:
        raise SystemExit("STOP: fresh backup failed; no upgrade performed.")

    with backup.open("rb") as source:
        result = subprocess.run(
            KUBE + [
                "exec", "-i", "deployment/project15-database", "--",
                "pg_restore", "--list"
            ],
            stdin=source, capture_output=True, timeout=120
        )
    if result.returncode or not result.stdout:
        raise SystemExit("STOP: backup archive unreadable; no upgrade performed.")
    print("PASS: protected current backup created and archive readable.", flush=True)

    current = json.loads(run(["helm", "status", "project15", *HELM, "-o", "json"]))
    if (
        current["info"]["status"] != "deployed"
        or current["version"] != previous_revision
        or pvc_snapshot() != claims
        or secret_snapshot() != secrets_before
        or database_spec() != database_before
    ):
        raise SystemExit("STOP: cluster state changed during preflight.")

    command = [
        "helm", "upgrade", "project15", str(REPO / "helm/project15"), *HELM,
        "-f", str(REPO / "helm/project15/values-local.yaml"),
        "-f", str(override),
        "--history-max", "2", "--atomic", "--wait", "--timeout", "5m",
        "--output", "json"
    ]
    print("Starting controlled application upgrade.", flush=True)
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    elapsed = 0
    while True:
        try:
            output, errors = process.communicate(timeout=15)
            break
        except subprocess.TimeoutExpired:
            elapsed += 15
            print(f"Upgrade running: {elapsed} seconds.", flush=True)

    descriptor, log_name = tempfile.mkstemp(
        prefix="helm-", suffix=".log", dir=state
    )
    with os.fdopen(descriptor, "w") as log:
        log.write(output)
        log.write("\n")
        log.write(errors)

    if process.returncode:
        print("Protected diagnostic log:", log_name)
        raise SystemExit("STOP: Helm upgrade failed; rollback state needs verification.")

    release = json.loads(output)
    if release["info"]["status"] != "deployed":
        raise SystemExit("STOP: unexpected Helm release status.")

    if pvc_snapshot() != claims:
        raise SystemExit("STOP: PVC identity or specification differs after upgrade.")
    if secret_snapshot() != secrets_before:
        raise SystemExit("STOP: credential Secret identity or data changed.")
    if database_spec() != database_before:
        raise SystemExit("STOP: database Deployment specification changed.")

    deployments = json.loads(run(KUBE + [
        "get", "deployments", "project15-app", "project15-database", "-o", "json"
    ]))
    for deployment in deployments["items"]:
        status = deployment["status"]
        if (
            deployment["spec"]["replicas"] != 1
            or status.get("updatedReplicas") != 1
            or status.get("readyReplicas") != 1
            or status.get("availableReplicas") != 1
            or status.get("observedGeneration", 0) < deployment["metadata"]["generation"]
        ):
            raise SystemExit("STOP: Deployment readiness verification failed.")
        if deployment["metadata"]["name"] == "project15-app":
            containers = deployment["spec"]["template"]["spec"]["containers"]
            actual = next(item["image"] for item in containers if item["name"] == "app")
            if actual != reference:
                raise SystemExit("STOP: deployed application image differs.")

    health = (
        "import urllib.request\n"
        "for endpoint in ('live', 'ready'):\n"
        "    with urllib.request.urlopen("
        "'http://127.0.0.1:8000/health/' + endpoint, timeout=10) as response:\n"
        "        assert response.status == 200\n"
    )
    run(KUBE + [
        "exec", "deployment/project15-app", "-c", "app", "--",
        "python", "-c", health
    ])

    (reports / "deployment.json").write_text(json.dumps({
        "context": "minikube",
        "namespace": "project15",
        "previous_revision": previous_revision,
        "revision": release["version"],
        "image_reference": reference,
        "backup_archive": str(backup),
        "pvc_bindings_and_specs_preserved": True,
        "credential_secrets_unchanged": True,
        "database_deployment_spec_unchanged": True,
        "health_endpoints_http_200": True,
    }, indent=2) + "\n")

    print("PASS: deployed the published application digest.")
    print("Helm revision:", release["version"])
    print("PASS: PVCs, credential Secrets and database specification preserved.")
    print("PASS: both Deployments ready; health endpoints HTTP 200.")
    print("Saved deployment.json; backup retained outside Git.")

def main():
    if len(sys.argv) != 3 or sys.argv[2] not in ("--check-only", "--execute"):
        raise SystemExit("Usage: deploy-minikube.py REPORT_DIRECTORY --check-only|--execute")
    reports = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="project15-deploy-plan-") as temporary:
        override = Path(temporary) / "override.json"
        reference, revision, claims = prepare(reports, override)
        print("PASS: publication metadata and digest match.")
        print("Current Helm revision:", revision)
        print("PASS: only the application image may change.")
        print("PASS: both PVCs are Bound; identities and specifications recorded.")
        if sys.argv[2] == "--execute":
            execute(reports, override, reference, revision, claims)
        else:
            print("Check only; no backup, upgrade or cluster changes performed.")

if __name__ == "__main__":
    main()
