#!/usr/bin/env python3
"""Idempotently sync the CodeNook bootloader block in a workspace CLAUDE.md.

Wraps the bootloader between explicit ``<!-- codenook:begin -->`` and
``<!-- codenook:end -->`` markers. Re-running replaces the block in
place; user content outside the markers is never touched. When no
CLAUDE.md exists, a stub is created containing only the block.

Used by the top-level ``install.py`` (DR-006).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BEGIN = "<!-- codenook:begin -->"
END = "<!-- codenook:end -->"


def _render_seed_line(plugins: list[str]) -> str:
    if not plugins:
        return ""
    if len(plugins) == 1:
        names = f"**{plugins[0]}**"
        verb = "Workspace has plugin installed:"
    else:
        names = ", ".join(f"**{p}**" for p in plugins)
        verb = "Workspace has plugins installed:"
    return (
        f"{verb} {names} "
        f"(the conductor picks one per task via `task new --plugin <id>`).\n\n"
    )


def render_block(version: str, plugin) -> str:
    if isinstance(plugin, str):
        plugins = [plugin] if plugin else []
    elif plugin is None:
        plugins = []
    else:
        plugins = [p for p in plugin if p]
    seed_line = _render_seed_line(plugins)
    return rf"""{BEGIN}
<!-- DO NOT EDIT BY HAND. Managed by `python install.py`. To remove this block,
     re-run install.py with --no-claude-md and delete the markers manually. -->

## CodeNook v{version} bootloader

{seed_line}CodeNook is a multi-agent task orchestrator. The LLM (you) acts as a
**pure conductor**: when the user asks for a CodeNook task, you hand
the work off to the orchestrator and relay its messages verbatim. You
do **not** decide on your own whether something should become a task.

### When to start a CodeNook task (explicit user trigger only)

Start a task **only** when the user explicitly asks for one. Recognise
phrases such as:

- "open / start / new / create a codenook task"
- "use codenook to …"
- "走 codenook 流程", "用 codenook 做", "新建 codenook 任务",
  "开个 codenook 任务", "交给 codenook"

If the user just asks a question or asks you to do something **without**
mentioning codenook, answer normally — do not auto-spawn a task. When
unsure, ask the user whether they want a CodeNook task instead of
guessing.

### Invoking the orchestrator (env-portable form)

**Always use the `.codenook/bin/codenook` CLI wrapper.** Do **not** call
the underlying kernel scripts (under
`.codenook/codenook-core/skills/builtin/`) directly — they are private
implementation details and may be renamed or replaced across kernel
upgrades. The wrapper auto-discovers a working `python3` (and Git-for-
Windows bash on Windows when the kernel still needs it internally) so
the same CLI works identically on macOS, Linux, and Windows.

**Per-shell invocation form** (replace `<codenook>` in every example
below with the form for your host shell):

| Host shell        | `<codenook>` expands to                |
|-------------------|----------------------------------------|
| bash / zsh / sh   | `.codenook/bin/codenook`               |
| PowerShell / cmd  | `.codenook\bin\codenook.cmd`           |

On Windows, do **not** spend time hunting for `bash.exe` or installing
python — if the wrapper can't find them it will print a clear error
pointing to the fix. Just call the wrapper and surface its output. On
Linux/macOS the script is a plain bash CLI; both `bash` and `python3`
are expected on `PATH` already.

### How to start a task

The wrapper allocates the next `T-NNN-<slug>` for you (the slug is
auto-derived from `--input`; empty input falls back to plain
`T-NNN`). **Do not** scan `.codenook/tasks/` and increment ids by
hand.

The flow is **conductor-driven plugin selection** → `task
new --plugin <id>` → `tick`. The conductor (you) reads the user's
intent, picks the best-matching plugin, and creates the task with
`--plugin` set explicitly.

**Mandatory boot ritual (do this once per session, before any
CodeNook action):**

The first time the user mentions CodeNook in a session — or any
time you are about to invoke a `<codenook>` subcommand and you
have NOT yet loaded the workspace inventory in this conversation
— you MUST first read **all** of the following in one batch:

1. `.codenook/state.json` — kernel version + installed plugin ids
2. `.codenook/plugins/<id>/plugin.yaml` for every id in (1)
3. `.codenook/memory/index.yaml` — the workspace knowledge +
   skill inventory (a few KB; cheap)
4. `<codenook> status` — active tasks (phase / status / model /
   exec mode for each)

These four sources together are typically <15 KB and give you
everything needed to: (a) recognise existing tasks the user may
be referring to, (b) match the user's request to the right
plugin, (c) surface relevant prior knowledge. Skipping this
ritual leads to the conductor inventing tasks that already
exist, picking the wrong plugin, or missing applicable memory
— do not skip it. Cache the result for the rest of the session;
re-read only when the user signals "something changed" (new
install, new task, new memory entry).

**What the conductor reads when picking a plugin / starting a task:**

- `.codenook/state.json` — `installed_plugins` field is the
  authoritative list of plugin ids in this workspace. Read this
  first; do not rely on globbing.
- `.codenook/plugins/<id>/plugin.yaml` — for each id from
  `state.json`, read the manifest and look at the match fields
  (which use-cases / keywords / examples). Rank against the
  user's request and pick one. If two tie or none fits, ask.
- `.codenook/memory/index.yaml` — generated inventory of every
  knowledge entry and workspace-shared skill in this workspace
  (topic / name, summary, tags, status, path). Read this first
  to discover what's available; then `view` the specific entries
  by their `path` only when you actually need their full body.
  Treat skill entries as first-class skill candidates — rank
  them next to plugin `available_skills:` entries when the
  user's request matches.
- `.codenook/memory/history/` and `.codenook/memory/_pending/` —
  prior task summaries and draft notes. Useful when the user
  references "last time" or wants to continue earlier work.
- `.codenook/memory/config.yaml` — workspace-level overrides
  (default plugin, dual_mode, target_dir, etc.) — honour these
  when the user did not state otherwise.

**Discovering existing tasks (do NOT glob `.codenook/tasks/`):**

- Always run `<codenook> status` (no arguments) to enumerate every
  active task — it prints task ids, current phase, status, and the
  resolved model + execution mode for each. Many host runtimes
  (Claude Code, etc.) ignore dot-directories in their default
  `glob` filter, so `glob ".codenook/tasks/*/state.json"` will
  silently return zero results even when tasks exist; the CLI
  is the only reliable discovery surface.
- For a single task's full state, run `<codenook> status --task
  T-NNN` (prints the rendered state.json).
- Only fall back to reading `.codenook/tasks/T-NNN/state.json`
  directly when the CLI is unavailable for some reason.

The conductor MAY read these files freely. They are workspace-
shared resources, not phase outputs. The "zero domain budget"
hard rules below restrict only state mutation and per-phase
artifact interpretation, not orientation reads.

```bash
# 1. Pick a plugin. Read `.codenook/state.json` `installed_plugins`
#    for the authoritative id list, then read each
#    `.codenook/plugins/<id>/plugin.yaml`. Skim
#    `.codenook/memory/index.yaml` for the available memory
#    entries. Rank candidates
#    against the user request, choose the best fit. If two tie or
#    none fits well, ask the user which one.
#
# 2. Pre-task interview (mandatory, ~2-4 questions). Before
#    creating the task, ask the user 2-4 short clarifying
#    questions via your `ask_user` tool to gather concrete
#    context. The exact questions depend on the chosen plugin —
#    look at the plugin's first phase (typically `clarify`,
#    `outline`, or `intake`) and ask what its role would
#    otherwise need to ask. Aim for: scope, audience / target,
#    style / constraints, and any inputs the user already has.
#    Concatenate the answers (one Q+A per line) into a single
#    multi-line string — that becomes --input. Skip ONLY when
#    the user explicitly says "just go" / "你看着办" / passes a
#    pre-filled brief.
#
# 3. Create the task. Pass --plugin explicitly. --title is a
#    short label for filesystem / UI use (drives the task-id
#    slug). --summary carries the user's verbatim original
#    request. --input carries the gathered interview answers
#    (richer context the first role consumes). --accept-defaults
#    fills dual_mode/priority/target_dir with sane values so no
#    entry-question gate fires. Returns the new T-NNN-<slug> on
#    stdout (slug derived from --title → --input (single-line) →
#    --summary in that order; multi-line --input is skipped to avoid
#    meaningless concatenated slugs; CJK preserved).
<codenook> task new --title "<short title>" \
                    --summary "<verbatim user request>" \
                    --input "<multi-line interview answers>" \
                    --plugin <chosen-plugin-id> \
                    --accept-defaults

# 4. Drive the tick loop. Each call advances at most one phase and
#    returns a JSON envelope with the new status.
<codenook> tick --task <T-NNN> --json
```

Loop step 4 on `status: advanced`. Stop on `done` / `blocked` and
report verbatim. On `waiting`, scan `.codenook/hitl-queue/*.json`
for entries with `decision == null`, relay each `prompt` field
verbatim to the user, capture the answer, then:

```bash
<codenook> decide --task <T-NNN> --phase <phase-or-gate-id> \
                  --decision <approve|reject|needs_changes> \
                  [--comment "..."]
```

The `--phase` flag accepts **either** the phase id from `phases.yaml`
(e.g. `clarify`, `design`, `plan`) **or** the gate id from the queue
entry (e.g. `requirements_signoff`, `design_signoff`). The CLI maps
phase → gate via the plugin's `phases.yaml`. When the phase has no
`gate:` field declared, fall back to passing the gate id directly.

Resume the tick loop when all gates resolve.

### The dispatch envelope

When `tick --json` returns and CodeNook has dispatched a phase agent
(clarifier, designer, implementer, tester, reviewer, …), the JSON
includes an **`envelope`** object with the fields you need to do the
LLM round-trip yourself:

```json
{{"status": "advanced",
 "next_action": "dispatched clarifier",
 "dispatched_agent_id": "ag_T-001_clarify_1",
 "envelope": {{
   "action": "phase_prompt",
   "task_id": "T-001", "plugin": "development",
   "phase": "clarify", "role": "clarifier",
   "system_prompt_path": ".codenook/plugins/development/roles/clarifier.md",
   "prompt_path":        ".codenook/tasks/T-001/prompts/phase-1-clarifier.md",
   "reply_path":         ".codenook/tasks/T-001/outputs/phase-1-clarifier.md"
 }}}}
```

Protocol:

1. **Read `system_prompt_path`** (when present, role profile) and
   **`prompt_path`** (always present, the per-call instructions).
2. **Dispatch a sub-agent** via your host's sub-agent / Task facility,
   *except* when `role == "clarifier"` — see special case below.
   Use `system_prompt_path`'s contents as the system prompt and
   `prompt_path`'s contents as the user message. The sub-agent must
   write its complete response to the file at `reply_path`
   (overwriting any prior content, including required frontmatter).
3. **Loop back to `tick`** — the next tick consumes `reply_path`
   and either advances to the next phase (returning a new envelope)
   or reports `done` / `blocked`.

**Special case — `role == "clarifier"` runs INLINE:** clarify is
fundamentally "conductor talks to the user to extract requirements".
The conductor (you) is already in dialog with the user, so spawning
a fresh sub-agent (new context window, role/knowledge re-load,
extra LLM round-trip — typically 30-60s) is wasteful. For clarifier
envelopes:

  a. Read `system_prompt_path` (clarifier role) and `prompt_path`
     (per-call instructions) yourself.
  b. Conduct the Q&A with the user inline, in this session, using
     `ask_user` for each question; iterate until clarifier criteria
     are met.
  c. Write the final clarifier output (frontmatter + body, exactly
     as a sub-agent would have produced) to `reply_path`.
  d. Call `tick` again to advance the phase.

Do **not** dispatch a sub-agent for clarifier. Other phase roles
(designer, planner, implementer, tester, acceptor, reviewer,
validator) continue to dispatch as in step 2 — they do real
phase work that benefits from a dedicated context window.

If your host has no sub-agent facility, you may process *any*
prompt inline using the same write-to-`reply_path`-then-tick
pattern.

When `tick --json` returns **without** an `envelope` field, just
inspect `status`:

- `advanced` — phase done, transition fired; loop on `tick` again.
- `waiting` — sub-agent still expected; either dispatch it (per the
  envelope from the prior tick) or wait for an external signal.
- `done` / `blocked` — terminal; report `next_action` /
  `message_for_user` verbatim.

On `tick --json` returning `waiting`, you may also need to clear
an HITL gate. Scan `.codenook/hitl-queue/*.json` for entries with
`decision == null`. For each open entry:

1. **MANDATORY channel-choice ask.** Issue exactly one `ask_user` with
   two choices: `terminal` (default) and `html`. Treat any answer other
   than `html` as `terminal`.

2. **Render & relay according to the chosen channel:**

   - `terminal`: read the gate prompt and the role's primary output
     file (paths come from the gate JSON). Output the content as
     your **normal markdown response** in the chat — do NOT put it
     inside the `ask_user` modal (modals don't render markdown).
     Then issue a follow-up `ask_user` to collect approve/reject and
     an optional comment.

   - `html`: produce a self-contained, styled HTML page in your reply
     code/canvas, write it to `.codenook/hitl-queue/<eid>.html`
     (atomic write), then shell out to open it in the browser:
     ```
     start "" "<full path>"   (Windows)
     open "<full path>"        (macOS)
     xdg-open "<full path>"    (Linux)
     ```
     Then issue an `ask_user` to collect the decision.

3. **Submit the decision** (use the same form as the post-phase
   `<codenook> decide` above so the conductor only ever needs one
   verb — the helper auto-derives `--id` from the gate metadata
   when only `--task` + `--phase` are supplied):
   ```bash
   <codenook> decide --task <T-NNN> --phase <phase-or-gate-id> \
                     --decision <approve|reject|needs_changes> [--comment "..."]
   ```
   The legacy `<codenook> hitl decide --id <eid> --decision ...`
   form still works (and is what the kernel writes through to)
   but is no longer the recommended surface.

Resume the tick loop when all gates resolve.

### Model selection in dispatch envelope

When `tick --json` returns a phase-dispatch envelope, it MAY
include an optional `"model"` field (e.g. `"claude-opus-4.7"`).

When the field is present, you MUST pass that exact string as the
`model:` parameter when dispatching the phase sub-agent via your
task tool. Do not substitute, prefer, or omit the value — pass it
through verbatim.

When the field is absent, dispatch with no `model:` parameter
(use your tool's platform default).

**Pre-flight ask (v0.25.1+) — MANDATORY when model is unresolved.**
Before dispatching a sub-agent for any envelope where the `model`
field is **absent**, **null**, **empty**, or where `codenook status`
shows `model=<default>` / `model=<unknown>` for this task, you MUST
issue exactly one `ask_user` first:

> "About to dispatch <role> as a background sub-agent for <task_id>
> phase <phase>. No model is configured for this task (status shows
> `<default>`). Pick a model — or hit Enter to use your platform
> default."

Provide a small `choices` list (e.g. the user's last-picked model,
"platform default", "abort dispatch"). Pass the chosen string
through as `model:` verbatim, exactly as if it had come from the
envelope. If the user picks "abort dispatch", do not call `tick`
again — wait for further instructions.

This pre-flight is **NOT** required when the envelope already
carries an explicit non-empty `model` field — that case is fully
declarative and the kernel has already resolved it through the
priority chain. Skip the ask, dispatch verbatim.

This is the only mechanism by which CodeNook controls model
selection. The user configures models declaratively in
`plugins/<id>/plugin.yaml`, `plugins/<id>/phases.yaml`,
`<workspace>/.codenook/config.yaml`, or per-task via
`<codenook> task new --model <name>` / `task set-model`. The
kernel resolves the priority chain (task > phase > plugin >
workspace) and surfaces the result here.

### Execution mode in dispatch envelope

`tick --json` may return one of two dispatch action values in the
envelope:

- `action: "phase_prompt"` — spawn a sub-agent via your task
  tool using the envelope's `system_prompt_path` / `prompt_path`
  / `model`. Default behavior; unchanged from v0.18.x.
- `action: "inline_dispatch"` — DO NOT spawn a sub-agent. Read
  the role file at `envelope.role_path` yourself, conduct the
  work inline in this conversation, write the produced output
  file to `envelope.output_path`, then call
  `<codenook> tick --task <T-NNN>` again to advance state.

When `action == "inline_dispatch"` the envelope also carries
`execution_mode: "inline"` and the same `system_prompt_path` /
`prompt_path` / `reply_path` triple as a normal dispatch
envelope, so the conductor has every path it needs to do the
work without re-querying the kernel. `role_path` and
`output_path` are aliases for `system_prompt_path` and
`reply_path` respectively, provided for clarity in the inline
flow.

The user opts into inline mode at task creation
(`<codenook> task new --exec inline`) or post-hoc
(`<codenook> task set-exec --task T-NNN --mode inline`).
Inline is intended for chat-heavy or serial work where
sub-agent spawn overhead is unwanted; sub-agent remains the
default for isolation and parallelism. Tasks created before
v0.19 (no `execution_mode` field in `state.json`) keep the
historical sub-agent behaviour.

The `model` field in inline-mode envelopes is informational
only — the conductor cannot switch models mid-conversation.
Treat it as a hint for which "voice" / role profile to adopt.

### Task creation entry points

The user creates tasks via `<codenook> task new`. Three
recommended modes:

- One-shot, fully scripted:
  `<codenook> task new --plugin <id> --profile <name> --input "..." --title "..."`
- Interactive wizard:
  `<codenook> task new --interactive`
  prompts the user for plugin / profile / title / input / model /
  exec mode and creates the task at the end.
- Minimal (legacy):
  `<codenook> task new --title "..." --accept-defaults`
  uses plugin/profile/exec defaults; relies on the kernel's
  default phase chain to extract requirements.

You (the conductor) MAY suggest `--interactive` to users who
appear to be unsure what plugin or profile they need.

`--profile <name>` selects one of the keys declared under
`profiles:` in the chosen plugin's `phases.yaml`. `--input
<text>` (or `--input-file <path>`) seeds the task description;
when present it is surfaced in the dispatch envelope as
`task_input` so phase agents and the inline conductor can use
it without a separate clarify round. Use
`<codenook> plugin info <id>` to discover the profiles + phase
catalogue for an installed plugin. `<codenook> task set-profile
--task T-NNN --profile <name>` switches profile post-hoc, but
only before the first phase verdict is recorded.

### CLI is the ONLY sanctioned entry point

The `codenook` CLI is the canonical contract. Internal kernel scripts
under `.codenook/codenook-core/skills/builtin/` are private
implementation details — calling them directly is unsupported and may
break across kernel upgrades. Specifically:

- POSIX shells (bash/zsh): use `<ws>/.codenook/bin/codenook ...`
- Windows (PowerShell / cmd): use `<ws>\.codenook\bin\codenook.cmd ...`

Both shims dispatch to the same Python entrypoint, so behaviour is
identical across platforms. There is no "raw-bash form" fallback.

### Plugin knowledge discovery

When a plugin ships knowledge under `<plugin>/knowledge/`, the kernel
discovers all `*.md` files **recursively** (subdirectories included).
Files may carry YAML frontmatter (`title`, `summary`, `tags`); when
absent, the kernel infers `title` from the filename, `tags` from the
parent directory names relative to `knowledge/`, and `summary` from
the body's first heading or paragraph. Plugins may also ship
`knowledge/INDEX.yaml` (preferred) or `knowledge/INDEX.md` (markdown
bullet links) to override metadata for files lacking frontmatter.

Run `<codenook> knowledge reindex` to rebuild
`<workspace>/.codenook/memory/index.yaml` (auto-run on every install
and upgrade so it is never empty). Use
`<codenook> knowledge list [--plugin <id>]` to enumerate the indexed
entries and `<codenook> knowledge search <query>` to rank them by
substring score across tags / title / summary. Conductors and phase
agents may consult this index when grounding their work.

Plugin manifest templates may also include the literal token
`{{KNOWLEDGE_HITS}}`; the kernel substitutes it at dispatch time
with the top-N matches from `index.yaml` via
`knowledge_query.find_relevant`. Templates without the placeholder
are returned unchanged. See `docs/memory-and-extraction.md` §8.

### Hard rules for the LLM (zero domain budget)

- MAY read `.codenook/plugins/*/plugin.yaml` and
  `.codenook/memory/{{knowledge,skills,history,_pending,config.yaml}}`
  for orientation (plugin selection, scope hints, conventions).
  These are workspace-shared resources and reading is expected.
- MUST NOT read `.codenook/plugins/*/roles/` or
  `.codenook/plugins/*/skills/` or `.codenook/plugins/*/knowledge/`
  in conductor context — those are sub-agent system prompts /
  per-phase resources, not for the conductor to interpret.
- MUST NOT mention plugin ids in user-facing prose unless echoing
  back what the user said. Pick the plugin silently via
  `--plugin <id>`.
- MUST NOT modify `draft-config.yaml`, `state.json` by hand — only via
  the `codenook` CLI wrapper, which fronts `orchestrator-tick` (via
  `tick.py` / `tick.sh`), and `hitl-adapter` (via `terminal.py` /
  `terminal.sh`).
- MUST NOT spawn phase agents (designer / implementer / tester /
  reviewer / acceptor / validator) directly. That's `codenook tick`'s
  job (which fronts `tick.py` on Windows hosts and `tick.sh` on
  Linux/macOS — both are equivalent entry points to `_tick.py`).
- MUST run the `clarifier` phase **inline** in the conductor session
  (read role profile + per-call prompt yourself, drive the Q&A with
  the user, write the reply file, then call `tick`). Do **not**
  dispatch a sub-agent for clarifier — that defeats the latency
  optimisation introduced in v0.13.22.
- MUST NOT interpret, paraphrase, or summarise the HITL `prompt`
  field or per-phase outputs. Relay verbatim.
- MUST end every reply by asking the user what their next step is
  (e.g. "What would you like to do next?" / "下一步想做什么？"). Use
  the host's interactive prompt facility when available; otherwise ask
  in plain text. This applies whether or not a CodeNook task is active.
- If a task seems to require breaking one of these rules, surface the
  problem to the user instead of working around it.

### Workspace layout the orchestrator reads

- `.codenook/state.json` — installed plugins, kernel version, paths
- `.codenook/codenook-core/` — self-contained kernel (read-only)
- `.codenook/schemas/` — `task-state`, `installed`, `hitl-entry`, `queue-entry`
- `.codenook/plugins/<id>/` — read-only phase prompts and roles for
  each installed plugin (ids listed in `state.json.installed_plugins`)
- `.codenook/memory/` — `knowledge`, `skills`, `history`, `_pending`, `config.yaml`
- `.codenook/tasks/<task_id>/` — per-task state, prompts, audit log

**Plugin and kernel files are read-only.** Writes happen under
`.codenook/tasks/`, `.codenook/memory/`, and `.codenook/queue/` only.

### Task-chain fields

`state.json` supports `parent_id` (linked parent task) and `chain_root`
(cached terminal ancestor; auto-maintained by `codenook chain link`).
See the installed plugin's `README.md` § task-chains for plugin-specific
notes.

For install flow and CLI subcommand reference see the project README
and `docs/architecture.md`.
{END}
"""


def _resolve_installed_plugins(workspace: Path, *, fallback: str) -> list[str]:
    """Return the full installed-plugin id list from ``state.json``.

    Falls back to ``[fallback]`` when state.json is missing / unparseable
    (e.g. first-ever install where the file isn't written yet, or unit
    tests that call this helper before staging plugins).
    """
    state_file = workspace / ".codenook" / "state.json"
    if state_file.is_file():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            ids = [
                p["id"]
                for p in data.get("installed_plugins") or []
                if isinstance(p, dict) and p.get("id")
            ]
            if ids:
                return sorted(set(ids))
        except (OSError, ValueError):
            pass
    return [fallback] if fallback else []


def sync(workspace: Path, version: str, plugin: str) -> None:
    claude = workspace / "CLAUDE.md"
    plugins = _resolve_installed_plugins(workspace, fallback=plugin)
    block = render_block(version, plugins)

    if not claude.exists():
        claude.write_text(block + "\n", encoding="utf-8")
        return

    text = claude.read_text(encoding="utf-8")
    bi = text.find(BEGIN)
    ei = text.find(END)

    if bi != -1 and ei != -1 and ei > bi:
        # Replace existing block (idempotent — second run = zero diff).
        ei_end = ei + len(END)
        new_text = text[:bi] + block.rstrip("\n") + text[ei_end:]
        if new_text != text:
            claude.write_text(new_text, encoding="utf-8")
        return

    if bi != -1 or ei != -1:
        # Half-open marker — refuse rather than corrupt user content.
        raise SystemExit(
            "claude_md_sync: CLAUDE.md has an unbalanced codenook marker; "
            "fix manually before re-running."
        )

    # No block yet → append, preserving existing content.
    sep = "" if text.endswith("\n") else "\n"
    claude.write_text(text + sep + "\n" + block + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--workspace", required=True)
    p.add_argument("--version", required=True)
    p.add_argument("--plugin", required=True)
    args = p.parse_args(argv)
    ws = Path(args.workspace).resolve()
    if not ws.is_dir():
        print(f"claude_md_sync: not a directory: {ws}", file=sys.stderr)
        return 2
    sync(ws, args.version, args.plugin)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
