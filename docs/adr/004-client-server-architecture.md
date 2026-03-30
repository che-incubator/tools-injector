# ADR-004: Client-server architecture for inject-tool

**Date:** 2026-04-03
**Status:** Proposed

## Context

`inject-tool.py` requires python3, but many workspace containers (Alpine-based, minimal images) don't have it. The python3 fallback image (ADR-001) creates a chicken-and-egg problem: you can't inject python3 without python3. The `inject-tool init` feature (ADR-003) is unusable in these containers.

## Decision

Replace the python3-dependent CLI with a client-server split:

- **Service** (`inject-tool-service`) — a Python HTTP server (stdlib `http.server`) running as a single-replica Deployment. Contains all patching logic extracted from `inject-tool.py`, the tool registry, and uses the pod's ServiceAccount for K8s API access. Endpoints: `POST /inject`, `POST /remove`, `GET /list`, `POST /init`, `GET /healthz`.

- **Client** (`inject-tool`) — a ~70-line POSIX shell script delivered via ConfigMap. Translates CLI commands to HTTP requests using `curl` or `wget` (no python3 dependency). Reads `DEVWORKSPACE_NAME`/`DEVWORKSPACE_NAMESPACE` from env. Service URL defaults to `http://inject-tool-service:8080`.

For `init`, the client scans `/projects/*/.che/inject-tools.json` locally and POSTs the raw configs to the service, which handles resolution and patching.

This is a PoC. No hot-inject support, no authentication between client and service, no migration path from the python3 CLI.

## Consequences

- Zero runtime dependencies in workspace containers — any container with `curl` or `wget` can use inject-tool.
- Service uses minimal RBAC (get/list/patch on DevWorkspaces in its namespace).
- Service is ClusterIP only — relies on Kubernetes network isolation for security.
- Adds operational complexity: a Deployment, Service, ServiceAccount, and RBAC resources per namespace.
- `setup.sh` is extended to deploy all service resources.
