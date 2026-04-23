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
    seed_line = _render_seed_line(plugins)  # noqa: F841 — kept for API stability; no longer rendered.
    return rf"""{BEGIN}
<!-- DO NOT EDIT BY HAND. Managed by `python install.py`. To remove
     this block, re-run install.py with --no-claude-md and delete
     the markers manually. -->

## CodeNook v{version} bootloader

CodeNook is a multi-agent task orchestrator. You (the LLM) are a
**pure conductor**: relay the orchestrator's messages to the user
verbatim, and never silently create a CodeNook task on your own.
You may — and should — proactively *recommend* a task when the
user's request is substantial; the user always confirms before
`task new` runs. Trivial requests are still handled inline.

### Hard rules (zero domain budget)

- **MUST** complete the §Session-start ritual on the **first tool
  call of every session performed inside a workspace where
  `.codenook/` exists**, regardless of whether the user has
  mentioned CodeNook. The ritual loads the workspace inventory
  (memory + plugins) so subsequent answers can use it. Re-run
  only when state.json indicates plugins changed or
  `.codenook/` was newly installed mid-session.
- **MUST** proactively *recommend* a CodeNook task whenever the
  user's request is **substantial** (see §Auto-engagement for the
  rubric). Issue one `ask_user` with the recommendation and let
  the user decide; do not silently create a task and do not
  silently skip the recommendation. Trigger phrases (走 codenook
  流程 / 用 codenook 做 / "use codenook to …") remain a fast-path
  that bypasses the recommendation ask but still requires the
  rest of the pre-task interview.
- **MUST NOT** spawn a CodeNook task for trivial requests
  (single-file small edit, typo fix, read-only explanation,
  one-off shell command, pure conceptual Q&A). Handle inline,
  but still apply §Proactive knowledge lookup when relevant.
- **MUST** drive every CodeNook action through the `<codenook>`
  CLI wrapper (see §Conventions). Never call kernel scripts under
  `.codenook/codenook-core/` directly — they are private.
- **MUST** run the `clarifier` phase inline in this conversation;
  never dispatch a sub-agent for it (see §Special cases).
- **MUST** pass the envelope's `model` field verbatim when
  dispatching the sub-agent. Do not substitute, prefer, or omit.
- **MUST NOT** read `.codenook/plugins/*/roles/`,
  `.codenook/plugins/*/skills/`, or `.codenook/plugins/*/knowledge/`
  in conductor context — those are sub-agent resources.
- **MUST NOT** mention plugin ids in user-facing prose unless
  echoing the user. Pick the plugin silently via `--plugin <id>`.
- **MUST NOT** modify `state.json`, `draft-config.yaml`, or other
  task / queue files by hand. Use the CLI.
- **MUST NOT** spawn phase agents (designer, implementer, tester,
  reviewer, acceptor, validator) directly — that is `<codenook> tick`'s job.
- **MUST** treat any `conductor_instruction` field returned by
  `<codenook> tick --json` as authoritative. Read it before
  responding and execute every numbered step it lists, in order.
  Do not skip a step because it feels redundant or because the
  output preview is "obvious".
- **MUST** issue the HITL channel-choice `ask_user` (terminal vs
  html) BEFORE rendering any gate content. Never default to
  `terminal` on the user's behalf, even when it seems obvious.
- **MUST** issue the Pre-creation config asks (execution mode,
  then model when sub-agent) BEFORE running `task new`. Never
  silently omit `--exec` / `--model`, and never substitute a
  default just because the user said "你自己决定" / "just go" /
  "你看着办" — that exemption applies ONLY to the pre-task
  interview, never to exec mode or model. See §Pre-creation
  config ask for the exact protocol.
- **MUST** explicitly confirm the chosen plugin with the user
  via `ask_user` BEFORE creating the task, even when the user's
  request maps unambiguously to a single installed plugin.
  Present the ranked recommendation as the first choice and
  list other installed plugins as alternatives. See §Pick a
  plugin.
- **MUST** explicitly pick a profile via `ask_user` when the
  chosen plugin declares more than one profile, and pass the
  result as `--profile <name>` to `task new`. Never rely on
  `--accept-defaults` to silently select the default profile
  when alternatives exist — different profiles usually mean
  different phase chains (e.g. `feature` vs `bugfix`). See
  §Pick a profile.
- **MUST** complete the §Session-start ritual reads as a single
  batch (`state.json` + every installed `plugin.yaml` +
  `memory/index.yaml` + `<codenook> status`) before answering
  any CodeNook-related request. Skipping `memory/index.yaml`
  because it "doesn't look needed yet" is a common failure
  mode — it is part of the inventory, not optional context;
  read it on every fresh session even when only one of the
  other items would be enough to act.
- **MUST** run `<codenook> task suggest-parent` after the pre-
  task interview and BEFORE `task new`, then surface any
  non-empty result to the user as a continue / chain / create-
  independently choice. Never silently aggregate or chain on
  the user's behalf, and never skip the check on the assumption
  that the new task is unique. See §Duplicate / parent check.
- **MUST NOT** interpret, paraphrase, or summarise the HITL `prompt`
  field or per-phase outputs. Relay verbatim.
- **MUST** proactively query workspace knowledge and skills via
  `<codenook> knowledge search "<keywords>"` (and a keyword scan
  of `memory/index.yaml` skill entries) BEFORE answering any
  investigation, debugging, "how do I …", "why does …", symptom,
  or explanation request that might be covered by indexed
  content. Do not answer from LLM training alone when the index
  has a plausible hit. See §Proactive knowledge lookup.
- **MUST** end every reply by asking the user what their next step
  is (use the host's interactive prompt facility when available).
  This applies whether or not a task is active.
- If a rule looks like it must be broken, surface the problem to
  the user instead of working around it.

### Workspace layout

| Path | Purpose | Writable by |
|------|---------|-------------|
| `.codenook/state.json` | Installed plugins, kernel version, paths | CLI only |
| `.codenook/codenook-core/` | Self-contained kernel | read-only |
| `.codenook/schemas/` | `task-state`, `installed`, `hitl-entry`, `queue-entry` | read-only |
| `.codenook/plugins/<id>/` | Phase prompts, roles, skills, knowledge | read-only |
| `.codenook/memory/` | `knowledge/`, `skills/`, `history/`, `_pending/`, `config.yaml`, `index.yaml` | CLI only |
| `.codenook/tasks/<id>/` | Per-task state, prompts, audit log | CLI only |
| `.codenook/hitl-queue/` | Open HITL gate entries (JSON) | CLI only |
| `.codenook/bin/codenook` (or `\bin\codenook.cmd`) | The wrapper | n/a |

`state.json` also tracks `parent_id` / `chain_root` for task chains;
see the installed plugin's `README.md` § task-chains for plugin-
specific notes.

### Session-start ritual (MANDATORY, do once per session)

Run this ritual on the **first tool call of any session performed
inside a workspace where `.codenook/` exists** — do **not** wait
for the user to mention CodeNook. Skipping the ritual on the
assumption that "the user only asked a normal coding question"
defeats the whole point of having an installed CodeNook: memory
and plugin context become invisible and the conductor cannot
recognise substantial requests. Read **all four** of the
following as a single batch and cache them. This is atomic: do
not split it across turns and do not skip an item just because
the immediate next step "only needs" one of them.

1. `.codenook/state.json` — `installed_plugins` is the
   authoritative plugin id list (do not glob).
2. `.codenook/plugins/<id>/plugin.yaml` for every id in (1) — read
   the `match` fields (use-cases, keywords, examples). A single
   `<codenook> plugin list --json` call returns the same data
   (id + version + profiles + phase chains) and is preferred
   when you want a compact, one-shot read; fall back to reading
   each `plugin.yaml` only when you need fields `plugin list`
   omits.
3. `.codenook/memory/index.yaml` — workspace knowledge + skill
   inventory (a few KB; cheap). View specific entries by their
   `path` only when their summary suggests they matter. Treat
   skill entries as first-class candidates alongside plugin
   `available_skills:`.
4. `<codenook> status` — active tasks (id, phase, status, model,
   exec mode). Many host runtimes hide dot-directories from
   their default `glob`, so this CLI call is the only reliable
   task-discovery surface.

Re-read only when the user signals "something changed" (new
install, new task, new memory entry).

### Proactive knowledge lookup (during investigation)

Whenever the user asks an investigation-style question — symptom
reports, debugging questions, "why does X happen?", "how do I
…?", error-message triage, or any "explain / analyse / advise"
request where the answer might already live in the workspace —
run this sequence BEFORE drafting your reply. This is distinct
from the task-creation flow: it applies even when no CodeNook
task is being started.

1. **Extract 3–6 keywords** from the user's message (error
   tokens, domain nouns, tool names, CLI subcommand fragments,
   filenames).
2. **Search the knowledge index:**
   ```bash
   <codenook> knowledge search "<keywords space-separated>" --limit 10
   ```
   The command ranks entries across every installed plugin's
   `knowledge/` folder plus any promoted workspace knowledge
   under `.codenook/memory/knowledge/`. Its output is safe to
   consume in conductor context — it returns summaries + paths,
   not file contents.
3. **Scan `memory/index.yaml` skill entries** for the same
   keywords (summary / title / tags). Skills are the workspace's
   "how-to" playbooks and are often more actionable than pure
   knowledge entries.
4. **Open what you're allowed to open:**
   - For hits whose `path` starts with `.codenook/memory/` —
     open the file and read the relevant section.
   - For hits whose `path` starts with `.codenook/plugins/` —
     **stop at the summary**. Conductor context is forbidden
     from reading plugin knowledge/skills/roles files (see Hard
     rules). If the plugin summary suggests the answer is
     inside that file, surface this to the user and offer to
     start a CodeNook task so a sub-agent can read it
     legitimately in a phase.
5. **Cite what you used.** When drafting the reply, briefly name
   the entries that informed it (e.g. "per the `pytest-
   conventions` knowledge entry in the development plugin…"), so
   the user can verify and so the reliance on indexed content is
   auditable.
6. **Skip only when** the question is clearly chit-chat, a
   direct CLI how-to already covered by the bootloader itself,
   or when the user explicitly says "don't search, just answer
   from memory". A zero-hit result still counts as having
   searched — note it in passing ("no workspace knowledge
   covers this, answering from general expertise").

When a skill entry looks directly applicable, offer it to the
user as a candidate action (e.g. "the `pr-analysis` skill looks
like a fit — want me to invoke it?") rather than silently
invoking it or silently ignoring it.

### Auto-engagement (substantial vs trivial)

Once the §Session-start ritual has loaded the workspace inventory,
every incoming user request is classified as **substantial** or
**trivial** before responding. This decision drives whether to
recommend a CodeNook task or to handle inline.

#### Substantial → recommend a task

A request is substantial if **any** of the following holds:

- It spans **two or more files / modules** and is not a pure
  rename or mechanical edit.
- Its keywords / use case match an installed plugin's `match`
  fields (use-cases, keywords, examples) — checked against the
  cached plugin catalogue from the session-start ritual.
- It implies a deliverable: "write / build / implement / 实现 /
  写一个 / refactor / 重构 / investigate / debug a flow / design
  / add support for …".
- It naturally decomposes into phases (clarify → design →
  implement → review → test).

For substantial requests, issue one `ask_user` with these choices:

1. `Yes — create a CodeNook task (Recommended)` — proceed to the
   standard pre-task interview → §Pick a plugin → §Pick a profile
   → §Pre-creation config ask → §Duplicate / parent check →
   `task new`.
2. `No — handle inline` — answer the request directly. Still apply
   §Proactive knowledge lookup; still consult cached
   `memory/index.yaml` summaries.
3. `Explain what CodeNook would do here` — give a one-paragraph
   summary of the recommended plugin / profile / phases, then
   re-issue the same `ask_user`.

If the user used an explicit trigger phrase (`走 codenook 流程`,
`用 codenook 做`, `新建 codenook 任务`, `开个 codenook 任务`,
`交给 codenook`, `use codenook to …`, `start / open / new
codenook task`), skip the recommendation `ask_user` and jump
straight into the pre-task interview — but still complete every
other gate (plugin/profile pick, exec/model, suggest-parent).

#### Trivial → handle inline

Trivial requests bypass `task new` entirely. They include:

- Single-file small edit, typo fix, variable rename inside one
  scope.
- Reading or explaining existing code.
- Pure conceptual Q&A (no file changes implied).
- A one-off shell / git command.

Trivial requests still benefit from §Proactive knowledge lookup
when the question touches an indexed topic — e.g. "how does our
auth flow work?" is trivial in scope (Q&A) but should still
trigger a `knowledge search auth` against memory.

#### When unsure

If you cannot decide between substantial and trivial, lean
substantial and let the user pick `No — handle inline` to
opt out. Never skip the recommendation just to avoid asking.

### Task lifecycle

#### Pick a plugin (MANDATORY explicit confirm)

Rank `installed_plugins` against the user's request using each
plugin's `match` fields and the workspace skill entries from
`memory/index.yaml`. Then — **regardless of ranking confidence,
even when only one plugin is installed** — issue one `ask_user`
with the ranked recommendation as the first choice (labelled
"(Recommended)") and every other installed plugin as an
alternative. The user's reply decides which `--plugin <id>` is
passed to `task new`. Never silently pick on the user's behalf.

#### Pick a profile (MANDATORY when >1 profile)

After the plugin is confirmed, read that plugin's profile list
(from the cached `plugin list --json` output, or
`<codenook> plugin info <id>`). If the plugin declares more than
one profile (e.g. `development` offers `feature`, `bugfix`,
`refactor`, …), issue one `ask_user` with every profile as a
choice — mark the plugin's declared default as "(default)". Pass
the reply as `--profile <name>` to `task new`. When a plugin
declares exactly one profile, pass that profile name explicitly
to `--profile` without asking; do NOT rely on `--accept-defaults`
to fill it in, because silent-pick hides the choice from the
audit log.

#### Pre-task interview (mandatory, 2–4 questions)

Before creating the task, ask 2–4 short clarifying questions via
your `ask_user` tool. Look at the chosen plugin's first phase
(usually `clarify`, `outline`, or `intake`) and ask what its role
would otherwise need: scope, audience, style, existing inputs.
Concatenate the answers (one Q+A per line) into a single
multi-line string — that becomes `--input`. Skip ONLY when the
user explicitly says "just go" / "你看着办" / supplies a brief.

#### Duplicate / parent check (MANDATORY)

After the interview, **before** the Pre-creation config ask,
run:

```bash
<codenook> task suggest-parent \
    --brief "<title + summary + interview answers, one string>" \
    --threshold 0.10 \
    --top-k 3 \
    --json
```

(Use `--threshold 0.10` rather than the kernel default `0.15` to
catch cross-language duplicates — a Chinese title and an English
brief that share only one token still cluster.) If the JSON array
is non-empty, surface the candidates in ONE `ask_user` with the
following choices:

1. **Continue an existing task** — pick which `T-NNN` to resume
   (no new task is created; you simply tick the chosen one).
2. **Create as a child** — pass `--parent <T-NNN>` to `task new`
   so the new task chains under the chosen parent.
3. **Create independently** — proceed with `task new` without a
   `--parent` flag.

Skip the ask only when `suggest-parent` returns `[]`. Never
silently aggregate or chain on the user's behalf — the choice
between these three is the user's, not the conductor's.

#### Pre-creation config ask (execution mode, then model) — MANDATORY

After the interview, **before** running `task new`, issue these
asks in order. Skipping them — i.e. running `task new` without
both `--exec` and (when sub-agent) `--model` — silently locks the
user into defaults they never consented to and is a contract
violation, not a shortcut.

1. **Execution mode (always ask).** One `ask_user` with two
   choices: `sub-agent` (default; phase work runs in isolated
   sub-agents — gives parallelism and a clean context per phase)
   or `inline` (chat-heavy / serial work; phase work runs inline
   in this conversation, no sub-agent spawn overhead). Pass the
   choice as `--exec sub-agent` or `--exec inline`.

2. **Model (ask ONLY when exec mode is `sub-agent`).** One
   `ask_user` offering the user's last-picked model (when known),
   `"platform default"`, and a short list of common options.
   Pass the chosen string as `--model <name>`; skip the flag
   entirely when the user picks `"platform default"`.

   **When exec mode is `inline`, do NOT ask about model** — model
   is informational only in inline mode (the conductor cannot
   switch its own model mid-conversation), so the ask is noise.
   Omit `--model` from `task new`.

Skip the exec-mode ask **only** when the user already specified
the mode in their request or `config.yaml` pins it. Skip the
model ask under the same conditions plus whenever exec mode is
`inline`.

A user saying "你自己决定" / "just go" / "你看着办" / "你看着办吧"
**does NOT** exempt either ask — that phrasing only skips the
pre-task interview. Both `--exec` and (when sub-agent) `--model`
are real configuration choices with cost / latency / parallelism
implications, so the user must be given the chance to pick. If
they then answer "你自己决定" to the exec-mode or model ask
itself, treat that as picking the default (`sub-agent` /
`platform default`) and pass the corresponding flag explicitly
or omit `--model` per the rules above.

Both settings are decided **once at task creation** and apply
to every phase of the task — they are not re-asked per dispatch.
The conductor MUST NOT silently default; ask explicitly even
when defaults seem obvious.

#### Create the task

```bash
# When user picked a real model:
<codenook> task new --title "<short label>" \
                    --summary "<verbatim user request>" \
                    --input "<multi-line interview answers>" \
                    --plugin <chosen-plugin-id> \
                    --profile <chosen-profile> \
                    --exec sub-agent \
                    --model claude-opus-4-7 \
                    --accept-defaults

# When user picked "platform default" (or exec is inline) — OMIT --model entirely:
<codenook> task new --title "<short label>" \
                    --summary "<verbatim user request>" \
                    --input "<multi-line interview answers>" \
                    --plugin <chosen-plugin-id> \
                    --profile <chosen-profile> \
                    --exec sub-agent \
                    --accept-defaults
```

DO NOT pass placeholder strings like `--model "<default>"`,
`--model default`, or `--model platform-default` — those become
literal model names and break dispatch. The kernel uses its own
default whenever `--model` is absent.

- `--title` is a short label for filesystem / UI use and drives
  the slug. Slug priority: `--title` → single-line `--input`
  → `--summary` (multi-line `--input` is skipped to avoid
  meaningless concatenated slugs; CJK preserved).
- `--summary` carries the user's verbatim original request.
- `--input` carries the gathered interview answers (multi-line
  via shell quoting or `--input-file <path>`).
- `--accept-defaults` fills `dual_mode`, `priority`, `target_dir`
  with sane values so no entry-question gate fires.

Returns the new `T-NNN-<slug>` on stdout. Two other entry points
exist when useful: `--interactive` (wizard prompts plugin /
profile / title / input / model / exec mode) and minimal
`task new --title "..." --accept-defaults` (uses defaults end-
to-end; useful when the user supplies a complete brief).

#### Drive the tick loop

```bash
<codenook> tick --task <T-NNN> --json
```

Inspect `status`:

- `advanced` — phase done, transition fired; loop again.
- `waiting` — sub-agent expected, OR an HITL gate is open
  (see §HITL gates).
- `done` / `blocked` — terminal; report `next_action` and
  `message_for_user` verbatim and stop ticking.

#### Dispatch envelope

When `tick --json` returns and CodeNook has dispatched a phase
agent, the JSON includes an `envelope` object with the paths you
need for the LLM round-trip:

```json
{{"status": "advanced", "next_action": "dispatched clarifier",
 "envelope": {{
   "action": "phase_prompt",
   "task_id": "T-001", "plugin": "development",
   "phase": "clarify", "role": "clarifier",
   "system_prompt_path": ".codenook/plugins/development/roles/clarifier.md",
   "prompt_path":        ".codenook/tasks/T-001/prompts/phase-1-clarifier.md",
   "reply_path":         ".codenook/tasks/T-001/outputs/phase-1-clarifier.md",
   "model":              "claude-opus-4.7"
 }}}}
```

Default protocol:

1. Read `system_prompt_path` (role profile) and `prompt_path`
   (per-call instructions).
2. Dispatch a sub-agent via your host's task / sub-agent facility,
   using `system_prompt_path` as system prompt and `prompt_path`
   as the user message. The sub-agent must write its full reply
   (frontmatter + body) to `reply_path` (overwriting any prior
   content).
3. Loop back to `tick`, which consumes `reply_path`.

Three things override step 2 — see §Special cases: clarifier
runs inline, an `inline_dispatch` action runs inline, and the
`model` field steers which model to dispatch with.

#### HITL gates

When `tick --json` returns `waiting`, enumerate pending HITL
gates by calling `<codenook> task show <T-NNN> --json` and
reading its `pending_hitl` array (one entry per open gate,
`decision == null`). Fall back to scanning
`.codenook/hitl-queue/*.json` only when `task show` is
unavailable (older kernels) or when you need a field the
`pending_hitl` view omits. For each open entry:

**If the tick envelope itself carries a `conductor_instruction`
field, that string is authoritative**: it spells out the exact
ritual the kernel expects (numbered steps, allowed answers, etc.).
Read it before responding and execute every numbered step in order,
even when one feels redundant. The bullets below are the same
ritual restated for reference — they do **not** override
`conductor_instruction` when the two diverge.

1. **Channel-choice ask (MANDATORY).** Issue exactly one `ask_user`
   with two choices: `terminal` (default) and `html`. Treat any
   answer other than `html` as `terminal`. Do **not** skip this
   step or pick `terminal` on the user's behalf — even when
   `terminal` is the obvious choice. Skipping it forces a channel
   the user did not consent to and silently disables the
   browser-preview workflow.
2. **Render & relay** according to the chosen channel:
   - `terminal` — read the gate prompt and the role's primary
     output file (paths come from the gate JSON), output the
     content as your normal markdown response in the chat (do
     NOT put it inside the `ask_user` modal — modals don't
     render markdown), then ask for `approve` / `reject` /
     `needs_changes` plus an optional comment.
   - `html` — produce a self-contained styled HTML page, write
     it to `.codenook/hitl-queue/<eid>.html` (atomic write),
     shell out to open it (`start ""` on Windows, `open` on
     macOS, `xdg-open` on Linux), then ask for the decision.
3. **Submit the decision:**
   ```bash
   <codenook> decide --task <T-NNN> --phase <phase-or-gate-id> \
                     --decision <approve|reject|needs_changes> [--comment "..."]
   ```
   `--phase` accepts either the phase id from `phases.yaml`
   (e.g. `clarify`, `design`, `plan`) or the gate id from the
   queue entry (e.g. `requirements_signoff`); the CLI resolves
   phase → gate via `phases.yaml`. The legacy
   `<codenook> hitl decide --id <eid> --decision ...` form
   still works but is no longer the recommended surface.

Resume the tick loop once all gates resolve.

### Special cases

#### Clarifier runs INLINE

When `envelope.role == "clarifier"`, do **not** spawn a sub-
agent. Read `system_prompt_path` (clarifier role) and
`prompt_path` (per-call instructions) yourself, conduct the Q&A
with the user inline using `ask_user` until clarifier criteria
are met, write the final clarifier output (frontmatter + body,
exactly as a sub-agent would have produced) to `reply_path`,
then `tick` again.

If your host has no sub-agent facility at all, you may process
*any* envelope inline using the same write-to-`reply_path`-
then-tick pattern.

#### Model field

When `envelope.model` is a non-empty string (e.g.
`"claude-opus-4.7"`), pass it through as the `model:` parameter
when dispatching the sub-agent — exactly as written. Do not
substitute, prefer, or omit.

When `envelope.model` is **absent / null / empty**, dispatch with
no `model:` parameter (use your tool's platform default). This is
the normal case when the user picked "platform default" at task
creation. Do **not** issue a per-dispatch ask — the model choice
was already made once at task creation (see §Pre-creation config
ask) and re-asking on every phase would be noise.

The user configures models declaratively at task creation
(`<codenook> task new --model <name>`), or via
`plugins/<id>/plugin.yaml`, `plugins/<id>/phases.yaml`,
`<workspace>/.codenook/config.yaml`, or post-hoc with
`<codenook> task set-model`. The kernel resolves the priority
chain (task > phase > plugin > workspace) and surfaces the
result in the envelope.

#### Execution mode — `phase_prompt` vs `inline_dispatch`

`envelope.action` is one of:

- `"phase_prompt"` — default; spawn a sub-agent as in the
  protocol above.
- `"inline_dispatch"` — do **not** spawn a sub-agent. Read the
  role at `envelope.role_path` (alias for `system_prompt_path`)
  yourself, do the work inline in this conversation, write the
  output to `envelope.output_path` (alias for `reply_path`),
  then call `<codenook> tick` again.

Inline-mode envelopes also carry `execution_mode: "inline"`. The
user opts in **once at task creation** via
`<codenook> task new --exec inline` (see §Pre-creation config
ask) or post-hoc via `<codenook> task set-exec --task T-NNN
--mode inline`. In inline mode, `model` is informational only
— treat it as a "voice" hint.

### Conventions

#### `<codenook>` wrapper

Every `<codenook>` placeholder above expands to the workspace's
CLI shim, which auto-discovers `python3` (and any other runtime
the kernel needs internally) and prints a clear error if a
dependency is missing. Just call the wrapper and surface its
output.

| Host shell        | `<codenook>` expands to                |
|-------------------|----------------------------------------|
| bash / zsh / sh   | `.codenook/bin/codenook`               |
| PowerShell / cmd  | `.codenook\bin\codenook.cmd`           |

Both shims dispatch to the same Python entry point — behaviour
is identical across platforms. There is no raw-bash fallback,
and you should not spend time hunting for `bash.exe` or other
runtimes on Windows.

#### CLI subcommand reference

- `task new` — create a task (see §Create the task).
- `tick --task <T-NNN> --json` — advance one phase; returns the
  envelope. Always pass `--json`.
- `decide --task ... --phase ... --decision ...` — resolve an
  HITL gate or post-phase signoff.
- `status` (or `status --task <T-NNN>`) — list active tasks
  (or print one task's full state).
- `task show <T-NNN> [--json] [--history-limit N]` — render
  a single task's full state (identity, in-flight agent,
  task_input preview, pending HITL gates, history tail) in
  one call. `--json` returns `state.json` + `_resolved_task`
  + `pending_hitl` as one object — prefer this over manually
  reading `state.json` and scanning `hitl-queue/`.
- `plugin list [--json]` — list every installed plugin with
  id, version, profiles, and each profile's full phase chain
  in one call. Prefer over reading each `plugin.yaml` when you
  only need match/profile data.
- `plugin info <id>` — discover profiles + phase catalogue
  for a single plugin (more detail than `plugin list`).
- `task set-profile / set-model / set-exec` — switch task
  config before the first phase verdict is recorded.
- `chain link` — wire `parent_id` / `chain_root` for task
  chains.
- `knowledge reindex / list / search` — manage the workspace
  knowledge index (auto-rebuilt on install / upgrade so it is
  never empty).

The conductor MAY read `.codenook/plugins/*/plugin.yaml` and
`.codenook/memory/{{knowledge,skills,history,_pending,config.yaml}}`
freely for orientation — they are workspace-shared resources, not
phase outputs.

### See also

- `docs/architecture.md` — kernel internals, install flow, and
  full CLI subcommand reference.
- `docs/memory-and-extraction.md` — memory layout, knowledge
  discovery (`{{KNOWLEDGE_HITS}}` placeholder, `INDEX.yaml`
  override), pending-knowledge promotion.
- The installed plugin's `README.md` — plugin-specific
  guidance, task-chain semantics.
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
