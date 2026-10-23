import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid


KUBE = ["kubectl", "--context=minikube", "-n", "project15"]
FILES = ("sbom.json", "scan-report.json")
STATE = Path.home() / ".local/state/project15-security-report-publication"
MAX_FILE = 20 * 1024 * 1024

RECEIVER = r'''
import base64,hashlib,json,os
from pathlib import Path
import sys,tempfile

root=Path(sys.argv[1])
names={"sbom.json","scan-report.json"}
limit=20*1024*1024
packet=json.load(sys.stdin)
operation=packet.get("operation")
if operation not in {"snapshot","publish","restore"}:
    raise RuntimeError("Unknown report operation")
if not root.is_dir() or root.is_symlink():
    raise RuntimeError("Invalid report directory")
def legacy_target(target):
    relative=Path(target)
    if not isinstance(target,str) or relative.is_absolute() or '..' in relative.parts:
        raise RuntimeError("Unsafe legacy report link")
    resolved=(root/relative).resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file() or resolved in {root.resolve()/name for name in names}:
        raise RuntimeError("Unsafe legacy report link")
    if resolved.stat().st_size>limit:
        raise RuntimeError("Existing report exceeds size bound")
    return resolved
for name in names:
    path=root/name
    if path.is_symlink():
        legacy_target(os.readlink(path))
    elif path.exists() and not path.is_file():
        raise RuntimeError("Unexpected existing report path")
if operation=="snapshot":
    result={}
    for name in sorted(names):
        path=root/name
        if not path.exists():
            result[name]=None
            continue
        if path.stat().st_size>limit:
            raise RuntimeError("Existing report exceeds size bound")
        data=path.read_bytes()
        result[name]={"data":base64.b64encode(data).decode(),"sha256":hashlib.sha256(data).hexdigest()}
        if path.is_symlink():
            result[name]['symlink']=os.readlink(path)
    print(json.dumps({"files":result}))
else:
    records=packet.get("files")
    if not isinstance(records,dict) or set(records)!=names:
        raise RuntimeError("Unexpected report file inventory")
    decoded={}
    links={}
    for name,record in records.items():
        if record is None and operation=="restore":
            decoded[name]=None
            continue
        allowed=[{"data","sha256"}]
        if operation=="restore":
            allowed.append({"data","sha256","symlink"})
        if not isinstance(record,dict) or set(record) not in allowed:
            raise RuntimeError("Malformed report record")
        data=base64.b64decode(record["data"],validate=True)
        if len(data)>limit or hashlib.sha256(data).hexdigest()!=record["sha256"]:
            raise RuntimeError("Report hash or size mismatch")
        if operation=="publish" and not isinstance(json.loads(data),dict):
            raise RuntimeError("Report must be a JSON object")
        if 'symlink' in record:
            target=legacy_target(record['symlink'])
            if target.read_bytes()!=data:
                raise RuntimeError("Legacy link target changed; protected backup requires inspection")
            links[name]=record['symlink']
        decoded[name]=data
    staged={}
    try:
        for name,data in decoded.items():
            if data is None:
                continue
            fd,temporary=tempfile.mkstemp(prefix=".project15-report-",dir=root)
            staged[name]=Path(temporary)
            if name in links:
                os.close(fd)
                os.unlink(temporary)
                os.symlink(links[name],temporary)
                continue
            with os.fdopen(fd,"wb") as stream:
                os.chmod(temporary,0o640)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
        for name,data in decoded.items():
            if data is None:
                (root/name).unlink(missing_ok=True)
            else:
                os.replace(staged[name],root/name)
    finally:
        for path in staged.values():
            path.unlink(missing_ok=True)
    print(json.dumps({"operation":operation,"files":sorted(decoded)}))
'''


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run(args, source=None, timeout=90):
    result = subprocess.run(args, input=source, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        fd, name = tempfile.mkstemp(prefix="diagnostic-", suffix=".log", dir=STATE)
        with os.fdopen(fd, "w") as stream:
            stream.write(result.stdout)
            stream.write(result.stderr)
        raise RuntimeError("Command failed; protected diagnostic log: " + name)
    return result.stdout


def kubectl(*args):
    return json.loads(run(KUBE + list(args) + ["-o", "json"]))


def canonical(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def snapshot():
    claims = {}
    for name in ("project15-database", "project15-security-reports"):
        claim = kubectl("get", "pvc", name)
        require(claim.get("status", {}).get("phase") == "Bound", "Required PVC is not Bound.")
        claims[name] = {"uid": claim["metadata"]["uid"], "spec": claim["spec"]}
    return {
        "claims": claims,
        "database_spec": kubectl("get", "deployment", "project15-database")["spec"],
        "application_spec": kubectl("get", "deployment", "project15-app")["spec"],
    }


def prepare(reports):
    reference = (reports / "image-reference.txt").read_text().strip()
    require(re.fullmatch(r"ghcr\.io/kfir-dev/project15-app@sha256:[a-f0-9]{64}", reference), "Unexpected image reference.")
    publication = json.loads((reports / "image-publication.json").read_text())
    deployment = json.loads((reports / "deployment.json").read_text())
    require(publication.get("image_reference") == reference and deployment.get("image_reference") == reference, "Publication/deployment metadata differs.")
    image_id = publication.get("local_image_id", "")
    require(re.fullmatch(r"sha256:[a-f0-9]{64}", image_id), "Published local image identity missing.")
    binding = json.loads((reports / "sbom-binding.json").read_text())
    require(binding.get("schema_version") == 1 and binding.get("archive_binding_verified") is True
            and binding.get("local_image_id") == image_id, "SBOM archive binding differs from the published image.")
    config_id = binding.get("image_config_id", "")
    require(re.fullmatch(r"sha256:[a-f0-9]{64}", config_id), "SBOM configuration identity missing.")
    records, hashes = {}, {}
    for name in FILES:
        path = reports / name
        require(not path.is_symlink() and path.is_file(), "Unexpected report source.")
        require(path.stat().st_size <= MAX_FILE, "Report exceeds size bound.")
        content = path.read_bytes()
        document = json.loads(content)
        require(isinstance(document, dict), "Report is not a JSON object.")
        if name == "sbom.json":
            require(document.get("bomFormat") == "CycloneDX", "Expected CycloneDX SBOM.")
            component = document.get("metadata", {}).get("component", {})
            require(component.get("type") == "container"
                    and component.get("version") == binding.get("syft_manifest_digest")
                    and re.fullmatch(r"sha256:[a-f0-9]{64}", component.get("version", "")), "SBOM metadata differs from the verified archive binding.")
            require(hashlib.sha256(content).hexdigest() == binding.get("sbom_sha256"), "SBOM content differs from the verified archive binding.")
        else:
            require(isinstance(document.get("Results"), list) and isinstance(document.get("Metadata"), dict), "Expected Trivy image report.")
            require(document["Metadata"].get("ImageID") == config_id, "Trivy report image differs from the published image configuration.")
        records[name] = {"data": base64.b64encode(content).decode(), "sha256": hashlib.sha256(content).hexdigest()}
        hashes[name] = canonical(document)
    before = snapshot()
    app = before["application_spec"]["template"]["spec"]
    container = next(item for item in app["containers"] if item["name"] == "app")
    require(container["image"] == reference, "Deployed image differs from the report build.")
    mount = next(item for item in container["volumeMounts"] if item["name"] == "security-reports")
    require(mount.get("readOnly") is True and mount["mountPath"] == "/app/security-reports", "Application report mount must remain read-only.")
    volume = next(item for item in app["volumes"] if item["name"] == "security-reports")
    require(volume.get("persistentVolumeClaim", {}).get("claimName") == "project15-security-reports", "Unexpected report PVC.")
    pods = kubectl("get", "pods", "-l", "app=project15-app")["items"]
    ready = [item for item in pods if not item["metadata"].get("deletionTimestamp") and item.get("status", {}).get("phase") == "Running" and any(condition["type"] == "Ready" and condition["status"] == "True" for condition in item["status"].get("conditions", []))]
    require(len(ready) == 1 and ready[0]["spec"].get("nodeName"), "Expected one ready application Pod.")
    require(next(item["image"] for item in ready[0]["spec"]["containers"] if item["name"] == "app") == reference, "Application Pod image differs.")
    return reference, records, hashes, before, ready[0]


def writer_manifest(name, nonce, reference, node):
    return {
        "apiVersion": "v1", "kind": "Pod",
        "metadata": {"name": name, "namespace": "project15", "labels": {"project15-report-publication": nonce}},
        "spec": {
            "nodeName": node, "restartPolicy": "Never", "activeDeadlineSeconds": 600,
            "terminationGracePeriodSeconds": 5, "automountServiceAccountToken": False,
            "enableServiceLinks": False,
            "imagePullSecrets": [{"name": "project15-ghcr-pull"}],
            "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "runAsGroup": 10001, "fsGroup": 10001, "fsGroupChangePolicy": "OnRootMismatch", "seccompProfile": {"type": "RuntimeDefault"}},
            "containers": [{
                "name": "publisher", "image": reference, "imagePullPolicy": "Always",
                "command": ["python", "-c", "import time; time.sleep(590)"],
                "env": [{"name": "PYTHONDONTWRITEBYTECODE", "value": "1"}],
                "securityContext": {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True, "capabilities": {"drop": ["ALL"]}},
                "resources": {"requests": {"cpu": "25m", "memory": "64Mi"}, "limits": {"cpu": "500m", "memory": "256Mi"}},
                "volumeMounts": [{"name": "reports", "mountPath": "/reports"}],
            }],
            "volumes": [{"name": "reports", "persistentVolumeClaim": {"claimName": "project15-security-reports"}}],
        },
    }


def transfer(name, operation, files=None):
    packet = {"operation": operation}
    if files is not None:
        packet["files"] = files
    return json.loads(run(KUBE + ["exec", "-i", name, "-c", "publisher", "--", "python", "-c", RECEIVER, "/reports"], source=json.dumps(packet)))


def observed_hashes(pod):
    probe = r'''
import hashlib,json,urllib.request
result={}
for filename,path in [("sbom.json","/api/security/sbom"),("scan-report.json","/api/security/scan-report")]:
    with urllib.request.urlopen("http://127.0.0.1:8000"+path,timeout=15) as response:
        if response.status!=200: raise RuntimeError("Report HTTP status differs")
        document=json.load(response)
    result[filename]=hashlib.sha256(json.dumps(document,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()
print(json.dumps(result))
'''
    return json.loads(run(KUBE + ["exec", pod, "-c", "app", "--", "python", "-c", probe]))


def execute(reports, reference, records, hashes, before, application):
    receipt = reports / "security-reports-publication.json"
    receipt.unlink(missing_ok=True)
    nonce = uuid.uuid4().hex[:12]
    name = "project15-report-publisher-" + nonce
    owned, backup, publication_attempted = False, None, False
    try:
        body = writer_manifest(name, nonce, reference, application["spec"]["nodeName"])
        owned = True
        run(KUBE + ["create", "-f", "-", "-o", "json"], source=json.dumps(body))
        for attempt in range(60):
            pod = kubectl("get", "pod", name)
            if any(item["type"] == "Ready" and item["status"] == "True" for item in pod.get("status", {}).get("conditions", [])):
                break
            require(pod.get("status", {}).get("phase") not in {"Failed", "Succeeded"}, "Temporary report publisher exited.")
            if attempt % 5 == 0:
                print("Waiting for temporary report publisher:", attempt * 2, "seconds", flush=True)
            time.sleep(2)
        else:
            raise RuntimeError("Temporary report publisher did not become ready.")
        require(snapshot() == before, "Workload/PVC configuration changed before report publication.")
        backup = transfer(name, "snapshot")["files"]
        fd, backup_name = tempfile.mkstemp(prefix="before-publication-", suffix=".json", dir=STATE)
        with os.fdopen(fd, "w") as stream:
            json.dump({"image_reference": reference, "files": backup}, stream)
        print("PASS: previous report contents backed up outside Git.", flush=True)
        publication_attempted = True
        transfer(name, "publish", records)
        require(observed_hashes(application["metadata"]["name"]) == hashes, "Live report contents differ from the current build.")
        require(snapshot() == before, "Workload/PVC configuration changed during report publication.")
        document = {
            "image_reference": reference, "canonical_sha256": hashes,
            "backup_archive": backup_name, "live_reports_verified": True,
            "application_report_mount_read_only": True,
            "workload_specs_and_pvc_identities_preserved": True,
        }
        receipt.write_text(json.dumps(document, indent=2) + "\n")
        receipt.chmod(0o600)
        print("PASS: both live report contents match the deployed build.", flush=True)
    except Exception:
        if publication_attempted and backup is not None:
            try:
                transfer(name, "restore", backup)
                print("PASS: previous report files restored after publication failure.", flush=True)
            except Exception:
                raise RuntimeError("Report publication and restoration need inspection; protected backup retained.") from None
        raise
    finally:
        if owned:
            remaining = json.loads(run(KUBE + ["get", "pod", name, "--ignore-not-found", "-o", "json"]) or "null")
            if remaining is not None:
                require(remaining["metadata"].get("labels", {}).get("project15-report-publication") == nonce, "Temporary Pod ownership differs; cleanup stopped.")
                run(KUBE + ["delete", "pod", name, "--wait=true", "--timeout=45s"], timeout=60)
            print("PASS: temporary report publisher removed.", flush=True)
    print("Saved security-reports-publication.json; no database files or Deployment specifications changed.")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("report_directory")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    require(not STATE.is_symlink(), "Unexpected protected-state path.")
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    reports = Path(args.report_directory).resolve(strict=True)
    prepared = prepare(reports)
    print("PASS: source reports, publication metadata, deployed digest and read-only report mount verified.", flush=True)
    if args.execute:
        execute(reports, *prepared)
    else:
        print("Check only; no publisher Pod created and no report files changed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        raise SystemExit("STOP: " + str(exc))
