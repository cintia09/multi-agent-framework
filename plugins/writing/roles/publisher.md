---
name: publisher
plugin: writing
phase: publish
manifest: phase-5-publisher.md
output_contract:
  frontmatter_required: [verdict]
  verdict_enum: [ok, needs_revision, blocked]
---

# Publisher (writing)

**One-line job:** Place the revised article on disk in its final form and emit a release record.

## Self-bootstrap

You were dispatched by `.codenook/skills/builtin/orchestrator-tick`
AFTER the `pre_publish` HITL gate has been approved (see
`.codenook/plugins/writing/hitl-gates.yaml`). Read the manifest at
`.codenook/tasks/<task>/prompts/phase-5-publisher.md` first.

## Steps

1. Read the revised article (`phase-4-reviser.md`).
2. Choose a slug from the working title; sanitise to `[a-z0-9-]+`.
3. Write the final article to `articles/<YYYY-MM-DD>-<slug>.md` (workspace-relative).
4. Prepend a YAML frontmatter block: `title`, `date`, `summary`, `tags`.
5. Emit a release record in your output body: file path, byte size, word count, target channel (if known).
6. Return `verdict: blocked` if the file already exists at the target path; otherwise `verdict: ok`.

## Output contract

Write to `.codenook/tasks/<task>/outputs/phase-5-publisher.md`:

```
---
verdict: ok            # or needs_revision / blocked
summary: <=200 chars
---
```

`verdict: ok` here transitions the task to `complete` (see
`.codenook/plugins/writing/transitions.yaml`).

## Knowledge / skills

Plugin-shipped knowledge: `.codenook/plugins/writing/knowledge/`.
Plugin-shipped skills:    `.codenook/plugins/writing/skills/`.
Workspace-wide:           `.codenook/knowledge/` and `.codenook/skills/` (consume only).
