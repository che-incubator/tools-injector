# inject-tool Python3 Rewrite + Multi-Tool Support

**Date**: 2026-03-27
**Status**: Implemented

## Goal

Rewrite `inject-tool` from bash (with 17 inline python3 calls) to a single-file Python3 script using only stdlib. Add multi-tool inject/remove support (single restart). Ship a python3 init-container image as fallback for containers that lack python3.

## Delivery

### ConfigMap contents (two files)

- **`inject-tool`** — bash shim (~10 lines). Finds python3: tries `python3` on PATH, then `/injected-tools/bin/python3`, then errors with install instructions. Exec's `inject-tool.py` with the found interpreter.
- **`inject-tool.py`** — full CLI, stdlib only (`json`, `urllib.request`, `ssl`, `subprocess`, `argparse`, `os`).

`setup.sh` updated to include both files in the ConfigMap. Both mounted at `/usr/local/bin/` via existing DWO automount annotations.

### Python3 fallback image

New `dockerfiles/python3/Dockerfile`:
- Alpine builder: extract python3 + stdlib
- UBI10 minimal runtime
- Binary at `/usr/local/bin/python3`

Added to: Makefile `TOOLS` list, CI workflow matrices, inject-tool registry as an init-pattern tool.

## CLI Interface

Same commands as current bash version, extended with multi-tool support:

```
inject-tool <tool> [tool2 ...]         Inject one or more tools (single restart)
inject-tool <tool> --hot               Inject binary without restart (one tool only)
inject-tool list                       List available tools and status
inject-tool remove <tool> [tool2 ...]  Remove one or more tools (single restart)
inject-tool remove <tool> --hot        Remove hot-injected binary only (one tool only)
inject-tool --help                     Show help
```

`--hot` with multiple tools is an error.

### Environment variables

| Var | Default | Description |
|-----|---------|-------------|
| `INJECT_TOOL_REGISTRY` | `quay.io/okurinny` | Image registry prefix |
| `INJECT_TOOL_TAG` | `next` | Image tag |
| `DEVWORKSPACE_NAMESPACE` | (required) | Auto-set by Che |
| `DEVWORKSPACE_NAME` | (required) | Auto-set by Che |
| `KUBERNETES_SERVICE_HOST` | (required) | Auto-set by k8s |
| `KUBERNETES_SERVICE_PORT` | (required) | Auto-set by k8s |

## Internal Structure

Single file `inject-tool.py`:

```
# Tool registry (constants)
TOOLS = {
    "opencode":    {"pattern": "init",   "image": "tools-injector/opencode",    "src": "/usr/local/bin/opencode", "binary": "opencode"},
    "goose":       {"pattern": "init",   "image": "tools-injector/goose",       "src": "/usr/local/bin/goose",    "binary": "goose"},
    "claude-code": {"pattern": "init",   "image": "tools-injector/claude-code", "src": "/usr/local/bin/claude",   "binary": "claude"},
    "kilocode":    {"pattern": "bundle", "image": "tools-injector/kilocode",    "src": "/opt/kilocode",           "binary": "kilo"},
    "gemini-cli":  {"pattern": "bundle", "image": "tools-injector/gemini-cli",  "src": "/opt/gemini-cli",         "binary": "gemini"},
    "tmux":        {"pattern": "init",   "image": "tools-injector/tmux",        "src": "/usr/local/bin/tmux",     "binary": "tmux"},
    "python3":     {"pattern": "init",   "image": "tools-injector/python3",     "src": "/usr/local/bin/python3",  "binary": "python3"},
}
TOOL_ENV = {
    "gemini-cli": "GEMINI_CLI_HOME=/tmp/gemini-home",
    "claude-code": "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1",
}
TOOL_SETUP = {
    "gemini-cli": "mkdir -p /tmp/gemini-home/.gemini && echo '{\"projects\":{}}' > /tmp/gemini-home/.gemini/projects.json",
}

# Kubernetes API helpers
get_token() -> str
api_url() -> str
fetch_workspace() -> dict          # returns parsed JSON dict
patch_workspace(ops: list[dict])   # sends JSON Patch array

# Workspace JSON helpers
find_component_index(ws: dict, name: str) -> int | None
find_editor(ws: dict) -> tuple[int, str] | None   # (index, name)
get_prestart(ws: dict) -> list | None
get_poststart(ws: dict) -> list | None

# Patch builders
build_inject_ops(tool: str, ws: dict, skip_infra: bool = False) -> list[dict]
build_remove_ops(tool: str, ws: dict, also_removing: list[str] = []) -> list[dict]

# Commands
cmd_inject(tools: list[str], hot: bool)
cmd_remove(tools: list[str], hot: bool)
cmd_list()

# Entrypoint
main()   # argparse + dispatch
```

### Key design decisions

- `fetch_workspace()` returns parsed dict — all helpers work with native Python data structures, no JSON string passing.
- Patch builders return `list[dict]` — caller concatenates and passes to `patch_workspace()`.
- `build_inject_ops(skip_infra=True)` skips: volume add, volume mount on editor, env/commands/events array creation, memory bump. Only emits tool-specific append ops.
- `build_remove_ops(also_removing=[...])` uses the list when checking "any other injectors remain?" to correctly decide whether to remove the shared volume and volume mount.

## Multi-Tool Injection Logic

```python
def cmd_inject(tools, hot):
    if hot:
        # --hot is single-tool only (enforced by argparse)
        hot_inject(tools[0])
        return

    ws = fetch_workspace()

    # Filter already-injected tools
    to_inject = [t for t in tools if find_component_index(ws, f"{t}-injector") is None]
    if not to_inject:
        print("==> All requested tools are already injected.")
        return

    # Build ops: first tool with infra, rest without
    all_ops = []
    for i, tool in enumerate(to_inject):
        all_ops.extend(build_inject_ops(tool, ws, skip_infra=(i > 0)))

    # Fix memory bump for multiple bundle tools
    bundle_count = sum(1 for t in to_inject if TOOLS[t]["pattern"] == "bundle")
    if bundle_count > 1:
        # Remove individual bump from first tool, add correct total
        all_ops = [op for op in all_ops if not op.get("path", "").endswith("/memoryLimit")]
        # ... add single replace op with total bump ...

    patch_workspace(all_ops)
```

## Multi-Tool Remove Logic

```python
def cmd_remove(tools, hot):
    if hot:
        # --hot is single-tool only (enforced by argparse)
        # ... rm binary ...
        return

    ws = fetch_workspace()

    all_ops = []
    for tool in tools:
        all_ops.extend(build_remove_ops(tool, ws, also_removing=tools))

    # Sort remove ops by descending index to avoid shifting
    all_ops.sort(key=remove_sort_key, reverse=True)

    patch_workspace(all_ops)
```

## Hot Inject

Same as current bash version. Uses `subprocess.run(["oc", "image", "extract", ...])`. Single-tool only — errors if multiple tools passed with `--hot`.

## Auth & API

Same as current bash version:
1. Try token from KUBECONFIG (grep for `token:`)
2. Fall back to service account token at `/var/run/secrets/kubernetes.io/serviceaccount/token`
3. API URL: `https://{KUBERNETES_SERVICE_HOST}:{KUBERNETES_SERVICE_PORT}/apis/workspace.devfile.io/v1alpha2/namespaces/{ns}/devworkspaces/{name}`
4. CA cert: `/var/run/secrets/kubernetes.io/serviceaccount/ca.crt` (skip verification if missing)
5. JSON Patch via `PATCH` with `Content-Type: application/json-patch+json`

Uses `urllib.request` (stdlib) instead of `curl`.

## What Does NOT Change

- Tool registry format and contents (same tools, same images, same patterns)
- DevWorkspace patching behavior (same JSON Patch ops, same API)
- ConfigMap deployment via `setup.sh` (updated to include two files)
- CI workflows (add python3 to matrix, rest unchanged)
- Makefile (add python3 to TOOLS list)
- Output messages and UX

## Out of Scope

- Adding pip or third-party packages
- Changing the tool registry to be dynamic/external
- Adding automated tests (future task)
- Changing the CLI interface beyond multi-tool support
