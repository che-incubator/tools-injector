# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Container images + `inject-tool` CLI for dynamically injecting AI CLI tools into Eclipse Che DevWorkspaces. Two components:

1. **Dockerfiles** (`dockerfiles/<tool>/`) — minimal multi-arch images, one directory per registered tool
2. **inject-tool** (`inject-tool/inject-tool.py`) — Python3 CLI that patches DevWorkspace CRs via Kubernetes API using RFC 6902 JSON Patch. Delivered via ConfigMap as a shell shim + `.py` file.

## Build Commands

```bash
make docker-build-local-<tool>   # Quick local build (current platform only)
make docker-build-<tool>         # Multi-arch build (amd64+arm64), no push
make docker-push-<tool>          # Push multi-arch + create manifest
make docker-<tool>               # Build + push shorthand
make docker-build-all            # Build all tools
make help                        # Show all targets
```

Override registry/tag: `IMAGE_REGISTRY=quay.io/myorg TAG=dev make docker-build-local-opencode`

## Architecture

### Two Injection Patterns

**Init pattern**: Single binary → Alpine builder stage → UBI10 minimal runtime. Binary copied to shared `/injected-tools` volume via preStart init container.

**Bundle pattern**: Node.js runtime + tool → `node:22-slim` builder → UBI10 minimal runtime (python3: python-build-standalone glibc bundle). Entire bundle at `/opt/<tool>/`, copied to `/injected-tools/<tool>/` via init container. Editor container gets +512Mi memory bump by default, overridable per tool with `editor.memoryBump` (python3 sets 0Mi).

Which tools use which pattern is recorded per tool in the `pattern` field of `inject-tool/registry.json`.

Alpine is used for builder stages because UBI10 requires x86-64-v3 which QEMU can't emulate during cross-arch builds.

### inject-tool Internals

The tool registry is `inject-tool/registry.json`:
- `registry`, `tag` — default image registry and tag (overridable via `INJECT_TOOL_REGISTRY`/`INJECT_TOOL_TAG` env vars)
- `infrastructure.patch` — RFC 6902 ops for the shared `injected-tools` volume
- `tools.<name>` — per-tool: `description`, `pattern`, `src`, `binary`, `patch` (append-only init container ops), `editor` (volumeMounts, env, postStart, optional `memoryBump`)

`inject-tool.py` loads `registry.json` at startup from the same directory (override path with `INJECT_TOOL_REGISTRY_FILE` env var for testing).

**Patching flow**: validate tools → extract auth token from KUBECONFIG (falls back to service account token) → fetch DevWorkspace CR from Kubernetes API → build inject ops per tool (first with infra, rest skip_infra) → merge into single JSON Patch array → PATCH via API → workspace restarts.

**Multi-tool**: `inject-tool opencode goose tmux` builds patches for each tool, merges into one API call, one restart. `--hot` stays single-tool only.

**Hot-inject mode** (`inject-tool <tool> --hot`): uses `oc image extract` to pull binary directly without restart. Init-pattern tools only; python3 is not hot-injectable. Not persistent across restarts.

### Deployment

`inject-tool/setup.sh <namespace>` creates a ConfigMap with DWO automount labels so every workspace in that namespace gets `/usr/local/bin/inject-tool`.

## CI/CD

- `.github/workflows/pr.yml` — builds changed tools multi-arch on every PR, tags with `pr-<number>`; the tool list and registry consistency checks derive from `inject-tool/registry.json`
- `.github/workflows/release.yml` — rebuilds every registered tool from `registry.json` and pushes `next` on merge to main
- `.github/workflows/version-bump.yml` — weekly (and manual) check for new upstream tool versions; opens one bump PR per outdated tool

All images push to `quay.io/che-incubator/tools-injector/<tool>`.

## Adding a New Tool

A new tool is referenced in **six** places — missing any of them silently breaks CI, version bumps, or releases. The `check-tool-registration` CI job catches list omissions; the PR and release build matrices derive from `registry.json` automatically. The rest is on you.

1. **`dockerfiles/<tool>/Dockerfile`** — image build, following the init or bundle pattern (see "Two Injection Patterns" above). For npm-based bundles, do not COPY the dereferenced `node_modules/.bin` symlink — wrap the real entrypoint in an `sh` script (see pi; gemini-cli is the counterexample).
2. **`dockerfiles/<tool>/VERSION`** — plain version string, no trailing newline. Must match the Dockerfile `ARG` and the registry `version` exactly; the version-bump workflow rewrites all three together.
3. **`Makefile`** — add the tool to `TOOLS` for local build targets.
4. **`inject-tool/registry.json`** — `tools.<name>` entry: `description`, `pattern`, `src`, `binary`, `version` (same string as the VERSION file), `injector` (init-container `memoryLimit`), `patch` (append-only init-container ops — keep the patch container's `memoryLimit` in sync with `injector.memoryLimit`), `editor` (volumeMounts, env, postStart, optional `memoryBump`/`memoryLimit`). Add `versionCommand`/`versionRegex` when the tool's `--version` output needs different probing.
5. **`.github/workflows/version-bump.yml`** — two places: the `workflow_dispatch` `inputs.tool` choice list, and the `check-versions` matrix entry (`name`, `source`, `repo`/`package`, `arg_name`, plus `strip_v`/`tag_prefix` as needed).
6. **`inject-tool/README.md`** — add a row to the Available Tools table.

Finally, create the Quay repository `quay.io/che-incubator/tools-injector/<tool>` and **make it public** — new Quay repos are private by default, and workspaces get 401s pulling them.

A PR triggers the multi-arch CI build (`pr-<number>` tag); merge rebuilds `:next`. Verify before merging: inject the tool into a DevWorkspace and run it; `inject-tool list` should show the new tool with its version.

## No Automated Tests

inject-tool logic is tested manually in DevWorkspaces. CI checks are limited to Docker builds and registry consistency (tool registration, version drift between the VERSION file, Dockerfile ARG, and registry).
