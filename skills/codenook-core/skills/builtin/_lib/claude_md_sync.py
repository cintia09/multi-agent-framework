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

### How to start a task

Allocate a fresh `T-NNN` id (scan existing `.codenook/tasks/T-*` and
increment the highest numeric suffix, zero-padded), then invoke:

```bash
bash .codenook/codenook-core/skills/builtin/router-agent/spawn.sh \\
    --workspace . --task-id <T-NNN>
```

`spawn.sh` returns a single-line JSON envelope:
`{{"action": "...", "task_id": "...", "prompt_path": "...", "reply_path": "...", ...}}`.
Read `prompt_path` as the system prompt for a sub-agent, dispatch it,
read `reply_path` after it returns, and relay that text **verbatim** to
the user. Do not paraphrase or summarise.

### On user follow-ups during the drafting dialog

Persist the user's exact reply to a scratch file (e.g.
`.codenook/tasks/<T-NNN>/.user-turn.txt`) and call:

```bash
bash .codenook/codenook-core/skills/builtin/router-agent/spawn.sh \\
    --workspace . --task-id <T-NNN> --user-turn-file <path>
```

Same dispatch/relay loop.

### On user confirmation ("go" / "confirm" / "approve")

```bash
bash .codenook/codenook-core/skills/builtin/router-agent/spawn.sh \\
    --workspace . --task-id <T-NNN> --confirm
```

On `action == "handoff"`: enter the tick driver loop:

```bash
bash .codenook/codenook-core/skills/builtin/orchestrator-tick/tick.sh \\
    --task <T-NNN> --workspace . --json
```

Read `status` from the JSON. Loop on `advanced`. Stop on `done` /
`blocked` and report verbatim. On `waiting`, scan
`.codenook/hitl-queue/*.json` for entries with `decision == null`,
relay each `prompt` field verbatim to the user, capture the answer,
then:

```bash
bash .codenook/codenook-core/skills/builtin/hitl-adapter/terminal.sh \\
    decide --id <hitl-entry-id> --decision <answer>
```

Resume the tick loop when all gates resolve.

### Plain-shell alternative

Users without a hosted agent can use the wrapper directly:

```bash
.codenook/bin/codenook task new   --title "Implement X"
.codenook/bin/codenook router     --task T-001 --user-turn "Implement X end-to-end"
.codenook/bin/codenook tick       --task T-001
.codenook/bin/codenook decide     --task T-001 --phase design --decision approve
.codenook/bin/codenook status     [--task T-001]
.codenook/bin/codenook chain link --child T-002 --parent T-001
```

The wrapper resolves the kernel via `kernel_dir` in `.codenook/state.json`.

### Hard rules for the LLM (zero domain budget)

- MUST NOT read `plugins/*/plugin.yaml`, `plugins/*/knowledge/`,
  `plugins/*/roles/`, `plugins/*/skills/` directly. Plugin selection
  happens inside router-agent.
- MUST NOT mention plugin ids in prose ("development", "writing", etc).
- MUST NOT modify `router-context.md`, `draft-config.yaml`, `state.json`
  by hand — only via `spawn.sh`, `orchestrator-tick`, `hitl-adapter`.
- MUST NOT spawn phase agents (designer / implementer / tester /
  reviewer / acceptor / validator) directly. That's `tick.sh`'s job.
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
