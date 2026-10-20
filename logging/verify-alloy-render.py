from collections import Counter
import sys
import yaml

def require(condition, message):
    if not condition:
        print("STOP:", message, flush=True)
        raise SystemExit(1)

try:
    documents = [item for item in yaml.safe_load_all(sys.stdin) if item]
    allowed = {"ServiceAccount", "ConfigMap", "Service", "Deployment",
               "Role", "RoleBinding"}
    for item in documents:
        kind = item["kind"]
        require(kind in allowed, "unexpected resource kind: " + kind)
        namespace = item.get("metadata", {}).get("namespace")
        if kind in ("Role", "RoleBinding"):
            require(namespace == "project15", "RBAC outside project15.")
        else:
            require(namespace in (None, "", "logging"),
                    "workload resource outside logging.")

    roles = [item for item in documents if item["kind"] == "Role"]
    bindings = [item for item in documents if item["kind"] == "RoleBinding"]
    require(len(roles) == len(bindings) == 1, "expected one Role and binding.")
    permissions = set()
    for rule in roles[0].get("rules", []):
        require(rule.get("apiGroups") == [""], "unexpected API group.")
        require(not rule.get("nonResourceURLs"), "unexpected non-resource access.")
        for resource in rule.get("resources", []):
            for verb in rule.get("verbs", []):
                permissions.add((resource, verb))
    expected = {
        ("pods", "get"), ("pods", "list"), ("pods", "watch"),
        ("pods/log", "get"),
    }
    require(permissions == expected, "unexpected API permissions.")
    binding = bindings[0]
    require(binding["roleRef"]["kind"] == "Role"
            and binding["roleRef"]["name"] == roles[0]["metadata"]["name"],
            "unexpected role reference.")
    require(binding.get("subjects") == [{
        "kind": "ServiceAccount", "name": "project15-alloy",
        "namespace": "logging",
    }], "unexpected role binding subject.")

    workloads = [item for item in documents if item["kind"] == "Deployment"]
    require(len(workloads) == 1, "expected one Alloy Deployment.")
    workload = workloads[0]
    require(workload["spec"].get("replicas") == 1, "unexpected replica count.")
    pod = workload["spec"]["template"]["spec"]
    require(pod.get("serviceAccountName") == "project15-alloy",
            "unexpected service account.")
    require(not pod.get("hostNetwork") and not pod.get("hostPID"),
            "unexpected host namespace access.")
    require(not any("hostPath" in volume for volume in pod.get("volumes", [])),
            "unexpected host filesystem mount.")

    containers = pod["containers"]
    main = [item for item in containers if item["name"] == "alloy"]
    require(len(main) == 1, "Alloy container not uniquely identified.")
    security = main[0].get("securityContext", {})
    require(security.get("runAsNonRoot") is True
            and security.get("runAsUser") == 10001
            and security.get("readOnlyRootFilesystem") is True
            and security.get("allowPrivilegeEscalation") is False
            and "ALL" in security.get("capabilities", {}).get("drop", []),
            "unexpected Alloy security context.")
    require(main[0]["resources"]["limits"]["memory"] == "512Mi",
            "unexpected Alloy memory limit.")
    for container in containers:
        for bound in ("requests", "limits"):
            resources = container.get("resources", {}).get(bound, {})
            require("cpu" in resources and "memory" in resources,
                    "container lacks bounded CPU/memory resources.")

    for item in documents:
        if item["kind"] == "Service":
            require(item["spec"].get("type", "ClusterIP") == "ClusterIP",
                    "externally exposed Alloy Service.")

    print("Resource kinds:", dict(Counter(item["kind"] for item in documents)))
    print("PASS: one Alloy Deployment with bounded resources and internal Service.")
    print("PASS: non-root execution; no host filesystem or namespace access.")
    print("PASS: only project15 Pod discovery and log-read permissions.")
    print("PASS: no Secret access or cluster-wide RBAC rendered.")
except Exception as exc:
    print("Inspector exception:", type(exc).__name__, flush=True)
    raise SystemExit(1)
