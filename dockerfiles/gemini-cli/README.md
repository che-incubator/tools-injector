# gemini-cli injector

UBI10-based init container image containing [Gemini CLI](https://github.com/google-gemini/gemini-cli) with Node.js runtime.

## Usage in a DevWorkspace

```yaml
components:
  - name: injected-tools
    volume:
      size: 256Mi
  - name: gemini-cli-injector
    container:
      image: quay.io/che-incubator/tools-injector/gemini-cli:next
      command: ["/bin/sh"]
      args: ["-c", "cp -a /opt/gemini-cli/. /injected-tools/gemini-cli/"]
      memoryLimit: 256Mi
      mountSources: false
      volumeMounts:
        - name: injected-tools
          path: /injected-tools

commands:
  - id: install-gemini-cli
    apply:
      component: gemini-cli-injector

events:
  preStart:
    - install-gemini-cli
```

The editor container must mount the `injected-tools` volume to access the tool at `/injected-tools/gemini-cli/bin/gemini`.
