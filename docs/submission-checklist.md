# Project 15 — submission evidence and remaining gaps

Evidence reviewed on 2026-10-23. This checklist distinguishes demonstrated behavior from incomplete requirements. It is not a statement of full compliance.

## Demonstrated evidence

| Area | Evidence | Scope |
| --- | --- | --- |
| Complete Jenkins delivery | Build #14, 2026-10-22; DevOps `3806299`, App `e004bae` | Build, gates, GHCR publication, guarded Helm deployment and post-deployment checks |
| Dockerfile lint | Archived `hadolint.json`: zero findings | Pinned Hadolint; warning/error gate; negative fixture rejected |
| Python SCA | Archived `pip-audit.json`: 59 dependencies, zero skipped, zero vulnerability entries | pip-audit; not the specifically named Dependency-Check/Snyk tools |
| Unit tests | 44 tests and flake8 passed at the recorded application checkpoint; Jenkins #14 reports no test failures | Product, cart, order, health, metrics, response-header and security-report tests |
| Secret detection | Both Git histories passed GitLeaks; synthetic credential rejected with redaction | Repository history and separately checked new configuration |
| SAST | SonarQube Quality Gate passed in successful pipeline | Configured project analysis |
| Kubernetes configuration | Checkov: 184 passed, zero failed, one documented DB UID suppression at the verified checkpoint | Strict failure on failing checks; not a severity-metadata-based HIGH-only evaluation |
| Container security | Trivy and Grype gates passed in successful build | CRITICAL gates; outstanding HIGH findings are not declared resolved |
| SBOM | Archived CycloneDX `sbom.json` | Syft-generated component inventory |
| API smoke tests | Archived `newman.xml`; collection has three GET requests and 15 assertions | Liveness, readiness and product listing |
| Passive API security | Archived ZAP summary: coverage verified; HIGH/MEDIUM/LOW/INFORMATIONAL all zero | Three GET operations; no active scans |
| Live report endpoints | `/api/security/sbom` and `/api/security/scan-report` returned JSON with HTTP 200 | Availability demonstrated; correspondence to the latest image still needs a provenance check |
| Deployment safety | Guarded deployment with backup and preservation checks; previous isolated DB restore test | Retained application data and protected backup files |
| Monitoring | Application metrics collected, Grafana dashboard viewed | Prometheus, Grafana, Alertmanager |
| Alert routing | Synthetic alert fired in Prometheus and reached Alertmanager; temporary rule removed | Internal delivery; no external notification delivery demonstrated |
| Logging | Application and database entries reached Loki and were viewed in Grafana | Alloy has restricted Pod/log permissions; unauthorized Loki access blocked in three attempts |
| Terraform workspaces | `dev`, `staging`, `prod` namespaces Active; all three plans reported no changes on 2026-10-22 | Namespace module in an existing cluster |
| State backend | Separate dev/prod PostgreSQL state rows inspected; staging apply and subsequent plans succeeded | Separate local PostgreSQL backend, not off-host HA storage |
| GitOps | `project15-root` and `project15-gitops` reported Synced/Healthy at commit `775a63a` | Separate namespace from Jenkins/Helm; static pinned image |
| Documentation | DevOps README architecture and evidence; specialized operational guides | Review any older guide commands before using them |

## Requirements needing closure or explicit disclosure

- **Named SCA tool:** the specification names OWASP Dependency-Check or Snyk. pip-audit is implemented and verified instead. Dependency-Check database initialization did not complete. Do not mark the named-tool requirement as met without acceptance of the substitution or a verified named-tool run.
- **Terraform provisioning:** the current module creates namespaces in an existing Minikube cluster. It does not provision that cluster. PostgreSQL is a supported Terraform backend but differs from the S3/Terraform Cloud options named in the specification.
- **GitHub Actions:** application test/security workflows exist. The complete demonstrated publication/deployment pipeline runs in Jenkins; an equivalent Actions delivery path has not been demonstrated.
- **External notifications:** configure and test a recipient/channel if required. Receipt by Alertmanager alone is not an external notification.
- **Branch protection:** obtain evidence of active branch protection/rulesets and required checks for the private repositories. Current enforcement has not been verified here.
- **License/compliance policy:** SBOM and vulnerability reports exist. Automated license-allow/deny enforcement and a consolidated compliance report have not been demonstrated.
- **DAST scope:** only the documented passive GET scope is verified. No full active/authenticated/write-operation security coverage is claimed.
- **Live business integration:** write behavior has unit tests. The current Newman deployment smoke test does not exercise the full cart-to-order flow.
- **Report provenance:** compare live report content hashes to the intended build artifacts before claiming that the endpoints serve the latest build reports.
- **Historical findings:** review outstanding HIGH container findings and retain an honest remediation/acceptance explanation.
- **Argo CD guide:** older instructions refer to a local image tag; check and update them against the current digest-pinned Application manifests.

## Final packaging checks

- [ ] Record the final Git commit of each repository and identify the last verified functional build.
- [ ] Ensure the examiner can access both private repositories.
- [ ] Retain Jenkins build #14 and its artifacts for the demonstration, subject to available disk space.
- [ ] Verify a clean working tree and that intended commits reached GitHub.
- [ ] Keep raw logs, credentials, state files, plans and database dumps out of the submission repository.
- [ ] Recheck application readiness, Argo status, dashboard and logs before the presentation.
- [ ] Present this checklist with incomplete items visible rather than describing them as finished.
- [ ] Rehearse the demonstration and explanation in the demo guide.
