# Contributing: Adding a New Tool

This guide covers adding a new tool to tools-injector. Tools fall into two categories:

- **Utility tools** (tmux, gh, python3) — injected into workspaces, no dashboard UI
- **AI agent tools** (claude-code, gemini-cli, etc.) — injected into workspaces AND appear in the Che Dashboard AI Provider Selector

## Injection Patterns

- **init** — single static binary at `/usr/local/bin/<binary>`. Copied to the shared volume via `/bin/cp`.
- **bundle** — tool + runtime (e.g., Node.js) at `/opt/<tool>/`. Entire directory copied via `cp -a`.

## Files to Create

### 1. `dockerfiles/<tool>/Dockerfile`

**Init pattern** (single binary):

```dockerfile
ARG <TOOL>_VERSION=<version>

FROM alpine:3.21 AS builder
ARG <TOOL>_VERSION
ARG TARGETARCH
RUN apk add --no-cache curl
RUN set -e && \
    case "${TARGETARCH}" in \
      amd64) ARCH="x86_64" ;; \
      arm64) ARCH="aarch64" ;; \
      *) echo "Unsupported: ${TARGETARCH}" && exit 1 ;; \
    esac && \
    curl -fsSL -o /usr/local/bin/<binary> "<download-url>" && \
    chmod +x /usr/local/bin/<binary>

FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0
COPY --from=builder /usr/local/bin/<binary> /usr/local/bin/<binary>
ARG <TOOL>_VERSION
ENV TOOL_NAME=<tool> TOOL_VERSION=${<TOOL>_VERSION}
LABEL org.opencontainers.image.description="<description>" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
```

**Bundle pattern** (Node.js tool):

```dockerfile
ARG <TOOL>_VERSION=<version>

FROM node:22-slim AS builder
ARG <TOOL>_VERSION
RUN npm install -g @scope/package@${<TOOL>_VERSION} && npm cache clean --force
RUN mkdir -p /bundle/bin /bundle/lib && \
    cp /usr/local/bin/node /bundle/bin/ && \
    cp -a /usr/local/lib/node_modules /bundle/lib/ && \
    cp -a /usr/local/bin/<binary> /bundle/bin/<binary>

FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0
COPY --from=builder /bundle /opt/<tool>
ARG <TOOL>_VERSION
ENV TOOL_NAME=<tool> TOOL_VERSION=${<TOOL>_VERSION}
LABEL org.opencontainers.image.description="<description>" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
```

Notes:
- The version ARG must be declared **before the first FROM** (global scope) and then **re-declared without a default after each FROM** that uses it. Global ARGs are available in `FROM` expressions but not inside stages unless re-declared.
- Alpine is used for builder stages because UBI10 requires x86-64-v3 CPU support, which QEMU cannot emulate when cross-building.
- `TOOL_NAME` and `TOOL_VERSION` env vars are required — downstream CI reads them via `docker inspect`.

### 2. `dockerfiles/<tool>/VERSION`

Single line with the bare version string. Must match the `ARG` default in the Dockerfile.

```text
1.2.3
```

If the upstream release tag uses a `v` prefix (e.g., `v1.2.3`) and you set `strip_v: true` in the version-bump workflow, omit the `v` here.

### 3. `dockerfiles/<tool>/README.md`

Brief README with a DevWorkspace YAML snippet showing how to use the tool as an init container.

## Files to Modify

### 4. `inject-tool/registry.json`

Add an entry to the `tools` object.

**Init pattern template:**

```json
"<tool-name>": {
  "description": "<human-readable description>",
  "pattern": "init",
  "src": "/usr/local/bin/<binary>",
  "binary": "<binary>",
  "injector": { "memoryLimit": "128Mi" },
  "patch": [
    {
      "op": "add",
      "path": "/spec/template/components/-",
      "value": {
        "name": "<tool-name>-injector",
        "container": {
          "image": "quay.io/che-incubator/tools-injector/<tool-name>:next",
          "command": ["/bin/cp"],
          "args": ["/usr/local/bin/<binary>", "/injected-tools/<binary>"],
          "memoryLimit": "128Mi",
          "mountSources": false,
          "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
        }
      }
    }
  ],
  "editor": {
    "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
    "env": [],
    "postStart": ""
  }
}
```

**Bundle pattern template:**

```json
"<tool-name>": {
  "description": "<human-readable description>",
  "pattern": "bundle",
  "src": "/opt/<tool-name>",
  "binary": "<binary>",
  "injector": { "memoryLimit": "256Mi" },
  "patch": [
    {
      "op": "add",
      "path": "/spec/template/components/-",
      "value": {
        "name": "<tool-name>-injector",
        "container": {
          "image": "quay.io/che-incubator/tools-injector/<tool-name>:next",
          "command": ["/bin/sh"],
          "args": ["-c", "cp -a /opt/<tool-name>/. /injected-tools/<tool-name>/"],
          "memoryLimit": "256Mi",
          "mountSources": false,
          "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
        }
      }
    }
  ],
  "editor": {
    "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
    "env": [],
    "postStart": ""
  }
}
```

Optional `editor` fields:
- `env` — array of `{"name": "...", "value": "..."}` objects for the editor container
- `memoryLimit` — minimum editor memory (e.g., `"1024Mi"` for memory-intensive tools)
- `postStart` — shell command to run in the editor container after start (e.g., creating config directories)

### 5. Tool list — 4 locations to update

The tool list is hardcoded in 4 places that must stay in sync:

| File | Location | Format |
|------|----------|--------|
| `Makefile` | Line ~16, `TOOLS :=` | Space-separated |
| `.github/workflows/pr.yml` | `TOOLS=` in `set-matrix` step | Space-separated string |
| `.github/workflows/release.yml` | `matrix.tool` | YAML list of `{name, dockerfile}` objects |
| `.github/workflows/version-bump.yml` | `matrix.tool` | YAML list with `{name, source, repo/package, arg_name}` |

**pr.yml** — append to the `TOOLS` string:
```bash
TOOLS='opencode goose claude-code kilocode gemini-cli tmux python3 gh <new-tool>'
```

**release.yml** — add a matrix entry:
```yaml
- name: <new-tool>
  dockerfile: dockerfiles/<new-tool>
```
Add `platforms: linux/amd64,linux/arm64,linux/s390x` if the tool supports extra architectures (default is `linux/amd64,linux/arm64`).

**version-bump.yml** — add a matrix entry based on the upstream version source:

GitHub releases:
```yaml
- name: <new-tool>
  source: github
  repo: <org>/<repo>
  arg_name: <TOOL>_VERSION
```

npm:
```yaml
- name: <new-tool>
  source: npm
  package: "@scope/package"
  arg_name: <TOOL>_VERSION
```

Add `strip_v: true` if the upstream tag has a `v` prefix but your VERSION file does not.

## AI Agent Tools — Additional Steps

If the tool is an AI agent (not a utility), it also needs to appear in the Che Dashboard AI Provider Selector.

### 6. `dashboard/registry.json`

Add the provider (if new) to the `providers` array and the tool to the `tools` array:

**Provider entry** (skip if the provider already exists):
```json
{
  "id": "<vendor>/<product>",
  "name": "<Display Name>",
  "publisher": "<Company>",
  "description": "<one-line description>",
  "docsUrl": "<API docs URL>",
  "icon": "<icon URL>",
  "tags": ["Tech-Preview"]
}
```

**Tool entry:**
```json
{
  "providerId": "<vendor>/<product>",
  "tag": "next",
  "name": "<Display Name>",
  "url": "<tool homepage>",
  "binary": "<binary>",
  "pattern": "init",
  "injectorImage": "quay.io/che-incubator/tools-injector/<tool-name>:next",
  "envVarName": "<API_KEY_ENV_VAR>"
}
```

The `binary` and `pattern` fields must match what you set in `inject-tool/registry.json`. CI validates this on every PR.

## Verification Checklist

- [ ] `docker build -t test dockerfiles/<tool>/` succeeds
- [ ] `docker inspect test` shows correct `TOOL_NAME` and `TOOL_VERSION` env vars
- [ ] `inject-tool/registry.json` is valid JSON
- [ ] Tool list matches in all 4 locations (Makefile, pr.yml, release.yml, version-bump.yml)
- [ ] For AI tools: `make validate-dashboard-registry` passes

## Deploying to a Cluster

### Production (cluster-wide)

```bash
inject-tool/setup.sh <operator-namespace>
```

The Che operator replicates the inject-tool ConfigMap to all user namespaces. Re-run after modifying inject-tool files or `dashboard/registry.json`.

### Development (per-namespace)

```bash
inject-tool/setup-dev.sh <your-namespace>
```

Creates a local ConfigMap without operator replication. Use on clusters where `setup.sh` has NOT been run.
