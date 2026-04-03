# Design: Auto-Inject Tools from Consumer Repos

**Date:** 2026-04-03
**Status:** Approved

## Problem

Consumer repos (e.g. `picoclaw-che`) may need workspace tools (e.g. `git`, `jq`)
that are not in the tools-injector central registry. Today the only options are:

1. Add the tool to tools-injector centrally (Dockerfile + registry.json entry) —
   doesn't scale, not every tool belongs in the central registry.
2. Run `inject-tool inject <tool>` manually — requires knowing exact tool names,
   only works for registered tools.

Neither option lets a repo declare "I need these tools" in a way that
tools-injector can act on.

## Solution

Two pieces:

1. **`.che/inject-tools.json`** — a config file in the consumer repo declaring
   needed tools (by registry name or with full custom definition).
2. **`inject-tool init`** — a new subcommand that scans workspace project
   directories for these config files and injects everything declared.

### User Flow

1. Add `.che/inject-tools.json` to the consumer repo.
2. Start a workspace from that repo.
3. Run `inject-tool init` once from the terminal.
4. Workspace restarts with all declared tools available.
5. All subsequent workspace starts — tools are already in the DevWorkspace spec,
   no action needed.

## Config File Format

File: `.che/inject-tools.json` in the consumer repo root.

```json
{
  "tools": [
    "opencode",
    "tmux",
    {
      "name": "dev-tools",
      "image": "quay.io/myorg/my-project-tools:latest",
      "binaries": [
        { "src": "/usr/bin/git", "binary": "git" },
        { "src": "/usr/bin/jq", "binary": "jq" }
      ]
    }
  ]
}
```

### String entries

Reference tools in the central `registry.json` by name. Validated at runtime —
unknown tool names produce a clear error.

### Object entries (custom tools)

Define tools not in the central registry. Required fields:

| Field      | Type   | Description                                      |
|------------|--------|--------------------------------------------------|
| `name`     | string | Identifier, used for component name (`<name>-injector`) |
| `image`    | string | Container image containing the binaries          |
| `binaries` | array  | List of `{src, binary}` pairs to copy            |

Optional fields:

| Field         | Type   | Default              | Description                        |
|---------------|--------|----------------------|------------------------------------|
| `description` | string | `"<name> (custom)"`  | Human-readable description         |
| `env`         | array  | `[]`                 | Environment variables for the editor container |
| `postStart`   | string | `""`                 | Shell command to run after workspace start |
| `memoryLimit` | string | `"128Mi"`            | Memory limit for the injector init container |

Each `binaries` entry:

| Field    | Type   | Description                            |
|----------|--------|----------------------------------------|
| `src`    | string | Path to the binary inside the image    |
| `binary` | string | Name of the binary in `/injected-tools/` |

## `inject-tool init` Subcommand

### Discovery

1. If `INJECT_TOOLS_CONFIG` env var is set, use that path directly.
2. Otherwise, scan `/projects/*/.che/inject-tools.json`.
3. Collect all tool declarations across all discovered config files.
4. Deduplicate by name (first occurrence in alphabetical directory order wins).

### Execution

For each tool:

- **Registry tools** (string entries): look up in `registry.json`, build patch
  ops via existing `build_inject_ops()`.
- **Custom tools** (object entries): construct a registry-compatible tool entry
  from the inline definition, then pass through `build_inject_ops()`.

Custom tool objects are converted to registry format as follows:

- `binaries` list is used to generate the init container's `command` and `args`:
  - Single binary: `command: ["/bin/cp"], args: ["<src>", "/injected-tools/<binary>"]`
  - Multiple binaries: `command: ["/bin/sh"], args: ["-c", "cp <src1> <src2> ... /injected-tools/"]`
- Symlink commands are generated for each binary in the `binaries` list.
- All other fields map directly to the existing registry schema.

All patch ops are merged into a single JSON Patch array and applied in one
Kubernetes API call, triggering one workspace restart.

### Idempotency

Already-injected tools (detected by `find_component_index(ws, "<name>-injector")`)
are skipped. Subsequent runs of `inject-tool init` are no-ops if all tools are
already injected.

### CLI Interface

```
inject-tool init              # scan and inject
inject-tool init --dry-run    # show what would be injected without patching
```

### Error Handling

- Missing config file: silent (not every project has one).
- Invalid JSON: error with file path and parse error.
- Unknown registry tool name: error listing available tools (same as today).
- Missing required fields in custom tool: error naming the field and config file.
- No tools to inject (all already present): info message, exit 0.

## What Doesn't Change

- `inject-tool inject/remove/list` — unchanged, still works for ad-hoc use.
- `registry.json` — unchanged, still the source of truth for known tools.
- ConfigMap delivery via `setup.sh` — unchanged.
- CI/CD pipelines — unchanged.
- Existing tool container images — unchanged.

## Dependencies

None. The config file is JSON (parsed with stdlib `json` module). All patching
logic reuses existing code in `inject-tool.py`.

## Future Considerations

- **Automatic trigger**: If a reliable mechanism to run `inject-tool init` on
  workspace start (before terminal open) becomes available, it can be added
  without changing the config format or subcommand.
- **DevWorkspaceTemplate contributions**: If the consumer repo's devfile
  references pre-created DevWorkspaceTemplates via `.spec.contributions`, tools
  can be injected at workspace creation time with no restart. This is a
  complementary approach, not a replacement.
- **OCI Image Volumes (KEP-4639)**: When OpenShift supports Kubernetes v1.36,
  the entire init-container pattern can be replaced with direct volume mounts
  from OCI images. The `.che/inject-tools.json` format would remain valid —
  only the patching implementation changes.
