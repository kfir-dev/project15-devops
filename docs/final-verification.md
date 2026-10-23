# Final operational verification — Project 15

Evidence reviewed on 2026-10-24. This is a verified operational checkpoint,
not a declaration that every specification item is complete.

## Functional delivery checkpoint

Jenkins `project15-ci` build **#16** completed successfully. Its page records:

- DevOps revision: `8eca62d70ca8fadac6026569615638e45511519d`.
- Application revision: `b9e9381222eedcbc8547f66d982945b2a716ef4d`.
- Deployed image: `ghcr.io/kfir-dev/project15-app@sha256:0a330aeafd54d09efaa852c1ca10ba1687e0635515643948048c6d6d05f4aff2`.
- Retained test, SBOM, vulnerability scan, publication, deployment, Newman
  and passive ZAP artifacts, including `sbom-binding.json` and
  `security-reports-publication.json`.

The report publisher's 28 standard-library tests passed on Linux before
the successful build. They exercise image binding, transfer validation,
internal legacy symlinks, rejection of unsafe links and restoration paths.

## Runtime verification

All seven operational checks passed:

| Check | Observed evidence |
| --- | --- |
| API and artifact provenance | Five baseline GETs and three GitOps GETs returned HTTP 200 with expected response schemas. Baseline responses had the nosniff header. Canonical JSON hashes of both live report endpoints matched retained build #16 reports; the deployed image reference matched that build. |
| Storage | All eight PVCs were Bound; original baseline volume bindings were preserved. |
| GitOps | Root and child Argo CD Applications were Synced and Healthy. |
| Metrics | Application scrape target was UP; HTTP request, latency and order metric families were present. |
| Grafana | Health API and Grafana database were OK. Dashboard rendering was not inspected during this recheck; earlier visual verification is recorded in the monitoring guide. |
| Logs | Both application and database logs were queryable in Loki. Latest retained Loki timestamps matched current source Pod logs within two minutes. The database source itself had been quiet for about 45 minutes. |
| CI services | Jenkins, SonarQube and its PostgreSQL container were healthy; SonarQube reported UP. |

The logging check compares source and Loki timestamps over the configured
48-hour retention window. It does not demand new log messages from an idle
database. It is a delivery checkpoint, not a continuous losslessness test.

Protected runtime evidence is retained locally outside Git. No raw report
snapshots, application log contents or credentials are included here.

## Terraform verification

The existing PostgreSQL backend was started with its state volume retained.
`terraform validate` returned valid with zero errors and zero warnings.
Detailed plans for `dev`, `staging` and `prod` each reported **no changes**.
The selected workspace was preserved. No apply, initialization, workspace
creation or infrastructure change was performed during this verification.

Terraform currently manages namespaces in an existing Minikube cluster.
It does not provision the cluster. The PostgreSQL backend differs from
the S3/Terraform Cloud options named by the specification.

## Repository and submission evidence

Both repositories are public. Protected-main delivery was exercised through
[PR #1](https://github.com/kfir-dev/project15-devops/pull/1) and
[PR #2](https://github.com/kfir-dev/project15-devops/pull/2), each merged after
the required secret-history check passed. See [repository governance](repository-governance.md).

Preserve build #16 and its artifacts for the demonstration. Refer to the
[submission checklist](submission-checklist.md) for outstanding items and
the [demo guide](demo-guide.md) for rehearsal. External alert notifications,
named-tool SCA acceptance, broader delivery/security coverage and automated
license-policy enforcement remain incomplete or unverified as documented.
