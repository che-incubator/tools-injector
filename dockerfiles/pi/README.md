# pi injector

UBI10-based init container image containing the [Pi coding agent](https://github.com/badlogic/pi-mono) (`@earendil-works/pi-coding-agent`) with a self-contained Node.js runtime (pi requires Node >= 22.19).

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 512Mi
  - name: pi-injector
    container:
      image: quay.io/che-incubator/tools-injector/pi:next
      command: ["/bin/sh"]
      args: ["-c", "cp -a /opt/pi/. /injected-tools/pi/"]
      memoryLimit: 256Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-pi
    apply:
      component: pi-injector

events:
  preStart:
    - install-pi
```

The editor container must mount the `injected-tools` volume to access the tool at `/injected-tools/pi/bin/pi`.

## Notes

- `/opt/pi/bin/pi` is a small shell wrapper that runs the bundled Node.js (>= 22.19, pi's minimum) against `dist/bundle/cli.js`. The npm bin entry cannot be copied as a single file: it is a symlink into `dist/bundle` whose launcher resolves `./cli-runtime.js` relative to itself, which breaks once the symlink is dereferenced. The wrapper also keeps the bundle independent of the node version in the target workspace.
- The npm payload is installed with `--ignore-scripts`; pi's package needs no install scripts. Unlike the pi.dev installer, npm does not pin transitive dependencies — acceptable here because the built image is immutable.
- The npm payload is architecture-independent; only the Node.js runtime stage differs per architecture.
