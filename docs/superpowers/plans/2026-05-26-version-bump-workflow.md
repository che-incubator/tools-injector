# Version Bump Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add automated version detection and bump PRs for all 8 injected tools via a GitHub Actions workflow.

**Architecture:** A single workflow file (`version-bump.yml`) runs on a configurable cron schedule or manual dispatch. It uses a matrix strategy with one job per tool. Each job reads the current version from `dockerfiles/<tool>/VERSION`, queries the upstream source (GitHub Releases API, npm registry, or Alpine apk), and if a newer stable version exists, updates the VERSION file + Dockerfile, commits, and opens a PR.

**Tech Stack:** GitHub Actions, shell (bash), `gh` CLI (available in runners), `npm` CLI, `docker` CLI.

**Spec:** `docs/superpowers/specs/2026-05-26-version-bump-workflow-design.md`

---

## File Map

**New files:**
- `dockerfiles/opencode/VERSION` — single line: `v1.2.27`
- `dockerfiles/goose/VERSION` — single line: `v1.28.0`
- `dockerfiles/claude-code/VERSION` — single line: `2.1.81`
- `dockerfiles/tmux/VERSION` — single line: `3.6a`
- `dockerfiles/gh/VERSION` — single line: `2.92.0`
- `dockerfiles/kilocode/VERSION` — single line (current npm latest, to be resolved)
- `dockerfiles/gemini-cli/VERSION` — single line (current npm latest, to be resolved)
- `dockerfiles/python3/VERSION` — single line (current Alpine version, to be resolved)
- `.github/workflows/version-bump.yml` — the bump workflow

**Modified files:**
- `dockerfiles/kilocode/Dockerfile` — pin npm install to specific version via ARG
- `dockerfiles/gemini-cli/Dockerfile` — pin npm install to specific version via ARG
- `dockerfiles/python3/Dockerfile` — add ARG for python3 version tracking

---

## Task 1: Create VERSION files for ARG-pinned tools

These 5 tools already have explicit version ARGs in their Dockerfiles. Extract the current values into VERSION files.

**Files:**
- Create: `dockerfiles/opencode/VERSION`
- Create: `dockerfiles/goose/VERSION`
- Create: `dockerfiles/claude-code/VERSION`
- Create: `dockerfiles/tmux/VERSION`
- Create: `dockerfiles/gh/VERSION`

- [ ] **Step 1: Create VERSION files**

Each file is a single line (no trailing newline) matching the current ARG default:

`dockerfiles/opencode/VERSION`:
```
v1.2.27
```

`dockerfiles/goose/VERSION`:
```
v1.28.0
```

`dockerfiles/claude-code/VERSION`:
```
2.1.81
```

`dockerfiles/tmux/VERSION`:
```
3.6a
```

`dockerfiles/gh/VERSION`:
```
2.92.0
```

- [ ] **Step 2: Verify VERSION files match Dockerfile ARGs**

```bash
for tool in opencode goose claude-code tmux gh; do
  VERSION=$(cat "dockerfiles/${tool}/VERSION")
  ARG_VAL=$(grep -oP '(?<=_VERSION=).*' "dockerfiles/${tool}/Dockerfile" | head -1)
  if [ "$VERSION" = "$ARG_VAL" ]; then
    echo "OK: ${tool} VERSION=${VERSION} matches ARG=${ARG_VAL}"
  else
    echo "MISMATCH: ${tool} VERSION=${VERSION} vs ARG=${ARG_VAL}"
    exit 1
  fi
done
```

Expected: all 5 print `OK`.

- [ ] **Step 3: Commit**

```bash
git add dockerfiles/opencode/VERSION dockerfiles/goose/VERSION \
       dockerfiles/claude-code/VERSION dockerfiles/tmux/VERSION \
       dockerfiles/gh/VERSION
git commit -s -m "chore: add VERSION files for ARG-pinned tools

Track current versions in dedicated files for automated bump detection.
opencode=v1.2.27, goose=v1.28.0, claude-code=2.1.81, tmux=3.6a, gh=2.92.0"
```

---

## Task 2: Pin npm tools and create their VERSION files

Kilocode and gemini-cli currently install the latest npm version. Pin them to a specific version using a Dockerfile ARG, and create VERSION files.

**Files:**
- Modify: `dockerfiles/kilocode/Dockerfile:4`
- Modify: `dockerfiles/gemini-cli/Dockerfile:4`
- Create: `dockerfiles/kilocode/VERSION`
- Create: `dockerfiles/gemini-cli/VERSION`

- [ ] **Step 1: Look up current latest stable versions**

```bash
npm view @kilocode/cli dist-tags.latest
npm view @google/gemini-cli dist-tags.latest
```

Note the exact version strings returned. Use these as the initial pinned versions.

- [ ] **Step 2: Update kilocode Dockerfile to pin version via ARG**

Current `dockerfiles/kilocode/Dockerfile` line 4:
```dockerfile
RUN npm install -g @kilocode/cli && \
```

Change to (using the version from Step 1, shown here as `$KILO_VER`):
```dockerfile
ARG KILOCODE_VERSION=$KILO_VER

RUN npm install -g @kilocode/cli@${KILOCODE_VERSION} && \
```

Insert the `ARG` line after `FROM node:22-slim AS builder` (line 2), and update the `RUN` line.

- [ ] **Step 3: Update gemini-cli Dockerfile to pin version via ARG**

Current `dockerfiles/gemini-cli/Dockerfile` line 4:
```dockerfile
RUN npm install -g @google/gemini-cli && \
```

Change to (using the version from Step 1, shown here as `$GEMINI_VER`):
```dockerfile
ARG GEMINI_CLI_VERSION=$GEMINI_VER

RUN npm install -g @google/gemini-cli@${GEMINI_CLI_VERSION} && \
```

Insert the `ARG` line after `FROM node:22-slim AS builder` (line 2), and update the `RUN` line.

- [ ] **Step 4: Create VERSION files**

`dockerfiles/kilocode/VERSION`:
```
$KILO_VER
```

`dockerfiles/gemini-cli/VERSION`:
```
$GEMINI_VER
```

(Replace `$KILO_VER` and `$GEMINI_VER` with actual values from Step 1.)

- [ ] **Step 5: Verify VERSION matches Dockerfile ARG**

```bash
for tool in kilocode gemini-cli; do
  VERSION=$(cat "dockerfiles/${tool}/VERSION")
  ARG_NAME=$(echo "$tool" | tr '[:lower:]-' '[:upper:]_')_VERSION
  ARG_VAL=$(grep -oP "(?<=${ARG_NAME}=).*" "dockerfiles/${tool}/Dockerfile" | head -1)
  echo "${tool}: VERSION=${VERSION} ARG=${ARG_VAL}"
  [ "$VERSION" = "$ARG_VAL" ] || { echo "MISMATCH"; exit 1; }
done
```

Expected: both match.

- [ ] **Step 6: Commit**

```bash
git add dockerfiles/kilocode/Dockerfile dockerfiles/kilocode/VERSION \
       dockerfiles/gemini-cli/Dockerfile dockerfiles/gemini-cli/VERSION
git commit -s -m "chore: pin npm tools to specific versions

Add ARG-based version pinning for kilocode and gemini-cli.
Previously installed whatever 'latest' was at build time."
```

---

## Task 3: Add python3 version tracking

Python3 comes from Alpine's `apk`. We track its version but the Dockerfile doesn't use a download URL we can parameterize — the version comes from whatever Alpine 3.21 ships. We add a VERSION file for tracking purposes and an ARG for documentation, but the `apk add` command doesn't change behavior.

**Files:**
- Modify: `dockerfiles/python3/Dockerfile:4`
- Create: `dockerfiles/python3/VERSION`

- [ ] **Step 1: Look up current Alpine 3.21 python3 version**

```bash
docker run --rm alpine:3.21 sh -c 'apk update >/dev/null 2>&1 && apk policy python3' | sed -n 's/^  \([0-9].*\):/\1/p' | head -1
```

This queries repository metadata and returns something like `3.12.13-r0`. Extract just the version: `3.12.13`.

- [ ] **Step 2: Add ARG to python3 Dockerfile**

Current `dockerfiles/python3/Dockerfile` line 4:
```dockerfile
RUN apk add --no-cache python3 && \
```

Add a tracking ARG before the RUN (after `FROM alpine:3.21 AS builder`, line 1):
```dockerfile
ARG PYTHON3_VERSION=3.12.11
```

The `apk add` command stays as-is — Alpine pins the version within a release. The ARG is for the bump workflow to compare against.

- [ ] **Step 3: Create VERSION file**

`dockerfiles/python3/VERSION`:
```
3.12.11
```

(Use the actual version from Step 1.)

- [ ] **Step 4: Commit**

```bash
git add dockerfiles/python3/Dockerfile dockerfiles/python3/VERSION
git commit -s -m "chore: add python3 version tracking

Add VERSION file and ARG for Alpine-provided python3 version.
Enables automated version monitoring."
```

---

## Task 4: Create the version-bump workflow

The main workflow file that ties everything together.

**Files:**
- Create: `.github/workflows/version-bump.yml`

- [ ] **Step 1: Create the workflow file**

```yaml
#
# Copyright (c) 2021 Red Hat, Inc.
# This program and the accompanying materials are made
# available under the terms of the Eclipse Public License 2.0
# which is available at https://www.eclipse.org/legal/epl-2.0/
#
# SPDX-License-Identifier: EPL-2.0
#
name: Version Bump

on:
  schedule:
    - cron: '17 8 * * 1'
  workflow_dispatch:
    inputs:
      tool:
        description: 'Specific tool to check (leave empty for all)'
        required: false
        type: string

permissions:
  contents: write
  pull-requests: write

jobs:

  check-versions:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        tool:
          - name: opencode
            source: github
            repo: anomalyco/opencode
            arg_name: OPENCODE_VERSION
          - name: goose
            source: github
            repo: block/goose
            arg_name: GOOSE_VERSION
          - name: claude-code
            source: github
            repo: anthropics/claude-code
            arg_name: CLAUDE_CODE_VERSION
            strip_v: true
          - name: tmux
            source: github
            repo: tmux/tmux
            arg_name: TMUX_VERSION
          - name: gh
            source: github
            repo: cli/cli
            arg_name: GH_VERSION
            strip_v: true
          - name: kilocode
            source: npm
            package: "@kilocode/cli"
            arg_name: KILOCODE_VERSION
          - name: gemini-cli
            source: npm
            package: "@google/gemini-cli"
            arg_name: GEMINI_CLI_VERSION
          - name: python3
            source: alpine
            arg_name: PYTHON3_VERSION

    steps:
      - name: "Filter by tool input"
        if: >-
          inputs.tool != '' &&
          inputs.tool != matrix.tool.name
        run: |
          echo "Skipping ${{ matrix.tool.name }} (requested: ${{ inputs.tool }})"
          exit 0

      - name: "Checkout source code"
        if: inputs.tool == '' || inputs.tool == matrix.tool.name
        uses: actions/checkout@v4

      - name: "Read current version"
        if: inputs.tool == '' || inputs.tool == matrix.tool.name
        id: current
        run: |
          CURRENT=$(cat "dockerfiles/${{ matrix.tool.name }}/VERSION" | tr -d '[:space:]')
          echo "version=${CURRENT}" >> "$GITHUB_OUTPUT"
          echo "Current ${{ matrix.tool.name }} version: ${CURRENT}"

      - name: "Fetch latest version (GitHub)"
        if: >-
          (inputs.tool == '' || inputs.tool == matrix.tool.name) &&
          matrix.tool.source == 'github'
        id: latest_github
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          TAG=$(gh api "repos/${{ matrix.tool.repo }}/releases/latest" --jq '.tag_name')
          echo "Raw tag: ${TAG}"

          if [ "${{ matrix.tool.strip_v }}" = "true" ]; then
            LATEST="${TAG#v}"
          else
            LATEST="${TAG}"
          fi

          echo "version=${LATEST}" >> "$GITHUB_OUTPUT"
          echo "Latest ${{ matrix.tool.name }} version: ${LATEST}"

      - name: "Fetch latest version (npm)"
        if: >-
          (inputs.tool == '' || inputs.tool == matrix.tool.name) &&
          matrix.tool.source == 'npm'
        id: latest_npm
        run: |
          LATEST=$(npm view "${{ matrix.tool.package }}" dist-tags.latest)
          echo "version=${LATEST}" >> "$GITHUB_OUTPUT"
          echo "Latest ${{ matrix.tool.name }} version: ${LATEST}"

      - name: "Fetch latest version (Alpine)"
        if: >-
          (inputs.tool == '' || inputs.tool == matrix.tool.name) &&
          matrix.tool.source == 'alpine'
        id: latest_alpine
        run: |
          ALPINE_VER=$(grep '^FROM alpine:' "dockerfiles/python3/Dockerfile" | head -1 | sed 's/.*alpine://; s/ .*//')
          RAW=$(docker run --rm "alpine:${ALPINE_VER}" sh -c 'apk update >/dev/null 2>&1 && apk policy python3 2>/dev/null | sed -n "s/^  \([0-9].*\):/\1/p" | head -1')
          # Extract version: "3.12.13-r0" -> "3.12.13"
          LATEST=$(echo "$RAW" | sed 's/-r[0-9]*$//')
          if [ -z "$LATEST" ]; then
            echo "::error::Failed to fetch python3 version from Alpine ${ALPINE_VER}"
            exit 1
          fi
          echo "version=${LATEST}" >> "$GITHUB_OUTPUT"
          echo "Latest ${{ matrix.tool.name }} version: ${LATEST} (Alpine ${ALPINE_VER})"

      - name: "Resolve latest version"
        if: inputs.tool == '' || inputs.tool == matrix.tool.name
        id: latest
        run: |
          if [ -n "${{ steps.latest_github.outputs.version }}" ]; then
            echo "version=${{ steps.latest_github.outputs.version }}" >> "$GITHUB_OUTPUT"
          elif [ -n "${{ steps.latest_npm.outputs.version }}" ]; then
            echo "version=${{ steps.latest_npm.outputs.version }}" >> "$GITHUB_OUTPUT"
          elif [ -n "${{ steps.latest_alpine.outputs.version }}" ]; then
            echo "version=${{ steps.latest_alpine.outputs.version }}" >> "$GITHUB_OUTPUT"
          else
            echo "No version found"
            exit 1
          fi

      - name: "Compare versions"
        if: inputs.tool == '' || inputs.tool == matrix.tool.name
        id: compare
        run: |
          CURRENT="${{ steps.current.outputs.version }}"
          LATEST="${{ steps.latest.outputs.version }}"
          if [ "$CURRENT" = "$LATEST" ]; then
            echo "needs_bump=false" >> "$GITHUB_OUTPUT"
            echo "${{ matrix.tool.name }} is up to date (${CURRENT})"
          else
            echo "needs_bump=true" >> "$GITHUB_OUTPUT"
            echo "${{ matrix.tool.name }} needs bump: ${CURRENT} → ${LATEST}"
          fi

      - name: "Check for existing PR"
        if: >-
          (inputs.tool == '' || inputs.tool == matrix.tool.name) &&
          steps.compare.outputs.needs_bump == 'true'
        id: existing_pr
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          BRANCH="bump/${{ matrix.tool.name }}-${{ steps.latest.outputs.version }}"
          EXISTING=$(gh pr list --head "${BRANCH}" --state open --json number --jq 'length')
          if [ "$EXISTING" -gt 0 ]; then
            echo "exists=true" >> "$GITHUB_OUTPUT"
            echo "PR already exists for ${BRANCH}, skipping"
          else
            echo "exists=false" >> "$GITHUB_OUTPUT"
          fi

      - name: "Create bump branch and update files"
        if: >-
          (inputs.tool == '' || inputs.tool == matrix.tool.name) &&
          steps.compare.outputs.needs_bump == 'true' &&
          steps.existing_pr.outputs.exists == 'false'
        env:
          CURRENT: ${{ steps.current.outputs.version }}
          LATEST: ${{ steps.latest.outputs.version }}
          TOOL: ${{ matrix.tool.name }}
          ARG_NAME: ${{ matrix.tool.arg_name }}
        run: |
          BRANCH="bump/${TOOL}-${LATEST}"
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git checkout -b "${BRANCH}"

          # Update VERSION file
          echo -n "${LATEST}" > "dockerfiles/${TOOL}/VERSION"

          # Update Dockerfile ARG
          sed -i "s/^ARG ${ARG_NAME}=.*/ARG ${ARG_NAME}=${LATEST}/" "dockerfiles/${TOOL}/Dockerfile"

          git add "dockerfiles/${TOOL}/VERSION" "dockerfiles/${TOOL}/Dockerfile"
          git commit -s -m "bump(${TOOL}): ${CURRENT} → ${LATEST}"
          git push origin "${BRANCH}"

      - name: "Open pull request"
        if: >-
          (inputs.tool == '' || inputs.tool == matrix.tool.name) &&
          steps.compare.outputs.needs_bump == 'true' &&
          steps.existing_pr.outputs.exists == 'false'
        env:
          GH_TOKEN: ${{ github.token }}
          CURRENT: ${{ steps.current.outputs.version }}
          LATEST: ${{ steps.latest.outputs.version }}
          TOOL: ${{ matrix.tool.name }}
        run: |
          BRANCH="bump/${TOOL}-${LATEST}"

          # Build release URL
          RELEASE_URL=""
          if [ "${{ matrix.tool.source }}" = "github" ]; then
            TAG="${LATEST}"
            # Add v prefix back for GitHub URL if it was stripped
            if [ "${{ matrix.tool.strip_v }}" = "true" ]; then
              TAG="v${LATEST}"
            fi
            RELEASE_URL="https://github.com/${{ matrix.tool.repo }}/releases/tag/${TAG}"
          elif [ "${{ matrix.tool.source }}" = "npm" ]; then
            RELEASE_URL="https://www.npmjs.com/package/${{ matrix.tool.package }}/v/${LATEST}"
          fi

          BODY="## Version Bump

          **Tool:** ${TOOL}
          **Current:** ${CURRENT}
          **New:** ${LATEST}"

          if [ -n "$RELEASE_URL" ]; then
            BODY="${BODY}
          **Release:** ${RELEASE_URL}"
          fi

          BODY="${BODY}

          ---
          *Automated by the version-bump workflow.*"

          gh pr create \
            --head "${BRANCH}" \
            --base main \
            --title "bump(${TOOL}): ${CURRENT} → ${LATEST}" \
            --body "${BODY}" \
            --label "automated" \
            --label "version-bump"
```

- [ ] **Step 2: Validate YAML syntax**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/version-bump.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`

If python3/PyYAML is not available locally, use:
```bash
gh workflow list 2>/dev/null
```
(Syntax errors will be caught on push by GitHub.)

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/version-bump.yml
git commit -s -m "feat: add automated version bump workflow

Checks all 8 tools for new upstream releases via GitHub Releases API,
npm registry, and Alpine apk. Opens per-tool PRs when updates are found.
Runs weekly (Monday 8:17 UTC) and supports manual dispatch."
```

---

## Task 5: Verify the complete setup

End-to-end verification that VERSION files, Dockerfiles, and the workflow are all consistent.

**Files:** (read-only verification, no modifications)

- [ ] **Step 1: Verify all 8 VERSION files exist and have content**

```bash
for tool in opencode goose claude-code tmux gh kilocode gemini-cli python3; do
  FILE="dockerfiles/${tool}/VERSION"
  if [ ! -f "$FILE" ]; then
    echo "MISSING: $FILE"
    exit 1
  fi
  VERSION=$(cat "$FILE" | tr -d '[:space:]')
  if [ -z "$VERSION" ]; then
    echo "EMPTY: $FILE"
    exit 1
  fi
  echo "OK: ${tool}=${VERSION}"
done
```

Expected: all 8 print `OK`.

- [ ] **Step 2: Verify all Dockerfiles have matching ARG defaults**

```bash
for tool in opencode goose claude-code tmux gh kilocode gemini-cli python3; do
  VERSION=$(cat "dockerfiles/${tool}/VERSION" | tr -d '[:space:]')
  # Find the ARG line (case-insensitive tool name with underscores + _VERSION)
  ARG_LINE=$(grep '^ARG .*_VERSION=' "dockerfiles/${tool}/Dockerfile" | head -1)
  ARG_VAL=$(echo "$ARG_LINE" | cut -d= -f2)
  if [ "$VERSION" = "$ARG_VAL" ]; then
    echo "OK: ${tool} VERSION=${VERSION} == ARG=${ARG_VAL}"
  else
    echo "MISMATCH: ${tool} VERSION=${VERSION} vs ARG=${ARG_VAL}"
    exit 1
  fi
done
```

Expected: all 8 match.

- [ ] **Step 3: Verify workflow matrix covers all tools**

```bash
TOOLS_IN_MAKEFILE=$(grep '^TOOLS :=' Makefile | sed 's/TOOLS := //')
for tool in $TOOLS_IN_MAKEFILE; do
  if grep -q "name: ${tool}" .github/workflows/version-bump.yml; then
    echo "OK: ${tool} in workflow matrix"
  else
    echo "MISSING: ${tool} not in workflow matrix"
    exit 1
  fi
done
```

Expected: all 8 tools found in the workflow.

- [ ] **Step 4: Verify workflow YAML is valid**

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/version-bump.yml'))" && echo "YAML OK"
```

Expected: `YAML OK`
