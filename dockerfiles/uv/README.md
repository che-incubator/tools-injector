# uv injector

UBI10-based init container image containing the [uv](https://github.com/astral-sh/uv) and `uvx` binaries (static musl builds, so they run on glibc and musl workspaces).

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 1Gi
  - name: uv-injector
    container:
      image: quay.io/che-incubator/tools-injector/uv:next
      command: ["/bin/cp"]
      args: ["/usr/local/bin/uv", "/usr/local/bin/uvx", "/injected-tools/"]
      memoryLimit: 128Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-uv
    apply:
      component: uv-injector

events:
  preStart:
    - install-uv
```

The editor container must mount the `injected-tools` volume. `inject-tool uv` additionally sets these env vars on the editor so all uv state survives restarts on the volume:

| Env var | Value | Purpose |
|---|---|---|
| `UV_PYTHON_INSTALL_DIR` | `/injected-tools/uv-state/python` | managed Python installations (`uv python install`) |
| `UV_TOOL_DIR` | `/injected-tools/uv-state/tools` | `uv tool install` targets |
| `UV_TOOL_BIN_DIR` | `/injected-tools/bin` | tool executables; on `PATH`, so installed tools are immediately callable |

## Notes

- The init container copies both `uv` and `uvx` (cp accepts multiple sources with a directory destination). Hot inject (`inject-tool uv --hot`) extracts the `uv` binary only; use `uv tool run` as the `uvx` equivalent in that mode.
- `UV_PYTHON_BIN_DIR` is deliberately left at uv's default (`~/.local/bin`): pointing it at `/injected-tools/bin` would make `uv python install` write its own `python3` symlink there, clobbering the python3 injector's. Managed interpreters persist in `UV_PYTHON_INSTALL_DIR`; `uv run`, `uvx` and `uv tool` find them without the bin-dir symlinks.
