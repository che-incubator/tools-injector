# goose injector

UBI10-based init container image containing the [goose](https://github.com/block/goose) CLI binary.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: goose-injector
    container:
      image: quay.io/che-incubator/tools-injector/goose:next
      command: ["/bin/cp"]
      args: ["/usr/local/bin/goose", "/injected-tools/goose"]
      memoryLimit: 128Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-goose
    apply:
      component: goose-injector

events:
  preStart:
    - install-goose
```

The editor container must mount the `injected-tools` volume to access the binary.
