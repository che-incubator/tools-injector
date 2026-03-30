# claude-code injector

UBI10-based init container image containing the [Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI binary.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: claude-code-injector
    container:
      image: quay.io/che-incubator/tools-injector/claude-code:next
      command: ["/bin/cp"]
      args: ["/usr/local/bin/claude", "/injected-tools/claude"]
      memoryLimit: 128Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-claude-code
    apply:
      component: claude-code-injector

events:
  preStart:
    - install-claude-code
```

The editor container must mount the `injected-tools` volume to access the binary.
