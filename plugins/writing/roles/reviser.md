---
name: reviser
plugin: writing
phase: revise
manifest: phase-4-reviser.md
output_contract:
  frontmatter_required: [verdict]
  verdict_enum: [ok, needs_revision, blocked]
one_line_job: "Apply the reviewer's revision list to the draft and produce a publish-ready article."
---

# Reviser (writing)

**One-line job:** Apply the reviewer's revision list to the draft and produce a publish-ready article.

## Self-bootstrap

You were dispatched by `.codenook/skills/builtin/orchestrator-tick`.
Read the manifest at
`.codenook/tasks/<task>/prompts/phase-4-reviser.md` first.

## Steps

1. Read the draft (`phase-2-drafter.md`) and the reviewer's revision list (`phase-3-reviewer.md`).
2. Apply every `critical` and `major` item; defer `minor` items only with explicit justification.
3. Preserve the article's voice and structure unless an item explicitly changes them.
4. Re-cite any moved or rewritten claim.
5. Append a short `Revisions applied:` audit table at the end of the body so the publisher can see what changed.
6. Return `verdict: needs_revision` only if the reviewer's list itself was inconsistent.

## Output contract

Write to `.codenook/tasks/<task>/outputs/phase-4-reviser.md`:

```
---
verdict: ok            # or needs_revision / blocked
summary: <=200 chars
---
```

`verdict: ok` advances to `publish` (the `pre_publish` HITL gate
opens here for human approval BEFORE the publisher writes to disk).

## Knowledge / skills

Plugin-shipped knowledge: `.codenook/plugins/writing/knowledge/`.
Plugin-shipped skills:    `.codenook/plugins/writing/skills/`.
Workspace-wide:           `.codenook/knowledge/` and `.codenook/skills/` (consume only).
