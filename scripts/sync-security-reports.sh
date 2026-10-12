#!/usr/bin/env bash
set -Eeuo pipefail

REPO="kfir-dev/project15-app"
WORKFLOW="container-security.yml"
NAMESPACE="project15"
PVC="project15-security-reports"
POD="security-reports-sync-$(cat /proc/sys/kernel/random/uuid | cut -c 1-8)"
TMP_DIR="$(mktemp -d)"
POD_CREATED=false
POD_CREATION_ATTEMPTED=false
VERSION_CREATED=false
VERSION_ACTIVATED=false

cleanup() {
  if [[ "$VERSION_CREATED" == true &&
        "$VERSION_ACTIVATED" == false &&
        "$POD_CREATED" == true &&
        "$RUN_ID" =~ ^[0-9]+$ ]]; then
    kubectl exec -n "$NAMESPACE" "$POD" -- sh -ec '
      version="$1"
      active="$(readlink /reports/current || true)"
      if [ "$active" != "versions/$version" ]; then
        temporary="$(readlink /reports/current.new || true)"
        if [ "$temporary" = "versions/$version" ]; then
          rm -f /reports/current.new
        fi
        rm -rf "/reports/versions/$version"
      fi
    ' sh "$RUN_ID" >/dev/null 2>&1 || true
  fi

  if [[ "$POD_CREATION_ATTEMPTED" == true ]]; then
    kubectl delete pod "$POD" -n "$NAMESPACE" \
      --ignore-not-found --wait=true >/dev/null 2>&1 || true
  fi
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "Checking Kubernetes context..."
[[ "$(kubectl config current-context)" == "minikube" ]] || {
  echo "ERROR: Kubernetes context is not minikube"
  exit 1
}

echo "Finding latest successful workflow..."
RUN_ID="$(gh run list \
  --repo "$REPO" \
  --workflow "$WORKFLOW" \
  --branch main \
  --status success \
  --limit 1 \
  --json databaseId \
  --jq '.[0].databaseId')"

[[ "$RUN_ID" =~ ^[0-9]+$ ]] || {
  echo "ERROR: No successful workflow run found"
  exit 1
}

echo "Verifying workflow commit..."
MAIN_SHA="$(gh api "repos/$REPO/commits/main" --jq '.sha')"

RUN_SHA="$(gh run view "$RUN_ID" \
  --repo "$REPO" \
  --json headSha \
  --jq '.headSha')"

if [[ "$MAIN_SHA" != "$RUN_SHA" ]]; then
  echo "ERROR: Security reports are not from the latest main commit"
  echo "Main: $MAIN_SHA"
  echo "Run:  $RUN_SHA"
  exit 1
fi

echo "Commit verified: $RUN_SHA"

echo "Downloading reports from run $RUN_ID..."
gh run download "$RUN_ID" \
  --repo "$REPO" \
  --name security-reports \
  --dir "$TMP_DIR"

echo "Validating reports..."
python3 - "$TMP_DIR" <<'PY'
import json
import sys
from pathlib import Path

directory = Path(sys.argv[1])

sbom = json.loads((directory / "sbom.json").read_text())
scan = json.loads((directory / "scan-report.json").read_text())

assert sbom.get("bomFormat") == "CycloneDX"
assert len(sbom.get("components", [])) > 0
assert isinstance(scan.get("Results"), list)
assert len(scan["Results"]) > 0

print("SBOM components:", len(sbom["components"]))
print("Trivy scan results:", len(scan["Results"]))
PY

echo "Checking PVC..."
kubectl get pvc "$PVC" -n "$NAMESPACE" \
  -o jsonpath='{.status.phase}' | grep -qx Bound

echo "Checking temporary pod name..."
if kubectl get pod "$POD" -n "$NAMESPACE" >/dev/null 2>&1; then
  echo "ERROR: Pod $POD already exists. Aborting."
  exit 1
fi

echo "Creating temporary writer pod..."
POD_CREATION_ATTEMPTED=true
kubectl run "$POD" \
  -n "$NAMESPACE" \
  --image=busybox:1.36 \
  --restart=Never \
  --overrides="{
    \"spec\": {
      \"automountServiceAccountToken\": false,
      \"containers\": [{
        \"name\": \"$POD\",
        \"image\": \"busybox:1.36\",
        \"command\": [\"sh\", \"-c\", \"sleep 3600\"],
        \"securityContext\": {
          \"allowPrivilegeEscalation\": false,
          \"capabilities\": {\"drop\": [\"ALL\"]},
          \"seccompProfile\": {\"type\": \"RuntimeDefault\"}
        },
        \"volumeMounts\": [{
          \"name\": \"reports\",
          \"mountPath\": \"/reports\"
        }]
      }],
      \"volumes\": [{
        \"name\": \"reports\",
        \"persistentVolumeClaim\": {
          \"claimName\": \"$PVC\"
        }
      }]
    }
  }"

POD_CREATED=true

kubectl wait \
  --for=condition=Ready \
  "pod/$POD" \
  -n "$NAMESPACE" \
  --timeout=120s

echo "Copying reports into version $RUN_ID..."

kubectl exec -n "$NAMESPACE" "$POD" -- \
  mkdir "/reports/versions/$RUN_ID"

VERSION_CREATED=true

kubectl cp "$TMP_DIR/sbom.json" \
  "$NAMESPACE/$POD:/reports/versions/$RUN_ID/sbom.json"

kubectl cp "$TMP_DIR/scan-report.json" \
  "$NAMESPACE/$POD:/reports/versions/$RUN_ID/scan-report.json"

echo "Verifying uploaded reports..."

for file in sbom.json scan-report.json; do
  LOCAL_HASH="$(sha256sum "$TMP_DIR/$file" | awk '{print $1}')"

  REMOTE_HASH="$(kubectl exec -n "$NAMESPACE" "$POD" -- \
    sha256sum "/reports/versions/$RUN_ID/$file" | awk '{print $1}')"

  if [[ "$LOCAL_HASH" != "$REMOTE_HASH" ]]; then
    echo "ERROR: Checksum mismatch for $file"
    exit 1
  fi
done

echo "Activating report version $RUN_ID..."

kubectl exec -n "$NAMESPACE" "$POD" -- sh -ec '
  version="$1"
  chmod 644 "/reports/versions/$version/"*.json
  if [ -e /reports/current.new ] || [ -L /reports/current.new ]; then
    echo "ERROR: Temporary current.new link already exists"
    exit 1
  fi
  ln -s "versions/$version" /reports/current.new
  test -s /reports/current.new/sbom.json
  test -s /reports/current.new/scan-report.json
  mv -Tf /reports/current.new /reports/current
' sh "$RUN_ID"

VERSION_ACTIVATED=true
echo "Security reports synchronized from run $RUN_ID"
