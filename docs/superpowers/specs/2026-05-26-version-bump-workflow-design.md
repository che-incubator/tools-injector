# Version Bump Workflow Design

## Summary

A GitHub Actions workflow that automatically detects new upstream versions for all 8 injected tools and opens per-tool PRs with the version bump. Runs on a configurable schedule (default weekly) and supports manual dispatch.

## Current State

Tools are versioned in three ways:
- **ARG-pinned** (opencode, goose, claude-code, tmux, gh): `ARG <TOOL>_VERSION=x.y.z` in Dockerfile
- **npm latest** (kilocode, gemini-cli): `npm install -g @pkg` with no version pin
- **Alpine package** (python3): `apk add python3` with no version pin

There is no automated way to detect or apply upstream version changes.

## Design

### VERSION Files

Each tool gets a `dockerfiles/<tool>/VERSION` file containing a single line with the version string. Examples:
- `v1.2.27` (opencode — includes `v` prefix to match upstream tags)
- `2.1.81` (claude-code — no `v` prefix, matches upstream)
- `1.27.3` (kilocode — npm version, no prefix)

The VERSION file and the Dockerfile ARG/install line are updated in lockstep by the workflow. Both always contain the same version. The Dockerfile remains self-contained for local builds (the ARG default matches VERSION).

### Dockerfile Changes

**ARG-pinned tools** (no Dockerfile change needed — ARG already exists):
- The workflow updates the `ARG <TOOL>_VERSION=...` line with `sed`.

**npm tools** (one-time migration):
- `npm install -g @kilocode/cli` → `npm install -g @kilocode/cli@1.27.3`
- `npm install -g @google/gemini-cli` → `npm install -g @google/gemini-cli@0.7.0`
- Subsequent bumps update the version suffix.

**python3** (add version constraint):
- `apk add python3` → `apk add --no-cache "python3~=3.12"` or similar constraint matching Alpine's minor version.

### Version Detection

The workflow uses a matrix strategy. Each matrix entry defines the tool name, source type, and source-specific metadata.

| Source type | Tools | Detection method |
|---|---|---|
| GitHub Releases | opencode, goose, claude-code, tmux, gh | `gh api repos/<owner>/<repo>/releases/latest --jq .tag_name` |
| npm registry | kilocode, gemini-cli | `npm view <package> dist-tags.latest` |
| Alpine apk | python3 | `docker run --rm alpine:3.21 sh -c 'apk update && apk policy python3'` |

All detection methods return only stable releases (GitHub's `/releases/latest` excludes pre-releases; npm's `dist-tags.latest` is stable by definition).

#### Matrix Definition

```yaml
matrix:
  tool:
    - name: opencode
      source: github
      repo: anomalyco/opencode
    - name: goose
      source: github
      repo: block/goose
    - name: claude-code
      source: github
      repo: anthropics/claude-code
      strip_v: true
    - name: tmux
      source: github
      repo: tmux/tmux
    - name: gh
      source: github
      repo: cli/cli
      strip_v: true
    - name: kilocode
      source: npm
      package: "@kilocode/cli"
    - name: gemini-cli
      source: npm
      package: "@google/gemini-cli"
    - name: python3
      source: alpine
```

### Update Flow

For each tool where `current_version != latest_version`:

1. Check if an open PR already exists for `bump/<tool>-*` — if so, skip (idempotency).
2. Create branch `bump/<tool>-<new_version>`.
3. Update `dockerfiles/<tool>/VERSION` with the new version string.
4. Update `dockerfiles/<tool>/Dockerfile`:
   - ARG-pinned: `sed` the `ARG <TOOL>_VERSION=...` line.
   - npm: `sed` the `npm install -g @pkg@...` line.
   - python3: `sed` the `apk add` line's version constraint.
5. Commit: `bump(<tool>): <old_version> → <new_version>`
6. Push branch and open PR targeting `main`.

### PR Format

- **Title:** `bump(<tool>): <old_version> → <new_version>`
- **Body:** Summary of the version change with a link to the upstream release or changelog.
- **Labels:** `automated`, `version-bump`

### Triggers

```yaml
on:
  schedule:
    - cron: '17 8 * * 1'  # Weekly, Monday 8:17 UTC (default)
  workflow_dispatch:
    inputs:
      tool:
        description: 'Specific tool to check (leave empty for all)'
        required: false
        type: string
```

The schedule cron can be edited in the YAML to any frequency from daily to biweekly. The `workflow_dispatch` input allows manual runs for a specific tool or all tools.

### Special Cases

**claude-code:** GitHub release tags may not use `v` prefix. The `strip_v: true` flag handles this — after fetching the tag, strip `v` if present before comparing/writing to VERSION. The download URL in the Dockerfile uses the version without `v`.

**tmux:** Releases are on `tmux/tmux` but binaries are downloaded from `tmux/tmux-builds`. The version tag from `tmux/tmux` is used, and it matches the `tmux-builds` release tags. The version format may include a letter suffix (e.g., `3.6a`).

**python3:** Alpine package versions have `-rN` suffixes (e.g., `3.12.11-r1`). The workflow strips the `-rN` suffix when writing to VERSION. This check is rarely actionable since Alpine's python3 version only changes between Alpine releases, but it ensures we track the current state.

**npm tools (initial pin):** The first run of the workflow will detect that kilocode and gemini-cli have no version pin and perform a one-time migration to add the version suffix to the `npm install` command.

### Files Created/Modified

New files:
- `.github/workflows/version-bump.yml` — the workflow
- `dockerfiles/<tool>/VERSION` (8 files) — version tracking

Modified files:
- `dockerfiles/kilocode/Dockerfile` — add version pin to npm install
- `dockerfiles/gemini-cli/Dockerfile` — add version pin to npm install
- `dockerfiles/python3/Dockerfile` — add version constraint to apk add (optional, can defer)

### Non-Goals

- No automatic merging of bump PRs (human review required).
- No rollback mechanism (revert the PR if a version is bad).
- No cross-tool dependency tracking (each tool is independent).
