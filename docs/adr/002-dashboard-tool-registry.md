# ADR-002: Externalize tool registry to registry.json

**Date:** 2026-03-31
**Status:** Implemented

## Context

After the Python3 rewrite (ADR-001), the tool registry was still hardcoded as Python dicts (`TOOLS`, `TOOL_ENV`, `TOOL_SETUP`) inside `inject-tool.py`. This made it impossible for the Che Dashboard to discover available tools and pre-inject them during workspace creation.

## Decision

Create `inject-tool/registry.json` as the single source of truth for all tool metadata and patch operations. The file contains:

- `registry`, `tag` — default image registry and tag (overridable via `INJECT_TOOL_REGISTRY`/`INJECT_TOOL_TAG` env vars).
- `infrastructure.patch` — RFC 6902 ops for the shared `injected-tools` volume (applied once regardless of tool count).
- `tools.<name>` — per-tool definition: `description`, `pattern`, `src`, `binary`, `patch` (append-only init container ops), `editor` (volumeMounts, env, postStart).

Patch arrays use only append operations (`/spec/template/components/-`) so they're safe to apply without knowing component indices.

`setup.sh` creates two ConfigMaps:
1. **`inject-tool`** — includes `registry.json` alongside the shim and `.py`, automounted into workspaces.
2. **`tools-injector-registry`** — registry.json only, labeled `app.kubernetes.io/part-of=tools-injector` for Dashboard discovery.

## Consequences

- Dashboard can read the registry ConfigMap and present a tool picker at workspace creation time — no restart needed.
- `inject-tool.py` loads `registry.json` at startup; image overrides still work via env vars.
- Adding a new tool only requires a registry.json entry and a Dockerfile — no Python code changes.
- The `editor` section is structured (not raw JSON Patch) so Dashboard can apply it using its own knowledge of the editor component.
