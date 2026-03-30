# opencode injector

UBI10-based init container image containing the [opencode](https://github.com/anomalyco/opencode) CLI binary.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: opencode-injector
    container:
      image: quay.io/che-incubator/tools-injector/opencode:next
      command: ["/bin/cp"]
      args: ["/usr/local/bin/opencode", "/injected-tools/opencode"]
      memoryLimit: 128Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-opencode
    apply:
      component: opencode-injector

events:
  preStart:
    - install-opencode
```

The editor container must mount the `injected-tools` volume to access the binary.
