# Project 15: local Argo CD checkpoint

The existing Helm release in namespace `project15` remains the baseline. This GitOps check uses a separate namespace and release (`project15-gitops`), so Argo CD does not take ownership of Helm-managed objects or the existing PVC.

## Chart contract

When `database.existingSecret` is empty, Helm creates the same Secret as before from `database.password`. When it names a Secret, the chart reads `POSTGRES_PASSWORD` and `DATABASE_URL` from that existing Secret and does not render a Secret. Never commit either value.

The local Application in `argocd/project15-local.yaml` uses `project15-app:db-recovery-v0.9.0` already loaded into Minikube, a separate Ingress host `project15-gitops.local`, and `ClusterIP` for the app. `main` is the Git source; do not apply the Application before pushing the chart changes. No automatic prune is configured for this local stateful demonstration.

## Preconditions and checks

```bash
cd ~/projects/project15-devops
helm lint helm/project15 --set-file database.password="$HOME/.config/project15/postgres-password"
helm lint helm/project15 --set database.existingSecret=project15-gitops-database
helm template project15-gitops helm/project15 \
  --set database.existingSecret=project15-gitops-database \
  --set app.image.tag=db-recovery-v0.9.0 \
  --set app.service.type=ClusterIP \
  --set ingress.host=project15-gitops.local > /tmp/project15-gitops-rendered.yaml
```

The baseline image and database remain in Minikube. Check cluster capacity before installing Argo CD. Kubernetes v1.37.0 is newer than the Kubernetes versions listed as tested for Argo CD 3.5; document the actual local result and do not treat this setup as a compatibility guarantee for EKS.

## Install Argo CD

Use a pinned official install manifest, with server-side apply for its large CRDs:

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.2/manifests/install.yaml
kubectl -n argocd rollout status deployment/argocd-repo-server --timeout=300s
kubectl -n argocd rollout status statefulset/argocd-application-controller --timeout=300s
kubectl -n argocd get pods
```

## Read-only repository access

Create a dedicated key for the private `project15-devops` repository. Never reuse a personal SSH key. GitHub deploy keys are limited to one repository and read-only by default. Store the unencrypted key with mode 600 and restrict access to the local Kubernetes cluster.

```bash
if [ ! -f "$HOME/.ssh/project15_argocd_deploy" ]; then
  ssh-keygen -q -t ed25519 -N '' -C project15-argocd-minikube \
    -f "$HOME/.ssh/project15_argocd_deploy"
fi
chmod 600 "$HOME/.ssh/project15_argocd_deploy"
gh api -X POST repos/kfir-dev/project15-devops/keys \
  -f title='Project 15 Argo CD Minikube' \
  -f key="$(cat "$HOME/.ssh/project15_argocd_deploy.pub")" \
  -F read_only=true --jq '.id'

kubectl -n argocd create secret generic project15-devops-repo \
  --from-literal=type=git \
  --from-literal=url=git@github.com:kfir-dev/project15-devops.git \
  --from-file=sshPrivateKey="$HOME/.ssh/project15_argocd_deploy" \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n argocd label secret project15-devops-repo \
  argocd.argoproj.io/secret-type=repository
```

Do not paste the private key into chat, logs, or Git. Check the Argo CD repository status before syncing. Keep SSH host verification enabled.

## Database credentials for the separate namespace

Generate a different password once and keep it outside Git. Create the namespace and Secret before allowing Argo CD to sync:

```bash
install -d -m 700 "$HOME/.config/project15"
umask 077
if [ ! -f "$HOME/.config/project15/argocd-postgres-password" ]; then
  printf %s "$(openssl rand -hex 24)" > "$HOME/.config/project15/argocd-postgres-password"
fi
python3 - <<'PY' > "$HOME/.config/project15/argocd-database-url"
from pathlib import Path
from urllib.parse import quote
from sys import stdout
password = (Path.home() / '.config/project15/argocd-postgres-password').read_text().strip()
stdout.write(f'postgresql+psycopg://project15:{quote(password, safe="")}@project15-gitops-database:5432/project15')
PY
kubectl create namespace project15-gitops --dry-run=client -o yaml | kubectl apply -f -
kubectl -n project15-gitops create secret generic project15-gitops-database \
  --from-file=POSTGRES_PASSWORD="$HOME/.config/project15/argocd-postgres-password" \
  --from-file=DATABASE_URL="$HOME/.config/project15/argocd-database-url" \
  --dry-run=client -o yaml | kubectl apply -f -
```

For this new database, generate the password only once. Reuse its files after a restart. If the Secret already exists, do not regenerate the password against its PVC.

## Sync and verify

After the chart and Application manifest are committed and pushed to `main`:

```bash
kubectl apply -f argocd/project15-local.yaml
kubectl -n argocd get application project15-gitops
kubectl -n project15-gitops get pods,deploy,svc,pvc,ingress
kubectl -n project15-gitops exec deployment/project15-gitops-app -c app -- \
  flask --app run.py db current
```

The application should become `Synced` and `Healthy`. Test the GitOps Ingress separately with `Host: project15-gitops.local`. Verify a read-only deploy key and absence of credentials in the staged diff before commit. Stop Minikube without deleting either PVC.
