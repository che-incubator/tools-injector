#!/usr/bin/env bash
# setup-dev.sh <namespace>
#
# Development setup: deploys inject-tool to a single namespace for
# local development and testing. Unlike setup.sh, this does NOT use
# Che operator replication labels — the ConfigMap stays local and
# won't be overwritten by the operator's reconciler.
#
# For production cluster-wide deployment, use setup.sh instead.
set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace>}"
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

echo ""
echo "Done."
echo ""
echo "ConfigMap 'inject-tool' created in namespace '${NAMESPACE}'."
echo "Automounted into every workspace at /usr/local/bin/."
echo ""
echo "Note: This is a local dev deployment. On clusters where setup.sh was"
echo "already run, the Che operator may overwrite this ConfigMap. See README."
echo ""
echo "Usage (from inside a workspace terminal):"
echo "  inject-tool --help"
