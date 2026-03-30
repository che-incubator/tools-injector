# ADR-003: Project-scoped tool injection via init subcommand

**Date:** 2026-04-03
**Status:** Reverted (removed in 2026-05-02, needs further design)

## Context

Consumer repos needed a way to declare "I need these tools" without modifying the tools-injector central registry. The only options were adding every tool centrally (doesn't scale) or running `inject-tool <tool>` manually (requires knowing exact names, only works for registered tools).

## Decision

Two pieces:

1. **`.che/inject-tools.json`** — a config file in the consumer repo declaring needed tools, supporting both registry references (strings) and inline custom tool definitions (objects with `name`, `image`, `binaries`).

2. **`inject-tool init`** — a subcommand that scans `/projects/*/.che/inject-tools.json`, resolves all declarations, deduplicates by name, and applies a single merged JSON Patch. Override scan path with `INJECT_TOOLS_CONFIG` env var. `--dry-run` previews without patching.

Custom tool objects are converted to registry-compatible entries at runtime:
- Single binary: `command: ["/bin/cp"], args: ["<src>", "/injected-tools/<binary>"]`
- Multiple binaries: `command: ["/bin/sh"], args: ["-c", "cp <src1> <src2> ... /injected-tools/"]`

Already-injected tools are detected by `find_component_index(ws, "<name>-injector")` and skipped, making `init` idempotent.

## Consequences

- Repos declare their tool needs declaratively — one `inject-tool init` on first workspace start, idempotent after.
- Custom tools support `env`, `postStart`, and `memoryLimit` optional fields.
- No changes to existing `inject/remove/list` commands, registry.json, or CI.
- Future: if a reliable workspace startup hook becomes available, `init` can be triggered automatically.
