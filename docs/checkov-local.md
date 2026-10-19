# Checkov local review

Run from the repository root:

```bash
bash ci/scan-kubernetes.sh "$HOME/project15-security-check-reports"
```

The script runs Helm lint, renders the chart with values-local.yaml, and
scans the rendered Kubernetes resources with digest-pinned Checkov 3.3.8.
It does not apply resources or query database credentials.

The render uses the external database Secret by name and rejects rendered
Secret objects. Image references are pinned by digest, and local image
pull policies are Always.

Checkov runs without network access and without platform metadata downloads.
Any failed check, parsing error or empty scan blocks the gate. Severity
metadata is unavailable in this mode; this is not a HIGH-only threshold.

The sole permitted suppression is CKV_K8S_40 on the database Deployment.
See checkov-exceptions.md for its PVC ownership rationale and review trigger.
Unexpected suppressions also block the gate.

The JSON report is retained as checkov-report.json.
Diagnostic stderr is stored locally as checkov.log and is not archived.

## Verified local checkpoint: 2026-10-19

- Passed: 184
- Failed: 0
- Skipped: 1, exactly the documented PostgreSQL UID exception
- Parsing errors: 0

Jenkins build 7 passed the integrated gate and archived checkov-report.json.
The separate project15-gitops deployment is outside this local scan's scope.
