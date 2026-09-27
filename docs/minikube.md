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

Create one local password file outside Git. Helm reads it without placing the password in the terminal history.

```bash
install -d -m 700 "$HOME/.config/project15"
# For a new cluster only: create the password once, then keep it for later upgrades.
if [ ! -f "$HOME/.config/project15/postgres-password" ]; then
  umask 077
  openssl rand -hex 24 > "$HOME/.config/project15/postgres-password"
fi
cd ~/projects/project15-devops
helm lint helm/project15 --set-file database.password=$HOME/.config/project15/postgres-password
helm template project15 helm/project15 --set-file database.password=$HOME/.config/project15/postgres-password > /tmp/project15-rendered.yaml
helm upgrade --install project15 helm/project15 \
  --namespace project15 --create-namespace \
  --set-file database.password=$HOME/.config/project15/postgres-password \
  --wait --timeout 5m
```

Keep this password file private (mode 600) and outside Git. Reuse the same password when upgrading an existing PostgreSQL volume; generating a new one will break access to the existing database. The `values.yaml` file contains no password. Kubernetes and Helm release metadata retain the Secret; limit access to the cluster and release namespace.

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
