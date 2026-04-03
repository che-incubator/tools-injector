# Custom Tools Guide

This guide explains how to inject custom CLI tools (tools not in the central registry) into your DevWorkspace without modifying the tools-injector project.

## Overview

Custom tools let you inject any CLI binary into your DevWorkspace by defining them in `.che/inject-tools.json` in your repository. This is useful for:

- Project-specific tooling not appropriate for the central registry
- Internal or proprietary tools
- Quickly prototyping new tools before proposing them for the registry
- Using specific versions of tools different from those in the registry

## Building a Custom Tool Image — Init Pattern (Single Binary)

The simplest pattern copies a single binary from a builder stage into a minimal UBI10 runtime.

Example: injecting `git` from a custom image.

**Dockerfile:**

```dockerfile
FROM alpine:3.21 AS builder
RUN apk add --no-cache git

FROM registry.access.redhat.com/ubi10/ubi-minimal:latest
COPY --from=builder /usr/bin/git /usr/bin/git
```

Build and push:

```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t quay.io/myorg/git-tool:latest \
  --push .
```

**Corresponding `.che/inject-tools.json` entry:**

```json
{
  "tools": [
    {
      "name": "git",
      "image": "quay.io/myorg/git-tool:latest",
      "binaries": [
        { "src": "/usr/bin/git", "binary": "git" }
      ]
    }
  ]
}
```

## Multi-Tool Image (Multiple Binaries, One Image)

For repositories that need several tools, build one image containing all of them. This reduces the number of init containers and simplifies maintenance.

**Dockerfile example combining git + jq + curl:**

```dockerfile
FROM alpine:3.21 AS builder
RUN apk add --no-cache git jq curl

FROM registry.access.redhat.com/ubi10/ubi-minimal:latest
COPY --from=builder /usr/bin/git /usr/bin/git
COPY --from=builder /usr/bin/jq /usr/bin/jq
COPY --from=builder /usr/bin/curl /usr/bin/curl
```

**Corresponding `.che/inject-tools.json`:**

```json
{
  "tools": [
    {
      "name": "dev-tools",
      "image": "quay.io/myorg/my-project-tools:latest",
      "binaries": [
        { "src": "/usr/bin/git", "binary": "git" },
        { "src": "/usr/bin/jq", "binary": "jq" },
        { "src": "/usr/bin/curl", "binary": "curl" }
      ]
    }
  ]
}
```

## Using an Existing Image (No Build Required)

If a public image already contains the binary you need, reference it directly without building your own Dockerfile.

**Example using alpine/git:**

```json
{
  "tools": [
    {
      "name": "git",
      "image": "alpine/git:latest",
      "binaries": [
        { "src": "/usr/bin/git", "binary": "git" }
      ]
    }
  ]
}
```

**Important:** Verify that the image architecture matches your cluster. Use `skopeo inspect` to check available architectures:

```bash
skopeo inspect docker://alpine/git:latest | jq '.Architecture'
```

## Complete Example

A full `.che/inject-tools.json` can mix registry tools (referenced by name) with custom tool definitions:

```json
{
  "tools": [
    "opencode",
    "tmux",
    {
      "name": "dev-tools",
      "image": "quay.io/myorg/my-project-tools:latest",
      "binaries": [
        { "src": "/usr/bin/git", "binary": "git" },
        { "src": "/usr/bin/jq", "binary": "jq" }
      ]
    }
  ]
}
```

When you run `inject-tool init`, it will:
1. Resolve `opencode` and `tmux` from the central registry
2. Use your custom `dev-tools` definition
3. Merge all patches into a single DevWorkspace update

## Checklist

Before injecting custom tools, verify:

- [ ] Image is accessible from the cluster (public registry or credentials configured in the namespace)
- [ ] For multi-arch clusters, the image supports the required architectures (typically amd64 and arm64)
- [ ] Binaries are statically linked OR all runtime dependencies are included in the image
- [ ] Total size of all binaries fits within the shared volume size (default 256Mi)
- [ ] Test with `inject-tool init --dry-run` to preview the patch before applying

To verify your custom tool configuration before injection:

```bash
inject-tool init --dry-run
```

This will show the JSON Patch operations without modifying the DevWorkspace.

## Optional Fields

Custom tool definitions support additional configuration beyond `name`, `image`, and `binaries`:

| Field | Description | Example |
|-------|-------------|---------|
| `description` | Human-readable description shown in logs and dry-run output | `"Git CLI for version control"` |
| `env` | Environment variables to inject into the editor container | `[{"name": "GIT_CONFIG", "value": "/config/gitconfig"}]` |
| `postStart` | Shell command to run after the workspace starts | `"git config --global user.name 'Dev User'"` |
| `memoryLimit` | Additional memory to allocate to the editor container (e.g., for Node.js runtimes) | `"512Mi"` |

**Example with optional fields:**

```json
{
  "tools": [
    {
      "name": "dev-tools",
      "description": "Project-specific development utilities",
      "image": "quay.io/myorg/my-project-tools:latest",
      "binaries": [
        { "src": "/usr/bin/git", "binary": "git" }
      ],
      "env": [
        { "name": "GIT_CONFIG", "value": "/config/gitconfig" }
      ],
      "postStart": "git config --global init.defaultBranch main"
    }
  ]
}
```

## Troubleshooting

**Binary not found after injection:**

- Verify the source path in the image: `podman run --rm <image> ls -la /usr/bin/git`
- Check init container logs: `oc logs <workspace-pod> -c inject-<tool-name>`

**Permission denied when running the binary:**

- Ensure the binary has execute permissions in the image
- Add `chmod +x` to your Dockerfile if needed

**Image pull errors:**

- Verify the image exists: `skopeo inspect docker://<image>`
- For private registries, ensure image pull secrets are configured in the namespace

**Volume size exceeded:**

- Check total binary sizes: `podman run --rm <image> du -sh /usr/bin/*`
- Reduce binary count or request a larger volume (requires cluster admin)
