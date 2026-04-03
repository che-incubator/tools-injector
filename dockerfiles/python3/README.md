# python3 injector

UBI10-based init container image containing Python3 + stdlib extracted from Alpine.

Used as a fallback runtime for `inject-tool.py` in workspace containers that lack python3.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: python3-injector
    container:
      image: quay.io/akurinnoy/tools-injector/python3:next
      command: ["/bin/cp"]
      args: ["/usr/local/bin/python3", "/injected-tools/python3"]
      memoryLimit: 128Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-python3
    apply:
      component: python3-injector

events:
  preStart:
    - install-python3
```

The editor container must mount the `injected-tools` volume to access the binary.
