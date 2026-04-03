# inject-tool Service Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the python3-dependent `inject-tool` CLI with a client-server architecture: thin POSIX shell client in workspaces, Python HTTP service pod handles all patching logic.

**Architecture:** A Deployment runs a Python HTTP server (`http.server` stdlib) with the existing patching logic from `inject-tool.py`. The workspace-side `inject-tool` becomes a ~70-line shell script that translates CLI commands to HTTP calls. `setup.sh` deploys everything: service, RBAC, and the client ConfigMap.

**Tech Stack:** Python 3 stdlib (`http.server`, `json`, `urllib.request`, `ssl`), POSIX shell, Kubernetes YAML manifests

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `inject-tool/service/server.py` | Create | HTTP server: routing, JSON request/response handling, `/healthz` |
| `inject-tool/service/injector.py` | Create | Core patching logic extracted from `inject-tool.py`: registry, K8s API, patch ops |
| `inject-tool/service/registry.json` | Copy | Tool registry (copy of existing `inject-tool/registry.json`) |
| `inject-tool/service/Dockerfile` | Create | Python 3 container image for the service |
| `inject-tool/manifests/rbac.yaml` | Create | ServiceAccount + Role + RoleBinding |
| `inject-tool/manifests/deployment.yaml` | Create | Deployment + Service |
| `inject-tool/inject-tool` | Rewrite | Thin POSIX shell client |
| `inject-tool/setup.sh` | Rewrite | Deploy service + RBAC + ConfigMap |
| `Makefile` | Modify | Add `inject-tool-service` build target |
| `.github/workflows/pr.yml` | Modify | Add service image build to matrix |
| `.github/workflows/release.yml` | Modify | Add service image build to matrix |

---

### Task 1: Extract Patching Logic into `injector.py`

**Files:**
- Create: `inject-tool/service/injector.py`
- Copy: `inject-tool/service/registry.json` (from `inject-tool/registry.json`)

This task extracts the core patching logic from `inject-tool.py` into a standalone module that the HTTP server will import. The K8s API functions are adapted to use in-cluster ServiceAccount auth (no kubeconfig fallback).

- [ ] **Step 1: Copy registry.json**

```bash
cp inject-tool/registry.json inject-tool/service/registry.json
```

- [ ] **Step 2: Create `injector.py`**

Create `inject-tool/service/injector.py` with the following content. This is extracted from `inject-tool.py` with these changes:
- K8s API uses in-cluster ServiceAccount token (no kubeconfig fallback)
- API URL constructed from workspace/namespace parameters (not env vars)
- Functions accept workspace name and namespace as arguments instead of reading env vars
- `hot_inject` and `hot_remove` are removed
- `cmd_*` functions replaced by handler functions that return dicts instead of printing/exiting

```python
"""injector — core patching logic for inject-tool-service."""

import copy
import json
import os
import ssl
import urllib.request

# ============================================================================
# Registry
# ============================================================================
def _registry_path():
    override = os.environ.get("INJECT_TOOL_REGISTRY_FILE")
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "registry.json")


def load_registry():
    path = _registry_path()
    with open(path) as f:
        data = json.load(f)
    for key in ("registry", "tag", "tools"):
        if key not in data:
            raise ValueError(f"registry.json missing required key '{key}'")
    return data


REGISTRY_DATA = load_registry()
_base_registry = os.environ.get("INJECT_TOOL_REGISTRY") or REGISTRY_DATA["registry"]
_base_tag = os.environ.get("INJECT_TOOL_TAG") or REGISTRY_DATA["tag"]


def tool_image(tool):
    return f"{_base_registry}/tools-injector/{tool}:{_base_tag}"


# ============================================================================
# Kubernetes API (in-cluster)
# ============================================================================
CA_CERT = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
SA_TOKEN_PATH = "/var/run/secrets/kubernetes.io/serviceaccount/token"


def _get_token():
    with open(SA_TOKEN_PATH) as f:
        return f.read().strip()


def _api_url(namespace, workspace):
    host = os.environ.get("KUBERNETES_SERVICE_HOST", "kubernetes.default.svc")
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    return (f"https://{host}:{port}/apis/workspace.devfile.io/v1alpha2"
            f"/namespaces/{namespace}/devworkspaces/{workspace}")


def _ssl_context():
    ctx = ssl.create_default_context()
    if os.path.isfile(CA_CERT):
        ctx.load_verify_locations(CA_CERT)
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_workspace(namespace, workspace):
    token = _get_token()
    req = urllib.request.Request(
        _api_url(namespace, workspace),
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        return json.loads(resp.read())


def patch_workspace(namespace, workspace, ops):
    token = _get_token()
    data = json.dumps(ops).encode()
    req = urllib.request.Request(
        _api_url(namespace, workspace),
        data=data,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json-patch+json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, context=_ssl_context()) as resp:
        return json.loads(resp.read())


# ============================================================================
# Workspace JSON helpers
# ============================================================================
def get_components(ws):
    return ws.get("spec", {}).get("template", {}).get("components", [])


def get_commands(ws):
    return ws.get("spec", {}).get("template", {}).get("commands", [])


def get_events(ws):
    return ws.get("spec", {}).get("template", {}).get("events", {})


def find_component_index(ws, name):
    for i, c in enumerate(get_components(ws)):
        if c.get("name") == name:
            return i
    return None


def find_editor(ws):
    for i, c in enumerate(get_components(ws)):
        if c.get("container") and not c.get("name", "").endswith("-injector"):
            return i, c["name"]
    return None


def find_command_index(ws, cmd_id):
    for i, c in enumerate(get_commands(ws)):
        if c.get("id") == cmd_id:
            return i
    return None


def find_event_index(ws, event_type, event_id):
    events = get_events(ws).get(event_type, [])
    for i, e in enumerate(events):
        if e == event_id:
            return i
    return None


def parse_memory(mem_str):
    if not mem_str:
        return 0
    if mem_str.endswith("Gi"):
        return int(float(mem_str[:-2]) * 1024)
    if mem_str.endswith("Mi"):
        return int(mem_str[:-2])
    return 0


# ============================================================================
# Custom tool support
# ============================================================================
def build_custom_tool_entry(tool_def):
    for field in ("name", "image", "binaries"):
        if field not in tool_def:
            raise ValueError(f"Custom tool missing required field '{field}': {json.dumps(tool_def)}")
    if not isinstance(tool_def["binaries"], list) or not tool_def["binaries"]:
        raise ValueError(f"Custom tool '{tool_def['name']}': 'binaries' must be a non-empty array")
    for b in tool_def["binaries"]:
        if "src" not in b or "binary" not in b:
            raise ValueError(f"Custom tool '{tool_def['name']}': each binary needs 'src' and 'binary'")

    name = tool_def["name"]
    binaries = tool_def["binaries"]
    mem_limit = tool_def.get("memoryLimit", "128Mi")

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
                "image": tool_def["image"],
                "command": command,
                "args": args,
                "memoryLimit": mem_limit,
                "mountSources": False,
                "volumeMounts": [{"name": "injected-tools", "path": "/injected-tools"}],
            },
        },
    }]

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


# ============================================================================
# Patch construction (from inject-tool.py — unchanged logic)
# ============================================================================
def build_inject_ops(tool, ws, skip_infra=False, tool_entry=None):
    reg_tool = tool_entry if tool_entry else REGISTRY_DATA["tools"][tool]
    pattern = reg_tool["pattern"]
    binary_name = reg_tool["binary"]
    ops = []

    editor = find_editor(ws)
    editor_idx = editor[0] if editor else None
    editor_name = editor[1] if editor else None

    if not skip_infra and find_component_index(ws, "injected-tools") is None:
        ops.extend(copy.deepcopy(REGISTRY_DATA["infrastructure"]["patch"]))

    patch_ops = copy.deepcopy(reg_tool["patch"])
    for op in patch_ops:
        if op.get("op") == "add" and isinstance(op.get("value"), dict):
            container = op["value"].get("container", {})
            if "image" in container and not tool_entry:
                container["image"] = tool_image(tool)
    ops.extend(patch_ops)

    if editor_idx is not None and not skip_infra:
        mounts = get_components(ws)[editor_idx].get("container", {}).get("volumeMounts", [])
        has_mount = any(m.get("name") == "injected-tools" for m in mounts)
        if not has_mount:
            for vm in reg_tool["editor"]["volumeMounts"]:
                if mounts:
                    ops.append({"op": "add",
                                "path": f"/spec/template/components/{editor_idx}/container/volumeMounts/-",
                                "value": vm})
                else:
                    ops.append({"op": "add",
                                "path": f"/spec/template/components/{editor_idx}/container/volumeMounts",
                                "value": [vm]})
                    mounts = [vm]

    if editor_idx is not None and reg_tool["editor"]["env"]:
        env_list = get_components(ws)[editor_idx].get("container", {}).get("env")
        env_exists = env_list is not None and len(env_list) > 0
        for i, env_var in enumerate(reg_tool["editor"]["env"]):
            if not skip_infra and not env_exists and i == 0:
                ops.append({"op": "add",
                            "path": f"/spec/template/components/{editor_idx}/container/env",
                            "value": [env_var]})
                env_exists = True
            else:
                ops.append({"op": "add",
                            "path": f"/spec/template/components/{editor_idx}/container/env/-",
                            "value": env_var})

    if not skip_infra and editor_idx is not None and pattern == "bundle":
        current_mem = parse_memory(
            get_components(ws)[editor_idx].get("container", {}).get("memoryLimit", ""))
        if current_mem == 0:
            ops.append({"op": "add",
                        "path": f"/spec/template/components/{editor_idx}/container/memoryLimit",
                        "value": "1536Mi"})
        else:
            ops.append({"op": "replace",
                        "path": f"/spec/template/components/{editor_idx}/container/memoryLimit",
                        "value": f"{current_mem + 512}Mi"})

    commands = ws.get("spec", {}).get("template", {}).get("commands")
    if skip_infra or commands is not None:
        ops.append({"op": "add", "path": "/spec/template/commands/-",
                    "value": {"id": f"install-{tool}", "apply": {"component": f"{tool}-injector"}}})
    else:
        ops.append({"op": "add", "path": "/spec/template/commands",
                    "value": [{"id": f"install-{tool}", "apply": {"component": f"{tool}-injector"}}]})

    prestart = get_events(ws).get("preStart")
    if not skip_infra and prestart is None:
        ops.append({"op": "add", "path": "/spec/template/events",
                    "value": {"preStart": [f"install-{tool}"]}})
    else:
        ops.append({"op": "add", "path": "/spec/template/events/preStart/-",
                    "value": f"install-{tool}"})

    if editor_name:
        symlink_cmd_id = f"symlink-{tool}"
        if find_command_index(ws, symlink_cmd_id) is None:
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

    return ops


def build_remove_ops(tool, ws, also_removing=None):
    if also_removing is None:
        also_removing = []
    comp_name = f"{tool}-injector"
    ops = []

    comp_idx = find_component_index(ws, comp_name)
    if comp_idx is None:
        raise ValueError(f"{tool} is not injected.")
    ops.append({"op": "remove", "path": f"/spec/template/components/{comp_idx}"})

    cmd_idx = find_command_index(ws, f"install-{tool}")
    if cmd_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/commands/{cmd_idx}"})

    event_idx = find_event_index(ws, "preStart", f"install-{tool}")
    if event_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/events/preStart/{event_idx}"})

    symlink_idx = find_command_index(ws, f"symlink-{tool}")
    if symlink_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/commands/{symlink_idx}"})

    post_idx = find_event_index(ws, "postStart", f"symlink-{tool}")
    if post_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/events/postStart/{post_idx}"})

    removing_names = {f"{r}-injector" for r in also_removing}
    other_injectors = [
        c for c in get_components(ws)
        if c.get("name", "").endswith("-injector")
        and c["name"] != comp_name
        and c["name"] not in removing_names
    ]

    if not other_injectors:
        vol_idx = find_component_index(ws, "injected-tools")
        if vol_idx is not None:
            ops.append({"op": "remove", "path": f"/spec/template/components/{vol_idx}"})
        editor = find_editor(ws)
        if editor:
            editor_idx = editor[0]
            mounts = get_components(ws)[editor_idx].get("container", {}).get("volumeMounts", [])
            for mi, m in enumerate(mounts):
                if m.get("name") == "injected-tools":
                    ops.append({"op": "remove",
                                "path": f"/spec/template/components/{editor_idx}/container/volumeMounts/{mi}"})
                    break

    return ops


def _remove_sort_key(op):
    if op.get("op") != "remove":
        return (-1, "")
    parts = op.get("path", "").split("/")
    for p in reversed(parts):
        if p.isdigit():
            return (int(p), "/".join(parts[:-1]))
    return (-1, op.get("path", ""))


# ============================================================================
# Handler functions (called by server.py)
# ============================================================================
def handle_inject(namespace, workspace, tools):
    for name in tools:
        if name not in REGISTRY_DATA["tools"]:
            raise ValueError(f"Unknown tool: {name}")

    ws = fetch_workspace(namespace, workspace)

    to_inject = []
    for tool in tools:
        if find_component_index(ws, f"{tool}-injector") is not None:
            continue
        to_inject.append(tool)

    if not to_inject:
        return {"status": "ok", "message": "All requested tools are already injected."}

    all_ops = []
    for i, tool in enumerate(to_inject):
        all_ops.extend(build_inject_ops(tool, ws, skip_infra=(i > 0)))

    bundle_count = sum(1 for t in to_inject if REGISTRY_DATA["tools"][t]["pattern"] == "bundle")
    if bundle_count > 1:
        editor = find_editor(ws)
        if editor:
            editor_idx = editor[0]
            all_ops = [op for op in all_ops if not op.get("path", "").endswith("/memoryLimit")]
            current_mem = parse_memory(
                get_components(ws)[editor_idx].get("container", {}).get("memoryLimit", ""))
            total_bump = bundle_count * 512
            if current_mem == 0:
                total_mem = 1024 + total_bump
                all_ops.append({"op": "add",
                                "path": f"/spec/template/components/{editor_idx}/container/memoryLimit",
                                "value": f"{total_mem}Mi"})
            else:
                total_mem = current_mem + total_bump
                all_ops.append({"op": "replace",
                                "path": f"/spec/template/components/{editor_idx}/container/memoryLimit",
                                "value": f"{total_mem}Mi"})

    patch_workspace(namespace, workspace, all_ops)
    return {"status": "ok", "message": f"Patched {len(to_inject)} tool(s), workspace restarting"}


def handle_remove(namespace, workspace, tools):
    for name in tools:
        if name not in REGISTRY_DATA["tools"]:
            raise ValueError(f"Unknown tool: {name}")

    ws = fetch_workspace(namespace, workspace)

    all_ops = []
    for tool in tools:
        all_ops.extend(build_remove_ops(tool, ws, also_removing=tools))

    all_ops.sort(key=_remove_sort_key, reverse=True)
    patch_workspace(namespace, workspace, all_ops)
    return {"status": "ok", "message": f"Removed {len(tools)} tool(s), workspace restarting"}


def handle_list(namespace, workspace):
    ws = fetch_workspace(namespace, workspace)
    result = []
    for tool in sorted(REGISTRY_DATA["tools"]):
        t = REGISTRY_DATA["tools"][tool]
        injected = find_component_index(ws, f"{tool}-injector") is not None
        result.append({
            "name": tool,
            "description": t["description"],
            "pattern": t["pattern"],
            "injected": injected,
        })
    return {"status": "ok", "tools": result}


def handle_init(namespace, workspace, configs, dry_run=False):
    # Resolve tools from configs
    seen = set()
    resolved = []
    for config in configs:
        project = config.get("project", "unknown")
        tools = config.get("tools", [])
        for item in tools:
            if isinstance(item, str):
                if item in seen:
                    continue
                if item not in REGISTRY_DATA["tools"]:
                    raise ValueError(f"Project '{project}': unknown tool '{item}'")
                seen.add(item)
                resolved.append((item, None))
            elif isinstance(item, dict):
                name = item.get("name")
                if not name:
                    raise ValueError(f"Project '{project}': custom tool missing 'name'")
                if name in seen:
                    continue
                entry = build_custom_tool_entry(item)
                seen.add(name)
                resolved.append((name, entry))
            else:
                raise ValueError(f"Project '{project}': each tool must be a string or object")

    if not resolved:
        return {"status": "ok", "message": "No tools declared in configs."}

    ws = fetch_workspace(namespace, workspace)

    to_inject = []
    for name, entry in resolved:
        if find_component_index(ws, f"{name}-injector") is not None:
            continue
        to_inject.append((name, entry))

    if not to_inject:
        return {"status": "ok", "message": "All declared tools are already injected."}

    if dry_run:
        tool_list = [{"name": n, "type": "custom" if e else "registry"} for n, e in to_inject]
        return {"status": "ok", "message": f"Dry run: would inject {len(to_inject)} tool(s)", "tools": tool_list}

    all_ops = []
    for i, (name, entry) in enumerate(to_inject):
        all_ops.extend(build_inject_ops(name, ws, skip_infra=(i > 0), tool_entry=entry))

    patch_workspace(namespace, workspace, all_ops)
    n_projects = len(configs)
    return {"status": "ok", "message": f"Discovered {len(to_inject)} tool(s) from {n_projects} project(s), workspace restarting"}
```

- [ ] **Step 3: Commit**

```bash
git add inject-tool/service/injector.py inject-tool/service/registry.json
git commit -s -m "feat: extract patching logic into injector.py for service"
```

---

### Task 2: Create HTTP Server (`server.py`)

**Files:**
- Create: `inject-tool/service/server.py`

- [ ] **Step 1: Create `server.py`**

```python
"""inject-tool HTTP server — routes requests to injector handlers."""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import injector


class Handler(BaseHTTPRequestHandler):

    def _send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length))

    def _require_fields(self, data, *fields):
        missing = [f for f in fields if f not in data]
        if missing:
            self._send_json(400, {"status": "error", "message": f"Missing required fields: {', '.join(missing)}"})
            return False
        return True

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return

        if parsed.path == "/list":
            params = parse_qs(parsed.query)
            ws = params.get("workspace", [None])[0]
            ns = params.get("namespace", [None])[0]
            if not ws or not ns:
                self._send_json(400, {"status": "error", "message": "Missing workspace or namespace query param"})
                return
            try:
                result = injector.handle_list(ns, ws)
                self._send_json(200, result)
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        self._send_json(404, {"status": "error", "message": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)

        try:
            data = self._read_json()
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json(400, {"status": "error", "message": f"Invalid JSON: {e}"})
            return

        if parsed.path == "/inject":
            if not self._require_fields(data, "workspace", "namespace", "tools"):
                return
            try:
                result = injector.handle_inject(data["namespace"], data["workspace"], data["tools"])
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(400, {"status": "error", "message": str(e)})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        if parsed.path == "/remove":
            if not self._require_fields(data, "workspace", "namespace", "tools"):
                return
            try:
                result = injector.handle_remove(data["namespace"], data["workspace"], data["tools"])
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(400, {"status": "error", "message": str(e)})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        if parsed.path == "/init":
            if not self._require_fields(data, "workspace", "namespace", "configs"):
                return
            try:
                result = injector.handle_init(
                    data["namespace"], data["workspace"],
                    data["configs"], data.get("dry_run", False))
                self._send_json(200, result)
            except ValueError as e:
                self._send_json(400, {"status": "error", "message": str(e)})
            except Exception as e:
                self._send_json(500, {"status": "error", "message": str(e)})
            return

        self._send_json(404, {"status": "error", "message": "Not found"})

    def log_message(self, fmt, *args):
        print(f"[server] {fmt % args}", file=sys.stderr, flush=True)


def main():
    port = int(os.environ.get("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"inject-tool-service listening on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add inject-tool/service/server.py
git commit -s -m "feat: add HTTP server for inject-tool-service"
```

---

### Task 3: Create Service Dockerfile

**Files:**
- Create: `inject-tool/service/Dockerfile`

- [ ] **Step 1: Create Dockerfile**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY server.py injector.py registry.json ./

EXPOSE 8080

CMD ["python3", "server.py"]
```

- [ ] **Step 2: Commit**

```bash
git add inject-tool/service/Dockerfile
git commit -s -m "feat: add Dockerfile for inject-tool-service"
```

---

### Task 4: Create Kubernetes Manifests

**Files:**
- Create: `inject-tool/manifests/rbac.yaml`
- Create: `inject-tool/manifests/deployment.yaml`

- [ ] **Step 1: Create `rbac.yaml`**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: inject-tool-service
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: inject-tool-service
rules:
  - apiGroups: ["workspace.devfile.io"]
    resources: ["devworkspaces"]
    verbs: ["get", "list", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: inject-tool-service
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: inject-tool-service
subjects:
  - kind: ServiceAccount
    name: inject-tool-service
```

- [ ] **Step 2: Create `deployment.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inject-tool-service
  labels:
    app: inject-tool-service
spec:
  replicas: 1
  selector:
    matchLabels:
      app: inject-tool-service
  template:
    metadata:
      labels:
        app: inject-tool-service
    spec:
      serviceAccountName: inject-tool-service
      containers:
        - name: server
          image: IMAGE_PLACEHOLDER
          ports:
            - containerPort: 8080
          resources:
            requests:
              memory: 64Mi
            limits:
              memory: 128Mi
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 3
---
apiVersion: v1
kind: Service
metadata:
  name: inject-tool-service
spec:
  selector:
    app: inject-tool-service
  ports:
    - port: 8080
      targetPort: 8080
```

Note: `IMAGE_PLACEHOLDER` is replaced by `setup.sh` at deploy time with the actual image reference.

- [ ] **Step 3: Commit**

```bash
git add inject-tool/manifests/rbac.yaml inject-tool/manifests/deployment.yaml
git commit -s -m "feat: add Kubernetes manifests for inject-tool-service"
```

---

### Task 5: Rewrite Thin Shell Client

**Files:**
- Rewrite: `inject-tool/inject-tool`

- [ ] **Step 1: Rewrite `inject-tool` as POSIX shell client**

```sh
#!/bin/sh
# inject-tool — thin client for inject-tool-service
# Delivered via ConfigMap automount to /usr/local/bin/inject-tool

set -e

SERVICE_URL="${INJECT_TOOL_SERVICE_URL:-http://inject-tool-service:8080}"
WS_NAME="${DEVWORKSPACE_NAME}"
WS_NS="${DEVWORKSPACE_NAMESPACE}"

die() { echo "ERROR: $1" >&2; exit 1; }

# Check required env vars
[ -n "$WS_NAME" ] || die "DEVWORKSPACE_NAME not set. Are you running inside a Che workspace?"
[ -n "$WS_NS" ] || die "DEVWORKSPACE_NAMESPACE not set. Are you running inside a Che workspace?"

# HTTP helpers: try curl, fall back to wget
http_get() {
    url="$1"
    if command -v curl >/dev/null 2>&1; then
        curl -sf "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO- "$url"
    else
        die "Neither curl nor wget found."
    fi
}

http_post() {
    url="$1"
    body="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -sf -X POST -H "Content-Type: application/json" -d "$body" "$url"
    elif command -v wget >/dev/null 2>&1; then
        echo "$body" | wget -qO- --post-data="$(cat)" --header="Content-Type: application/json" "$url"
    else
        die "Neither curl nor wget found."
    fi
}

# Extract message from JSON response (simple grep, no jq needed)
extract_message() {
    echo "$1" | sed -n 's/.*"message" *: *"\([^"]*\)".*/\1/p'
}

extract_status() {
    echo "$1" | sed -n 's/.*"status" *: *"\([^"]*\)".*/\1/p'
}

# Format and display list response
display_list() {
    response="$1"
    printf "%-15s %-10s %s\n" "Tool" "Pattern" "Status"
    printf "%-15s %-10s %s\n" "----" "-------" "------"
    echo "$response" | sed 's/},{/}\n{/g' | while IFS= read -r line; do
        name=$(echo "$line" | sed -n 's/.*"name" *: *"\([^"]*\)".*/\1/p')
        pattern=$(echo "$line" | sed -n 's/.*"pattern" *: *"\([^"]*\)".*/\1/p')
        injected=$(echo "$line" | sed -n 's/.*"injected" *: *\([a-z]*\).*/\1/p')
        [ -z "$name" ] && continue
        if [ "$injected" = "true" ]; then
            status="injected"
        else
            status="not injected"
        fi
        printf "%-15s %-10s %s\n" "$name" "$pattern" "$status"
    done
}

# Build JSON array from init configs
build_init_payload() {
    dry_run="$1"
    projects_dir="${PROJECTS_DIR:-/projects}"
    configs=""
    sep=""
    for f in "$projects_dir"/*/.che/inject-tools.json; do
        [ -f "$f" ] || continue
        project=$(basename "$(dirname "$(dirname "$f")")")
        content=$(cat "$f")
        tools=$(echo "$content" | sed -n 's/.*"tools" *: *\(\[.*\]\).*/\1/p')
        [ -z "$tools" ] && continue
        configs="${configs}${sep}{\"project\":\"${project}\",\"tools\":${tools}}"
        sep=","
    done
    if [ -z "$configs" ]; then
        echo ""
        return
    fi
    echo "{\"workspace\":\"${WS_NAME}\",\"namespace\":\"${WS_NS}\",\"configs\":[${configs}],\"dry_run\":${dry_run}}"
}

# Parse arguments
command=""
tools=""
dry_run="false"

case "${1:-}" in
    list)
        command="list"
        ;;
    remove)
        command="remove"
        shift
        tools="$*"
        [ -n "$tools" ] || die "Usage: inject-tool remove <tool> [tool2...]"
        ;;
    init)
        command="init"
        shift
        for arg in "$@"; do
            case "$arg" in
                --dry-run) dry_run="true" ;;
                *) die "Unknown option: $arg" ;;
            esac
        done
        ;;
    -h|--help|"")
        echo "Usage: inject-tool <tool> [tool2...]"
        echo "       inject-tool list"
        echo "       inject-tool remove <tool> [tool2...]"
        echo "       inject-tool init [--dry-run]"
        exit 0
        ;;
    -*)
        die "Unknown option: $1"
        ;;
    *)
        command="inject"
        tools="$*"
        ;;
esac

# Execute command
case "$command" in
    list)
        response=$(http_get "${SERVICE_URL}/list?workspace=${WS_NAME}&namespace=${WS_NS}")
        display_list "$response"
        ;;
    inject)
        # Build JSON array of tool names
        json_tools=""
        sep=""
        for t in $tools; do
            json_tools="${json_tools}${sep}\"${t}\""
            sep=","
        done
        body="{\"workspace\":\"${WS_NAME}\",\"namespace\":\"${WS_NS}\",\"tools\":[${json_tools}]}"
        response=$(http_post "${SERVICE_URL}/inject" "$body")
        msg=$(extract_message "$response")
        echo "==> ${msg:-Done}"
        ;;
    remove)
        json_tools=""
        sep=""
        for t in $tools; do
            json_tools="${json_tools}${sep}\"${t}\""
            sep=","
        done
        body="{\"workspace\":\"${WS_NAME}\",\"namespace\":\"${WS_NS}\",\"tools\":[${json_tools}]}"
        response=$(http_post "${SERVICE_URL}/remove" "$body")
        msg=$(extract_message "$response")
        echo "==> ${msg:-Done}"
        ;;
    init)
        body=$(build_init_payload "$dry_run")
        if [ -z "$body" ]; then
            echo "==> No .che/inject-tools.json found in ${PROJECTS_DIR:-/projects}/*/. Nothing to do."
            exit 0
        fi
        response=$(http_post "${SERVICE_URL}/init" "$body")
        msg=$(extract_message "$response")
        echo "==> ${msg:-Done}"
        ;;
esac
```

- [ ] **Step 2: Commit**

```bash
git add inject-tool/inject-tool
git commit -s -m "feat: rewrite inject-tool as thin POSIX shell client"
```

---

### Task 6: Rewrite `setup.sh`

**Files:**
- Rewrite: `inject-tool/setup.sh`

- [ ] **Step 1: Rewrite `setup.sh`**

```bash
#!/usr/bin/env bash
# setup.sh <namespace> [--image <service-image>]
#
# Deploys inject-tool-service and the thin client ConfigMap.
set -euo pipefail

NAMESPACE="${1:?Usage: $0 <namespace> [--image <image>]}"
shift || true

SERVICE_IMAGE="quay.io/akurinnoy/tools-injector/inject-tool-service:next"

while [ $# -gt 0 ]; do
    case "$1" in
        --image) SERVICE_IMAGE="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Deploying RBAC..."
kubectl apply -f "${SCRIPT_DIR}/manifests/rbac.yaml" -n "${NAMESPACE}"

echo "==> Deploying service (image: ${SERVICE_IMAGE})..."
sed "s|IMAGE_PLACEHOLDER|${SERVICE_IMAGE}|g" "${SCRIPT_DIR}/manifests/deployment.yaml" \
    | kubectl apply -f - -n "${NAMESPACE}"

echo "==> Creating inject-tool client ConfigMap..."
CM_NAME="inject-tool"
kubectl create configmap "${CM_NAME}" \
    --from-file=inject-tool="${SCRIPT_DIR}/inject-tool" \
    -n "${NAMESPACE}" \
    --dry-run=client -o yaml | kubectl apply -f -

echo "==> Labeling for DWO automount..."
kubectl label configmap "${CM_NAME}" \
    controller.devfile.io/mount-to-devworkspace=true \
    controller.devfile.io/watch-configmap=true \
    -n "${NAMESPACE}" \
    --overwrite

echo "==> Setting mount annotations..."
kubectl annotate configmap "${CM_NAME}" \
    controller.devfile.io/mount-path=/usr/local/bin \
    controller.devfile.io/mount-as=subpath \
    controller.devfile.io/mount-access-mode=0755 \
    -n "${NAMESPACE}" \
    --overwrite

echo ""
echo "Done."
echo ""
echo "Service deployed to namespace '${NAMESPACE}':"
echo "  inject-tool-service   — HTTP service handling tool injection"
echo "  inject-tool           — thin client automounted into workspaces"
echo ""
echo "Usage (from inside a workspace terminal):"
echo "  inject-tool list"
echo "  inject-tool opencode tmux"
echo "  inject-tool init"
```

- [ ] **Step 2: Commit**

```bash
git add inject-tool/setup.sh
git commit -s -m "feat: rewrite setup.sh to deploy service + client ConfigMap"
```

---

### Task 7: Add CI Build Targets

**Files:**
- Modify: `Makefile`
- Modify: `.github/workflows/pr.yml`
- Modify: `.github/workflows/release.yml`

- [ ] **Step 1: Add `inject-tool-service` to Makefile**

Add the following targets after the existing tool targets:

```makefile
# inject-tool-service
.PHONY: docker-build-inject-tool-service docker-push-inject-tool-service docker-inject-tool-service

docker-build-inject-tool-service: ## Build inject-tool-service multi-arch (no push)
	docker buildx build --platform linux/amd64,linux/arm64 \
		-t $(IMAGE_REGISTRY)/tools-injector/inject-tool-service:$(TAG) \
		-f inject-tool/service/Dockerfile inject-tool/service

docker-push-inject-tool-service: ## Build and push inject-tool-service multi-arch
	docker buildx build --platform linux/amd64,linux/arm64 \
		-t $(IMAGE_REGISTRY)/tools-injector/inject-tool-service:$(TAG) \
		-f inject-tool/service/Dockerfile inject-tool/service --push

docker-inject-tool-service: docker-push-inject-tool-service ## Build + push shorthand
```

- [ ] **Step 2: Add `inject-tool-service` to CI workflows**

In `.github/workflows/pr.yml`, add to the matrix:

```yaml
          - name: inject-tool-service
            dockerfile: inject-tool/service
```

In `.github/workflows/release.yml`, add the same entry to the matrix.

Note: The `context` in the build step should use `.` for tool Dockerfiles and `inject-tool/service` for the service. Since the existing workflow uses `context: .` and `file: ${{ matrix.tool.dockerfile }}/Dockerfile`, the service entry works with this pattern because `inject-tool/service/Dockerfile` is a valid path from the repo root. However, the Dockerfile's `COPY` commands use relative paths from the build context. Update the service Dockerfile's build context in the workflow:

Actually, the simpler approach: change the service Dockerfile to work with repo root as context:

Update `inject-tool/service/Dockerfile`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY inject-tool/service/server.py inject-tool/service/injector.py inject-tool/service/registry.json ./

EXPOSE 8080

CMD ["python3", "server.py"]
```

This way the existing CI pattern (`context: .`, `file: ${{ matrix.tool.dockerfile }}/Dockerfile`) works for the service too.

- [ ] **Step 3: Commit**

```bash
git add Makefile .github/workflows/pr.yml .github/workflows/release.yml inject-tool/service/Dockerfile
git commit -s -m "feat: add inject-tool-service to CI and Makefile"
```

---

### Task 8: End-to-End Test on Cluster

**Files:** None (manual testing)

- [ ] **Step 1: Build and push the service image locally**

```bash
make docker-push-inject-tool-service
```

Or if no local buildx:
```bash
docker build -t quay.io/akurinnoy/tools-injector/inject-tool-service:next -f inject-tool/service/Dockerfile inject-tool/service
docker push quay.io/akurinnoy/tools-injector/inject-tool-service:next
```

- [ ] **Step 2: Deploy to cluster**

```bash
./inject-tool/setup.sh kubeadmin-che
```

- [ ] **Step 3: Verify service pod is running**

```bash
kubectl get pods -n kubeadmin-che -l app=inject-tool-service
kubectl logs -n kubeadmin-che -l app=inject-tool-service
```

Expected: pod in Running state, log shows "inject-tool-service listening on :8080"

- [ ] **Step 4: Test from a workspace terminal**

Open a workspace (e.g., picoclaw-terminal) and run:

```bash
inject-tool list
inject-tool opencode
inject-tool init
inject-tool init --dry-run
```

Verify each command returns proper output and the workspace restarts after injection.

- [ ] **Step 5: Final commit (if any fixes needed)**

```bash
git add -A
git commit -s -m "fix: adjustments from e2e testing"
```
