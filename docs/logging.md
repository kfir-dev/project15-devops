# Local application logging

## Verified deployment — 2026-10-20

- Kubernetes context: `minikube`; namespace: `logging`.
- Loki Helm release: `project15-loki`, revision 1.
- Loki chart 18.17.1, application 3.7.8.
- Alloy Helm release: `project15-alloy`, revision 1.
- Alloy chart 1.14.0, application v1.21.0.
- Chart repositories, versions and archive checksums: `logging/chart-lock.json`.
- Both main application images are pinned by digest in their Helm values.
- Both configurations passed their native binary validators.
- Render audits verified workload count, internal Services, storage and RBAC.

Alloy replaces Promtail, which reached end of life on March 2, 2026.

## Data path and scope

Kubernetes container logs -> Alloy -> Loki -> existing Grafana.

Alloy discovers Pods only in namespace `project15`, filtered to application
labels `project15-app` and `project15-database`. Matching init-container logs
may also be collected. It uses the Kubernetes API rather than host log mounts.

The pipeline attaches namespace, Pod, container, application and job labels.
The job label is `project15-logs`.

Lines matching the configured case-insensitive sensitive-keyword expression
are dropped. This is a limited safeguard, not a guarantee that arbitrary
secrets will be detected. Applications must avoid logging credentials.

Alloy temporary state is ephemeral; restarts may replay log entries.
This profile does not guarantee lossless delivery or high availability.

## Storage and resources

Loki runs as one replica using filesystem storage on a dedicated 2Gi PVC.
The PVC was verified Bound. Retention is configured for 48 hours.
Retention is time based and does not guarantee that the disk cannot fill.
The StatefulSet PVC deletion behavior is Retain.

- Loki: requests 100m CPU / 256Mi; limits 700m CPU / 1Gi.
- Alloy: requests 50m CPU / 128Mi; limits 300m CPU / 512Mi.
- Alloy config reloader: requests 10m CPU / 32Mi; limits 100m CPU / 64Mi.

This is a local development profile, not a production storage architecture.

## Permissions

Alloy runs as a non-root user with a read-only root filesystem and bounded
temporary storage. It has no host filesystem or host namespace access.

The `project15` Role grants only:
- Pods: get, list, watch.
- Pod logs: get.

Effective RBAC was verified: Pod discovery and log reads in `project15`
are allowed; Secret reads, log reads in `default`, and node reads are denied.
The Alloy chart renders no cluster-wide RBAC.

Loki automatic service-account credential mounting is disabled.
Its rendered resources contain no cluster-wide RBAC or API permission grants.

## Network policy verification

`logging/loki-networkpolicy.json` permits Loki TCP 3100 ingress from
the configured Alloy Pods in `logging` and Grafana Pods in `monitoring`.
Loki has no public Ingress, NodePort or LoadBalancer Service.
Local Loki multi-tenant authentication is disabled.

Installed network plugin image:
`docker.io/kindest/kindnetd:v20260820-69b56db7`.

Actual enforcement was verified using an unprivileged temporary Pod in
`logging`, without API credentials or matching allow-list labels:
- A control connection to the Kubernetes API TCP port succeeded.
- Loki DNS resolution succeeded.
- Three unauthorized TCP connection attempts to Loki timed out.
- The temporary Pod was removed.

Authorized delivery was separately verified through Alloy ingestion and
Grafana queries. This is targeted evidence for the tested path, not an
exhaustive test of all cluster network policies.

## Grafana access and queries

Datasource provisioning: `logging/grafana-datasource-configmap.json`.
Datasource name: `Project15 Loki`; UID: `project15-loki`.
Prometheus remains the default datasource.

Forward the existing Grafana Service from a dedicated WSL terminal:

    kubectl --context=minikube --namespace=monitoring port-forward --address=127.0.0.1 service/project15-monitoring-grafana 3000:80

Open http://localhost:3000/explore, select Project15 Loki, choose Code mode
and Last 24 hours, then query:

    {job="project15-logs", namespace="project15"}

To select one application:

    {job="project15-logs", application="project15-app"}

Loki API queries returned log entries for both application and database.
A Grafana export contained 22 entries from both sources, confirming the
complete collection and viewing path. Log message bodies were not included
in verification output. Do not commit raw log exports to Git.

## Preservation and shutdown

Installation verified that existing application and monitoring release
revisions and original PVC identities and specifications were preserved.
Original policies, application Deployments and PVCs were unchanged by the
temporary network probe.

Stop the Grafana port-forward with Ctrl+C before the normal shutdown.
Stopping Minikube preserves logging PVCs. Do not uninstall releases or
delete PVCs during routine shutdown.
