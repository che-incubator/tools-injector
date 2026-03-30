# kilocode injector

UBI10-based init container image containing [Kilo Code CLI](https://github.com/nicepkg/kilo-code) with Node.js runtime.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: kilocode-injector
    container:
      image: quay.io/che-incubator/tools-injector/kilocode:next
      command: ["/bin/sh"]
      args: ["-c", "cp -a /opt/kilocode/. /injected-tools/kilocode/"]
      memoryLimit: 256Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-kilocode
    apply:
      component: kilocode-injector

events:
  preStart:
    - install-kilocode
```

The editor container must mount the `injected-tools` volume to access the tool at `/injected-tools/kilocode/bin/kilo`.
