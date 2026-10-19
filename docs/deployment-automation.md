# Minikube deployment automation

The Jenkins sequence is:
security and quality gates, image build and scans, GHCR publication,
guarded deployment of that build's digest, then Newman API smoke tests.

## Deployment scope

Context: minikube. Namespace and Helm release: project15.
This updates an existing deployed release; it does not bootstrap a cluster.

The helper verifies publication metadata and allows only the application
container image field to differ from the installed Helm manifest.
Unexpected chart or resource changes stop deployment for review.

## Data and credential safeguards

Before upgrade, the helper:
- Records both PVC identities, specifications and Bound volume bindings.
- Records database Deployment configuration and credential Secret data in memory.
- Creates a mode-600 PostgreSQL backup outside Git and checks archive readability.
- Rechecks Helm revision, PVCs, Secrets and database configuration.

Helm uses atomic upgrade, readiness waiting, a five-minute timeout and
two retained revisions. Database configuration and credential values are
not passed as generated overrides; the override contains image settings only.

After upgrade, the helper verifies the published digest, Deployment readiness,
unchanged PVCs, Secrets and database specification, plus HTTP 200 from
liveness and database readiness. Evidence is saved as deployment.json.
Backup archives and protected Helm logs remain under:
~/.local/state/project15-deployments/

Newman then tests the new active deployment through Ingress and exports JUnit.

## Failure handling

Helm atomic rollback handles rollout failures.
A subsequent verification or API-test failure stops the pipeline and requires
inspection of the deployed release. It does not automatically restore data.
Helm rollback does not revert database schema changes or external credentials.

## Verified checkpoint: 2026-10-19

The helper was manually invoked with the image published by Jenkins build 8.
It deployed Helm revision 14 and verified preserved PVCs, credential Secrets
and database configuration, ready Deployments and HTTP 200 health endpoints.

The combined Jenkins deployment and Newman sequence still requires verification.
