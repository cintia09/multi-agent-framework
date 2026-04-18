# writing plugin

A v6 CodeNook plugin that drives long-form authoring tasks through a
5-phase pipeline:
**outline -> draft -> review -> revise -> publish**.

## Pinned design

The M7 task prompt and `docs/v6/implementation-v6.md` §M7.2 (L869-875)
disagree on naming. We pin to the **task prompt**:

- Phases: `outline / draft / review / revise / publish`
- Roles:  `outliner / drafter / reviewer / reviser / publisher`

Divergences from the spec (documented inline in `phases.yaml`):

1. Spec lists `edit` as the third phase. We split into a dedicated
   `review` phase (pure critique) and a dedicated `revise` phase
   (apply the critique). This gives the orchestrator a tighter
   feedback loop and lets the iteration cap apply per-phase.
2. Spec sets `publish.role: null` and relies entirely on the
   `pre_publish` HITL gate. We add a real `publisher` role so
   `orchestrator-tick` has something to dispatch and the E2E mock
   can drive the task to `complete`. The `pre_publish` gate is
   preserved.

`routing.priority: 50` -- specialised tier, same as `development`. The
M7 router_select shim picks `writing` over `generic` whenever the user
input contains writing keywords (`article`, `blog`, `essay`, ...).

## Layout

```
plugins/writing/
  plugin.yaml            # M2 install manifest + v6 router surface
  config-defaults.yaml   # tier_* model defaults + pre_publish HITL gate
  config-schema.yaml     # M5 config-validate DSL fragment
  phases.yaml            # 5 phase entries
  transitions.yaml       # ok / needs_revision / blocked table
  entry-questions.yaml   # outline requires `title`; rest are open
  hitl-gates.yaml        # pre_publish (human-only)
  roles/                 # 5 role profiles
  manifest-templates/    # 5 phase-N-<role>.md dispatch templates
  validators/            # post-draft.sh
  prompts/               # criteria-draft.md, criteria-revise.md
  knowledge/             # writing-style.md
  examples/              # blog-post/seed.json
```

## Verdict contract

```
---
verdict: ok            # or needs_revision / blocked
summary: <=200 chars
---
```

`orchestrator-tick.read_verdict` reads only this; the body is for
humans (and the distiller).
