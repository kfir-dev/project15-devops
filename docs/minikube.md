# Project 15 on Minikube

Run these commands in Ubuntu WSL, with Docker Desktop integration enabled.

## Prepare image and Ingress

```bash
cd ~/projects/project15-app
docker build -t project15-app:local .
minikube image load project15-app:local
minikube addons enable ingress
```

## Install

Run commands from the repository root after preparing the image and Ingress.

### External database credentials

Before the first installation, provision an Opaque Secret named
`project15-database-external` in namespace `project15`, independently of Helm.
Required keys are `POSTGRES_PASSWORD` and `DATABASE_URL`. The URL must use
the configured database user, database name and service, with the same
password correctly URL-encoded.

Keep credentials out of Git, Helm values, command arguments and terminal
output. Keep the password field empty in Helm values.

For an existing PVC, changing the Secret alone does not change the PostgreSQL
role password. First test a protected backup by restoring it into isolated
temporary storage. Then coordinate the role password and both Secret keys
during an application maintenance window.

Check that the external Secret exists without displaying its contents:

```bash
kubectl --context=minikube -n project15 get secret project15-database-external -o name
```

Provision an image pull Secret named `project15-ghcr-pull` in namespace
`project15` before deploying the private GHCR image. Use a separate GitHub
classic token with `read:packages` only. Keep its value outside Git,
Helm values, terminal output and command arguments.

Install or upgrade using the checked-in local overrides:

```bash
helm upgrade --install project15 helm/project15 --kube-context minikube --namespace project15 --create-namespace -f helm/project15/values-local.yaml --history-max 2 --wait --timeout 5m
```

Retain two clean Helm revisions. This retention setting does not rotate
passwords or clean Git history. Helm rollback does not revert the external
Secret or the PostgreSQL role password; verify compatibility before rollback.

### Verified rotation checkpoint: 2026-10-18

- A protected backup was successfully restored in an isolated temporary Pod.
- Both Deployments use the external Secret.
- The PostgreSQL password and both Secret keys were rotated.
- The new password authenticated and executed SELECT 1; the old password
  was rejected.
- Application readiness returned HTTP 200 and checks the database.
- Both original PVC volume bindings were preserved.
- Only clean Helm revisions 11 and 12 remained; revision 12 was deployed.
- The legacy Secret, temporary restore Pod and temporary credential recovery
  files were removed. The tested backup was retained outside Git.

## Verify

```bash
kubectl -n project15 get pods,svc,pvc,ingress
kubectl -n project15 rollout status deployment/project15-database
kubectl -n project15 rollout status deployment/project15-app
kubectl -n project15 exec deployment/project15-app -- flask --app run.py db current
```

To test the Ingress itself, run this in a terminal and leave it open:

```bash
kubectl -n ingress-nginx port-forward service/ingress-nginx-controller 8080:80
```

In another WSL terminal:

```bash
curl --silent --show-error --fail-with-body \
  --header 'Host: project15.local' \
  http://127.0.0.1:8080/health/ready
```

The application uses port 8000 and stores PostgreSQL data on a PersistentVolumeClaim. An init container waits for PostgreSQL before the application runs its startup migration. With one application replica, migrations run once during startup. Keep that replica count until migrations have a separate job.

## Stop

```bash
minikube stop
```

Stopping preserves the cluster and PostgreSQL data. Do not delete the Minikube cluster or PVC when you want to resume later.

## Verified GHCR deployment checkpoint: 2026-10-19

- Jenkins build 7 passed, including Helm lint and Checkov.
- Checkov reported 184 passed, 0 failed and 1 documented database UID exception.
- A fresh protected PostgreSQL backup was created and its archive was readable.
- Helm revision 13 was deployed successfully.
- The application uses the tested GHCR digest:
  `sha256:7375a18e93431860271c55f0bc6f5df4c8eef03e63983492d511206e490b0fab`.
- PostgreSQL retains its existing image digest:
  `sha256:d4a8e1f88f475ee3e0137fa89d21ebc59f6c6ab16bf369ee92907607cc3455ae`.
- Both Deployments are ready and use the external database Secret.
- PostgreSQL UID/GID 999, fsGroup 999 and Recreate strategy were preserved.
- Both original PVC volume bindings were preserved.
- Application liveness and database readiness returned HTTP 200.

This deployment was performed as a controlled manual Helm upgrade.
See deployment-automation.md for the subsequent automation work.
