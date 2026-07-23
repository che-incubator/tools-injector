# Cursor CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Cursor CLI as an injectable bundle tool in Eclipse Che DevWorkspaces, delivered via a multi-arch Docker image and `inject-tool` registry entry.

**Architecture:** Cursor CLI ships as a Node.js bundle (~187MB unpacked), not a single static binary. A minimal repo-owned `install.sh` downloads the official tarball for a pinned version/arch, lays out `/opt/cursor-cli/{app,bin}`, and the init container copies the bundle to `/injected-tools/cursor-cli/` on workspace start. Both `agent` and `cursor-agent` are exposed in `bin/`.

**Tech Stack:** Alpine builder (cross-arch) → UBI10 minimal runtime → RFC 6902 JSON Patch via `inject-tool` (bundle pattern).

**Status:** Implemented locally. Pinned version `2026.07.13-7fe37d2`. Podman build verified on `linux/arm64`. Che end-to-end test pending.

## Global Constraints

- Tool name: `cursor-cli` (folder, registry key, image name)
- Injection pattern: `bundle` (same as `gemini-cli`, `kilocode`)
- Version pinning: `CURSOR_CLI_VERSION` build arg + `dockerfiles/cursor-cli/VERSION`
- Pinned version: `2026.07.13-7fe37d2` (latest lab at time of implementation; matches `curl https://cursor.com/install?channel=lab`)
- Release channel: `lab` (only channel with working install URLs today; `stable` returns HTTP 400)
- Download URL: `https://downloads.cursor.com/${CHANNEL}/${VERSION}/linux/${ARCH}/agent-cli-package.tar.gz`
- Arch mapping: Docker `amd64` → `x64`, `arm64` → `arm64`
- Exposed commands: both `agent` and `cursor-agent` in `/opt/cursor-cli/bin/`
- Do **not** use Cursor's official install script (`curl | bash`) — it lacks version pinning and includes user onboarding logic irrelevant to containers
- Hot inject (`inject-tool --hot`) is not supported for bundle tools
- Auth: users provide `CURSOR_API_KEY` or run `agent auth` — do not hardcode secrets in registry
- Shared volume size: bump global `injected-tools` volume from `256Mi` to `512Mi` in `registry.json` `infrastructure.patch` (cursor-cli bundle alone is ~187MB; headroom needed for multi-tool workspaces)

---

## Background: Why Not the Official Install Script?

Cursor's install script (`curl https://cursor.com/install | bash`):

- Hardcodes the version in the script body — no official `?version=` param
- `?channel=lab` selects latest lab only, not a specific version
- `?channel=stable` returns HTTP 400
- Installs to `$HOME/.local/...` with PATH/shell setup we don't need
- ~80% of the script is user onboarding (colors, shell detection, PATH hints)

**Chosen approach:** a repo-owned minimal `install.sh` that performs only the container-relevant steps (download, extract, layout, symlinks). Same tarball and extract flags as the official script, fully version-pinned.

---

## File Structure

| Action | File | Responsibility | Status |
|--------|------|----------------|--------|
| Create | `dockerfiles/cursor-cli/install.sh` | Download tarball, extract, create bin symlinks | Done |
| Create | `dockerfiles/cursor-cli/Dockerfile` | Multi-stage build: Alpine builder → UBI10 runtime | Done |
| Create | `dockerfiles/cursor-cli/VERSION` | Pinned version string (`2026.07.13-7fe37d2`) | Done |
| Create | `dockerfiles/cursor-cli/README.md` | DevWorkspace YAML example, auth notes | Done |
| Modify | `inject-tool/registry.json` | Bump `infrastructure.patch` volume to `512Mi`; add `cursor-cli` bundle entry | Done |
| Modify | `dockerfiles/*/README.md` | Update DevWorkspace YAML examples: `256Mi` → `512Mi` for `injected-tools` volume | Done |
| Modify | `inject-tool/README.md` | Document `cursor-cli` in tools table and bundle list | Done |
| Modify | `Makefile` | Add `cursor-cli` to `TOOLS` list | Done |
| Modify | `.github/workflows/pr.yml` | Add `cursor-cli` to `TOOLS` string | Done |
| Modify | `.github/workflows/release.yml` | Add matrix entry | Done |

No changes to `inject-tool.py` — bundle support already exists.

---

## Install Script Design

`dockerfiles/cursor-cli/install.sh` — minimal, POSIX `sh`, no OS/shell detection:

```sh
#!/bin/sh
set -eu

VERSION="${CURSOR_CLI_VERSION:?CURSOR_CLI_VERSION is required}"
CHANNEL="${CURSOR_CLI_CHANNEL:-lab}"
ARCH="${TARGETARCH:?TARGETARCH is required}"
DEST="${CURSOR_CLI_DEST:-/opt/cursor-cli}"

case "$ARCH" in
  amd64) DL_ARCH=x64 ;;
  arm64) DL_ARCH=arm64 ;;
  *) echo "unsupported arch: $ARCH" >&2; exit 1 ;;
esac

URL="https://downloads.cursor.com/${CHANNEL}/${VERSION}/linux/${DL_ARCH}/agent-cli-package.tar.gz"

mkdir -p "$DEST/app" "$DEST/bin"
curl -fsSL "$URL" | tar --strip-components=1 -xzf - -C "$DEST/app"
ln -sf ../app/cursor-agent "$DEST/bin/agent"
ln -sf ../app/cursor-agent "$DEST/bin/cursor-agent"
```

**Inputs (env vars set by Dockerfile):**

| Variable | Source | Default |
|----------|--------|---------|
| `CURSOR_CLI_VERSION` | `ARG` / `VERSION` file | `2026.07.13-7fe37d2` |
| `CURSOR_CLI_CHANNEL` | `ARG` | `lab` |
| `TARGETARCH` | BuildKit | auto |
| `CURSOR_CLI_DEST` | optional override | `/opt/cursor-cli` |

**Outputs:**

```
/opt/cursor-cli/
  app/
    cursor-agent    # shell wrapper → runs bundled node + index.js
    node            # bundled Node runtime (~120MB)
    index.js        # CLI entry
    *.node          # native modules
    ...
  bin/
    agent           → ../app/cursor-agent
    cursor-agent    → ../app/cursor-agent
```

After injection into a DevWorkspace, `inject-tool` creates additional symlinks:

```
/injected-tools/bin/agent        → /injected-tools/cursor-cli/bin/agent
/injected-tools/bin/cursor-agent → via postStart symlink
```

**Note on inject-tool symlink behavior:** `registry.json` has a single `binary` field used for the primary PATH symlink. Register `binary: "agent"` as primary. The `cursor-agent` symlink in `/opt/cursor-cli/bin/` is copied with the bundle and remains accessible at `/injected-tools/cursor-cli/bin/cursor-agent`. A `postStart` command adds `/injected-tools/bin/cursor-agent`.

---

## Dockerfile Design

```dockerfile
# Stage 1: Download Cursor CLI bundle via minimal install script
# Alpine builder: UBI10 requires x86-64-v3, QEMU can't emulate amd64 on ARM hosts.
FROM alpine:3.21 AS builder

ARG CURSOR_CLI_VERSION=2026.07.13-7fe37d2
ARG CURSOR_CLI_CHANNEL=lab
ARG TARGETARCH

ENV CURSOR_CLI_VERSION=${CURSOR_CLI_VERSION} \
    CURSOR_CLI_CHANNEL=${CURSOR_CLI_CHANNEL} \
    TARGETARCH=${TARGETARCH}

RUN apk add --no-cache curl tar
COPY dockerfiles/cursor-cli/install.sh /tmp/install.sh
RUN chmod +x /tmp/install.sh && /tmp/install.sh

# Stage 2: Minimal runtime image (init container only)
FROM registry.access.redhat.com/ubi10/ubi-minimal:10.0

COPY --from=builder /opt/cursor-cli /opt/cursor-cli

LABEL org.opencontainers.image.description="Cursor CLI init container for DevWorkspace injection" \
      org.opencontainers.image.source="https://github.com/che-incubator/tools-injector"
```

Build commands:

```bash
# Recommended (avoids Makefile hyphen ambiguity for docker-build-local-*)
podman build -f dockerfiles/cursor-cli/Dockerfile \
  -t quay.io/che-incubator/tools-injector/cursor-cli:next .

# Multi-arch (CI)
make docker-build-cursor-cli

# Override version at build time
podman build -f dockerfiles/cursor-cli/Dockerfile \
  --build-arg CURSOR_CLI_VERSION=2026.07.13-7fe37d2 \
  -t quay.io/che-incubator/tools-injector/cursor-cli:next .
```

**Makefile note:** `make docker-build-local-cursor-cli` matches the `docker-build-%` rule with stem `local-cursor-cli` (same issue as `gemini-cli`). Use `make docker-build-cursor-cli` or direct `podman`/`docker build` instead.

---

## Infrastructure Change: Global Volume Bump

In `inject-tool/registry.json`, update `infrastructure.patch` so new workspaces get a larger shared volume:

```json
"infrastructure": {
  "patch": [
    {
      "op": "add",
      "path": "/spec/template/components/-",
      "value": { "name": "injected-tools", "volume": { "size": "512Mi" } }
    }
  ]
}
```

**Scope:** This applies when `inject-tool` creates the `injected-tools` volume for the first time on a DevWorkspace. Workspaces that already have a 256Mi volume are **not** auto-resized — document that existing workspaces may need manual volume resize or re-creation.

**Docs consistency:** All `dockerfiles/*/README.md` examples updated to `size: 512Mi`.

---

## Registry Entry Design

Add to `inject-tool/registry.json`:

```json
"cursor-cli": {
  "description": "Cursor Agent CLI",
  "pattern": "bundle",
  "src": "/opt/cursor-cli",
  "binary": "agent",
  "injector": {
    "memoryLimit": "512Mi"
  },
  "patch": [
    {
      "op": "add",
      "path": "/spec/template/components/-",
      "value": {
        "name": "cursor-cli-injector",
        "container": {
          "image": "quay.io/che-incubator/tools-injector/cursor-cli:next",
          "command": ["/bin/sh"],
          "args": ["-c", "cp -a /opt/cursor-cli/. /injected-tools/cursor-cli/"],
          "memoryLimit": "512Mi",
          "mountSources": false,
          "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }]
        }
      }
    }
  ],
  "editor": {
    "volumeMounts": [{ "name": "injected-tools", "path": "/injected-tools" }],
    "env": [],
    "postStart": "mkdir -p \"${XDG_CACHE_HOME:-$HOME/.cache}/cursor-compile-cache\" && mkdir -p /injected-tools/bin && ln -sf /injected-tools/cursor-cli/bin/cursor-agent /injected-tools/bin/cursor-agent"
  }
}
```

**Symlink strategy:**

| Command | Path after injection |
|---------|---------------------|
| `agent` | `/injected-tools/bin/agent` (via inject-tool primary `binary`) |
| `cursor-agent` | `/injected-tools/bin/cursor-agent` (via `postStart` symlink above) |
| Direct access | `/injected-tools/cursor-cli/bin/{agent,cursor-agent}` (always available from bundle copy) |

---

## Known Constraints and Risks

### Volume size

The cursor-cli bundle alone is ~187MB. Global volume is bumped to **512Mi** as part of this work. Existing DevWorkspaces that already have a 256Mi `injected-tools` volume are not automatically resized.

### Editor memory

Bundle tools automatically receive +512Mi editor memory bump in `inject-tool.py`. No extra config required unless agent runs prove memory-heavy (then set `editor.memoryLimit: "1024Mi"` like `claude-code`).

### Version availability

Pinned versions must exist on CDN. `2026.07.13-7fe37d2` verified downloadable for `linux/arm64` during build. Bumping `VERSION` requires confirming the tarball exists for both `x64` and `arm64`.

### Auto-update

Cursor CLI auto-updates by default. In injected workspaces, the bundle is static. Document that users should rely on image version bumps, not `agent update`.

---

## Implementation Tasks

### Task 1: Create install script

**Files:**
- Create: `dockerfiles/cursor-cli/install.sh`

- [x] **Step 1:** Write `install.sh` per design above (download, extract, both symlinks)
- [x] **Step 2:** Make executable (`chmod +x`)
- [x] **Step 3:** Smoke-test locally outside Docker:

```bash
export CURSOR_CLI_VERSION=2026.07.13-7fe37d2
export TARGETARCH=arm64  # or amd64
export CURSOR_CLI_DEST=/tmp/cursor-cli-test
sh dockerfiles/cursor-cli/install.sh
```

Expected: tarball extracts, both symlinks created. (`--version` only works inside Linux container — host macOS cannot execute bundled Linux `node`.)

---

### Task 2: Create Docker image

**Files:**
- Create: `dockerfiles/cursor-cli/Dockerfile`
- Create: `dockerfiles/cursor-cli/VERSION`
- Create: `dockerfiles/cursor-cli/README.md`

- [x] **Step 1:** Write Dockerfile per design above
- [x] **Step 2:** Write `VERSION` with pinned version `2026.07.13-7fe37d2` matching Dockerfile default ARG
- [x] **Step 3:** Write README with DevWorkspace YAML example (mirror `gemini-cli/README.md`), using `size: 512Mi` for `injected-tools`, auth notes (`CURSOR_API_KEY`, `agent auth`), and both command names
- [x] **Step 4:** Build locally:

```bash
podman build -f dockerfiles/cursor-cli/Dockerfile \
  -t quay.io/che-incubator/tools-injector/cursor-cli:next .
```

Expected: build succeeds. **Verified** on Podman/linux/arm64.

- [x] **Step 5:** Verify both commands inside image:

```bash
podman run --rm quay.io/che-incubator/tools-injector/cursor-cli:next \
  /opt/cursor-cli/bin/agent --version
podman run --rm quay.io/che-incubator/tools-injector/cursor-cli:next \
  /opt/cursor-cli/bin/cursor-agent --version
```

Expected: `2026.07.13-7fe37d2` from both. **Verified.**

---

### Task 3: Register in inject-tool and bump global volume

**Files:**
- Modify: `inject-tool/registry.json`
- Modify: `dockerfiles/*/README.md` (8 files: claude-code, gemini-cli, gh, goose, kilocode, opencode, python3, tmux)
- Modify: `inject-tool/README.md`

- [x] **Step 1:** Change `infrastructure.patch` volume size from `256Mi` to `512Mi`
- [x] **Step 2:** Add `cursor-cli` entry per registry design above
- [x] **Step 3:** Update all `dockerfiles/*/README.md` DevWorkspace examples: `size: 256Mi` → `size: 512Mi`
- [x] **Step 4:** Verify listing (requires cluster auth for full `list`; registry validated via JSON parse)

```bash
python3 -c "import json; d=json.load(open('inject-tool/registry.json')); print(d['tools']['cursor-cli']['pattern'])"
```

Expected: `bundle`. **Verified.**

- [x] **Step 5:** Confirm infrastructure patch value:

```bash
python3 -c "import json; d=json.load(open('inject-tool/registry.json')); print(d['infrastructure']['patch'][0]['value']['volume']['size'])"
```

Expected: `512Mi`. **Verified.**

---

### Task 4: Wire build system and CI

**Files:**
- Modify: `Makefile` — add `cursor-cli` to `TOOLS := ...`
- Modify: `.github/workflows/pr.yml` — add `cursor-cli` to `TOOLS='...'`
- Modify: `.github/workflows/release.yml` — add matrix entry

- [x] **Step 1:** Update all three files
- [x] **Step 2:** Verify Makefile target exists:

```bash
make help | grep cursor-cli
```

Expected: `docker-build-cursor-cli`, etc. appear.

---

### Task 5: Multi-arch validation

- [ ] **Step 1:** Build both architectures:

```bash
make docker-build-cursor-cli
```

Expected: amd64 and arm64 images build successfully. (arm64 verified via Podman; amd64 pending CI or local buildx.)

- [ ] **Step 2:** Confirm tarball downloads for both arch mappings (`x64`, `arm64`).

---

### Task 6: Manual Che integration test

In a DevWorkspace with `inject-tool` deployed:

```bash
inject-tool cursor-cli
# workspace restarts
agent --version
cursor-agent --version
which agent          # → /injected-tools/bin/agent
which cursor-agent   # → /injected-tools/bin/cursor-agent
```

With `CURSOR_API_KEY` set:

```bash
agent -p "hello"
```

- [ ] Verify bundle copied to `/injected-tools/cursor-cli/`
- [ ] Verify both commands in PATH
- [ ] Verify editor memory bumped (+512Mi)
- [ ] Verify `inject-tool remove cursor-cli` cleans up
- [ ] Verify `inject-tool cursor-cli --hot` fails with expected error

---

## Test Plan Checklist

- [x] `install.sh` downloads and lays out bundle (arm64)
- [x] Both `agent` and `cursor-agent` return `2026.07.13-7fe37d2` inside built image
- [x] Podman build succeeds (`linux/arm64`)
- [ ] `make docker-build-cursor-cli` succeeds (multi-arch)
- [x] `registry.json` valid; `cursor-cli` entry present; volume `512Mi`
- [ ] New DevWorkspace gets `injected-tools` volume at `512Mi`
- [ ] End-to-end injection in DevWorkspace works
- [ ] Both commands available in PATH after injection
- [ ] `agent` runs with valid `CURSOR_API_KEY`
- [ ] Removal works cleanly

---

## Decisions (Resolved)

| Decision | Choice |
|----------|--------|
| Install approach | Minimal repo-owned `install.sh` (not official `curl \| bash`) |
| Version pinning | `CURSOR_CLI_VERSION` build arg + `VERSION` file |
| Pinned version | `2026.07.13-7fe37d2` (latest lab at implementation time) |
| Release channel | `lab` (default) |
| Injection pattern | `bundle` |
| Exposed commands | Both `agent` and `cursor-agent` in `bin/` |
| Primary registry binary | `agent` |
| Secondary PATH symlink | `cursor-agent` via `postStart` |
| Global volume size | Bump `injected-tools` from `256Mi` to `512Mi` in `infrastructure.patch` |

## Decisions (Deferred)

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Editor memory floor | default +512Mi vs explicit 1024Mi | Start with automatic +512Mi bump |
| Makefile `docker-build-local-*` hyphen ambiguity | fix pattern rule vs document workaround | Document workaround; fix in separate PR if desired |

---

## Estimated Scope

| Component | Effort |
|-----------|--------|
| `install.sh` + Dockerfile + README + VERSION | ~1h |
| registry.json + README volume docs + Makefile + CI | ~45m |
| Multi-arch build verification | ~30m (large image) |
| Che manual testing | ~1h (needs cluster + API key) |

**Total:** ~half day for implementation + validation.
