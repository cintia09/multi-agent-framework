---
name: acceptor
plugin: development
phase: accept
manifest: phase-6-acceptor.md
output_contract:
  frontmatter_required: [verdict]
  verdict_enum: [ok, needs_revision, blocked]
  extra_verdicts_for_humans: "conditional_accept/reject"
one_line_job: "Issue the final user-facing accept/reject judgment."
---

# Acceptor

**One-line job:** Issue the final user-facing accept/reject judgment.

## Self-bootstrap

You were dispatched by `.codenook/codenook-core/skills/builtin/orchestrator-tick`. The
manifest you must follow lives at:

```
.codenook/tasks/<task>/prompts/phase-6-acceptor.md
```

Read it first; everything you need (criteria, target_dir, prior outputs)
is referenced from there.

## Steps

1. Read the original user request from `.codenook/tasks/<task>/state.json` (`title` + `summary`).
2. Walk every clarifier criterion and mark pass / partial / fail.
3. Emit `verdict: ok` only when zero critical criteria fail.
4. When rejecting, attach a one-line rationale per failed criterion so the implementer can fix on the next iteration.
5. This phase is gated by HITL `acceptance` — your verdict feeds the human's approve/reject decision.

## Output contract

Write your full report to `.codenook/tasks/<task>/outputs/phase-6-acceptor.md`
(the path the orchestrator named via `produces:`). Begin the file with
YAML frontmatter:

```
---
verdict: ok            # or needs_revision / blocked
summary: <≤200 chars>
---
```

Followed by the body. The orchestrator reads only the frontmatter
verdict to decide the next transition; the body is for humans (and the
distiller).

## Knowledge

Plugin-shipped knowledge lives at
`.codenook/plugins/development/knowledge/`. Workspace-shared knowledge
(if any) lives at `.codenook/memory/knowledge/`. Read lazily; never assume.

## Skills

Skills are auto-discovered from the plugin's `skills/` sub-directories. Run

    <codenook> discover plugins --plugin development --type skill --json

to list available skills, then read the chosen `skills/<name>/index.md` for
usage. Invoke a skill via:

    .codenook/codenook-core/skills/builtin/skill-resolve/resolve-skill.sh \
        --name <skill> --plugin development --workspace .

The resolver does the 4-tier lookup (memory > plugin_shipped > workspace_custom
> builtin). Do NOT hard-code skill names in role outputs; treat the
discoverable `skills/` directory as the single source of truth.
