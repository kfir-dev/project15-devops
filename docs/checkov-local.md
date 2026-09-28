# Checkov local review

Render the same namespace and values used by the local Argo CD Application. No secret value is rendered here.

```bash
cd ~/projects/project15-devops
helm lint helm/project15 --set database.existingSecret=project15-gitops-database
helm template project15-gitops helm/project15 \
  --namespace project15-gitops \
  --set database.existingSecret=project15-gitops-database \
  --set app.image.tag=db-recovery-v0.9.0 \
  --set app.service.type=ClusterIP \
  --set ingress.host=project15-gitops.local \
  > /tmp/project15-checkov-input.yaml
docker run --rm --volume /tmp/project15-checkov-input.yaml:/scan.yaml:ro \
  bridgecrew/checkov:3.3.8 --file /scan.yaml --framework kubernetes \
  --compact > /tmp/project15-checkov-result.txt 2>&1
scan_status=$?
printf 'Checkov exit: %s\n' "$scan_status"
head -n 12 /tmp/project15-checkov-result.txt
grep -B 1 -A 2 'FAILED for resource:' /tmp/project15-checkov-result.txt
```

The first scan found 154 passing and 31 failing checks. The original render omitted `--namespace`, so CKV_K8S_21 described the `default` namespace even though Argo CD deploys to `project15-gitops`. Explicit namespace metadata makes the scan represent the actual deployment. The app init container now has the same restricted capabilities and read-only root as the main app; both pods disable service account token mounting and set RuntimeDefault seccomp.

Remaining findings must be reviewed individually. Local images intentionally use `imagePullPolicy: Never`, and image digests require the future registry. The official PostgreSQL image performs filesystem initialization as root: do not force non-root or read-only root on the existing persistent volume without a migration and runtime test. Secrets as environment variables, database capabilities, and NetworkPolicy require separate changes and verification. Do not skip checks to make the exit code green.

Checkov severity thresholds require platform-supplied severity metadata. Until that is available, treat any failing check as a failure; do not claim that the HIGH-only gate has been enforced.
