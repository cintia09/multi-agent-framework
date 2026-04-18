# writing plugin -- changelog

## 0.1.0 -- initial release (M7)

* 5-phase long-form authoring pipeline:
  outline -> draft -> review -> revise -> publish.
* 5 role profiles in `roles/`: outliner, drafter, reviewer, reviser,
  publisher.
* `applies_to: [content, writing]` + `routing.priority: 50` --
  specialised tier alongside `development`. Wins over `generic`
  fallback whenever writing keywords match.
* `criteria-draft.md` + `criteria-revise.md` prompts.
* `validators/post-draft.sh` -- post-condition check on drafter output.
* `knowledge/writing-style.md` plugin-shipped voice + structure +
  length-budget cheat sheet.
* `pre_publish` HITL gate (human-only) before the publisher writes
  anything to disk.
* Manifest exposes both the M2 install-pipeline contract and the v6
  router surface.
