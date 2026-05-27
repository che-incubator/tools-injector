# GitHub CLI (gh) injector

UBI10-based init container image containing the [GitHub CLI](https://github.com/cli/cli) binary.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: gh-injector
    container:
      image: quay.io/che-incubator/tools-injector/gh:next
      command: ["/bin/cp"]
      args: ["/usr/local/bin/gh", "/injected-tools/gh"]
      memoryLimit: 128Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-gh
    apply:
      component: gh-injector

events:
  preStart:
    - install-gh
```

The editor container must mount the `injected-tools` volume to access the binary.
