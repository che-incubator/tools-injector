# inject-tool

Dynamically inject CLI tools into running DevWorkspaces.

## Setup

Deploy to a namespace (all workspaces in that namespace get `inject-tool`):

```bash
./setup.sh <namespace>
```

## Usage

From inside a DevWorkspace terminal:

```bash
# Inject one or more tools (single restart)
inject-tool opencode
inject-tool claude-code goose tmux

# Inject without restart (one tool only, requires oc CLI)
inject-tool opencode --hot

# List available tools, injection status, and installed/available versions
inject-tool list

# Remove one or more tools (single restart)
inject-tool remove opencode
inject-tool remove kilocode gemini-cli

# Remove hot-injected binary only (one tool only)
inject-tool remove opencode --hot
```

## Available Tools

| Tool | Pattern | Description |
|------|---------|-------------|
| opencode | init | AI coding assistant |
| goose | init | AI developer agent |
| codex | init | OpenAI's Codex CLI |
| claude-code | init | Anthropic's CLI for Claude |
| tmux | init | Terminal multiplexer |
| python3 | bundle | Python3 runtime (python-build-standalone glibc bundle; fallback for inject-tool.py) |
| kilocode | bundle | AI coding agent |
| gemini-cli | bundle | Google's Gemini CLI |
| cursor-cli | bundle | Cursor Agent CLI |
| gh | init | GitHub CLI |
| uv | init | Python package and project manager |
| pi | bundle | Pi coding agent by earendil-works |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `INJECT_TOOL_REGISTRY` | `quay.io/che-incubator` | Image registry prefix |
| `INJECT_TOOL_TAG` | `next` | Image tag |

## Architecture

The tool is delivered as two files via ConfigMap automount:

- **`inject-tool`** — shell shim that finds python3 (system PATH → `/injected-tools/bin/python3` → error) and exec's the Python3 script.
- **`inject-tool.py`** — full CLI written in Python3 stdlib only. Uses `urllib.request` for Kubernetes API, native `json` for patch building.

**Init container tools** (opencode, goose, claude-code, tmux): patches the DevWorkspace CR to add an init container that copies the tool binary to a shared `/injected-tools` volume. A postStart event creates a symlink in `/injected-tools/bin/` and adds it to PATH via `~/.bashrc`.

**Bundle tools** (kilocode, gemini-cli, cursor-cli, python3): patches the DevWorkspace CR to add an init container that copies the full runtime + tool directory to `/injected-tools/<tool>/`. The editor container gets a +512Mi memory bump by default, overridable per tool via `editor.memoryBump` (python3 sets 0Mi).

**Hot inject** (`--hot`): extracts the binary from the container image using `oc image extract`. Init-pattern tools only. Not persistent across restarts.

**`list` version probing**: the available version comes from the `version` field in `registry.json` (kept in sync with `dockerfiles/<tool>/VERSION` and the Dockerfile `ARG` by the version-bump workflow, and checked in CI). For every tool whose binary is present, `list` runs its version command in parallel with a per-command timeout — `<binary> --version` by default, overridable per tool via `versionCommand`/`versionRegex` in `registry.json`. A hanging or failing tool shows `?`; a tool injected but not yet restarted shows `pending restart`.
