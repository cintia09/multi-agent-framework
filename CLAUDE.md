# CodeNook — repository-level main session guide

> This file is read by the **main session** (the conductor) on entry to
> the repository. It documents the protocol the main session must
> follow when handling user task requests.
>
> The main session is a **pure protocol conductor**: it relays
> messages, drives an opaque tick loop, and brokers HITL gates. It is
> intentionally domain-agnostic. All task-creation domain reasoning
> lives behind the router-agent skill; all per-phase work lives behind
> `orchestrator-tick`.
>
> Canonical layering reference: `docs/router-agent.md` §2.
>
> **Path convention.** Once installed, the kernel is self-contained at
> `<ws>/.codenook/codenook-core/`. All command paths below use that
> location, so they work in any installed workspace regardless of
> where this source repository lives. Inside the source repository
> itself (this file's location), the equivalent path is
> `skills/codenook-core/` — same tree, same scripts.

---

## Task lifecycle protocol (domain-agnostic)

The protocol below is the only path the main session takes when the
user expresses task intent. Each numbered section is a verbatim
contract; the main session does not improvise around it.

## 1. When the user expresses task intent

When a user message reads as a request to start new work:

* DO NOT inspect the workspace for plugin manifests, knowledge files,
  or any domain artifact. The main session has zero domain awareness
  budget here.
* DO allocate a fresh task id by scanning the workspace's existing
  `tasks/T-*` directories and incrementing the highest numeric
  suffix (zero-padded to three digits, e.g. `T-001`, `T-042`).
* DO invoke the router entry once via the workspace CLI:

  ```bash
  <codenook> router --task <new-T-NNN>
  ```

  Where `<codenook>` is whichever CLI shim is appropriate for your
  shell — typically `<ws>/.codenook/bin/codenook` on POSIX or
  `<ws>\.codenook\bin\codenook.cmd` on Windows.

* The router returns a single-line JSON envelope of the form
  `{"action": "...", "task_id": "...", "prompt_path": "...", "reply_path": "...", ...}`.
  Read the `prompt_path` file, dispatch a sub-agent (Task tool /
  sub-agent dispatch) using that prompt as the system prompt, and
  when the sub-agent finishes, read the `reply_path` file and show
  its contents verbatim to the user.
* The main session does not paraphrase, summarise, or annotate the
  router's reply.

## 2. On each user follow-up turn

When the user replies during an open drafting dialog:

* Persist the user's exact utterance to a scratch file
  (`tasks/<T-NNN>/.user-turn.txt` or similar).
* DO invoke the router again with the existing task id and the turn
  file:

  ```bash
  <codenook> router --task <T-NNN> --user-turn-file <path-to-user-turn-text>
  ```

* Run the same dispatch loop: read `prompt_path`, dispatch a fresh
  sub-agent with that prompt, read `reply_path`, relay verbatim.
* DO NOT interpret the reply. Do not summarise. Do not add domain
  commentary. The reply is an opaque string from the main session's
  point of view.

## 3. On user confirmation

When the user explicitly confirms (e.g. "go", "confirm", "approve",
"ship it"):

* DO invoke the router in confirm mode:

  ```bash
  <codenook> router --task <T-NNN> --confirm
  ```

* On `action == "handoff"`: the draft is frozen, `state.json` is
  materialised, and the first tick has run. Enter the tick driver
  loop (see §4).
* On `action == "error"` with `code == "draft_invalid"`: show the
  `errors` array verbatim to the user and return to step 2 (continue
  the dialog by collecting the next user turn and calling the router
  again).
* On `action == "busy"`: surface the message verbatim and let the
  user retry.

## 4. Tick driver loop

After a successful handoff the main session owns nothing but the
metronome. Loop:

1. Invoke

   ```bash
   <codenook> tick --task <T-NNN> --json
   ```

2. Read the `status` field from the JSON envelope. Treat it as
   opaque — the only branches the main session needs are:

   * `advanced` — work happened; loop again.
   * `waiting` — a sub-agent or external signal is pending; stop
     polling, then check the HITL queue (see §5).
   * `done` — terminal success; report the opaque status to the
     user and exit the loop.
   * `blocked` — terminal failure or operator action required;
     report the opaque status (and any `message_for_user` field,
     verbatim) to the user and exit the loop.

3. Do NOT peek into phase outputs, role files, or any artifact the
   tick produces. The tick's job is to dispatch performers; the main
   session's job is to keep the clock ticking.

## 5. HITL relay

When the tick returns `waiting`, scan
`<ws>/.codenook/hitl-queue/*.json` for entries whose `decision` is
`null`. For each such entry:

1. **MANDATORY channel-choice ask.** Before relaying ANY HITL gate
   prompt, you MUST first issue exactly one `ask_user` (or
   equivalent) with two choices — `terminal` (default) and `html` —
   to let the user pick the channel for this gate. This step is
   non-negotiable: do NOT skip it, do NOT inline it into a later
   question, do NOT decide on the user's behalf. Any answer other
   than `html` is treated as `terminal`. The ONLY case in which you
   may skip the ask is when no shell wrapper is reachable in your
   runtime (so `html` cannot be honoured anyway); in that case use
   `terminal` unconditionally.

2. **Relay the prompt.**
   - `terminal` — read the entry JSON and show the `prompt` field
     verbatim to the user. Do not interpret the gate, do not
     editorialise, do not suggest an answer.
   - `html` — render the gate as a self-contained file and
     **auto-open it in the default browser** with `--open`:

     ```bash
     <codenook> hitl render --id <hitl-entry-id> --open
     ```

     The CLI writes the file, prints its path, then opens it via
     `open` (macOS) / `xdg-open` (Linux) / `start` (Windows). Then
     collect the decision back in the terminal as usual.

3. Capture the user's free-form answer and submit:

   ```bash
   <codenook> hitl decide --id <hitl-entry-id> --decision <answer>
   ```

4. When all open gates are resolved, resume the tick loop (§4).

## 6. Termination

The protocol terminates when any of:

* The user explicitly cancels.
* The router-agent reply signals `action == "handoff"` and the
  subsequent tick loop reaches `done` or `blocked`.
* The task `state.json` reaches a terminal phase (`done`,
  `cancelled`, `error`).
* The user issues an explicit stop instruction.

## 7. Hard rules (forbidden)

The main session's domain budget is zero. The following are strictly
prohibited; violations are bugs in the conductor:

* The main session MUST NOT read `plugins/*/plugin.yaml`,
  `plugins/*/knowledge/`, `plugins/*/roles/`, or `plugins/*/skills/`.
* The main session MUST NOT mention plugin names by id (`development`,
  `writing`, `generic`) or any other plugin identifier in its own
  prose.
* The main session MUST NOT inspect the `applies_to`, `keywords`, or
  `domain_description` fields of any plugin manifest.
* The main session MUST NOT modify `router-context.md`,
  `draft-config.yaml`, or `state.json` directly. Mutations happen
  exclusively through `spawn.sh`, `orchestrator-tick`, and
  `hitl-adapter`.
* The main session MUST NOT spawn phase agents (clarifier, designer,
  implementer, tester, validator, acceptor, reviewer) directly. That
  is `orchestrator-tick`'s responsibility.
* The main session MUST NOT inspect, summarise, or otherwise interpret
  the contents of `router-reply.md`, the HITL `prompt` field, or any
  per-phase output. These are opaque payloads to be relayed.

If a task ever appears to require the main session to break one of
these rules, escalate by surfacing the problem to the user instead of
working around the rule.

## 8. Anti-pattern reference

The block below is shown only as an example of behaviour the main
session must never exhibit. It is fenced as `forbidden` so the linter
ignores its contents.

```forbidden
# DO NOT do this from the main session:
cat plugins/generic/plugin.yaml
cat plugins/development/roles/implementer.md
# DO NOT pick a plugin or role from main session prose:
"I think the writing plugin's clarifier role suits this task."
```

---

## Context watermark protocol

The main session must periodically self-estimate context usage (heuristic:
local token estimate, CJK 1:1, ASCII 1:4). When the estimate reaches the
80% model window watermark, follow this protocol to avoid losing task
knowledge to context overflow:

1. **Stop new feature work** — do not spawn new sub-agents and do not
   open new files for reading.
2. **Sediment current task knowledge** — for each active task ID, call:
   `<codenook> extract --task <T-NNN> --reason context-pressure`
   This command asynchronously dispatches knowledge / skill / config
   extractors in a subprocess, returns within ≤ 200ms wall-clock, and
   does not block the main session.
3. **Compact or reset** — based on the `enqueued_jobs` count in the
   returned JSON, decide whether to trigger `/clear` or `/compact`, and
   resume from work already recorded in memory if needed.

The main session is **not allowed** to scan any file under
`.codenook/memory/` directly; it can only rely on the exit JSON from
`<codenook> extract --reason context-pressure` and forward it as a
string to the user. The full watermark protocol (path A / path B,
idempotency keys, `MEMORY_INDEX` injection, `extraction-log.jsonl`
audit semantics, context-pressure event type) is documented in
`docs/memory-and-extraction.md` §5 / §8.

---

## Linter

The rules above are enforced by
`<ws>/.codenook/codenook-core/skills/builtin/_lib/claude_md_linter.py`
(or `skills/codenook-core/skills/builtin/_lib/claude_md_linter.py` when
viewed from inside the source repository). The bats suite runs the
linter against this file on every test run; any new domain-aware token
added to the protocol section will fail the build.
