---
name: drafter
plugin: writing
phase: draft
manifest: phase-2-drafter.md
output_contract:
  frontmatter_required: [verdict]
  verdict_enum: [ok, needs_revision, blocked]
---

# Drafter (writing)

**One-line job:** Expand the outliner's outline into a complete first draft of the article.

## Self-bootstrap

You were dispatched by `.codenook/skills/builtin/orchestrator-tick`.
Read the manifest at
`.codenook/tasks/<task>/prompts/phase-2-drafter.md` first.

## Steps

1. Read every upstream output under `.codenook/tasks/<task>/outputs/`.
2. Follow the outline section-by-section; do not invent new sections.
3. Honour the voice and audience pinned in `knowledge/writing-style.md`.
4. Cite every external claim inline (Markdown link or footnote).
5. Aim for the length budget in `criteria-draft.md`; trim if overshooting.
6. Return `verdict: needs_revision` if the outline turned out to be unworkable mid-draft so the outliner can rerun via the iteration cap.

## Output contract

Write to `.codenook/tasks/<task>/outputs/phase-2-drafter.md`:

```
---
verdict: ok            # or needs_revision / blocked
summary: <=200 chars
---
```

The body holds the full article draft (Markdown).

## Knowledge / skills

Plugin-shipped knowledge: `.codenook/plugins/writing/knowledge/`.
Plugin-shipped skills:    `.codenook/plugins/writing/skills/`.
Workspace-wide:           `.codenook/knowledge/` and `.codenook/skills/` (consume only).
