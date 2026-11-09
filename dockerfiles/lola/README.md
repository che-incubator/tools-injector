# lola injector

UBI10-based init container image containing [lola](https://github.com/LobsterTrap/lola) (`lola-ai` on PyPI), a universal AI context package manager, installed into a Python 3.13 bundle from [python-build-standalone](https://github.com/astral-sh/python-build-standalone) (glibc build).

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 512Mi
  - name: lola-injector
    container:
      image: quay.io/che-incubator/tools-injector/lola:next
      command: ["/bin/sh"]
      args: ["-c", "cp -a /opt/lola/. /injected-tools/lola/"]
      memoryLimit: 64Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-lola
    apply:
      component: lola-injector

events:
  preStart:
    - install-lola
```

The editor container must mount the `injected-tools` volume to access the tool at `/injected-tools/lola/bin/lola`.

## Notes

- `/opt/lola/bin/lola` is a small shell wrapper that runs the bundled Python in isolated mode (`-I`) against `lola.__main__:main`. pip's console script cannot be used: its shebang hardcodes the build-time interpreter path, which breaks once the bundle is copied to `/injected-tools/lola/`.
- The bundle carries its own Python, separate from the `python3` tool; only `lola` is linked into `/injected-tools/bin`.
- The bundle is a glibc build: the workspace image must be glibc based (UBI/RHEL), not Alpine/musl.
- lola runs `git` from the workspace `PATH` for git module sources, and keeps its state in `~/.lola` (override with `LOLA_HOME`).
- Transitive pip dependencies are not pinned; acceptable because the built image is immutable.
- `--hot` is not supported for bundle tools.
