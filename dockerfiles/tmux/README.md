# tmux injector

UBI10-based init container image containing a pre-built [tmux](https://github.com/tmux/tmux) binary from [tmux-builds](https://github.com/tmux/tmux-builds) releases.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: tmux-injector
    container:
      image: quay.io/che-incubator/tools-injector/tmux:next
      command: ["/bin/cp"]
      args: ["/usr/local/bin/tmux", "/injected-tools/tmux"]
      memoryLimit: 128Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-tmux
    apply:
      component: tmux-injector

events:
  preStart:
    - install-tmux
```

The editor container must mount the `injected-tools` volume to access the binary.
