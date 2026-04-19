# CodeNook — repository-level main session guide

> This file is read by the **main session** (the conductor) on entry to
> the repository. It documents the protocol the main session must
> follow when handling user task requests in CodeNook v6.
>
> The main session is a **pure protocol conductor**: it relays
> messages, drives an opaque tick loop, and brokers HITL gates. It is
> intentionally domain-agnostic. All task-creation domain reasoning
> lives behind the router-agent skill; all per-phase work lives behind
> `orchestrator-tick`.
>
> Canonical layering reference: `docs/v6/router-agent-v6.md` §2.

---

## v6 task lifecycle protocol (domain-agnostic)

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
* DO invoke the router-agent spawn entry once:

  ```bash
  skills/codenook-core/skills/builtin/router-agent/spawn.sh \
      --workspace <ws> \
      --task-id <new-T-NNN>
  ```

* The spawn entry returns a single-line JSON envelope of the form
  `{"action": "...", "task_id": "...", "prompt_path": "...", "reply_path": "...", ...}`.
  Read the `prompt_path` file, dispatch a sub-agent (Task tool /
  sub-agent dispatch) using that prompt as the system prompt, and
  when the sub-agent finishes, read the `reply_path` file and show
  its contents verbatim to the user.
* The main session does not paraphrase, summarise, or annotate the
  router-agent's reply.

## 2. On each user follow-up turn

When the user replies during an open drafting dialog:

* Persist the user's exact utterance to a scratch file
  (`tasks/<T-NNN>/.user-turn.txt` or similar).
* DO invoke spawn again with the existing task id and the turn file:

  ```bash
  spawn.sh --task-id <T-NNN> --workspace <ws> \
           --user-turn-file <path-to-user-turn-text>
  ```

* Run the same dispatch loop: read `prompt_path`, dispatch a fresh
  sub-agent with that prompt, read `reply_path`, relay verbatim.
* DO NOT interpret the reply. Do not summarise. Do not add domain
  commentary. The reply is an opaque string from the main session's
  point of view.

## 3. On user confirmation

When the user explicitly confirms (e.g. "go", "confirm", "approve",
"ship it"):

* DO invoke spawn in confirm mode:

  ```bash
  spawn.sh --task-id <T-NNN> --workspace <ws> --confirm
  ```

* On `action == "handoff"`: the draft is frozen, `state.json` is
  materialised, and the first tick has run. Enter the tick driver
  loop (see §4).
* On `action == "error"` with `code == "draft_invalid"`: show the
  `errors` array verbatim to the user and return to step 2 (continue
  the dialog by collecting the next user turn and calling spawn
  again).
* On `action == "busy"`: surface the message verbatim and let the
  user retry.

## 4. Tick driver loop

After a successful handoff the main session owns nothing but the
metronome. Loop:

1. Invoke

   ```bash
   skills/codenook-core/skills/builtin/orchestrator-tick/tick.sh \
       --task <T-NNN> --workspace <ws> --json
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

* Read the entry JSON.
* Show the `prompt` field verbatim to the user. Do not interpret the
  gate, do not editorialise, do not suggest an answer.
* Capture the user's free-form answer.
* Invoke

  ```bash
  skills/codenook-core/skills/builtin/hitl-adapter/terminal.sh decide \
      --id <hitl-entry-id> --decision <answer>
  ```

* When all open gates are resolved, resume the tick loop (§4).

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

## 上下文水位监控 (M9.2)

主会话需要周期性自评估上下文使用率（启发式：本地估算 token，CJK 1:1，
ASCII 1:4）。当估算 ≥ 80% model window 水位时（water-mark），按以下协议
处理，避免上下文溢出导致丢失任务知识：

1. **停止新功能工作**——不再启动新的 sub-agent / 不再展开新文件读。
2. **沉淀当前任务知识**——对每个 active task ID 调用一次：
   `bash skills/codenook-core/skills/builtin/extractor-batch/extractor-batch.sh \
       --task-id <T-NNN> --reason context-pressure --workspace <ws>`
   该命令在子进程异步派发 knowledge / skill / config 三类 extractor，
   wall-clock ≤ 200ms 返回，不阻塞主会话。
3. **压缩或重置自身**——根据返回 JSON 的 `enqueued_jobs` 数量决定是否
   触发 `/clear` 或 `/compact`，必要时 resume 已记录在 memory 中的工作。

主会话**不允许**直接扫描 `.codenook/memory/` 下任何文件；只能依赖
`extractor-batch.sh --reason context-pressure` 的退出 JSON 当字符串转给
用户。完整水位触发协议（路径 A / 路径 B、幂等键、`MEMORY_INDEX` 注入、
`extraction-log.jsonl` 审计语义、context-pressure 事件类型）见
`docs/v6/memory-and-extraction-v6.md` §5 / §8。

---

## Linter

The rules above are enforced by
`skills/codenook-core/skills/builtin/_lib/claude_md_linter.py`. The
bats suite runs the linter against this file on every test run; any
new domain-aware token added to the protocol section will fail the
build.
