#!/usr/bin/env python3
"""inject-tool — dynamically inject CLI tools into DevWorkspaces."""

import argparse
import copy
import json
import os
import ssl
import subprocess
import sys
import urllib.request

# ============================================================================
# Tool registry (loaded from registry.json at startup)
# ============================================================================
def _registry_path():
    override = os.environ.get("INJECT_TOOL_REGISTRY_FILE")
    if override:
        return override
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "registry.json")


def load_registry():
    path = _registry_path()
    try:
        with open(path) as f:
            data = json.load(f)
    except OSError as e:
        print(f"ERROR: Cannot read registry file at {path}: {e}", file=sys.stderr)
        print("Set INJECT_TOOL_REGISTRY_FILE to override the path.", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: registry.json is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    for key in ("registry", "tag", "tools"):
        if key not in data:
            print(f"ERROR: registry.json is missing required key '{key}'", file=sys.stderr)
            sys.exit(1)

    return data


REGISTRY_DATA = load_registry()

_base_registry = os.environ.get("INJECT_TOOL_REGISTRY") or REGISTRY_DATA["registry"]
_base_tag = os.environ.get("INJECT_TOOL_TAG") or REGISTRY_DATA["tag"]


# ============================================================================
# Helpers
# ============================================================================
def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg):
    print(f"==> {msg}")


def tool_image(tool):
    return f"{_base_registry}/tools-injector/{tool}:{_base_tag}"


def validate_tools(tool_names):
    tools = REGISTRY_DATA["tools"]
    for name in tool_names:
        if name not in tools:
            print(f"Unknown tool: {name}\n", file=sys.stderr)
            print("Available tools:", file=sys.stderr)
            for t in sorted(tools):
                print(f"  {t:<15s} {tools[t]['pattern']}", file=sys.stderr)
            sys.exit(1)


def validate_env():
    for var in ("DEVWORKSPACE_NAMESPACE", "DEVWORKSPACE_NAME"):
        if not os.environ.get(var):
            die(f"{var} not set. Are you running inside a Che workspace?")


# ============================================================================
# Kubernetes API
# ============================================================================
CA_CERT = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
SA_TOKEN = "/var/run/secrets/kubernetes.io/serviceaccount/token"


def get_token():
    kubeconfig = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))
    if os.path.isfile(kubeconfig):
        with open(kubeconfig) as f:
            for line in f:
                if "token:" in line:
                    token = line.split("token:")[-1].strip()
                    if token:
                        return token

    if os.path.isfile(SA_TOKEN):
        with open(SA_TOKEN) as f:
            return f.read().strip()

    die(f"Could not find auth token. No kubeconfig at {kubeconfig} and no service account token.")


def api_url():
    host = os.environ.get("KUBERNETES_SERVICE_HOST")
    port = os.environ.get("KUBERNETES_SERVICE_PORT")
    if not host or not port:
        die("KUBERNETES_SERVICE_HOST/PORT not set.")
    ns = os.environ["DEVWORKSPACE_NAMESPACE"]
    name = os.environ["DEVWORKSPACE_NAME"]
    return f"https://{host}:{port}/apis/workspace.devfile.io/v1alpha2/namespaces/{ns}/devworkspaces/{name}"


def _ssl_context():
    ctx = ssl.create_default_context()
    if os.path.isfile(CA_CERT):
        ctx.load_verify_locations(CA_CERT)
    else:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_workspace():
    token = get_token()
    req = urllib.request.Request(
        api_url(),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_context()) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        die(f"Kubernetes API returned HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        die(f"Failed to connect to Kubernetes API: {e.reason}")


def patch_workspace(ops):
    token = get_token()
    data = json.dumps(ops).encode()
    req = urllib.request.Request(
        api_url(),
        data=data,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json-patch+json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, context=_ssl_context()) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        die(f"Patch failed with HTTP {e.code}: {body}")
    except urllib.error.URLError as e:
        die(f"Failed to connect to Kubernetes API: {e.reason}")


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
    """Return (index, name) of the editor component, or None."""
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
    """Parse '2Gi' or '1024Mi' to int (Mi). Returns 0 if unparseable."""
    if not mem_str:
        return 0
    if mem_str.endswith("Gi"):
        return int(float(mem_str[:-2]) * 1024)
    if mem_str.endswith("Mi"):
        return int(mem_str[:-2])
    return 0


# ============================================================================
# CLI parsing
# ============================================================================
def parse_args():
    parser = argparse.ArgumentParser(
        prog="inject-tool",
        description="Dynamically inject CLI tools into DevWorkspaces.",
    )
    sub = parser.add_subparsers(dest="command")

    inject_p = sub.add_parser("inject", help="Inject one or more tools")
    inject_p.add_argument("tools", nargs="+", metavar="tool")
    inject_p.add_argument("--hot", action="store_true", help="Extract binary without restart (one tool only)")

    sub.add_parser("list", help="List available tools and status")

    remove_p = sub.add_parser("remove", help="Remove one or more injected tools")
    remove_p.add_argument("tools", nargs="+", metavar="tool")
    remove_p.add_argument("--hot", action="store_true", help="Remove hot-injected binary only (one tool only)")

    # Handle bare tool names: "inject-tool opencode" → "inject-tool inject opencode"
    argv = sys.argv[1:]
    known_commands = {"inject", "list", "remove"}
    if argv and argv[0] not in known_commands and not argv[0].startswith("-"):
        argv = ["inject"] + argv

    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    return args


# ============================================================================
# Commands
# ============================================================================
def cmd_list():
    validate_env()
    ws = fetch_workspace()
    print(f"{'Tool':<15s} {'Pattern':<10s} {'Status'}")
    print(f"{'----':<15s} {'-------':<10s} {'------'}")
    for tool in sorted(REGISTRY_DATA["tools"]):
        pattern = REGISTRY_DATA["tools"][tool]["pattern"]
        comp_name = f"{tool}-injector"
        status = "injected" if find_component_index(ws, comp_name) is not None else "not injected"
        print(f"{tool:<15s} {pattern:<10s} {status}")


def build_inject_ops(tool, ws, skip_infra=False):
    reg_tool = REGISTRY_DATA["tools"][tool]
    pattern = reg_tool["pattern"]
    binary_name = reg_tool["binary"]
    ops = []

    editor = find_editor(ws)
    editor_idx = editor[0] if editor else None
    editor_name = editor[1] if editor else None

    # 1. Add injected-tools volume if missing
    if not skip_infra and find_component_index(ws, "injected-tools") is None:
        ops.extend(copy.deepcopy(REGISTRY_DATA["infrastructure"]["patch"]))

    # 2. Add injector component from registry patch (with image override)
    patch_ops = copy.deepcopy(reg_tool["patch"])
    for op in patch_ops:
        if op.get("op") == "add" and isinstance(op.get("value"), dict):
            container = op["value"].get("container", {})
            if "image" in container:
                container["image"] = tool_image(tool)
    ops.extend(patch_ops)

    # 3. Add volume mount to editor
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
    elif editor_idx is None and not skip_infra:
        print("WARNING: Could not find editor component. You may need to add the volume mount manually.",
              file=sys.stderr)

    # 3b. Add tool-specific env vars
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

    # 3c. Memory bump for bundle tools
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

    # 4. Add apply command
    commands = ws.get("spec", {}).get("template", {}).get("commands")
    if skip_infra or commands is not None:
        ops.append({"op": "add", "path": "/spec/template/commands/-",
                     "value": {"id": f"install-{tool}", "apply": {"component": f"{tool}-injector"}}})
    else:
        ops.append({"op": "add", "path": "/spec/template/commands",
                     "value": [{"id": f"install-{tool}", "apply": {"component": f"{tool}-injector"}}]})

    # 5. Add preStart event
    prestart = get_events(ws).get("preStart")
    if not skip_infra and prestart is None:
        ops.append({"op": "add", "path": "/spec/template/events",
                     "value": {"preStart": [f"install-{tool}"]}})
    else:
        ops.append({"op": "add", "path": "/spec/template/events/preStart/-",
                     "value": f"install-{tool}"})

    # 6. Symlink command + postStart event
    if editor_name:
        symlink_cmd_id = f"symlink-{tool}"
        if find_command_index(ws, symlink_cmd_id) is None:
            if pattern == "init":
                symlink_target = f"/injected-tools/{binary_name}"
            else:
                symlink_target = f"/injected-tools/{tool}/bin/{binary_name}"

            path_cmd = (
                'grep -q injected-tools /etc/profile.d/injected-tools.sh 2>/dev/null'
                ' || echo \'export PATH="/injected-tools/bin:$PATH"\' > /etc/profile.d/injected-tools.sh 2>/dev/null;'
                ' grep -q injected-tools "$HOME/.bashrc" 2>/dev/null'
                ' || echo \'export PATH="/injected-tools/bin:$PATH"\' >> "$HOME/.bashrc" 2>/dev/null; true'
            )
            cmdline = (
                f"mkdir -p /injected-tools/bin && "
                f"ln -sf {symlink_target} /injected-tools/bin/{binary_name} && "
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


def hot_inject(tool):
    reg_tool = REGISTRY_DATA["tools"][tool]
    if reg_tool["pattern"] != "init":
        die(f"--hot is only supported for init container tools. Use 'inject-tool {tool}' (without --hot) instead.")
    if subprocess.run(["which", "oc"], capture_output=True).returncode != 0:
        die(f"--hot mode requires the 'oc' CLI. Use 'inject-tool {tool}' (without --hot) for default mode.")

    image = tool_image(tool)
    binary_src = reg_tool["src"]
    binary_name = reg_tool["binary"]

    os.makedirs("/injected-tools", exist_ok=True)
    info(f"Extracting {binary_name} from {image}...")
    result = subprocess.run(
        ["oc", "image", "extract", image, "--path", f"{binary_src}:/injected-tools/", "--confirm"],
        capture_output=True, text=True)
    if result.returncode != 0:
        die(f"oc image extract failed: {result.stderr}")
    os.chmod(f"/injected-tools/{binary_name}", 0o755)
    info(f"Injected {tool} at /injected-tools/{binary_name} (hot inject — will not survive restart)")


def cmd_inject(tools, hot):
    validate_env()

    if hot:
        if len(tools) > 1:
            die("--hot does not support multiple tools. Inject one tool at a time with --hot.")
        hot_inject(tools[0])
        return

    ws = fetch_workspace()

    # Filter already-injected tools
    to_inject = []
    for tool in tools:
        if find_component_index(ws, f"{tool}-injector") is not None:
            info(f"{tool} is already injected, skipping.")
        else:
            to_inject.append(tool)

    if not to_inject:
        info("All requested tools are already injected.")
        return

    # Build ops: first tool with infra, rest without
    all_ops = []
    for i, tool in enumerate(to_inject):
        all_ops.extend(build_inject_ops(tool, ws, skip_infra=(i > 0)))

    # Fix memory bump for multiple bundle tools
    bundle_count = sum(1 for t in to_inject if REGISTRY_DATA["tools"][t]["pattern"] == "bundle")
    if bundle_count > 1:
        editor = find_editor(ws)
        if editor:
            editor_idx = editor[0]
            # Remove individual bump ops and add correct total
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

    tool_names = ", ".join(to_inject)
    info(f"Injecting {tool_names}...")
    patch_workspace(all_ops)
    info(f"Injected {tool_names}. Workspace is restarting...")


def build_remove_ops(tool, ws, also_removing=None):
    if also_removing is None:
        also_removing = []
    comp_name = f"{tool}-injector"
    ops = []

    # Find and remove injector component
    comp_idx = find_component_index(ws, comp_name)
    if comp_idx is None:
        die(f"{tool} is not injected.")
    ops.append({"op": "remove", "path": f"/spec/template/components/{comp_idx}"})

    # Remove apply command
    cmd_idx = find_command_index(ws, f"install-{tool}")
    if cmd_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/commands/{cmd_idx}"})

    # Remove from preStart events
    event_idx = find_event_index(ws, "preStart", f"install-{tool}")
    if event_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/events/preStart/{event_idx}"})

    # Remove symlink command
    symlink_idx = find_command_index(ws, f"symlink-{tool}")
    if symlink_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/commands/{symlink_idx}"})

    # Remove from postStart events
    post_idx = find_event_index(ws, "postStart", f"symlink-{tool}")
    if post_idx is not None:
        ops.append({"op": "remove", "path": f"/spec/template/events/postStart/{post_idx}"})

    # Check if any other injectors remain (excluding tools being removed in this batch)
    removing_names = {f"{r}-injector" for r in also_removing}
    other_injectors = [
        c for c in get_components(ws)
        if c.get("name", "").endswith("-injector")
        and c["name"] != comp_name
        and c["name"] not in removing_names
    ]

    # If no other injectors, remove shared infrastructure
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
    """Sort key for remove ops: descending by numeric index in path."""
    if op.get("op") != "remove":
        return (-1, "")
    parts = op.get("path", "").split("/")
    for p in reversed(parts):
        if p.isdigit():
            return (int(p), "/".join(parts[:-1]))
    return (-1, op.get("path", ""))


def cmd_remove(tools, hot):
    validate_env()

    if hot:
        if len(tools) > 1:
            die("--hot does not support multiple tools.")
        tool = tools[0]
        reg_tool = REGISTRY_DATA["tools"][tool]
        if reg_tool["pattern"] != "init":
            die("--hot remove is only supported for init container tools.")
        binary_path = f"/injected-tools/{reg_tool['binary']}"
        if os.path.exists(binary_path):
            os.remove(binary_path)
        info(f"Removed {binary_path}")
        return

    ws = fetch_workspace()

    all_ops = []
    for tool in tools:
        all_ops.extend(build_remove_ops(tool, ws, also_removing=tools))

    # Sort remove ops by descending index to avoid shifting
    all_ops.sort(key=_remove_sort_key, reverse=True)

    tool_names = ", ".join(tools)
    info(f"Removing {tool_names}...")
    patch_workspace(all_ops)
    info(f"Removed {tool_names}. Workspace is restarting...")


# ============================================================================
# Main
# ============================================================================
def main():
    args = parse_args()

    if args.command == "list":
        cmd_list()
    elif args.command == "inject":
        validate_tools(args.tools)
        cmd_inject(args.tools, args.hot)
    elif args.command == "remove":
        validate_tools(args.tools)
        cmd_remove(args.tools, args.hot)


if __name__ == "__main__":
    main()
