# tmux injector

UBI10-based init container image containing [tmux](https://github.com/tmux/tmux) extracted from CentOS Stream RPMs.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: tmux-injector
    container:
      image: quay.io/okurinny/tools-injector/tmux:next
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
