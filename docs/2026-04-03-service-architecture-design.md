# inject-tool Service Architecture Design

## Goal

Replace the python3-dependent `inject-tool` CLI with a client-server architecture. A dedicated service pod handles all heavy logic (JSON parsing, K8s API calls, patch construction). The workspace-side client becomes a trivial POSIX shell script with zero runtime dependencies beyond `wget` or `curl`.

This is a PoC. No migration path, no backwards compatibility with the python3 CLI, no hot inject support.

## Problem

`inject-tool.py` requires python3, but many workspace containers (Alpine-based, minimal images) don't have it. This creates a chicken-and-egg problem: you can't inject python3 without python3. The `inject-tool init` feature (which reads `.che/inject-tools.json` from project repos) is unusable in these containers.

## Architecture

Two components:

```
Workspace Pod                         inject-tool-service Pod
┌─────────────────────┐    HTTP       ┌──────────────────────────┐
│                     │               │                          │
│  inject-tool (sh)   │── /inject ──> │  Python HTTP server      │
│  reads local config │── /init ────> │  injector.py (core)      │
│  displays results   │── /list ────> │  registry.json           │
│                     │── /remove ──> │  K8s API (ServiceAccount)│
└─────────────────────┘               └──────────────────────────┘
     ConfigMap                             Deployment + Service
     (automount)                           + ServiceAccount + RBAC
```

### Service (`inject-tool-service`)

A Python HTTP server using stdlib `http.server`. Runs as a single-replica Deployment in the namespace. Contains:

- `server.py` — HTTP request routing, JSON parsing, response formatting
- `injector.py` — patching logic extracted from `inject-tool.py`: registry loading, workspace fetching, RFC 6902 patch construction, K8s API PATCH calls
- `registry.json` — tool registry, embedded in the container image

Uses the pod's ServiceAccount token for K8s API access (`/var/run/secrets/kubernetes.io/serviceaccount/token`). Talks to `https://kubernetes.default.svc`.

Resources: 64Mi memory request, 128Mi limit.

### Client (`inject-tool`)

A POSIX shell script (~50-80 lines) delivered via ConfigMap automount to `/usr/local/bin/inject-tool`. Translates CLI commands into HTTP requests:

| Command | HTTP Request |
|---|---|
| `inject-tool opencode tmux` | `POST /inject {"workspace":"...","namespace":"...","tools":["opencode","tmux"]}` |
| `inject-tool list` | `GET /list?workspace=...&namespace=...` |
| `inject-tool remove opencode` | `POST /remove {"workspace":"...","namespace":"...","tools":["opencode"]}` |
| `inject-tool init` | Reads `/projects/*/.che/inject-tools.json`, `POST /init` with configs |
| `inject-tool init --dry-run` | Same with `"dry_run": true` |

HTTP client: tries `curl` first, falls back to `wget`. Both support POST with JSON body and custom headers.

Service URL: defaults to `http://inject-tool-service:8080` (Kubernetes DNS). Overridable via `INJECT_TOOL_SERVICE_URL` env var.

Workspace identity: read from `DEVWORKSPACE_NAME` and `DEVWORKSPACE_NAMESPACE` env vars (injected by DWO into every workspace container).

### `init` Command Flow

1. Client scans `${PROJECTS_DIR:-/projects}/*/.che/inject-tools.json`
2. Client reads each file's content and builds a JSON payload with project name + raw config
3. Client POSTs to `/init`
4. Service resolves registry tool names, merges custom tool definitions, builds patches
5. Service applies merged patch to DevWorkspace CR
6. Client displays result

## API

### `POST /inject`

Request:
```json
{
  "workspace": "picoclaw-terminal",
  "namespace": "kubeadmin-che",
  "tools": ["opencode", "tmux"]
}
```

Response (200):
```json
{"status": "ok", "message": "Patched 2 tools, workspace restarting"}
```

### `POST /remove`

Request:
```json
{
  "workspace": "picoclaw-terminal",
  "namespace": "kubeadmin-che",
  "tools": ["opencode"]
}
```

Response (200):
```json
{"status": "ok", "message": "Removed 1 tool, workspace restarting"}
```

### `GET /list?workspace=<name>&namespace=<ns>`

Response (200):
```json
{
  "tools": [
    {"name": "opencode", "description": "AI coding assistant", "pattern": "init", "injected": true},
    {"name": "tmux", "description": "Terminal multiplexer", "pattern": "init", "injected": false}
  ]
}
```

### `POST /init`

Request:
```json
{
  "workspace": "picoclaw-terminal",
  "namespace": "kubeadmin-che",
  "configs": [
    {
      "project": "picoclaw-terminal",
      "tools": [
        "opencode",
        {
          "name": "dev-tools",
          "image": "quay.io/akurinnoy/picoclaw-terminal/dev-tools:next",
          "binaries": [{"src": "/usr/bin/git", "binary": "git"}]
        }
      ]
    }
  ],
  "dry_run": false
}
```

Response (200):
```json
{"status": "ok", "message": "Discovered 2 tools from 1 project, workspace restarting"}
```

Dry-run response (200):
```json
{"status": "ok", "message": "Dry run: would inject 2 tools", "patch": [...]}
```

### Error Responses

- 400: bad request, unknown tool, invalid JSON
- 404: workspace not found
- 500: K8s API error

Body: `{"status": "error", "message": "..."}`

### `GET /healthz`

Response (200): `{"status": "ok"}`

## Deployment

`setup.sh <namespace>` creates all resources:

### ServiceAccount + RBAC

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: inject-tool-service
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: inject-tool-service
rules:
  - apiGroups: ["workspace.devfile.io"]
    resources: ["devworkspaces"]
    verbs: ["get", "list", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: inject-tool-service
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: inject-tool-service
subjects:
  - kind: ServiceAccount
    name: inject-tool-service
```

### Deployment + Service

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inject-tool-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: inject-tool-service
  template:
    metadata:
      labels:
        app: inject-tool-service
    spec:
      serviceAccountName: inject-tool-service
      containers:
        - name: server
          image: quay.io/akurinnoy/tools-injector/inject-tool-service:next
          ports:
            - containerPort: 8080
          resources:
            requests:
              memory: 64Mi
            limits:
              memory: 128Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 3
---
apiVersion: v1
kind: Service
metadata:
  name: inject-tool-service
spec:
  selector:
    app: inject-tool-service
  ports:
    - port: 8080
      targetPort: 8080
```

### ConfigMap (thin client)

The existing `inject-tool` ConfigMap is updated to contain only the shell client script. Same DWO automount labels and annotations.

## File Layout

```
inject-tool/
├── setup.sh                # deploys service + configmap
├── inject-tool             # thin shell client (ConfigMap content)
├── manifests/
│   ├── deployment.yaml
│   ├── service.yaml
│   └── rbac.yaml
└── service/
    ├── Dockerfile
    ├── server.py           # HTTP server
    ├── injector.py         # patching logic
    └── registry.json       # tool registry
```

## Security

- Service is ClusterIP only — not exposed outside the cluster
- No authentication between client and service — relies on Kubernetes network isolation
- Service uses minimal RBAC: only get/list/patch on DevWorkspaces in its namespace
- No secrets involved

## Not in Scope (PoC)

- Hot inject (`--hot`)
- Authentication between client and service
- Migration from python3 CLI
- Multi-namespace support
- Rate limiting
- TLS between client and service (in-cluster traffic)
