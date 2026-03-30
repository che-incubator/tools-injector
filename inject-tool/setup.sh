#!/usr/bin/env bash
# setup.sh <namespace>
#
# Creates a ConfigMap with the inject-tool shim and Python3 script,
# labeled for DWO automount. After running this, every workspace in the
# namespace will have the tool available at /usr/local/bin/inject-tool.
set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace>}"
CM_NAME="inject-tool"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[[ -f "${SCRIPT_DIR}/inject-tool" ]] || {
  echo "ERROR: inject-tool shim not found in ${SCRIPT_DIR}" >&2
  exit 1
}
[[ -f "${SCRIPT_DIR}/inject-tool.py" ]] || {
  echo "ERROR: inject-tool.py not found in ${SCRIPT_DIR}" >&2
  exit 1
}
[[ -f "${SCRIPT_DIR}/registry.json" ]] || {
  echo "ERROR: registry.json not found in ${SCRIPT_DIR}" >&2
  exit 1
}

echo "Creating ConfigMap '${CM_NAME}' in namespace '${NAMESPACE}'..."

kubectl create configmap "${CM_NAME}" \
  --from-file=inject-tool="${SCRIPT_DIR}/inject-tool" \
  --from-file=inject-tool.py="${SCRIPT_DIR}/inject-tool.py" \
  --from-file=registry.json="${SCRIPT_DIR}/registry.json" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Labeling for DWO automount..."
kubectl label configmap "${CM_NAME}" \
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

REGISTRY_CM_NAME="tools-injector-registry"

echo ""
echo "Creating ConfigMap '${REGISTRY_CM_NAME}' in namespace '${NAMESPACE}'..."

kubectl create configmap "${REGISTRY_CM_NAME}" \
  --from-file=registry.json="${SCRIPT_DIR}/registry.json" \
  -n "${NAMESPACE}" \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Labeling registry ConfigMap..."
kubectl label configmap "${REGISTRY_CM_NAME}" \
  app.kubernetes.io/part-of=tools-injector \
  -n "${NAMESPACE}" \
  --overwrite

echo ""
echo "Done."
echo ""
echo "ConfigMaps created in namespace '${NAMESPACE}':"
echo "  inject-tool             — automounted into every workspace at /usr/local/bin/"
echo "  tools-injector-registry — exposes tool registry to Che Dashboard"
echo ""
echo "Usage (from inside a workspace terminal):"
echo "  inject-tool --help"
