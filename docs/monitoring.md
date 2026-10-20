# Local monitoring

## Deployment

- Context: `minikube`; namespace: `monitoring`.
- Helm release: `project15-monitoring`; verified revision: 2.
- Chart: `kube-prometheus-stack` 92.10.1.
- Chart archive checksum is recorded in `monitoring/chart-lock.json`.
- Configuration: `monitoring/values-local.json`.
- `monitoring/check-chart.py` verifies the archive, Helm lint and render audit.
- Chart version and archive are pinned; this does not imply that every monitoring image is pinned by digest.
- This local profile excludes etcd, controller-manager, scheduler and kube-proxy scraping.

## Storage and credentials

Dedicated monitoring PVCs are Bound:
- Grafana: 1Gi.
- Prometheus: 2Gi; retention 2 days with a 1GB retention-size setting.
- Alertmanager: 1Gi.

Grafana references the independently managed `project15-grafana-admin` Secret
in namespace `monitoring`, using keys `admin-user` and `admin-password`.
Credential values are not stored in Helm values, dashboards or Git.

The monitoring installation and memory upgrade verified that the application
Helm release and the original application and monitoring PVC identities and
specifications were preserved.

## Application metrics

Prometheus scrapes `project15-app.project15.svc.cluster.local:8000/metrics`.
The target was verified UP, with all three metric families present:
- `project15_http_requests_total`
- `project15_http_request_duration_seconds`
- `project15_orders_created_total`

`monitoring/app-metrics-networkpolicy.json` permits TCP 8000 from Prometheus
Pods in the monitoring namespace to application Pods. This policy is managed
separately from the application Helm release.

## Application dashboard

Source: `monitoring/dashboards/project15-application.json`.
Provisioning ConfigMap: `monitoring/app-dashboard-configmap.json`.
Dashboard UID: `project15-application`.

Six panels were verified displaying data: request rate, HTTP 5xx percentage,
p95 response time, orders during the selected time range, scrape availability,
and request rate by endpoint. Health checks contribute to recorded traffic.

## Local Grafana access

Run in a dedicated WSL terminal:

    kubectl --context=minikube --namespace=monitoring port-forward --address=127.0.0.1 service/project15-monitoring-grafana 3000:80

Open http://localhost:3000/d/project15-application and use the credentials
stored in the password manager. Keep the forwarding terminal open.
Stop forwarding with Ctrl+C. Restart it after a Grafana Pod replacement.

## Memory incident

Grafana was OOMKilled with exit code 137 under the initial 384Mi limit.
The configured request was raised to 256Mi and the limit to 768Mi.
The controlled Helm upgrade completed successfully, and the application
dashboard subsequently loaded with data. Longer-term stability remains
to be observed.

## Alerting verification and remaining work

`Project15MetricsUnavailable` is loaded, has evaluation health `ok`,
and was verified `inactive` while the application target was UP.
Its expression is:

    up{job="project15-app"} == 0 or absent(up{job="project15-app"})

The configured pending duration is 2 minutes.
On 2026-10-19, a temporary synthetic PrometheusRule was verified firing in Prometheus, and the same uniquely labelled alert was received by Alertmanager. The temporary rule was removed after verification. Application Deployments and PVCs were unchanged. This verifies the internal delivery path; the actual application-outage condition and its 2-minute pending duration were not exercised.
No external notification destination has been configured or verified.

## Shutdown

Stop the Grafana port-forward before the normal environment shutdown.
Stopping Minikube stops monitoring workloads while preserving their PVCs.
Do not uninstall the release or delete PVCs as part of routine shutdown.
