# codex injector

UBI10-based init container image containing the [Codex](https://github.com/openai/codex) CLI binary.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 512Mi
  - name: codex-injector
    container:
      image: quay.io/che-incubator/tools-injector/codex:next
      command: ["/bin/cp"]
      args: ["/usr/local/bin/codex", "/injected-tools/codex"]
      memoryLimit: 128Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-codex
    apply:
      component: codex-injector

events:
  preStart:
    - install-codex
```

The editor container must mount the `injected-tools` volume to access the binary.

The binary is about 300 MB at 0.164.0, so size the `injected-tools` volume accordingly.
