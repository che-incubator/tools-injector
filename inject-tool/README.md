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

# List available tools and injection status
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
| claude-code | init | Anthropic's CLI for Claude |
| tmux | init | Terminal multiplexer |
| python3 | init | Python3 runtime (fallback for inject-tool.py) |
| kilocode | bundle | AI coding agent |
| gemini-cli | bundle | Google's Gemini CLI |

## Configuration

| Env Var | Default | Description |
|---------|---------|-------------|
| `INJECT_TOOL_REGISTRY` | `quay.io/che-incubator` | Image registry prefix |
| `INJECT_TOOL_TAG` | `next` | Image tag |

## Architecture

The tool is delivered as two files via ConfigMap automount:

- **`inject-tool`** — shell shim that finds python3 (system PATH → `/injected-tools/bin/python3` → error) and exec's the Python3 script.
- **`inject-tool.py`** — full CLI written in Python3 stdlib only. Uses `urllib.request` for Kubernetes API, native `json` for patch building.

**Init container tools** (opencode, goose, claude-code, tmux, python3): patches the DevWorkspace CR to add an init container that copies the tool binary to a shared `/injected-tools` volume. A postStart event creates a symlink in `/injected-tools/bin/` and adds it to PATH via `~/.bashrc`.

**Bundle tools** (kilocode, gemini-cli): patches the DevWorkspace CR to add an init container that copies the full Node.js runtime + tool directory to `/injected-tools/<tool>/`. The editor container gets a +512Mi memory bump.

**Hot inject** (`--hot`): extracts the binary from the container image using `oc image extract`. Init-pattern tools only. Not persistent across restarts.
