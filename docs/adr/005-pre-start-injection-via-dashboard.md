# ADR-005: Pre-start tool injection via Che Dashboard

- **Date**: 2026-06-24
- **Status**: Proposed
- **Tags**: architecture, dashboard, devfile, injection

## Context and Problem Statement

`inject-tool` only works against running workspaces — it patches the DevWorkspace CR via Kubernetes API, which triggers a workspace restart. Users need tools available on first workspace start, declared per-repository without manual steps. The previous attempt at project-scoped injection (ADR-003) was reverted because it still required post-start execution and a restart.

The core challenge is a chicken-and-egg problem: the tool configuration lives in the Git repo, but the repo is cloned *into* the workspace. Something must read the configuration before the workspace pods start.

## Decision Drivers

- Tools must be fully functional on first boot — binaries, env vars, memory limits, postStart setup
- No workspace restart on first use
- Per-repository configuration with loose coupling to tools-injector internals
- Must work with both init-pattern (single binary) and bundle-pattern (Node.js) tools
- No new cluster infrastructure (no webhook service, no dedicated operator)

## Considered Options

- Init container that patches DevWorkspace CR (one automatic restart)
- Static DevWorkspaceTemplate with generous defaults (no restart, wastes resources)
- Mutating admission webhook (no restart, operational complexity)
- Che Dashboard integration (no restart, no waste, no new infrastructure)

## Decision Outcome

Chosen option: **"Che Dashboard integration"**, because it is the only approach that satisfies all decision drivers — full tool functionality on first boot, no restart, no wasted resources, and no new infrastructure. The Dashboard already fetches and resolves devfiles before creating DevWorkspace CRs, making it the natural place to apply injection.

### Positive Consequences

- Tools available on first workspace start with zero user interaction beyond the devfile attribute
- No cluster-level infrastructure to deploy or maintain (no webhook, no operator)
- Per-repository granularity — each repo declares exactly the tools it needs
- Reuses the existing `tools-injector-registry` ConfigMap (ADR-002) as the contract between tools-injector and Dashboard
- Coexists with post-start `inject-tool` CLI for adding tools to running workspaces

### Negative Consequences

- Requires Dashboard code changes, coupling injection feature delivery to the Dashboard release cycle
- Dashboard must understand registry.json schema — schema changes require coordinated updates
- The devfile attribute is consumed only at workspace creation time — changing it requires recreating the workspace

## Pros and Cons of the Options

### Che Dashboard integration ✅ Chosen

- ✅ No restart — tools baked into DevWorkspace CR before creation
- ✅ Full functionality — can set env vars, memory limits, postStart (pod spec fields)
- ✅ No wasted resources — only requested tools get memory/env treatment
- ✅ No new infrastructure — uses existing Dashboard + ConfigMap
- ❌ Couples to Dashboard release cycle
- ❌ Dashboard must understand registry.json schema

### Init container that patches DevWorkspace CR

- ✅ No Dashboard changes needed
- ✅ Full functionality via CR patching
- ❌ One automatic restart on first workspace creation (DWO reconciles CR change)
- ❌ Init container can't modify its own pod spec (memory, env vars) — must patch CR and restart

### Static DevWorkspaceTemplate with generous defaults

- ✅ No restart — template merged at creation time
- ✅ No Dashboard changes needed
- ❌ All workspaces get high memory allocation regardless of requested tools
- ❌ Cannot conditionally set env vars based on which tools are requested
- ❌ Wastes cluster resources at scale

### Mutating admission webhook

- ✅ No restart — intercepts CR before DWO reconciles
- ✅ Full functionality — can set any pod spec field
- ✅ Per-workspace granularity via annotations
- ❌ Requires deploying and operating an HTTPS webhook service with TLS cert management
- ❌ Webhook availability affects workspace creation (webhook down → creation blocked)
- ❌ Must coordinate ordering with DWO's own webhooks

## Implementation

### Devfile attribute contract

Repos declare tools via a top-level devfile attribute:

```yaml
attributes:
  tools.che.io/inject: "claude-code,goose,tmux"
```

Comma-separated tool names matching keys in `registry.json`. Unknown names are skipped with a warning. Absent attribute means no injection.

### Registry.json schema update

A new `injector` section per tool provides structured metadata for Dashboard consumption:

```json
"injector": {
  "memoryLimit": "128Mi"
}
```

The Dashboard constructs init containers from existing fields (`pattern`, `src`, `binary`) and uses `injector.memoryLimit` for the init container memory limit. The `patch` section (raw JSON Patch ops) remains for `inject-tool.py` post-start use.

### Naming convention contract

Both Dashboard and `inject-tool` use `{tool}-injector` as the component name for injector init containers (e.g., `claude-code-injector`). This is the idempotency key — `inject-tool` checks for this component to detect already-injected tools.

## Links

- Supersedes: [ADR-003: Project-scoped injection](003-project-scoped-injection.md) (reverted approach)
- Builds on: [ADR-002: Dashboard tool registry](002-dashboard-tool-registry.md)
- Related: [ADR-004: Client-server architecture](004-client-server-architecture.md) (alternative approach)
- Spec: [Pre-start injection design](../superpowers/specs/2026-06-24-pre-start-injection-design.md)
