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

```bash
# 1. Create task scaffold (returns the new T-NNN on stdout)
<codenook> task new --title "<short title>" --accept-defaults

# 2. Hand the user's request to router-agent
<codenook> router --task <T-NNN> --user-turn "<verbatim user text>"
```

`router` prints a **single-line JSON envelope** on stdout, of the form:

```json
{{"action": "prompt", "task_id": "T-001",
 "prompt_path": ".codenook/tasks/T-001/.router-prompt.md",
 "context_path": ".codenook/tasks/T-001/router-context.md",
 "reply_path":   ".codenook/tasks/T-001/router-reply.md"}}
```

This envelope is **not** the reply — it tells you where to find the
prompt and where to put the response. To complete the round-trip:

1. **Read `prompt_path`** — it contains the full router-agent system
   prompt (role definition, plugin catalogue, draft state, etc).
2. **Dispatch a sub-agent** using your host's sub-agent / Task
   facility. Use `prompt_path`'s contents as the **system prompt**
   for that sub-agent and an **empty** user message. The sub-agent
   must write its complete response to the file at `reply_path`
   (overwriting any prior content).
3. **Read `reply_path`** and relay the contents **verbatim** to the
   user. Do not paraphrase, summarise, or annotate.

If your host has no sub-agent facility, you may process the prompt
in your own context, but you **must** still write the response to
`reply_path` before relaying — downstream tooling reads it.

> Headless / batch alternative: set `CN_ROUTER_DRIVE=1` before calling
> `router` and the wrapper will run `host_driver.py` in-process. This
> uses `_lib/llm_call.py` (mock by default; set `CN_LLM_MODE=real` to
> shell out to the `claude` CLI). Off by default — interactive
> conductors should drive the dispatch themselves per the steps above.

### On user follow-ups during the drafting dialog

Each follow-up is another `router` call with the user's exact words.
The same JSON envelope → dispatch → relay loop applies:

```bash
<codenook> router --task <T-NNN> --user-turn "<verbatim user reply>"
```

### On user confirmation ("go" / "confirm" / "approve")

The router-agent reply itself signals when confirmation is awaited
(see `awaiting: confirmation` in its frontmatter). Pass the user's
confirmation through as a normal `--user-turn`:

```bash
<codenook> router --task <T-NNN> --user-turn "go"
```

When the router replies with handoff (its body will say so), drive
the tick loop:

```bash
<codenook> tick --task <T-NNN> --json
```

Read `status` from the JSON. Loop on `advanced`. Stop on `done` /
`blocked` and report verbatim. On `waiting`, scan
`.codenook/hitl-queue/*.json` for entries with `decision == null`,
relay each `prompt` field verbatim to the user, capture the answer,
then:

```bash
<codenook> decide --task <T-NNN> --phase <phase> --decision <approve|reject|needs_changes> [--comment "..."]
```

Resume the tick loop when all gates resolve.

### Direct kernel-script form (advanced, bash environments only)

If you're already in bash/zsh on Linux/macOS, the underlying scripts
under `.codenook/codenook-core/skills/builtin/` can be called directly
(see `docs/router-agent.md`). The CLI wrapper above is preferred for
all routine flows. **Never attempt the raw-bash form from PowerShell
as a fallback — use the `.cmd` wrapper instead.**

### Hard rules for the LLM (zero domain budget)

- MUST NOT read `plugins/*/plugin.yaml`, `plugins/*/knowledge/`,
  `plugins/*/roles/`, `plugins/*/skills/` directly. Plugin selection
  happens inside router-agent.
- MUST NOT mention plugin ids in prose ("development", "writing", etc).
- MUST NOT modify `router-context.md`, `draft-config.yaml`, `state.json`
  by hand — only via the `codenook` CLI wrapper, which fronts
  `spawn.sh`, `orchestrator-tick`, and `hitl-adapter`.
- MUST NOT spawn phase agents (designer / implementer / tester /
  reviewer / acceptor / validator) directly. That's `codenook tick`'s
  job (which fronts `tick.sh`).
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
