import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
import xml.etree.ElementTree as ET

os.umask(0o077)
if len(sys.argv) != 2:
    raise SystemExit("Usage: test-api.py REPORT_DIRECTORY")

ci = Path(__file__).resolve().parent
reports = Path(sys.argv[1]).resolve()
reports.mkdir(parents=True, exist_ok=True)
collection = ci / "postman/smoke.postman_collection.json"

references = [
    line.split("=", 1)[1].strip()
    for line in (ci / "images.env").read_text().splitlines()
    if line.startswith("NEWMAN_IMAGE=")
]
if len(references) != 1 or not re.fullmatch(
    r"(docker\.io/)?postman/newman@sha256:[a-f0-9]{64}", references[0]
):
    raise SystemExit("STOP: digest-pinned Newman image required.")

data = json.loads(collection.read_text())
if len(data["item"]) != 3 or any(
    item["request"]["method"] != "GET" for item in data["item"]
):
    raise SystemExit("STOP: expected exactly three read-only requests.")

def inspect(arguments):
    result = subprocess.run(
        arguments, capture_output=True, text=True, timeout=45
    )
    if result.returncode:
        raise SystemExit("STOP: network inspection failed; raw output withheld.")
    return json.loads(result.stdout)

node = inspect(["docker", "inspect", "minikube"])[0]
networks = node["NetworkSettings"]["Networks"]
if "minikube" not in networks:
    raise SystemExit("STOP: expected Minikube Docker network missing.")
address = str(ipaddress.ip_address(networks["minikube"]["IPAddress"]))

ingress = inspect([
    "kubectl", "--context=minikube", "-n", "project15",
    "get", "ingress", "project15-app", "-o", "json"
])
if not any(
    rule.get("host") == "project15.local"
    for rule in ingress["spec"].get("rules", [])
):
    raise SystemExit("STOP: expected Ingress host missing.")

report = reports / "newman.xml"
report.unlink(missing_ok=True)
container_name = "project15-newman-" + uuid.uuid4().hex[:12]
command = [
    "docker", "run", "--rm", "--name", container_name,
    "--user", f"{os.getuid()}:{os.getgid()}",
    "--network", "minikube",
    "--env", "HOME=/tmp",
    "--tmpfs", "/tmp:rw,nosuid,nodev,mode=1777,size=256m",
    "--workdir", "/tmp",
    "--volume", f"{collection}:/collection.json:ro",
    "--volume", f"{reports}:/reports",
    references[0], "run", "/collection.json",
    "--env-var", f"baseUrl=http://{address}",
    "--env-var", "ingressHost=project15.local",
    "--reporters", "cli,junit",
    "--reporter-junit-export", "/reports/newman.xml",
    "--timeout-request", "10000",
    "--timeout-script", "5000",
    "--timeout", "60000",
    "--bail",
]
try:
    result = subprocess.run(command, timeout=120)
except subprocess.TimeoutExpired:
    raise SystemExit("STOP: Newman timed out.")
finally:
    subprocess.run(
        ["docker", "rm", "-f", container_name],
        capture_output=True, timeout=30
    )

if result.returncode:
    raise SystemExit("STOP: Newman failed; any generated report was retained.")
if not report.is_file():
    raise SystemExit("STOP: Newman JUnit report missing.")

root = ET.parse(report).getroot()
cases = list(root.iter("testcase"))
failures = list(root.iter("failure")) + list(root.iter("error"))
if not cases or failures:
    raise SystemExit("STOP: empty or failing JUnit report.")

print("PASS: Newman smoke tests passed through Ingress.")
print("JUnit test cases:", len(cases))
print("Report saved: newman.xml")
