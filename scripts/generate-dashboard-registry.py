#!/usr/bin/env python3
"""Generate dashboard/registry.json from inject-tool/registry.json + dashboard/providers.json."""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

INJECT_REGISTRY = os.path.join(ROOT_DIR, "inject-tool", "registry.json")
PROVIDERS = os.path.join(ROOT_DIR, "dashboard", "providers.json")
OUTPUT = os.path.join(ROOT_DIR, "dashboard", "registry.json")


def main():
    with open(INJECT_REGISTRY, encoding="utf-8") as f:
        inject = json.load(f)
    with open(PROVIDERS, encoding="utf-8") as f:
        providers = json.load(f)

    registry_base = inject["registry"]
    tag = inject["tag"]
    inject_tools = inject["tools"]

    provider_map = {p["id"]: p for p in providers["providers"]}
    errors = []

    dashboard_tools = []
    for tool_slug, meta in providers["tools"].items():
        if tool_slug not in inject_tools:
            errors.append(f"Tool '{tool_slug}' in providers.json not found in inject-tool/registry.json")
            continue

        inject_entry = inject_tools[tool_slug]
        provider_id = meta["providerId"]
        if provider_id not in provider_map:
            errors.append(f"Provider '{provider_id}' referenced by tool '{tool_slug}' not found in providers array")
            continue

        setup_cmd = inject_entry.get("editor", {}).get("postStart", "")

        tool_def = {
            "providerId": provider_id,
            "tag": tag,
            "name": meta["name"],
            "url": meta["url"],
            "binary": inject_entry["binary"],
            "pattern": inject_entry["pattern"],
            "injectorImage": f"{registry_base}/tools-injector/{tool_slug}:{tag}",
            "envVarName": meta["envVarName"],
        }
        if setup_cmd:
            tool_def["setupCommand"] = setup_cmd

        dashboard_tools.append(tool_def)

    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    output = {
        "providers": providers["providers"],
        "tools": dashboard_tools,
        "defaultAiProviders": providers["defaultAiProviders"],
    }

    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"Generated {OUTPUT} with {len(dashboard_tools)} tools")


if __name__ == "__main__":
    main()
