# Project 15 — submission evidence and remaining gaps

Evidence reviewed on 2026-10-24; see [final verification](final-verification.md). This checklist distinguishes demonstrated behavior from incomplete requirements. It is not a statement of full compliance.

## Demonstrated evidence

| Area | Evidence | Scope |
| --- | --- | --- |
| Complete Jenkins delivery | Build #16; DevOps `8eca62d`, App `b9e9381` | Build, gates, GHCR publication, guarded Helm deployment, image-bound report publication and post-deployment checks |
| Dockerfile lint | Zero findings recorded at #14; #16 Hadolint gate passed with report archived | Pinned Hadolint; warning/error gate; negative fixture rejected |
| Python SCA | 59 dependencies, zero skipped/vulnerabilities recorded at #14; #16 SCA gate passed with report archived | pip-audit; not the specifically named Dependency-Check/Snyk tools |
| Unit tests | 44 tests and flake8 passed at the recorded application checkpoint; Jenkins #16 reports no test failures; all 28 publisher tests passed on Linux | Product, cart, order, health, metrics, response-header and security-report tests |
| Secret detection | Both Git histories passed GitLeaks; synthetic credential rejected with redaction | Repository history and separately checked new configuration |
| SAST | SonarQube Quality Gate passed in successful pipeline | Configured project analysis |
| Kubernetes configuration | Checkov: 184 passed, zero failed, one documented DB UID suppression at the verified checkpoint | Strict failure on failing checks; not a severity-metadata-based HIGH-only evaluation |
| Container security | Trivy and Grype gates passed in successful build | CRITICAL gates; outstanding HIGH findings are not declared resolved |
| SBOM | Archived CycloneDX `sbom.json` | Syft-generated component inventory |
| API smoke tests | Archived `newman.xml`; collection has three GET requests and 15 assertions | Liveness, readiness and product listing |
| Passive API security | Build #16 passive ZAP stage passed and coverage/summary reports were archived; all-zero counts were separately verified at the earlier #14 checkpoint | Three GET operations; no active scans |
| Live report endpoints | `/api/security/sbom` and `/api/security/scan-report` returned JSON with HTTP 200 | Canonical JSON hashes matched build #16 artifacts, and the deployed image reference matched that same build |
| Deployment safety | Guarded deployment with backup and preservation checks; previous isolated DB restore test | Retained application data and protected backup files |
| Monitoring | Application metrics collected, Grafana dashboard viewed | Prometheus, Grafana, Alertmanager |
| Alert routing | Synthetic alert fired in Prometheus and reached Alertmanager; temporary rule removed | Internal delivery; no external notification delivery demonstrated |
| Logging | Application and database entries reached Loki and were viewed in Grafana | Alloy has restricted Pod/log permissions; unauthorized Loki access blocked in three attempts |
| Terraform workspaces | `dev`, `staging`, `prod` namespaces Active; validation passed without errors/warnings and all three plans reported no changes on 2026-10-24 | Namespace module in an existing cluster |
| State backend | Separate dev/prod PostgreSQL state rows inspected; staging apply and subsequent plans succeeded | Separate local PostgreSQL backend, not off-host HA storage |
| GitOps | `project15-root` and `project15-gitops` reported Synced/Healthy during the latest runtime recheck | Separate namespace from Jenkins/Helm; static pinned image |
| Repository governance | Both repositories public; required checks and protected-main settings verified; PRs #1 and #2 merged after checks | PRs required including administrators; no forced pushes/deletions |
| Documentation | DevOps README architecture and evidence; specialized operational guides | Review any older guide commands before using them |

## Requirements needing closure or explicit disclosure

- **Named SCA tool:** the specification names OWASP Dependency-Check or Snyk. pip-audit is implemented and verified instead. Dependency-Check database initialization did not complete. Do not mark the named-tool requirement as met without acceptance of the substitution or a verified named-tool run.
- **Terraform provisioning:** the current module creates namespaces in an existing Minikube cluster. It does not provision that cluster. PostgreSQL is a supported Terraform backend but differs from the S3/Terraform Cloud options named in the specification.
- **GitHub Actions:** application test/security workflows exist. The complete demonstrated publication/deployment pipeline runs in Jenkins; an equivalent Actions delivery path has not been demonstrated.
- **External notifications:** configure and test a recipient/channel if required. Receipt by Alertmanager alone is not an external notification.
- **License/compliance policy:** SBOM and vulnerability reports exist. Automated license-allow/deny enforcement and a consolidated compliance report have not been demonstrated.
- **DAST scope:** only the documented passive GET scope is verified. No full active/authenticated/write-operation security coverage is claimed.
- **Live business integration:** write behavior has unit tests. The current Newman deployment smoke test does not exercise the full cart-to-order flow.
- **Historical findings:** review outstanding HIGH container findings and retain an honest remediation/acceptance explanation.
- **Argo CD guide:** older instructions refer to a local image tag; check and update them against the current digest-pinned Application manifests.

## Final packaging checks

- [x] Record functional build #16 and its application/DevOps revisions; later documentation-only revisions must be identified separately.
- [x] Both repositories are public; final examiner access should still be checked from the submitted links.
- [ ] Retain Jenkins build #16 and its artifacts for the demonstration, subject to available disk space.
- [ ] Verify a clean working tree and that intended commits reached GitHub.
- [ ] Keep raw logs, credentials, state files, plans and database dumps out of the submission repository.
- [ ] Recheck application readiness, Argo status, dashboard and logs before the presentation.
- [ ] Present this checklist with incomplete items visible rather than describing them as finished.
- [ ] Rehearse the demonstration and explanation in the demo guide.
