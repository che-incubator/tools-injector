# ADR-001: Rewrite inject-tool from Bash to Python3

**Date:** 2026-03-27
**Status:** Implemented

## Context

The original `inject-tool.sh` was a 647-line Bash script that embedded 17 inline `python3 -c` calls for JSON manipulation. This made the code fragile, hard to extend, and impossible to support multi-tool injection (each tool required a separate workspace restart).

Adding new features (multi-tool inject/remove, custom tool definitions) would further complicate the bash+inline-python hybrid. A cleaner foundation was needed.

## Decision

Rewrite `inject-tool` as a two-file delivery:

- **`inject-tool`** — a ~10-line Bash shim that finds python3 (system PATH, then `/injected-tools/bin/python3`, then errors) and exec's `inject-tool.py`.
- **`inject-tool.py`** — full CLI using only Python3 stdlib (`json`, `urllib.request`, `ssl`, `subprocess`, `argparse`, `os`). No pip dependencies.

A new **python3 init-container image** (`dockerfiles/python3/`) provides a fallback for workspace containers that lack python3 (Alpine-based, minimal images).

Key design choices:
- `fetch_workspace()` returns a parsed dict — all helpers work with native Python data structures.
- Patch builders return `list[dict]` — caller concatenates and passes to `patch_workspace()`.
- Multi-tool: `build_inject_ops(skip_infra=True)` skips shared infrastructure ops; first tool sets up volume/mounts, subsequent tools only append their init containers.
- Multi-tool remove uses `also_removing` parameter to decide whether shared infrastructure should be cleaned up.

## Consequences

- Multi-tool inject/remove with a single workspace restart.
- `--hot` remains single-tool only (by design — it uses `oc image extract`).
- Both files delivered via the same ConfigMap with DWO automount.
- Workspace containers without python3 can inject it first, then use inject-tool normally.
- The CLI interface is backwards-compatible with the bash version.
