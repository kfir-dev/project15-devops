import base64
from collections import Counter
import sys
import yaml

class KubernetesLoader(yaml.SafeLoader):
    pass

def equals_as_string(loader, node):
    if not isinstance(node, yaml.ScalarNode) or node.value != "=":
        raise ValueError("Unexpected YAML value tag")
    return "="

KubernetesLoader.add_constructor("tag:yaml.org,2002:value", equals_as_string)

def require(condition, message):
    if not condition:
        print("STOP:", message, flush=True)
        raise SystemExit(1)

phase = "YAML parsing"
try:
    objects = [
        item for item in yaml.load_all(sys.stdin, Loader=KubernetesLoader) if item
    ]

    phase = "namespace isolation"
    def coredns_metrics_service(item):
        metadata = item.get("metadata", {})
        spec = item.get("spec", {})
        ports = spec.get("ports", [])
        return (
            item.get("kind") == "Service"
            and metadata.get("name") == "project15-monitoring-kube-coredns"
            and metadata.get("namespace") == "kube-system"
            and spec.get("type", "ClusterIP") == "ClusterIP"
            and spec.get("selector") == {"k8s-app": "kube-dns"}
            and len(ports) == 1
            and ports[0].get("port") == 9153
            and ports[0].get("targetPort") == 9153
            and ports[0].get("protocol", "TCP") == "TCP"
            and not ports[0].get("nodePort")
        )

    unexpected = [
        item for item in objects
        if item.get("metadata", {}).get("namespace") not in (None, "", "monitoring")
        and not coredns_metrics_service(item)
    ]
    for item in unexpected:
        metadata = item.get("metadata", {})
        print("Additional namespace resource:",
              item.get("kind"), metadata.get("name"), metadata.get("namespace"))
    require(not unexpected, "unexpected namespace or CoreDNS Service configuration")
    require(
        sum(coredns_metrics_service(item) for item in objects) == 1,
        "expected one restricted CoreDNS metrics Service"
    )

    def single(kind):
        matches = [item for item in objects if item.get("kind") == kind]
        require(len(matches) == 1, "expected one resource of kind " + kind)
        return matches[0]

    phase = "persistent storage"
    prometheus = single("Prometheus")
    alertmanager = single("Alertmanager")
    pvc = single("PersistentVolumeClaim")

    def size(claim):
        return claim["spec"]["resources"]["requests"]["storage"]

    require(size(pvc) == "1Gi", "unexpected Grafana storage")
    require(
        size(prometheus["spec"]["storage"]["volumeClaimTemplate"]) == "2Gi",
        "unexpected Prometheus storage"
    )
    require(
        size(alertmanager["spec"]["storage"]["volumeClaimTemplate"]) == "1Gi",
        "unexpected Alertmanager storage"
    )

    phase = "Grafana credential references"
    secrets = {
        item["metadata"]["name"]: item
        for item in objects if item.get("kind") == "Secret"
    }
    external = "project15-grafana-admin"
    require(external not in secrets, "Grafana admin Secret must remain external")

    workloads = [
        item for item in objects
        if item.get("kind") in ("Deployment", "StatefulSet")
        and any(
            container.get("name") == "grafana"
            for container in item["spec"]["template"]["spec"]["containers"]
        )
    ]
    require(len(workloads) == 1, "expected one Grafana workload")
    pod = workloads[0]["spec"]["template"]["spec"]

    keys = set()
    for container in pod["containers"]:
        if container.get("name") != "grafana":
            continue
        for entry in container.get("env", []):
            reference = entry.get("valueFrom", {}).get("secretKeyRef", {})
            if reference.get("name") == external:
                keys.add(reference.get("key"))
    for volume in pod.get("volumes", []):
        reference = volume.get("secret", {})
        if reference.get("secretName") == external:
            if reference.get("items"):
                keys.update(item["key"] for item in reference["items"])
            else:
                keys.update(("admin-user", "admin-password"))
    require(
        {"admin-user", "admin-password"}.issubset(keys),
        "Grafana admin Secret key references differ"
    )

    phase = "application scrape configuration"
    reference = prometheus["spec"]["additionalScrapeConfigs"]
    secret = secrets[reference["name"]]
    key = reference["key"]
    if key in secret.get("stringData", {}):
        source = secret["stringData"][key]
    else:
        source = base64.b64decode(secret["data"][key]).decode()
    jobs = yaml.load(source, Loader=KubernetesLoader)
    matches = [job for job in jobs if job.get("job_name") == "project15-app"]
    require(len(matches) == 1, "application scrape job missing")
    require(any(
        "project15-app.project15.svc.cluster.local:8000" in target.get("targets", [])
        for target in matches[0].get("static_configs", [])
    ), "application scrape target missing")

    print("PASS: monitoring namespace, restricted CoreDNS metrics Service and cluster scope verified.")
    print("PASS: separate storage: Grafana 1Gi, Prometheus 2Gi, Alertmanager 1Gi.")
    print("PASS: Grafana references external credential keys.")
    print("PASS: application metrics scrape target configured.")
    print("Resource kinds:", dict(Counter(item["kind"] for item in objects)))
except (KeyError, TypeError, ValueError, yaml.YAMLError) as error:
    print("STOP: render audit failed during", phase)
    print("Exception type:", type(error).__name__)
    raise SystemExit(1)
