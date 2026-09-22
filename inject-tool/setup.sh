#!/usr/bin/env bash
# setup.sh <operator-namespace>
#
# Production setup: deploys inject-tool and the AI tool registry to
# the Che operator namespace. The Che operator's WorkspacesConfigReconciler
# replicates the inject-tool ConfigMap to all user namespaces automatically.
#
# For development/testing in a personal namespace, use setup-dev.sh instead.
set -euo pipefail

NAMESPACE="${1:?Usage: $0 <operator-namespace>}"
CM_NAME="inject-tool"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

for f in inject-tool inject-tool.py registry.json; do
  [[ -f "${SCRIPT_DIR}/${f}" ]] || {
    echo "ERROR: ${f} not found in ${SCRIPT_DIR}" >&2
    exit 1
  }
done

echo "Creating ConfigMap '${CM_NAME}' in namespace '${NAMESPACE}'..."

kubectl create configmap "${CM_NAME}" \
  --from-file=inject-tool="${SCRIPT_DIR}/inject-tool" \
  --from-file=inject-tool.py="${SCRIPT_DIR}/inject-tool.py" \
  --from-file=registry.json="${SCRIPT_DIR}/registry.json" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Labeling for Che operator replication + DWO automount..."
kubectl label configmap "${CM_NAME}" \
  app.kubernetes.io/part-of=che.eclipse.org \
  app.kubernetes.io/component=workspaces-config \
  controller.devfile.io/mount-to-devworkspace=true \
  controller.devfile.io/watch-configmap=true \
  -n "${NAMESPACE}" \
  --overwrite

echo "Setting mount annotations..."
kubectl annotate configmap "${CM_NAME}" \
  controller.devfile.io/mount-path=/usr/local/bin \
  controller.devfile.io/mount-as=subpath \
  controller.devfile.io/mount-access-mode=0755 \
  -n "${NAMESPACE}" \
  --overwrite

DASHBOARD_CM_NAME="ai-tool-registry"
DASHBOARD_REGISTRY="${SCRIPT_DIR}/../dashboard/registry.json"

if [ -f "${DASHBOARD_REGISTRY}" ]; then
  echo ""
  echo "Creating ConfigMap '${DASHBOARD_CM_NAME}' in namespace '${NAMESPACE}'..."

  kubectl create configmap "${DASHBOARD_CM_NAME}" \
    --from-file=registry.json="${DASHBOARD_REGISTRY}" \
    -n "${NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f -

  echo "Labeling dashboard registry ConfigMap..."
  kubectl label configmap "${DASHBOARD_CM_NAME}" \
    app.kubernetes.io/component=ai-tool-registry \
    app.kubernetes.io/part-of=che.eclipse.org \
    -n "${NAMESPACE}" \
    --overwrite
fi

echo ""
echo "Done."
echo ""
echo "ConfigMaps created in namespace '${NAMESPACE}':"
echo "  inject-tool      — replicated to all user namespaces by Che operator,"
echo "                     automounted into every workspace at /usr/local/bin/"
if [ -f "${DASHBOARD_REGISTRY}" ]; then
  echo "  ai-tool-registry — AI provider registry for Dashboard AI selector"
fi
echo ""
echo "The Che operator will sync 'inject-tool' to user namespaces within ~30s."
echo "Users must restart their workspace to pick up new or updated files."
