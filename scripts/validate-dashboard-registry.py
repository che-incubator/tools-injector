#!/usr/bin/env python3
"""Validate dashboard/registry.json against inject-tool/registry.json."""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

INJECT_REGISTRY = os.path.join(ROOT_DIR, "inject-tool", "registry.json")
DASHBOARD_REGISTRY = os.path.join(ROOT_DIR, "dashboard", "registry.json")


def main():
    with open(INJECT_REGISTRY, encoding="utf-8") as f:
        inject = json.load(f)
    with open(DASHBOARD_REGISTRY, encoding="utf-8") as f:
        dashboard = json.load(f)

    inject_tools = inject["tools"]
    errors = []

    for tool in dashboard.get("tools", []):
        image = tool.get("injectorImage", "")
        slug = image.rsplit("/", 1)[-1].split(":")[0] if "/" in image else ""
        if not slug:
            errors.append(f"Tool '{tool.get('name')}' has no parseable slug from injectorImage '{image}'")
            continue

        if slug not in inject_tools:
            errors.append(f"Tool '{slug}' in dashboard registry not found in inject-tool/registry.json")
            continue

        inject_entry = inject_tools[slug]

        if tool["binary"] != inject_entry["binary"]:
            errors.append(f"{slug}: binary mismatch — dashboard='{tool['binary']}', inject-tool='{inject_entry['binary']}'")

        if tool["pattern"] != inject_entry["pattern"]:
            errors.append(f"{slug}: pattern mismatch — dashboard='{tool['pattern']}', inject-tool='{inject_entry['pattern']}'")

    provider_ids = {p["id"] for p in dashboard.get("providers", [])}
    for tool in dashboard.get("tools", []):
        if tool.get("providerId") not in provider_ids:
            errors.append(f"Tool '{tool.get('name')}' references unknown provider '{tool.get('providerId')}'")

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"dashboard/registry.json is valid ({len(dashboard.get('tools', []))} tools)")


if __name__ == "__main__":
    main()
