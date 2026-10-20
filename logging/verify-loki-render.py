import base64
from collections import Counter
import sys
import yaml

def require(condition, message):
    if not condition:
        raise SystemExit("STOP: " + message)

try:
    documents = [item for item in yaml.safe_load_all(sys.stdin) if item]
    allowed = {"ServiceAccount", "ConfigMap", "Secret", "Service",
               "StatefulSet", "PodDisruptionBudget", "NetworkPolicy", "Role", "RoleBinding"}
    require(bool(documents), "empty render.")
    for item in documents:
        require(item["kind"] in allowed,
                "unexpected resource kind: " + item["kind"])
        require(item.get("metadata", {}).get("namespace") in (None, "", "logging"),
                "resource outside logging namespace.")

    for item in documents:
        if item["kind"] == "Role":
            require(not item.get("rules"), "unexpected Loki API permissions.")
        if item["kind"] == "RoleBinding":
            require(item["roleRef"]["kind"] == "Role",
                    "unexpected cluster-level role reference.")
            require(all(subject.get("namespace", "logging") == "logging"
                        and subject.get("kind") == "ServiceAccount"
                        for subject in item.get("subjects", [])),
                    "unexpected role binding subject.")

    workloads = [item for item in documents if item["kind"] == "StatefulSet"]
    require(len(workloads) == 1, "expected one StatefulSet.")
    workload = workloads[0]
    require(workload["spec"].get("replicas") == 1, "unexpected replica count.")
    claims = workload["spec"].get("volumeClaimTemplates", [])
    require(len(claims) == 1, "expected one storage claim.")
    claim = claims[0]["spec"]
    require(claim["resources"]["requests"]["storage"] == "2Gi",
            "unexpected storage size.")
    require(claim.get("storageClassName") == "standard",
            "unexpected storage class.")
    retention = workload["spec"].get("persistentVolumeClaimRetentionPolicy", {})
    require(all(retention.get(key, "Retain") == "Retain"
                for key in ("whenDeleted", "whenScaled")),
            "unexpected PVC deletion policy.")

    pod = workload["spec"]["template"]["spec"]
    require(not any("hostPath" in v for v in pod.get("volumes", [])),
            "unexpected host filesystem mount.")
    require(pod.get("automountServiceAccountToken") is False,
            "automatic API credentials are not disabled.")
    require(len(pod["containers"]) == 1, "unexpected additional containers.")
    require(pod["containers"][0]["resources"]["limits"]["memory"] == "1Gi",
            "unexpected memory limit.")

    configs = []
    for item in documents:
        if item["kind"] == "Service":
            require(item["spec"].get("type", "ClusterIP") == "ClusterIP",
                    "externally exposed Service.")
            print("Service:", item["metadata"]["name"],
                  "| ports:", [p["port"] for p in item["spec"]["ports"]])
        if item["kind"] not in ("ConfigMap", "Secret"):
            continue
        contents = list(item.get("stringData", {}).values())
        for value in item.get("data", {}).values():
            contents.append(base64.b64decode(value).decode()
                            if item["kind"] == "Secret" else value)
        for value in contents:
            if "schema_config:" in value and "auth_enabled:" in value:
                configs.append(yaml.safe_load(value))

    require(len(configs) == 1, "expected one Loki configuration.")
    config = configs[0]
    require(config["auth_enabled"] is False, "unexpected authentication mode.")
    require(config["common"]["replication_factor"] == 1,
            "unexpected replication factor.")
    require(config["limits_config"]["retention_period"] == "48h",
            "unexpected retention period.")
    require(config["compactor"]["retention_enabled"] is True,
            "retention is not enabled.")
    require(all(c["object_store"] == "filesystem"
                for c in config["schema_config"]["configs"]),
            "unexpected storage backend.")

    print("Resource kinds:", dict(Counter(d["kind"] for d in documents)))
    print("PASS: Loki workload, storage, retention and internal Services verified.")
    print("PASS: no cluster-wide RBAC; namespace Roles grant no API permissions.")
except Exception as exc:
    print("Inspector exception:", type(exc).__name__)
    raise SystemExit(1)
