# CodeNook v6 — Conversational Router Agent

> **Status**: Draft (M8.0). Authored 2026 in response to the M3 router-triage / M7
> `router_select.py` shim falling short of the conversational task-creation flow
> the user now requires. This document is the canonical specification for the
> router-agent introduced in milestone **M8**. All M8.1–M8.8 implementation work
> must conform to it.

---

## 1. Motivation

The v6 router as shipped through M7 is a **stateless one-shot CLI**:

- **M3 `router-triage`** picks one phase or one plugin from a single input
  string and exits. There is no notion of conversation, draft, or confirmation.
- **M7 `_lib/router_select.py`** is a scoring shim used by `router-triage`; it
  reads `applies_to / keywords / examples` and returns a verdict. It is also
  one-shot.

Neither component can satisfy the M8 user requirement, which is a
**conversational task-creation flow** with the following properties:

1. **Multi-turn dialog** — the user can refine intent across several turns
   before a task is materialised.
2. **Knowledge-aware** — the router consults workspace knowledge and
   plugin-shipped knowledge to produce a useful first cut.
3. **Draft + confirm** — the router proposes a `draft-config.yaml` for explicit
   user approval before any state is committed.
4. **Parallel tasks** — drafting one task must not block other tasks (existing
   or new) from running.
5. **Clean handoff** — once the user confirms, the router itself materialises
   `state.json` and kicks the first `orchestrator-tick`, after which the
   v6 phase machinery owns the task.
6. **Domain isolation** — the main session must remain domain-agnostic; only
   the router-agent and plugin-side performers may interpret domain artifacts.

The router-agent introduced here is the M8 implementation backbone for the
above. M3 `router-triage` is **removed** in M8.7; M7 `router_select.py` is
**re-purposed** as an internal scoring helper called by the router-agent.

---

## 2. Domain Layering Principle (CRITICAL)

CodeNook v6 is a **four-layer system**. Each layer has a tightly scoped
domain awareness budget.

| Layer | Component | Domain awareness | What it is allowed to read |
|-------|-----------|------------------|----------------------------|
| **Conductor** | Main session (CLAUDE.md / shell.md) | **NONE** — pure protocol + UX | Spawn responses, HITL prompt strings, `router-reply.md` (treated opaquely as a string to relay) |
| **Specialist** | Router agent | **FULL** — picks plugin, builds config, consults knowledge | `plugins/*/plugin.yaml`, `plugins/*/knowledge/`, workspace `knowledge/`, `applies_to / keywords / examples / anti_examples`, plugin scoring helpers |
| **Metronome** | `orchestrator-tick`, `session-resume`, `hitl-adapter` | **NONE** — driven by plugin yaml; opaque state machine | Only `phases.yaml`, `transitions.yaml`, `hitl-gates.yaml`, the active task's `state.json`, plugin role files (passed through to performers) |
| **Performers** | Phase agents (`implementer`, `designer`, `clarifier`, …) | **FULL** — per role | Their role profile + manifest template + acceptance criteria + per-phase artifacts |

### 2.1 Hard rules

These rules are non-negotiable and are enforced by automated checks (see §10):

1. **Main session must NEVER** read `plugins/*/plugin.yaml`, any file under
   `plugins/*/knowledge/`, any file under `.codenook/knowledge/`, or evaluate
   any of the domain fields (`applies_to`, `keywords`, `examples`,
   `anti_examples`, `routing.priority`, plugin ids by name).
2. **Router-agent is the SOLE domain interpreter on the task-creation side.**
   No other component on the creation side may peek at plugin manifests.
3. **`orchestrator-tick`, `hitl-adapter`, `session-resume` are protocol
   surfaces.** The main session may invoke them, but treats their output
   (e.g. tick `status`, HITL prompt strings) opaquely — no parsing of
   domain-specific verdicts, no inspection of phase-internal artifacts.
4. **Plugin / skill discovery from main session is forbidden.** The main
   session only knows that the router-agent skill exists and how to spawn it.
5. **Performers (phase agents) live behind `orchestrator-tick`'s dispatch.**
   Main session never speaks to a performer directly.

### 2.2 Linter

A bats test in M8.6 scans `templates/CLAUDE.md` (and any shipped
`core/shell.md`) for the following forbidden tokens and fails the suite if any
are present outside of comments / verbatim-quote blocks:

```
plugins/                 plugin.yaml             applies_to
keywords:                examples:               anti_examples
knowledge/               phases.yaml             transitions.yaml
hitl-gates.yaml          development             writing
generic                  router_select           plugin_manifest_index
```

(Bare plugin ids are blocked by name; the linter is allow-listed only for the
canonical phrase "the router-agent" and for prose discussing this rule.)

---

## 3. Lifecycle

The router-agent is **stateless across turns**. Continuity comes from
`tasks/<tid>/router-context.md`. Each user turn re-spawns a fresh subagent that
reads the full context, decides, writes a reply, and exits.

```
┌──────────┐                   ┌─────────────────┐                ┌──────────────┐
│   user   │                   │  main session   │                │ router-agent │
└────┬─────┘                   └────────┬────────┘                └──────┬───────┘
     │   "help me build X"              │                                │
     │ ────────────────────────────────►│                                │
     │                                  │ 1. detect "new task" intent    │
     │                                  │ 2. mint T-NNN                  │
     │                                  │ 3. mkdir tasks/T-NNN/          │
     │                                  │ 4. write initial               │
     │                                  │    router-context.md           │
     │                                  │    (frontmatter + first user   │
     │                                  │     turn body)                 │
     │                                  │ 5. acquire router.lock         │
     │                                  │ 6. spawn router-agent          │
     │                                  │ ──────────────────────────────►│
     │                                  │                                │ T1: read context
     │                                  │                                │     read plugin manifests
     │                                  │                                │     read knowledge ToC
     │                                  │                                │     decide: need_more_info
     │                                  │                                │     write router-reply.md
     │                                  │                                │     write/append draft-config.yaml
     │                                  │                                │     update router-context.md frontmatter
     │                                  │                                │     exit {action:"reply"}
     │                                  │◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
     │                                  │ 7. release router.lock         │
     │                                  │ 8. read router-reply.md        │
     │   reply (opaque relay)           │                                │
     │ ◄────────────────────────────────│                                │
     │                                  │                                │
     │   "yes, also include Y"          │                                │
     │ ────────────────────────────────►│                                │
     │                                  │ 9. append user turn to         │
     │                                  │    router-context.md           │
     │                                  │ 10. acquire router.lock        │
     │                                  │ 11. spawn router-agent (T2)    │
     │                                  │ ──────────────────────────────►│
     │                                  │                                │ T2: same loop, refines
     │                                  │                                │     draft-config.yaml
     │                                  │◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
     │              ... iterate ...     │                                │
     │                                  │                                │
     │   "looks good, go"               │                                │
     │ ────────────────────────────────►│                                │
     │                                  │ 12. append user turn           │
     │                                  │ 13. spawn router-agent (Tn)    │
     │                                  │ ──────────────────────────────►│
     │                                  │                                │ Tn: ready_to_handoff
     │                                  │                                │     write final state.json
     │                                  │                                │     (via init-task)
     │                                  │                                │     freeze draft-config →
     │                                  │                                │     state.json.config
     │                                  │                                │     invoke first
     │                                  │                                │     orchestrator-tick
     │                                  │                                │     capture tick status
     │                                  │                                │     exit {action:"handoff",
     │                                  │                                │           task_id, status}
     │                                  │◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│
     │                                  │ 14. enter tick driver loop     │
     │                                  │     (status treated opaquely)  │
     │   first reply from performer     │                                │
     │ ◄────────────────────────────────│                                │
```

### 3.1 Step contract summary

| Step | Owner | What it MUST do | What it MUST NOT do |
|------|-------|-----------------|---------------------|
| 1–4 | Main session | Mint task id, scaffold `tasks/<tid>/`, write initial `router-context.md` with the user's verbatim turn | Read any plugin file or any knowledge file |
| 5 | Main session | Acquire `tasks/<tid>/router.lock` (fcntl, exclusive) | Hold it across user-input boundaries |
| 6 | Main session | Spawn router-agent with input `{task_id}` only | Pass plugin context, knowledge, or hints |
| T1..Tn | Router-agent | Read context, write reply, optionally update draft, optionally hand off | Write to `state.json` except on the handoff turn |
| 7 | Main session | Release lock as soon as subagent exits | Inspect router-reply.md content |
| 8 | Main session | Read `router-reply.md` and relay verbatim | Parse domain fields out of it |
| 14 | Main session | Drive subsequent ticks based on opaque `status` (`advanced` / `waiting` / `done` / `blocked`) | Read `state.json.config` or any phase artifact |

---

## 4. Schemas

All four files live under `tasks/<tid>/`. They are the canonical artifacts that
define a router-agent session. State that does not appear in one of these files
does not exist.

### 4.1 `router-context.md`

YAML frontmatter + markdown chat body. The frontmatter is the source of truth
for router state; the body is the chat log used by the next subagent
invocation to reconstitute conversational context.

**Frontmatter schema** (validated against `_lib/jsonschema_lite.py` rules
shipped in M5):

| Key | Type | Required | Notes |
|-----|------|----------|-------|
| `task_id` | string | yes | Matches `^T-\d{3,}$` (or `T-\d{3,}\.\d+` for subtasks). |
| `created_at` | ISO-8601 string | yes | UTC, second precision. |
| `state` | enum | yes | `drafting` \| `confirmed` \| `cancelled`. |
| `turn_count` | integer | yes | Number of `### user` blocks recorded so far. Increments before each spawn. |
| `draft_config_path` | string \| null | yes | Relative path (typically `./draft-config.yaml`); null until router has produced one. |
| `selected_plugin` | string \| null | yes | Plugin id the router currently intends to use; null until decided. |
| `decisions` | list of records | yes | Append-only audit trail. See below. |
| `last_router_action` | enum \| null | no | `reply` \| `handoff` \| `cancelled`; written by router on exit. |
| `started_at` | ISO-8601 string | yes | Wall-clock start, used for the 30-min cap (§9). |

Each `decisions[]` record:

```yaml
- ts: 2026-05-12T10:14:33Z
  turn: 3
  kind: plugin_pick           # plugin_pick | config_change | knowledge_consult | clarification | handoff | cancel
  detail: "Selected 'development' plugin (confidence 0.88, alternates: writing@0.04)."
```

**Body format**: alternating top-level `### user (<iso-ts>)` and
`### router (<iso-ts>)` headings. Nothing else may appear at heading depth 3.
Within a block, free-form markdown is allowed (code blocks, lists, etc.).

**Complete example**:

```markdown
---
task_id: T-042
created_at: 2026-05-12T10:11:00Z
started_at: 2026-05-12T10:11:00Z
state: drafting
turn_count: 2
draft_config_path: ./draft-config.yaml
selected_plugin: development
last_router_action: reply
decisions:
  - ts: 2026-05-12T10:11:18Z
    turn: 1
    kind: plugin_pick
    detail: "Tentative pick: development (score 0.81 vs writing 0.06 vs generic 0.10)."
  - ts: 2026-05-12T10:11:18Z
    turn: 1
    kind: knowledge_consult
    detail: "Read 3 docs: development/by-topic/cli-style.md, workspace/conventions.md, workspace/testing-policy.md."
  - ts: 2026-05-12T10:13:02Z
    turn: 2
    kind: clarification
    detail: "Asked user to confirm target_dir."
---

### user (2026-05-12T10:11:00Z)

Add a `--tag` filter to the xueba CLI `list` command. It should accept
multiple values (comma-separated) and AND them together.

### router (2026-05-12T10:11:18Z)

I'd like to use the **development** plugin for this task — it matches your
"add CLI flag" intent and there's an existing convention doc for the xueba
CLI in workspace knowledge.

A few quick questions before I draft the task config:

1. Target directory — is this still `~/code/xueba/`?
2. Should I require new tests for the filter (recommended)?
3. Any preference on argparse vs click?

### user (2026-05-12T10:13:02Z)

Yes, `~/code/xueba/`. Yes, require tests. Stay with argparse — that's what
the rest of the CLI uses.

### router (2026-05-12T10:13:18Z)

Got it. I've drafted the task config (see `draft-config.yaml`). Highlights:

- plugin: development
- target_dir: ~/code/xueba/
- dual_mode: false
- max_iterations: 8
- hitl_overrides: { accept: required }

Reply **"go"** to confirm and I'll hand off to the orchestrator. Or tell me
what to change.
```

### 4.2 `draft-config.yaml`

Mirrors the eventual `state.json.config` block exactly, plus a `_draft: true`
sentinel that prevents the orchestrator from ever loading it as if it were
final state.

```yaml
_draft: true
_draft_revision: 3                     # bumped each time router rewrites
_draft_updated_at: 2026-05-12T10:13:18Z

plugin: development                    # plugin id; must be installed
input: |
  Add a --tag filter to the xueba CLI list command.
  Multiple values are comma-separated and AND'd together.
target_dir: ~/code/xueba/              # absolute or ~-prefixed; required when plugin's data_layout=external
dual_mode: false                       # parallel implementer fan-out
max_iterations: 8

models:                                # tier symbols only; literal model ids are forbidden here
  implementer: tier_strong
  reviewer:    tier_balanced
  # router: <not allowed here — see decision #37>

hitl_overrides:
  accept: required                     # 'required' | 'optional' | 'skip'

custom:                                # plugin-specific knobs from config-schema.yaml
  test_runner: pytest
  require_changelog: true
```

**Validation rules** (enforced by `_lib/router_context.py` before a draft is
written):

- `_draft: true` is mandatory.
- `plugin` must resolve to an installed plugin (router-agent has the manifest
  index in scope).
- `models.<role>` values must be tier symbols (`tier_strong` /
  `tier_balanced` / `tier_cheap`); literal model ids are rejected.
- `models.router` is rejected (see decision #37).
- `target_dir` is required iff the chosen plugin declares
  `data_layout: external`.
- Unknown `custom.*` keys are validated against the plugin's
  `config-schema.yaml`.

### 4.3 `router-reply.md`

Plain markdown. The main session reads this file after each spawn and relays
its body verbatim to the user. Optional frontmatter signals what kind of
input the router is awaiting next.

```markdown
---
awaiting: confirmation     # confirmation | clarification | target_dir | cancel_ack | none
---

I've drafted the task config (see `draft-config.yaml`). Reply **"go"** to
confirm or tell me what to change.
```

`awaiting` values:

| Value | Meaning for main session |
|-------|-------------------------|
| `confirmation` | Show reply, wait for user input. |
| `clarification` | Same UX; semantic hint that more turns are expected. |
| `target_dir` | Same UX; main session may show a directory picker. |
| `cancel_ack` | Router has accepted a cancel; main session should NOT spawn again. |
| `none` (or absent) | Default: show reply, wait. |

The frontmatter is a **hint**, not a contract. The authoritative state
remains `router-context.md.state`.

### 4.4 `router.lock`

A standalone file used as the fcntl lock target. While locked, its contents
are JSON metadata describing the holder:

```json
{
  "pid": 84231,
  "hostname": "darwin-laptop",
  "started_at": "2026-05-12T10:13:01Z",
  "task_id": "T-042",
  "purpose": "router-agent-spawn"
}
```

Concurrency semantics in §6.

---

## 5. Router-Agent Prompt Contract

The system prompt the spawned subagent receives **must instruct it to do
exactly the following**, in this order. (The actual prompt template lives in
`skills/codenook-core/skills/builtin/router-agent/prompt.md`, shipped in M8.2.)

1. **Read context** — load `tasks/<tid>/router-context.md` in full
   (frontmatter + body). The body is the conversation history; the
   frontmatter is the latest decisions ledger.
2. **Enumerate plugins** — call `_lib/plugin_manifest_index.py` to obtain a
   compact catalog of installed plugins. The catalog exposes `id`, `summary`,
   `applies_to`, `keywords`, `examples`, `anti_examples`,
   `routing.priority`, `data_layout`, `data_root` (if any), and the path to
   `config-schema.yaml`. Disabled plugins are omitted; `generic` is always
   present last.
3. **Enumerate knowledge** — call `_lib/knowledge_index.py` to obtain a
   ToC of:
     - workspace knowledge (`.codenook/knowledge/**/*.md`)
     - plugin-shipped knowledge for installed plugins
       (`plugins/*/knowledge/**/*.md`)
   The index returns `{path, title, summary, tags, plugin_id?}` records.
   Bodies are fetched on demand via the same helper.
4. **Score and decide** — internally use `_lib/router_select.py` (the
   re-purposed M7 helper) to produce a per-plugin score. The router may
   override the top score based on conversation context.
5. **Branch**:
     - **`need_more_info`**: write `router-reply.md` with `awaiting:
       clarification` (or `target_dir` etc.); update `draft-config.yaml`
       partially if helpful; update frontmatter (`turn_count++`,
       `last_router_action: reply`, append `decisions[]` entries).
     - **`ready_to_handoff` AND user has confirmed in latest user turn**:
       write/finalise `draft-config.yaml`; call `init-task` to materialise
       `state.json` with `phase=null, plugin=<selected>,
       config=<frozen-draft>`; call `orchestrator-tick --task <tid>`
       **once**; capture its stdout `status`; update frontmatter
       (`state: confirmed`, `last_router_action: handoff`); write a final
       `router-reply.md` summarising the handoff.
     - **`cancelled`** (user said cancel / abort): update frontmatter
       (`state: cancelled`, `last_router_action: cancelled`); write
       `router-reply.md` with `awaiting: cancel_ack`; do NOT call
       `init-task`; do NOT write `state.json`.
6. **Always write `router-reply.md`.** Even on handoff. Even on cancel.
7. **Always update frontmatter atomically.** Use the helpers in
   `_lib/router_context.py` (write-temp-then-rename) to avoid partial writes.
8. **Exit with structured JSON on stdout** (newline-terminated, single line):

   ```json
   {"action":"reply","task_id":"T-042","turn":2,"awaiting":"confirmation"}
   {"action":"handoff","task_id":"T-042","turn":3,"tick_status":"advanced","next_phase":"clarify"}
   {"action":"cancelled","task_id":"T-042","turn":4}
   ```

   The main session keys off `action` only. Other fields are advisory.

9. **Forbidden actions** (the prompt must spell these out):
     - Do not write `state.json` except via `init-task` on the handoff turn.
     - Do not call `orchestrator-tick` more than once per spawn.
     - Do not modify any file outside `tasks/<tid>/`, except for the single
       `init-task` invocation on handoff.
     - Do not pull more than **20 knowledge documents** in a single turn
       (see §7).
     - Do not return prose to stdout outside of the final JSON line.

---

## 6. Concurrency Model

### 6.1 Per-task fcntl exclusive lock

The lock target is `tasks/<tid>/router.lock`. It is acquired by the **main
session** before each spawn, and released by the main session as soon as the
subagent exits. The subagent itself does not touch the lock file.

### 6.2 Per-task only

Different tasks have independent lock files, so:

- Two router-agent invocations for the **same** task serialise.
- Two router-agent invocations for **different** tasks run in parallel.
- A router-agent invocation runs in parallel with `orchestrator-tick` for
  any task (including its own — though that will only happen on the handoff
  turn, which is invoked from inside the router-agent itself).

### 6.3 Stale lock recovery

The lock file's JSON payload (§4.4) includes `pid`, `hostname`, and
`started_at`. The main session attempts the following before giving up on a
contended lock:

1. Try `flock(LOCK_EX | LOCK_NB)`.
2. If it fails, read the JSON payload.
3. If `started_at` is older than the **stale threshold** AND `pid` is not
   alive on `hostname` (current host only), force-release: unlink the
   lock file, retry once.
4. Otherwise wait up to a small grace window (default 2s) and retry.

**Stale threshold is pinned at 300 seconds (5 minutes)** for M8 — long
enough for a slow LLM-driven turn, short enough that crashed sessions
recover within one user round-trip. Configurable later via
`config.yaml.router.lock_stale_seconds`.

### 6.4 Main session must wait

The main session **must not** spawn a new router-agent for a task while its
lock is held. There is no queuing built into the lock; if the main session
needs to handle a second user turn for the same task, it waits on
`flock(LOCK_EX)` (blocking) up to a per-turn budget (default 60s), then
surfaces an error to the user (§9).

---

## 7. Knowledge Access

### 7.1 What the router may read

| Source | Path | Notes |
|--------|------|-------|
| Workspace knowledge | `.codenook/knowledge/**/*.md` | Always in scope. |
| Plugin-shipped knowledge | `plugins/<p>/knowledge/**/*.md` | Only for plugins currently installed. Plugins listed in `config.yaml.plugins.disabled` are excluded. |

`memory/<plugin>/` (the distiller's per-plugin output) is **NOT** loaded by
the router-agent in M8 — that store is owned by performers, and pulling it
into routing risks polluting routing decisions with task-execution detail.
This restriction may be relaxed in a future milestone.

### 7.2 Index helper

`_lib/knowledge_index.py` returns:

```python
[
  {"path": ".codenook/knowledge/conventions.md",
   "title": "Workspace conventions",
   "summary": "Project-wide style and process rules.",
   "tags": ["style", "process"],
   "plugin_id": null},
  {"path": "plugins/development/knowledge/cli-style.md",
   "title": "CLI flag conventions",
   "summary": "Long flags use --kebab-case; short flags reserved for the top 8.",
   "tags": ["cli", "argparse"],
   "plugin_id": "development"},
  ...
]
```

Bodies are fetched on demand via `knowledge_index.read(path)` to keep the
ToC scan cheap.

### 7.3 Per-turn cap

A router-agent invocation may load at most **20 knowledge documents** (full
bodies) per turn. The cap exists to bound subagent context growth and to
prevent pathological "read everything" behaviour. The cap is enforced by
`_lib/knowledge_index.py` (it raises after the 20th body fetch) and also
spelled out in the prompt contract (§5, item 9). It is configurable later
via `config.yaml.router.knowledge_max_per_turn`.

ToC entries themselves are not counted against the cap.

---

## 8. Handoff Protocol

The handoff is the **only** turn on which the router-agent crosses the line
from drafting to materialising state. It is also the only turn on which it
invokes any other skill.

### 8.1 Steps performed by the handoff-turn router-agent

1. Final-pass validate `draft-config.yaml` (schema + plugin-side
   `config-schema.yaml`).
2. Strip the `_draft*` keys from the draft → call `init-task --task <tid>
   --plugin <p> --config <path-to-frozen-config>`. `init-task` writes
   `tasks/<tid>/state.json` with `phase: null, plugin: <p>, config: …,
   created_at, status: "ready"`.
3. Update `router-context.md` frontmatter:
   `state: confirmed`, `last_router_action: handoff`,
   append `decisions[]` entry kind `handoff`.
4. Invoke `skills/codenook-core/skills/builtin/orchestrator-tick/tick.sh
   --task <tid>` **exactly once**.
5. Capture the tick's stdout — specifically the `status` field
   (`advanced` | `waiting` | `done` | `blocked`) and any `next_phase`.
6. Write `router-reply.md` with a brief handoff summary
   (`awaiting: none`).
7. Exit with:

   ```json
   {"action":"handoff","task_id":"T-NNN","turn":<n>,"tick_status":"<s>","next_phase":"<phase|null>"}
   ```

### 8.2 What the main session does next

The main session sees `action: handoff` and:

1. Releases the router lock.
2. Relays the `router-reply.md` body to the user.
3. Enters the **tick driver loop** for this task. The driver:
   - On every subsequent main-session turn that is "about" this task
     (signalled by user input or by the queue scheduler), invokes
     `orchestrator-tick --task <tid>` and acts on the opaque `status`.
   - **Never** opens `state.json`, `tasks/<tid>/config`, or any phase
     artifact directly. All it sees is the tick summary and the HITL prompts
     it must relay.

After handoff the router-agent is **done** with this task. It is not
re-spawned for the same task again unless the task is explicitly reset
(out of scope for M8; see §11).

---

## 9. Termination Conditions

| Condition | Detected by | Result |
|-----------|-------------|--------|
| User confirms (e.g. "go", "yes do it") | Router-agent (semantic) | Handoff (§8). |
| User cancels (e.g. "never mind") | Router-agent (semantic) | `state: cancelled`; `state.json` is **not** written; `router-reply.md` confirms. Main session shows reply, drops the task scaffold from active set. |
| Turn cap reached | Main session checks `turn_count` after each spawn | Default cap **20 turns**. Router writes a final reply (`awaiting: cancel_ack`) explaining the cap; main session asks user to reset (delete `tasks/<tid>/`) or rephrase from scratch. Configurable via `config.yaml.router.max_turns`. |
| Time cap exceeded | Main session checks `now() - frontmatter.started_at` before each spawn | Default cap **30 minutes** from first turn. Same UX as turn cap. Configurable via `config.yaml.router.max_wallclock_minutes`. |
| Lock acquisition timeout | Main session, when `flock` exceeds per-turn budget (60s) | Surface error to user; do not spawn. User may retry. |
| Subagent crash / non-zero exit / no JSON on stdout | Main session | Release lock; surface error; do not advance `turn_count`; the conversation can be retried. |

Cap defaults are non-binding for the spec doc — the M8.2 implementation
may tune them, but they MUST be configurable and they MUST default to values
no looser than those listed here.

---

## 10. Removal of router-triage

M3 `router-triage` is **replaced** by router-agent. Migration:

| Item | Action |
|------|--------|
| `skills/codenook-core/skills/builtin/router-triage/` | Deleted in M8.7. |
| `tests/m3-router-triage.bats` | Deleted in M8.7. |
| External consumers | NONE outside docs. `orchestrator-tick` does not import `router-triage`; nothing in `init.sh` calls it after M8.5. |
| `_lib/router_select.py` (M7) | **Repurposed** as an internal scoring helper of the router-agent. No longer a public skill. Its CLI entry (if any) is dropped; only the Python API survives. |
| `history/router-decisions.jsonl` | Continues to be written, but by the **router-agent** (not by main-session post-confirm). Schema gains a `turn` field and `kind: handoff|cancel` records. |
| Architecture §4 | Updated to point at this document; the catalog-scan paragraphs (§4.1) become a sub-bullet under §5 of this doc. |

The CLAUDE.md / shell.md template is updated in M8.6 to remove every mention
of `router-triage` and replace it with the spawn protocol for `router-agent`.

---

## 11. Open Items (Defer to Implementation)

The following are intentionally not pinned in M8.0. They are flagged here so
that M8.1–M8.8 owners do not silently re-litigate them.

1. **Subagent dispatch portability.** Claude Code uses the Task tool;
   Copilot CLI uses its own task tool; a plain shell host would need a
   third adapter. M8.2 must define a `dispatch_subagent.sh` abstraction with
   per-host adapters. The router-agent skill itself must remain
   dispatch-agnostic.
2. **Knowledge ToC caching.** `_lib/knowledge_index.py` currently rescans on
   every call. If router latency suffers, a workspace-level cache keyed on
   `mtime` snapshots may be added. Defer until M8.8 measurements.
3. **Router-agent token budget enforcement.** §7's per-turn knowledge cap is
   one bound. We may also want a hard cap on total tokens consumed per turn
   (prompt + completion). Mechanism TBD — likely a wrapper in
   `dispatch_subagent.sh` that aborts on overrun.
4. **Task reset / re-router.** What happens if a confirmed task needs to
   re-enter routing (e.g. user changes plugin mid-task)? Out of scope for
   M8; M9+ may introduce an explicit `router-agent --reset` flow.
5. **Multi-router collaboration / router learning.** Out of scope (see
   plan.md "Out of scope").
