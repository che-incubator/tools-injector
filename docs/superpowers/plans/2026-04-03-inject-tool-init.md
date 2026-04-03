# `inject-tool init` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `inject-tool init` subcommand that reads `.che/inject-tools.json` from workspace project directories and injects declared tools (registry or custom) in one operation.

**Architecture:** Extend `inject-tool.py` with config file discovery, custom tool resolution (converting inline definitions to registry-compatible format), and a new `init` subcommand that reuses existing `build_inject_ops()`. No new dependencies — JSON parsing via stdlib.

**Tech Stack:** Python 3 (stdlib only), Kubernetes JSON Patch API (existing)

**Spec:** `docs/2026-04-03-auto-inject-design.md`

---

### Task 1: Add `init` subcommand to CLI parser

**Files:**
- Modify: `inject-tool/inject-tool.py:228-256` (parse_args)
- Modify: `inject-tool/inject-tool.py:584-594` (main)

- [ ] **Step 1: Add `init` subparser in `parse_args()`**

In the `parse_args()` function, after the `remove` subparser (line 243), add:

```python
    init_p = sub.add_parser("init", help="Inject tools declared in .che/inject-tools.json")
    init_p.add_argument("--dry-run", action="store_true", help="Show what would be injected without patching")
```

Update the `known_commands` set on line 247 to include `"init"`:

```python
    known_commands = {"inject", "list", "remove", "init"}
```

- [ ] **Step 2: Add `init` dispatch in `main()`**

In the `main()` function, after the `remove` elif (line 594), add:

```python
    elif args.command == "init":
        cmd_init(args.dry_run)
```

- [ ] **Step 3: Add stub `cmd_init()` function**

Above `main()` (before the `# Main` section), add:

```python
def cmd_init(dry_run):
    info("init is not yet implemented.")
```

- [ ] **Step 4: Verify the CLI parses correctly**

Run inside a workspace terminal:

```bash
inject-tool init --help
```

Expected: help text showing `--dry-run` flag.

```bash
inject-tool init
```

Expected: `==> init is not yet implemented.`

- [ ] **Step 5: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat: add init subcommand stub to CLI parser"
```

---

### Task 2: Implement config file discovery

**Files:**
- Modify: `inject-tool/inject-tool.py` (add `discover_configs()` function)

- [ ] **Step 1: Add `discover_configs()` function**

Add this function in the `# Commands` section, before `cmd_list()`:

```python
PROJECTS_DIR = "/projects"


def discover_configs():
    """Find .che/inject-tools.json files in workspace projects.

    Returns a list of file paths, sorted alphabetically by parent directory.
    """
    override = os.environ.get("INJECT_TOOLS_CONFIG")
    if override:
        if not os.path.isfile(override):
            die(f"INJECT_TOOLS_CONFIG points to non-existent file: {override}")
        return [override]

    configs = []
    if not os.path.isdir(PROJECTS_DIR):
        return configs

    for entry in sorted(os.listdir(PROJECTS_DIR)):
        config_path = os.path.join(PROJECTS_DIR, entry, ".che", "inject-tools.json")
        if os.path.isfile(config_path):
            configs.append(config_path)

    return configs
```

- [ ] **Step 2: Add `load_inject_config()` function**

Add right after `discover_configs()`:

```python
def load_inject_config(config_path):
    """Load and validate a .che/inject-tools.json file.

    Returns the parsed JSON data.
    """
    try:
        with open(config_path) as f:
            data = json.load(f)
    except OSError as e:
        die(f"Cannot read config file {config_path}: {e}")
    except json.JSONDecodeError as e:
        die(f"Invalid JSON in {config_path}: {e}")

    if "tools" not in data or not isinstance(data["tools"], list):
        die(f"{config_path}: missing or invalid 'tools' array")

    return data
```

- [ ] **Step 3: Wire discovery into `cmd_init()` stub**

Replace the `cmd_init()` stub with:

```python
def cmd_init(dry_run):
    validate_env()

    configs = discover_configs()
    if not configs:
        info("No .che/inject-tools.json found in /projects/*/. Nothing to do.")
        return

    for config_path in configs:
        info(f"Found config: {config_path}")

    # Tool resolution will be added in the next task.
```

- [ ] **Step 4: Test discovery manually**

Create a test config file inside a workspace:

```bash
mkdir -p /projects/test-project/.che
echo '{"tools": ["opencode"]}' > /projects/test-project/.che/inject-tools.json
inject-tool init
```

Expected:
```
==> Found config: /projects/test-project/.che/inject-tools.json
```

Clean up:

```bash
rm -rf /projects/test-project
```

- [ ] **Step 5: Test INJECT_TOOLS_CONFIG override**

```bash
echo '{"tools": ["tmux"]}' > /tmp/test-inject.json
INJECT_TOOLS_CONFIG=/tmp/test-inject.json inject-tool init
```

Expected:
```
==> Found config: /tmp/test-inject.json
```

- [ ] **Step 6: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat: add config file discovery for inject-tool init"
```

---

### Task 3: Resolve tool declarations from config

**Files:**
- Modify: `inject-tool/inject-tool.py` (add `resolve_tools()` and `build_custom_tool_entry()`)

- [ ] **Step 1: Add `build_custom_tool_entry()` function**

Add after `load_inject_config()`:

```python
def build_custom_tool_entry(tool_def):
    """Convert a custom tool object from .che/inject-tools.json into a
    registry-compatible tool entry that build_inject_ops() can consume.
    """
    for field in ("name", "image", "binaries"):
        if field not in tool_def:
            die(f"Custom tool definition missing required field '{field}': {json.dumps(tool_def)}")

    if not isinstance(tool_def["binaries"], list) or not tool_def["binaries"]:
        die(f"Custom tool '{tool_def['name']}': 'binaries' must be a non-empty array")

    for b in tool_def["binaries"]:
        if "src" not in b or "binary" not in b:
            die(f"Custom tool '{tool_def['name']}': each binary entry needs 'src' and 'binary'")

    name = tool_def["name"]
    image = tool_def["image"]
    binaries = tool_def["binaries"]
    mem_limit = tool_def.get("memoryLimit", "128Mi")

    # Build the init container command
    if len(binaries) == 1:
        command = ["/bin/cp"]
        args = [binaries[0]["src"], f"/injected-tools/{binaries[0]['binary']}"]
    else:
        srcs = " ".join(b["src"] for b in binaries)
        command = ["/bin/sh"]
        args = ["-c", f"cp {srcs} /injected-tools/"]

    patch = [{
        "op": "add",
        "path": "/spec/template/components/-",
        "value": {
            "name": f"{name}-injector",
            "container": {
                "image": image,
                "command": command,
                "args": args,
                "memoryLimit": mem_limit,
                "mountSources": False,
                "volumeMounts": [{"name": "injected-tools", "path": "/injected-tools"}],
            },
        },
    }]

    # Use the first binary as the primary (for existing build_inject_ops logic)
    return {
        "description": tool_def.get("description", f"{name} (custom)"),
        "pattern": "init",
        "src": binaries[0]["src"],
        "binary": binaries[0]["binary"],
        "patch": patch,
        "editor": {
            "volumeMounts": [{"name": "injected-tools", "path": "/injected-tools"}],
            "env": tool_def.get("env", []),
            "postStart": tool_def.get("postStart", ""),
        },
        "_binaries": binaries,
    }
```

- [ ] **Step 2: Add `resolve_tools()` function**

Add after `build_custom_tool_entry()`:

```python
def resolve_tools(configs):
    """Resolve all tool declarations from config files.

    Returns a list of (tool_name, tool_entry_or_None) tuples.
    - Registry tools: (name, None) — looked up from REGISTRY_DATA at inject time.
    - Custom tools: (name, dict) — the registry-compatible entry.

    Deduplicates by name (first occurrence wins).
    """
    seen = set()
    resolved = []

    for config_path in configs:
        data = load_inject_config(config_path)
        for item in data["tools"]:
            if isinstance(item, str):
                # Registry tool reference
                if item in seen:
                    continue
                if item not in REGISTRY_DATA["tools"]:
                    die(f"{config_path}: unknown tool '{item}'. "
                        f"Available: {', '.join(sorted(REGISTRY_DATA['tools']))}")
                seen.add(item)
                resolved.append((item, None))

            elif isinstance(item, dict):
                # Custom tool definition
                name = item.get("name")
                if not name:
                    die(f"{config_path}: custom tool missing 'name': {json.dumps(item)}")
                if name in seen:
                    continue
                entry = build_custom_tool_entry(item)
                seen.add(name)
                resolved.append((name, entry))

            else:
                die(f"{config_path}: each tool must be a string or object, got: {type(item).__name__}")

    return resolved
```

- [ ] **Step 3: Wire resolution into `cmd_init()`**

Update `cmd_init()` to call `resolve_tools()`:

```python
def cmd_init(dry_run):
    validate_env()

    configs = discover_configs()
    if not configs:
        info("No .che/inject-tools.json found in /projects/*/. Nothing to do.")
        return

    for config_path in configs:
        info(f"Found config: {config_path}")

    resolved = resolve_tools(configs)
    if not resolved:
        info("No tools declared in config files.")
        return

    for name, entry in resolved:
        kind = "custom" if entry else "registry"
        info(f"  {name} ({kind})")

    # Injection will be added in the next task.
```

- [ ] **Step 4: Test resolution manually**

Create a config with both registry and custom tools:

```bash
mkdir -p /projects/test-project/.che
cat > /projects/test-project/.che/inject-tools.json << 'EOF'
{
  "tools": [
    "opencode",
    {
      "name": "dev-tools",
      "image": "quay.io/test/tools:latest",
      "binaries": [
        {"src": "/usr/bin/git", "binary": "git"},
        {"src": "/usr/bin/jq", "binary": "jq"}
      ]
    }
  ]
}
EOF
inject-tool init
```

Expected:
```
==> Found config: /projects/test-project/.che/inject-tools.json
==>   opencode (registry)
==>   dev-tools (custom)
```

Test error case — unknown registry tool:

```bash
echo '{"tools": ["nonexistent"]}' > /projects/test-project/.che/inject-tools.json
inject-tool init
```

Expected: error listing available tools.

Clean up:

```bash
rm -rf /projects/test-project
```

- [ ] **Step 5: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "feat: add tool resolution for registry and custom tools"
```

---

### Task 4: Refactor `build_inject_ops()` to accept a tool entry dict

**Files:**
- Modify: `inject-tool/inject-tool.py:274-398` (build_inject_ops)

Currently `build_inject_ops()` takes a tool name string and looks up
`REGISTRY_DATA["tools"][tool]`. It needs to also accept a pre-built tool entry
dict for custom tools.

- [ ] **Step 1: Add `tool_entry` parameter to `build_inject_ops()`**

Change the function signature from:

```python
def build_inject_ops(tool, ws, skip_infra=False):
    reg_tool = REGISTRY_DATA["tools"][tool]
```

To:

```python
def build_inject_ops(tool, ws, skip_infra=False, tool_entry=None):
    reg_tool = tool_entry if tool_entry else REGISTRY_DATA["tools"][tool]
```

- [ ] **Step 2: Handle multi-binary symlinks for custom tools**

The existing symlink logic (lines 363-397) creates one symlink for `reg_tool["binary"]`.
For custom tools with multiple binaries, we need symlinks for each.

Replace the symlink block (starting at `# 6. Symlink command + postStart event`,
line 362) with:

```python
    # 6. Symlink command + postStart event
    if editor_name:
        symlink_cmd_id = f"symlink-{tool}"
        if find_command_index(ws, symlink_cmd_id) is None:
            # Collect all binaries to symlink
            all_binaries = reg_tool.get("_binaries", [{"src": reg_tool["src"], "binary": binary_name}])

            symlink_parts = []
            for b in all_binaries:
                b_name = b["binary"]
                if pattern == "init":
                    symlink_target = f"/injected-tools/{b_name}"
                else:
                    symlink_target = f"/injected-tools/{tool}/bin/{b_name}"
                symlink_parts.append(f"ln -sf {symlink_target} /injected-tools/bin/{b_name}")

            path_cmd = (
                'grep -q injected-tools /etc/profile.d/injected-tools.sh 2>/dev/null'
                ' || echo \'export PATH="/injected-tools/bin:$PATH"\' > /etc/profile.d/injected-tools.sh 2>/dev/null;'
                ' grep -q injected-tools "$HOME/.bashrc" 2>/dev/null'
                ' || echo \'export PATH="/injected-tools/bin:$PATH"\' >> "$HOME/.bashrc" 2>/dev/null; true'
            )
            cmdline = (
                f"mkdir -p /injected-tools/bin && "
                f"{' && '.join(symlink_parts)} && "
                f"{path_cmd}"
            )
            setup_cmd = reg_tool["editor"].get("postStart", "")
            if setup_cmd:
                cmdline = f"{setup_cmd} && {cmdline}"

            ops.append({"op": "add", "path": "/spec/template/commands/-",
                         "value": {"id": symlink_cmd_id, "exec": {
                             "component": editor_name, "commandLine": cmdline}}})

            poststart = get_events(ws).get("postStart")
            if not skip_infra and poststart is None:
                ops.append({"op": "add", "path": "/spec/template/events/postStart",
                             "value": [symlink_cmd_id]})
            else:
                ops.append({"op": "add", "path": "/spec/template/events/postStart/-",
                             "value": symlink_cmd_id})
```

- [ ] **Step 3: Verify existing `inject-tool inject` still works**

Run inside a workspace:

```bash
inject-tool list
```

Expected: same output as before (no regression in existing functionality).

- [ ] **Step 4: Commit**

```bash
git add inject-tool/inject-tool.py
git commit -s -m "refactor: make build_inject_ops() accept custom tool entries"
```

---

### Task 5: Implement `cmd_init()` injection logic

**Files:**
- Modify: `inject-tool/inject-tool.py` (complete `cmd_init()`)

- [ ] **Step 1: Complete `cmd_init()` implementation**

Replace the `cmd_init()` function with:

```python
def cmd_init(dry_run):
    validate_env()

    configs = discover_configs()
    if not configs:
        info("No .che/inject-tools.json found in /projects/*/. Nothing to do.")
        return

    for config_path in configs:
        info(f"Found config: {config_path}")

    resolved = resolve_tools(configs)
    if not resolved:
        info("No tools declared in config files.")
        return

    ws = fetch_workspace()

    # Filter already-injected tools
    to_inject = []
    for name, entry in resolved:
        if find_component_index(ws, f"{name}-injector") is not None:
            info(f"{name} is already injected, skipping.")
        else:
            to_inject.append((name, entry))

    if not to_inject:
        info("All declared tools are already injected.")
        return

    if dry_run:
        info("Dry run — the following tools would be injected:")
        for name, entry in to_inject:
            kind = "custom" if entry else "registry"
            info(f"  {name} ({kind})")
        return

    # Build ops: first tool with infra, rest without
    all_ops = []
    for i, (name, entry) in enumerate(to_inject):
        all_ops.extend(build_inject_ops(name, ws, skip_infra=(i > 0), tool_entry=entry))

    tool_names = ", ".join(name for name, _ in to_inject)
    info(f"Injecting {tool_names}...")
    patch_workspace(all_ops)
    info(f"Injected {tool_names}. Workspace is restarting...")
```

- [ ] **Step 2: Test with registry tools**

```bash
mkdir -p /projects/test-project/.che
echo '{"tools": ["tmux"]}' > /projects/test-project/.che/inject-tools.json
inject-tool init --dry-run
```

Expected:
```
==> Found config: /projects/test-project/.che/inject-tools.json
==> Dry run — the following tools would be injected:
==>   tmux (registry)
```

- [ ] **Step 3: Test with custom tools**

```bash
cat > /projects/test-project/.che/inject-tools.json << 'EOF'
{
  "tools": [
    "tmux",
    {
      "name": "dev-tools",
      "image": "quay.io/test/tools:latest",
      "binaries": [
        {"src": "/usr/bin/git", "binary": "git"}
      ]
    }
  ]
}
EOF
inject-tool init --dry-run
```

Expected:
```
==> Found config: /projects/test-project/.che/inject-tools.json
==> Dry run — the following tools would be injected:
==>   tmux (registry)
==>   dev-tools (custom)
```

- [ ] **Step 4: Test full injection (live)**

Only run this when ready to test an actual workspace restart:

```bash
inject-tool init
```

Expected: workspace patches and restarts with declared tools.

- [ ] **Step 5: Test idempotency**

After workspace restarts, run again:

```bash
inject-tool init
```

Expected:
```
==> Found config: /projects/test-project/.che/inject-tools.json
==> tmux is already injected, skipping.
==> dev-tools is already injected, skipping.
==> All declared tools are already injected.
```

- [ ] **Step 6: Clean up and commit**

```bash
rm -rf /projects/test-project
git add inject-tool/inject-tool.py
git commit -s -m "feat: implement inject-tool init with registry and custom tool support"
```

---

### Task 6: Update ConfigMap delivery

**Files:**
- Modify: `inject-tool/setup.sh` (no changes needed — registry.json is already included)

The `setup.sh` script already packages `inject-tool`, `inject-tool.py`, and
`registry.json` into the ConfigMap. Since `init` is a new subcommand within
`inject-tool.py`, it will be available automatically after the ConfigMap is
re-applied.

- [ ] **Step 1: Verify setup.sh includes all needed files**

Read `inject-tool/setup.sh` and confirm it packages `inject-tool.py` — it does
(line 33). No changes needed.

- [ ] **Step 2: Re-apply ConfigMap on a test namespace**

```bash
./inject-tool/setup.sh <test-namespace>
```

Expected: ConfigMap updated, new workspaces get the updated inject-tool with `init`.

- [ ] **Step 3: Commit (no-op)**

No file changes in this task. Move to next task.

---

### Task 7: Update documentation

**Files:**
- Modify: `CLAUDE.md` (add `init` subcommand reference)
- Modify: `README.md` (add `init` usage and custom tools section)

- [ ] **Step 1: Add `init` to CLAUDE.md**

In `CLAUDE.md`, in the `inject-tool Internals` section, after the `**Multi-tool**`
paragraph, add:

```markdown
**Init mode** (`inject-tool init`): scans `/projects/*/.che/inject-tools.json` for tool declarations. Supports registry tool names (strings) and custom tool definitions (objects with `name`, `image`, `binaries`). Builds a single JSON Patch and applies it — one restart on first use, idempotent after. Override config path with `INJECT_TOOLS_CONFIG` env var. Use `--dry-run` to preview.
```

- [ ] **Step 2: Add usage section to README.md**

Add a section covering:
- `.che/inject-tools.json` format (string entries + object entries)
- `inject-tool init` and `inject-tool init --dry-run` usage
- Example for a consumer repo

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -s -m "docs: add inject-tool init usage and custom tools documentation"
```

---

### Task 8: Create custom tools documentation

**Files:**
- Create: `docs/custom-tools.md`

- [ ] **Step 1: Write custom tools guide**

Create `docs/custom-tools.md` covering:

- How to build a custom tool image (init pattern — single binary example)
- How to build a multi-tool image (multiple binaries in one image)
- How to use an existing public image without building anything
- Example `.che/inject-tools.json` with both registry and custom tools
- Multi-arch considerations (if using DevWorkspaces on different architectures)
- Checklist: verify image exists, binary paths are correct, volume size is sufficient

- [ ] **Step 2: Commit**

```bash
git add docs/custom-tools.md
git commit -s -m "docs: add custom tools guide for consumer repos"
```
