# python3 injector

UBI10-based init container image containing a Python3 bundle from [python-build-standalone](https://github.com/astral-sh/python-build-standalone) (glibc build).

Used as a fallback runtime for `inject-tool.py` in workspace containers that lack python3.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 512Mi
  - name: python3-injector
    container:
      image: quay.io/che-incubator/tools-injector/python3:next
      command: ["/bin/sh"]
      args: ["-c", "rm -rf /injected-tools/python3 && cp -a /opt/python3/. /injected-tools/python3/"]
      memoryLimit: 256Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-python3
    apply:
      component: python3-injector

events:
  preStart:
    - install-python3
```

The editor container must mount the `injected-tools` volume to access the tool. `inject-tool` exposes `/injected-tools/bin/python3` as a symlink to `/injected-tools/python3/bin/python3`.

Notes:

- The bundle is a glibc build: the workspace image must be glibc based (UBI/RHEL), not Alpine/musl.
- Unpacked size is ~104 MB on amd64.
- `--hot` is not supported for bundle tools.
