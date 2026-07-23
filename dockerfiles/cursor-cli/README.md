# cursor-cli injector

UBI10-based init container image containing [Cursor Agent CLI](https://cursor.com/docs/cli/overview) with bundled Node.js runtime.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 512Mi
  - name: cursor-cli-injector
    container:
      image: quay.io/che-incubator/tools-injector/cursor-cli:next
      command: ["/bin/sh"]
      args: ["-c", "cp -a /opt/cursor-cli/. /injected-tools/cursor-cli/"]
      memoryLimit: 512Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-cursor-cli
    apply:
      component: cursor-cli-injector

events:
  preStart:
    - install-cursor-cli
```

The editor container must mount the `injected-tools` volume to access the tool at `/injected-tools/cursor-cli/bin/agent` or `/injected-tools/cursor-cli/bin/cursor-agent`.

## Authentication

Set `CURSOR_API_KEY` in the workspace environment, or run `agent auth` interactively after injection.

## Version

Pinned in `VERSION` and overridable at build time:

```bash
CURSOR_CLI_VERSION=2026.07.13-7fe37d2 make docker-build-local-cursor-cli
```
