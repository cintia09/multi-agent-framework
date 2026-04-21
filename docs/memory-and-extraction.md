# Memory & Extraction (v0.14.0)

How CodeNook persists what tasks learn, after the v0.14.0 deletion
of the `task_specific` extraction route.

---

## §1. Two stores only

After `77cc637` (refactor: drop `task_specific` route; add
`memory/index.yaml` exporter), the workspace has **exactly one
persistent destination** for extracted artefacts:
`<ws>/.codenook/memory/`. The per-task `extracted/` directory
still exists in the schema but is no longer written to by the
extractors.

```
<ws>/.codenook/memory/
├── skills/<name>/SKILL.md      (procedural — runnable capabilities)
├── knowledge/<topic>.md        (declarative — decisions, conventions, env notes)
├── configs/<entry>.md          (config decisions — schema-bound)
├── index.yaml                  (human-readable inventory; regenerated on every write)
└── .index-snapshot.json        (machine cache — mtime-keyed, gitignored)
```

- **`memory/skills/`** — procedural. One directory per skill,
  containing a `SKILL.md` frontmatter manifest and an entrypoint.
  See [`skills-mechanism.md`](skills-mechanism.md).
- **`memory/knowledge/`** — declarative. One markdown per topic,
  frontmatter-keyed. Read by future role agents to avoid
  re-deriving decisions made in earlier tasks.
- **`memory/configs/`** — config decisions tied to the workspace
  config schema (e.g. preferred test runner, default branch
  strategy). Optional; only written when `config-extractor` finds a
  ratifiable change.

---

## §2. The `extractor-batch` protocol

`extractor-batch.sh` is the single dispatcher. Tick fires it
automatically after every consumed phase output, and the conductor
fires it manually on context-pressure.

**Signature**:

```bash
extractor-batch.sh \
  --task-id T-NNN \
  --reason {after_phase | context-pressure | manual} \
  --workspace <ws> \
  [--phase <phase-id>]
```

**Behaviour**:

- Best-effort + idempotent on `(task_id, phase, reason)`. Exit 0
  except on argument-parse error.
- Fans out three sub-extractors in parallel:
  `knowledge-extractor`, `skill-extractor`, `config-extractor`.
  Each is invoked with the same task / phase / workspace context.
- Returns a single JSON object on stdout:
  `{"enqueued_jobs": [...], "skipped": [{"name": ..., "reason": ...}]}`.
- For `--reason context-pressure`, the call is **non-blocking**:
  the dispatcher backgrounds the sub-extractors and returns within
  ≤200 ms wall-clock so the conductor can act on the watermark
  without losing turn time.

---

## §3. The three extractors

Each extractor is a `skills/builtin/<name>-extractor/` skill with
its own `SKILL.md`. They share the same patch-or-create flow:
**secret-scan → hash dedupe → similarity check → LLM judge →
write/patch → index.yaml regen → audit-log line**.

| Extractor | Looks for | Writes to | Frontmatter it emits |
|-----------|-----------|-----------|----------------------|
| `knowledge-extractor` | Declarative claims, decisions, conventions, environment notes in the phase output. | `memory/knowledge/<topic>.md` | `topic`, `source_task`, `source_phase`, `tags`, `hash`, `version`. |
| `skill-extractor` | Repeated CLI/script invocations (≥3 in the phase). One candidate per task. | `memory/skills/<name>/SKILL.md` (+ entrypoint) | `name`, `version`, `source_task`, `source_phase`, `hash`, `tags`. |
| `config-extractor` | Config decisions that fit the workspace `config-schema.yaml`. | `memory/configs/<entry>.md` | `entry`, `schema_path`, `value`, `source_task`, `source_phase`, `hash`. |

**Dedupe**: each candidate's hash (sha-256 of the canonical body) is
checked against `.index-snapshot.json`. Exact match = skip; near
match (cosine ≥ 0.85 over the body or LLM-judged equivalent) = patch
the existing entry; otherwise = create.

**Per-phase caps**: 1 skill, 5 knowledge entries, 3 config entries.
Caps are enforced inside the extractor; the dispatcher only sees the
final write/skip count.

---

## §4. `memory/index.yaml`

Regenerated on every memory write or delete by
`memory_index.regenerate()`. Schema:

```yaml
version: 1
generated_at: "2026-04-21T13:00:00Z"
knowledge:
  - topic: jwt-rotation-policy
    path: knowledge/jwt-rotation-policy.md
    source_task: T-031
    source_phase: design
    hash: a8b7…
    digest: "JWT rotation policy: 24h access + 7d refresh, rotate on use"
    tags: [security, auth]
skills:
  - name: run-pytest-with-coverage
    tier: extracted
    path: skills/run-pytest-with-coverage/SKILL.md
    source_task: T-042
    source_phase: test
    hash: 3c1f…
    digest: "Run pytest with coverage report on the src tree"
configs:
  - entry: default-test-runner
    path: configs/default-test-runner.md
    value: pytest
    source_task: T-042
    source_phase: test
    hash: 9d11…
```

**Lifecycle**:

- Created on first memory write.
- Rewritten atomically on every write or delete.
- Read by the conductor (memory-awareness step in the bootloader)
  and by role agents that ask "what does the workspace already
  know?". They never glob `memory/**/*.md` directly.
- Excluded from `.index-snapshot.json` regeneration so the index
  itself does not interfere with hash dedupe.

---

## §5. The context-pressure path

The conductor heuristically estimates its own context usage every
turn (CJK 1:1, ASCII 1:4). At the 80 % model-window watermark, the
bootloader instructs the conductor to:

1. **Stop new feature work** — no new sub-agent dispatches; no new
   reads.
2. **Sediment** — for every active task id, call
   ```bash
   extractor-batch.sh --task-id <T-NNN> --reason context-pressure --workspace <ws>
   ```
   This dispatches the three extractors **asynchronously** in a
   subprocess and returns within ≤200 ms. The returned JSON
   envelope contains `enqueued_jobs`.
3. **Compact or reset** — the conductor decides whether to
   `/clear` or `/compact` based on `enqueued_jobs.length` and the
   user's preference. After the reset, the next session reads
   `memory/index.yaml` and `state.json` and resumes from those — no
   context loss.

The conductor is **not allowed** to read `memory/**` directly during
the watermark protocol; it only uses the JSON envelope and the
index file. Full bootloader contract: see top-level
`CLAUDE.md` injected by `claude_md_sync.py`.

---

## §6. `extraction-log.jsonl`

Append-only audit log at `<ws>/.codenook/extraction-log.jsonl`. One
line per memory write or skip. Format:

```json
{"ts": "2026-04-21T13:01:23Z", "task": "T-042", "phase": "test",
 "extractor": "skill", "action": "create",
 "path": "memory/skills/run-pytest-with-coverage/SKILL.md",
 "hash": "3c1f…", "reason": "after_phase"}
```

`action` ∈ `create | patch | dedupe-skip | secret-block | error`.

The log is the **only** authoritative record of memory provenance.
Both `memory/index.yaml` and `.index-snapshot.json` are reproducible
from the file tree; the log is not. Treat it as append-only and
include it in workspace backups.

---

## §7. What was removed in v0.14.0

Historical note for upgraders.

Pre-v0.14.0, every extractor had **two destinations**: cross-task
(`memory/`) and task-specific (`tasks/<T>/extracted/`). The
`extraction_router` LLM call decided per artefact which one to
write to.

In `77cc637` the `task_specific` route was deleted entirely:

- The `extraction_router.py` call is kept as a thin compatibility
  shim that always returns `cross_task` (slated for full removal in
  a follow-up refactor).
- The `write_*_to_task` helpers in each extractor were deleted.
- `tasks/<T>/extracted/` is no longer written to. The directory
  still appears in the workspace schema for back-compat with
  pre-v0.14.0 task trees, but extractors never touch it.
- The `TC-ROUTE-01` test (which exercised the routing decision) was
  deleted.

Rationale: every artefact emitted in any recent task was being
routed to `cross_task` anyway; the routing decision added an LLM
round-trip and a second write target with no observed benefit. The
new `memory/index.yaml` exporter (added in the same commit) gives
conductors a cheaper way to discover what the workspace already
knows, which was the primary use-case the per-task route had been
serving.

---

## 8. `find_relevant()` and `{{KNOWLEDGE_HITS}}` (v0.22.0+)

Kernel-side knowledge auto-injection lives in
`skills/codenook-core/skills/builtin/_lib/knowledge_query.py`. It
turns the inert `<ws>/.codenook/memory/index.yaml` (built by the
v0.21.0 reindexer) into ranked context that ships inside every
dispatched phase prompt.

### API

```python
from knowledge_query import find_relevant

hits = find_relevant(
    workspace,           # Path to <ws> (parent of .codenook)
    query,               # free-form text  usually task.input
    role=None,           # optional dispatched role name; folded in
    phase_id=None,       # optional phase id; folded in
    plugin=None,         # optional plugin pin; entries with this
                         #   plugin id get a +1 scoring bias
    top_n=8,             # cap on returned hits
)
# -> [{"path","summary","tags","plugin","score","reason"}, ...]
```

Pure read; never raises; idempotent. When `index.yaml` is missing
the function falls back to a transient
`knowledge_index.aggregate_knowledge` scan over installed plugins.

### Scoring

Each query token (lowercase,  2 chars, deduped) contributes:

| Source                           | Weight |
|----------------------------------|--------|
| Tag substring/word/exact match   | 3     |
| Summary substring                | 1     |
| Path-segment substring           | 0.5   |

Plugin pin (`plugin=` matches the entry's `plugin`) adds a one-time
+1 bias. Hits are sorted by `(-score, plugin, path)` for
deterministic tie-breaking. Each hit carries a `reason` string that
explains the dominant contributors so prompts can show users *why*
an entry was selected.

### `{{KNOWLEDGE_HITS}}` placeholder

Plugin manifest templates may include the literal token
`{{KNOWLEDGE_HITS}}`. At dispatch time the kernel substitutes it
with a markdown bullet list of the top-N hits. Substitution happens
in two parity-locked spots:

1. `skills/codenook-core/skills/builtin/orchestrator-tick/_tick.py`
    inside `_render_phase_prompt`, alongside `{{TASK_CONTEXT}}`.
2. `skills/codenook-core/_lib/cli/cmd_tick.py` 
   `_augment_envelope` re-renders the same prompt file before
   returning the JSON envelope to the conductor, so the file the
   conductor loads is always fully substituted.

Templates without the placeholder are returned unchanged  full
backward compatibility for plugins that opt out.

The query the kernel builds is `task.task_input + state.keywords`.
Role and phase id are passed through the dedicated function args so
they are weighted into the token soup without needing the plugin
template author to interpolate them by hand.

### Config

`<ws>/.codenook/config.yaml` may carry:

```yaml
knowledge_hits:
  top_n: 8     # default; override per workspace
```

Read via `knowledge_query.resolve_top_n(workspace, default=8)`.
Invalid / missing values fall back to the supplied default.

### Empty-state UX

When `find_relevant` returns zero hits, the rendered block reads:

> _No matches found in index.yaml. Run `codenook knowledge reindex`
> if you expected hits._

This nudges users toward the reindex CLI when their plugin ships
knowledge but the workspace's index hasn't been refreshed.
