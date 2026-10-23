# Project 15 — demonstration and rehearsal

Updated on 2026-10-24 using successful build #16 and the latest runtime/Terraform checks. Target a 12–15 minute demonstration, followed by questions. Use the already verified environment and artifacts; do not introduce disruptive changes during the presentation.

## Opening explanation

This project delivers a Flask e-commerce API with PostgreSQL through a security-gated Jenkins pipeline. The application and infrastructure are in separate repositories. Jenkins tests the code, scans it and the image, generates an SBOM, publishes to GHCR and deploys the published image digest through Helm. Post-deployment checks run against the application. Prometheus/Grafana provide metrics, and Alloy/Loki provide logs. A separate Argo CD deployment demonstrates GitOps without taking ownership of the baseline Helm release.

## Demonstration sequence

| Time | Show | Explain |
| --- | --- | --- |
| 0–2 min | DevOps README architecture and the two repositories | Boundaries between application code, delivery code, runtime data and credentials |
| 2–6 min | Jenkins build #16 stage overview and artifacts | What each gate checks, which failures block delivery, and why publication follows the pre-deployment gates |
| 6–8 min | Application readiness and product list; a security report endpoint | Readiness includes database connectivity; show sbom-binding.json and security-reports-publication.json, then explain the verified match between live reports and build artifacts |
| 8–10 min | Grafana application dashboard | Request rate, errors, p95 latency, scrape availability and business counter |
| 10–11 min | Grafana Explore, Project15 Loki datasource | Filter `{job="project15-logs", namespace="project15"}`; avoid displaying sensitive raw log entries |
| 11–12 min | Argo CD Applications and separate workload namespace | Git is desired state; baseline and GitOps resources have different owners |
| 12–13 min | Terraform guide and successful no-change plans | Module inputs/outputs, workspace isolation and PostgreSQL backend; disclose that cluster provisioning is not implemented |
| 13–15 min | Submission checklist | Implemented evidence, open requirements and concrete next improvements |

## Safe read-only runtime checks

Run checks individually and inspect their result. These commands do not apply Terraform plans or alter workload specifications.

```bash
kubectl --context=minikube -n project15 get pods,deployments,pvc
```

```bash
kubectl --context=minikube -n argocd get applications
```

```bash
kubectl --context=minikube get namespaces -l app.kubernetes.io/managed-by=terraform
```

```bash
kubectl --context=minikube -n monitoring get pods,pvc
```

```bash
kubectl --context=minikube -n logging get pods,pvc
```

For Grafana, use a separate terminal and keep access on loopback:

```bash
kubectl --context=minikube -n monitoring port-forward --address=127.0.0.1 service/project15-monitoring-grafana 3000:80
```

Open http://localhost:3000 and use the existing protected login. Stop this forward with Ctrl+C when finished. Jenkins is at http://localhost:8080 and SonarQube at http://localhost:9000 when their services are running.

## Questions to rehearse

Answer in your own words before consulting the checkpoints.

1. **What happens from commit to deployment?** Describe checkout, tests, scans, image build, SBOM, image gates, publication, guarded deployment and post-deployment checks. The job was demonstrated through manual Build Now; do not claim an automatic commit trigger unless separately verified.
2. **How do SAST, SCA, container scanning and DAST differ?** Relate them to SonarQube, pip-audit, Trivy/Grype and the limited passive ZAP scope. Each has different coverage.
3. **Why publish and deploy a digest?** A digest identifies content. A tag can be moved. Connect publication metadata to the image actually deployed. An OCI index digest, platform manifest digest and image configuration digest can differ; the binding verifies their relationship instead of treating every SHA256 value as interchangeable.
4. **Does a green build mean the application is secure?** No. Explain configured thresholds, the documented Checkov exception, outstanding HIGH findings and untested scope.
5. **What is an SBOM?** A component inventory supports traceability and downstream analysis. It is not itself proof that components are safe or licenses comply with policy.
6. **What is the difference between liveness and readiness?** Liveness concerns process health; readiness determines whether the application can serve traffic, including its database dependency here.
7. **How are credentials handled?** Explain protected files, Jenkins credentials, Kubernetes Secrets, restricted permissions and avoiding raw configuration/state/log dumps. Kubernetes Secret encoding is not encryption by itself.
8. **What survives a Pod restart?** Explain database PVCs, separate monitoring/logging volumes and external backups. Ephemeral Alloy state may replay logs; do not promise exactly-once collection.
9. **What happens when deployment fails?** Explain the guards and Helm failure handling from the actual deployment script. A database backup is not an automatic data rollback, and Helm rollback does not reverse arbitrary schema changes.
10. **Why are Jenkins and Argo CD both present?** They manage separate namespaces here. Avoid two controllers writing the same resource. Automatic image promotion to GitOps is not part of the demonstrated flow.
11. **What does Terraform actually manage?** One namespace per workspace through a reusable module, with state in a separate PostgreSQL database. The Minikube cluster itself is pre-existing.
12. **What proves observability works?** Collected metrics, a viewed dashboard, an internally delivered test alert, actual Loki entries and a blocked unauthorized connection. External notification delivery remains incomplete.
13. **What would you improve next?** Prioritize exact requirement gaps and operational risks: named SCA tool acceptance, cluster provisioning, backend requirements, external alerts, license policy and wider integration/security testing.

14. **Why did a logging check fail while Loki was healthy?** The old check required messages in the last 15 minutes from both services. The database had produced no new logs in that interval. Comparing the latest source and Loki timestamps confirmed delivery; a quiet service is different from a collector lagging behind its source.
15. **What was fixed in report publication?** HTTP 200 alone did not prove freshness. A new stage publishes reports bound to the deployed image, verifies live content hashes and preserves previous report bytes and safe legacy links for recovery.

## Presentation boundaries

- Use a separate test identity and obtain explicit agreement before a demonstration that changes business data. The default demonstration above uses reads.
- Do not reveal credentials, dump Terraform state, show database contents or paste complete raw scanner logs.
- Keep the original application PVCs and backups. Avoid resets, pruning, volume deletion and resource ownership changes.
- If a live component fails, explain the failure and use the retained verified artifacts. Do not describe old evidence as current live health.
