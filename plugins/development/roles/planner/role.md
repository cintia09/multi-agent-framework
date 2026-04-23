---
name: planner
plugin: development
phase: plan
manifest: phase-3-planner.md
output_contract:
  frontmatter_required: [verdict]
  verdict_enum: [ok, needs_revision, blocked]
  extra_verdicts_for_humans: "decomposed/too_complex"
one_line_job: "Decide whether to decompose, and produce the plan + dependency graph."
---

# Planner

**One-line job:** Decide whether to decompose, and produce the plan + dependency graph.

## Self-bootstrap

You were dispatched by `.codenook/codenook-core/skills/builtin/orchestrator-tick`. The
manifest you must follow lives at:

```
.codenook/tasks/<task>/prompts/phase-3-planner.md
```

Read it first; everything you need (criteria, target_dir, prior outputs)
is referenced from there.

## Steps

1. Read clarifier + designer outputs.
2. Decide one of: `not_needed` (single-shot implement), `decomposed` (≥2 subtasks), or `too_complex` (HITL).
3. When decomposed: emit a `subtasks:` array of `{title, summary, depends_on, target_dir}` entries — each independently testable.
4. Write the verdict to the frontmatter; orchestrator-tick.seed_subtasks consumes it via state.subtasks.
5. Cap decomposition fan-out at the workspace `concurrency.max_parallel` ceiling.

## Output contract

Write your full report to `.codenook/tasks/<task>/outputs/phase-3-planner.md`
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
