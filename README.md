# tools-injector

Container images and `inject-tool` CLI for injecting AI CLI tools into Eclipse Che DevWorkspaces via init containers.

## Tool Images

| Tool | Pattern | Image | Architectures |
|------|---------|-------|---------------|
| opencode | init | `quay.io/che-incubator/tools-injector/opencode:next` | amd64, arm64 |
| goose | init | `quay.io/che-incubator/tools-injector/goose:next` | amd64, arm64 |
| claude-code | init | `quay.io/che-incubator/tools-injector/claude-code:next` | amd64, arm64 |
| gemini-cli | bundle | `quay.io/che-incubator/tools-injector/gemini-cli:next` | amd64, arm64, s390x, ppc64le |
| kilocode | bundle | `quay.io/che-incubator/tools-injector/kilocode:next` | amd64, arm64 |
| tmux | init | `quay.io/che-incubator/tools-injector/tmux:next` | amd64, arm64 |
| gh | init | `quay.io/che-incubator/tools-injector/gh:next` | amd64, arm64 |
| python3 | init | `quay.io/che-incubator/tools-injector/python3:next` | amd64, arm64 |

**Init pattern**: Single binary copied to a shared volume via preStart init container.
**Bundle pattern**: Node.js tool + runtime bundled at `/opt/<tool>/`, copied via init container.

## Prerequisites

Container images used as DevWorkspace editor or main components must meet these requirements for inject-tool to work correctly. Any Linux base image works (UBI, Alpine, Debian, etc.):

- **Writable HOME directory** — `HOME` env var must point to a writable path (e.g., `/home/user`). Tools like Claude Code write config/cache files on startup and will hang or crash if HOME is read-only.
- **OpenShift arbitrary UID support** — the home directory must be writable by group `0` (`chgrp -R 0 /home/user && chmod -R g=u /home/user`), since OpenShift assigns random UIDs that are always in group 0.
- **passwd entry** — a `/etc/passwd` entry for the container user with a proper home and shell (e.g., `user:x:1001:0:user:/home/user:/bin/bash`).

> **Note:** Most injected tools are statically linked and work on any Linux distro, including Alpine (musl libc). If a tool fails with a dynamic linker error on Alpine, it may need to be rebuilt as a static binary.

## How Tool Injection Works

There are two ways to inject tools into DevWorkspaces:

### 1. Che Dashboard — at workspace creation (pre-start)

The Che Dashboard reads an `ai-tool-registry` ConfigMap to display the **AI Provider Selector** on the Create Workspace page. When a user selects AI tools, the dashboard adds init containers and lifecycle commands to the DevWorkspace spec before the pod starts.

The dashboard handles:
- Creating init containers from the tool's `injectorImage`
- Symlinking binaries into `/injected-tools/bin/` and adding it to `$PATH`
- Running `setupCommand` (e.g., creating config directories)
- Mounting the shared `injected-tools` volume on the editor container

Tools are available on first workspace boot — no restart needed.

### 2. inject-tool CLI — in a running workspace (post-start)

The `inject-tool` CLI patches the DevWorkspace CR via the Kubernetes API, which triggers a workspace restart with the injected tools:

```bash
inject-tool list              # List available tools
inject-tool <tool>            # Inject a tool
inject-tool remove <tool>     # Remove an injected tool
inject-tool <tool> --hot      # Hot-inject without restart
```

See [inject-tool/README.md](inject-tool/README.md) for details.

## Setup

Deploy `inject-tool` and the dashboard AI registry to a Che namespace (requires `kubectl` or `oc` with cluster access):

```bash
inject-tool/setup.sh <namespace>
```

This creates two ConfigMaps in the namespace:
- **`inject-tool`** — automounted into every workspace at `/usr/local/bin/` via DWO labels (contains the CLI shim, Python script, and `inject-tool/registry.json`)
- **`ai-tool-registry`** — the dashboard AI registry (contains `dashboard/registry.json`, labeled `app.kubernetes.io/component=ai-tool-registry, app.kubernetes.io/part-of=che.eclipse.org`)

After setup, `inject-tool` is available in every new or restarted workspace, and the Dashboard AI Provider Selector shows all configured AI tools.

### Customizing the AI registry

Edit `dashboard/registry.json` to add, remove, or modify AI tools and providers. Then re-run `setup.sh` to update the ConfigMap. The dashboard picks up changes automatically — no restart needed.

To offer only specific tools, remove the others from the `tools` array. To hide the AI selector entirely, delete the `ai-tool-registry` ConfigMap:

```bash
kubectl delete configmap ai-tool-registry -n <namespace>
```

## Building

```bash
# Build a single tool for current platform
make docker-build-local-opencode

# Build multi-arch (amd64+arm64), no push
make docker-build-opencode

# Build and push multi-arch (requires docker buildx + registry login)
make docker-opencode

# Build all tools
make docker-build-all
```

## Vertex AI Authentication

See [docs/guides/vertex-ai-setup.md](docs/guides/vertex-ai-setup.md) for setting up Google Cloud ADC authentication in DevWorkspaces.

## License

[EPL-2.0](LICENSE)
