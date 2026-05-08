# Agent Rules

## Commit Format
Use:

```text
type(scope): subject [Agent: <MODEL NAME>]
```

## Attribution
- Commit trailer: `Co-authored-by: Chimera <chimera_defi@protonmail.com>`
- PR body must include:
  - `**Agent:** <model name>`
  - `**Co-authored-by:** Chimera <chimera_defi@protonmail.com>`
  - `## Original Request`

## Skill Lifecycle
- Keep this repo standalone.
- Integrate into token-reduce as a companion toolkit, not embedded source.
- Maintain telemetry and propagation scripts before rollout.
