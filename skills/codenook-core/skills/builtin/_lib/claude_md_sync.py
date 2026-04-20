#!/usr/bin/env python3
"""Idempotently sync the CodeNook bootloader block in a workspace CLAUDE.md.

Wraps the bootloader between explicit ``<!-- codenook:begin -->`` and
``<!-- codenook:end -->`` markers. Re-running replaces the block in
place; user content outside the markers is never touched. When no
CLAUDE.md exists, a stub is created containing only the block.

Used by the top-level ``install.sh`` (DR-006).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BEGIN = "<!-- codenook:begin -->"
END = "<!-- codenook:end -->"


def render_block(version: str, plugin: str) -> str:
    return f"""{BEGIN}
<!-- DO NOT EDIT BY HAND. Managed by `bash install.sh`. To remove this block,
     re-run install.sh with --no-claude-md and delete the markers manually. -->

## CodeNook v{version} bootloader

This workspace has the CodeNook plugin **`{plugin}`** installed.
CodeNook is a multi-agent task orchestrator. The LLM (you) acts as a
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
`spawn.sh`, `tick.sh`, or `terminal.sh` directly — those require `bash`
and `python3` to be on `PATH`, which is often **not** the case in a
Windows hosted-LLM session (Copilot CLI, Cursor, etc.). The wrapper
auto-discovers Git-for-Windows bash and a working python3 for you.

**Per-shell invocation form** (replace `<codenook>` in every example
below with the form for your host shell):

| Host shell        | `<codenook>` expands to                |
|-------------------|----------------------------------------|
| bash / zsh / sh   | `.codenook/bin/codenook`               |
| PowerShell / cmd  | `.codenook\\bin\\codenook.cmd`           |

On Windows, do **not** spend time hunting for `bash.exe` or installing
python — if the wrapper can't find them it will print a clear error
pointing to the fix. Just call the wrapper and surface its output. On
Linux/macOS the script is a plain bash CLI; both `bash` and `python3`
are expected on `PATH` already.

### How to start a task

The wrapper allocates the next `T-NNN` for you. **Do not** scan
`.codenook/tasks/` and increment ids by hand.

The default flow is **conductor-driven plugin selection** → `task
new --plugin <id>` → `tick`. The conductor (you) reads the user's
intent, picks the best-matching plugin, and creates the task with
`--plugin` set explicitly. The LLM-mediated router-agent drafting
dialog is **off by default** and only invoked when the user
explicitly asks for it.

**What the conductor reads when picking a plugin / starting a task:**

- `.codenook/state.json` — `installed_plugins` field is the
  authoritative list of plugin ids in this workspace. Read this
  first; do not rely on globbing.
- `.codenook/plugins/<id>/plugin.yaml` — for each id from
  `state.json`, read the manifest and look at the match fields
  (which use-cases / keywords / examples). Rank against the
  user's request and pick one. If two tie or none fits, ask.
- `.codenook/memory/knowledge/*.md` — workspace-shared knowledge
  distilled from prior tasks. May influence scope, defaults, or
  warnings to surface to the user. Skim file names; read on demand.
- `.codenook/memory/skills/*.md` — workspace-shared procedural
  skills (recipes, conventions). Same usage as `knowledge/`.
- `.codenook/memory/history/` and `.codenook/memory/_pending/` —
  prior task summaries and draft notes. Useful when the user
  references "last time" or wants to continue earlier work.
- `.codenook/memory/config.yaml` — workspace-level overrides
  (default plugin, dual_mode, target_dir, etc.) — honour these
  when the user did not state otherwise.

The conductor MAY read these files freely. They are workspace-
shared resources, not phase outputs. The "zero domain budget"
hard rules below restrict only state mutation and per-phase
artifact interpretation, not orientation reads.

```bash
# 1. Pick a plugin. Read `.codenook/state.json` `installed_plugins`
#    for the authoritative id list, then read each
#    `.codenook/plugins/<id>/plugin.yaml`. Skim
#    `.codenook/memory/{{knowledge,skills}}/`. Rank candidates
#    against the user request, choose the best fit. If two tie or
#    none fits well, ask the user which one.
#
# 2. Create the task. Pass --plugin explicitly. --summary carries
#    the user's request verbatim; --accept-defaults fills
#    dual_mode/priority/target_dir with sane defaults so no
#    entry-question gate fires. Returns the new T-NNN on stdout.
<codenook> task new --title "<short title>" \
                    --summary "<verbatim user request>" \
                    --plugin <chosen-plugin-id> \
                    --accept-defaults

# 3. Drive the tick loop. Each call advances at most one phase and
#    returns a JSON envelope with the new status.
<codenook> tick --task <T-NNN> --json
```

Loop step 3 on `status: advanced`. Stop on `done` / `blocked` and
report verbatim. On `waiting`, scan `.codenook/hitl-queue/*.json`
for entries with `decision == null`, relay each `prompt` field
verbatim to the user, capture the answer, then:

```bash
<codenook> decide --task <T-NNN> --phase <phase> \
                  --decision <approve|reject|needs_changes> \
                  [--comment "..."]
```

Resume the tick loop when all gates resolve.

#### Optional: router-agent drafting dialog (advanced, off by default)

Only invoke `router` when the user explicitly asks for an
LLM-mediated drafting dialog. The default conductor-driven flow
above handles the common case faster (no extra sub-agent round-trip
just to pick a plugin).

```bash
<codenook> router --task <T-NNN> --user-turn "<verbatim user text>"
```

`router` prints a JSON envelope with `prompt_path` / `reply_path`;
follow the same dispatch protocol as `tick` envelopes.

### The dispatch envelope (used by both `tick` and `router`)

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

`router` returns the same envelope shape (with `action: prompt`)
pointing at `.router-prompt.md` / `router-reply.md`. Same protocol
for both:

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

On `waiting` you may also need to clear an HITL gate. Scan
`.codenook/hitl-queue/*.json` for entries with `decision == null`,
relay each `prompt` field verbatim to the user, capture the answer,
then:

```bash
<codenook> decide --task <T-NNN> --phase <phase> \
                  --decision <approve|reject|needs_changes> \
                  [--comment "..."]
```

Resume the tick loop when all gates resolve.

### Direct kernel-script form (advanced, bash environments only)

If you're already in bash/zsh on Linux/macOS, the underlying scripts
under `.codenook/codenook-core/skills/builtin/` can be called directly
(see `docs/router-agent.md`). The CLI wrapper above is preferred for
all routine flows. **Never attempt the raw-bash form from PowerShell
as a fallback — use the `.cmd` wrapper instead.**

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
- MUST NOT modify `router-context.md`, `draft-config.yaml`,
  `state.json` by hand — only via the `codenook` CLI wrapper, which
  fronts `spawn.sh`, `orchestrator-tick`, and `hitl-adapter`.
- MUST NOT spawn phase agents (designer / implementer / tester /
  reviewer / acceptor / validator) directly. That's `codenook tick`'s
  job (which fronts `tick.sh`).
- MUST run the `clarifier` phase **inline** in the conductor session
  (read role profile + per-call prompt yourself, drive the Q&A with
  the user, write the reply file, then call `tick`). Do **not**
  dispatch a sub-agent for clarifier — that defeats the latency
  optimisation introduced in v0.13.22.
- MUST NOT interpret, paraphrase, or summarise `router-reply.md`, the
  HITL `prompt` field, or per-phase outputs. Relay verbatim.
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
- `.codenook/plugins/{plugin}/` — read-only phase prompts and roles
- `.codenook/memory/` — `knowledge`, `skills`, `history`, `_pending`, `config.yaml`
- `.codenook/tasks/<task_id>/` — per-task state, prompts, audit log

**Plugin and kernel files are read-only.** Writes happen under
`.codenook/tasks/`, `.codenook/memory/`, and `.codenook/queue/` only.

### Task-chain fields

`state.json` supports `parent_id` (linked parent task) and `chain_root`
(cached terminal ancestor; auto-maintained by `codenook chain link`).
See `plugins/{plugin}/README.md` § task-chains.

For init.sh subcommands and install flow see the project README and
`docs/architecture.md`.
{END}
"""


def sync(workspace: Path, version: str, plugin: str) -> None:
    claude = workspace / "CLAUDE.md"
    block = render_block(version, plugin)

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
