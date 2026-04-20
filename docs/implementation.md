# CodeNook — 实现文档（Implementation Plan）

> **状态**：基于已定稿的 `architecture.md`（§1–§12）落地为可运行代码与文件的实现指南。本文档**只讲怎么做**，不复述设计动机；每节末尾以 `→ 设计依据：架构文档 §X.Y` 形式回指。
>
> **v0.11.2 落地附注（DR-003）**：本文档中所有 `init.sh --install-plugin` / `--pack-plugin` / 类同子命令均为目标态设计。在 v0.11.2 仅 `--version` / `--help` / `--refresh-models` 已落地（`✅`），其余仍为 `exit 2: TODO` 占位（`🚧 v0.12 计划`）。当前可用的安装路径为顶层 `bash install.sh <workspace_path>`，内部委派 `skills/codenook-core/install.sh` 跑同样的 12 关。
>
> **范围约定**：
> - 单 workspace 模型，所有路径都是 `<workspace>/.codenook/...` 相对路径
> - 不写时间估计；以"依赖排序"组织 Milestone
> - 全部交付物落在一个 git 仓库（建议命名 `cintia09/codenook`），其中 `skills/codenook-core/` 作为可被 `init.sh` 拷贝出来的内核源
>
> → 设计依据：架构文档 §2、§9

---

## 目录

- [第一部分：实现路线图](#第一部分实现路线图)
- [第二部分：逐 Milestone 实现细节](#第二部分逐-milestone-实现细节)
- [第三部分：关键文件骨架](#第三部分关键文件骨架)
- [第四部分：v5 → v6 代码迁移映射表](#第四部分v5--v6-代码迁移映射表)
- [第五部分：依赖图](#第五部分依赖图)
- [第六部分：Definition of Done（验收脚本）](#第六部分definition-of-done验收脚本)
- [附录 A：架构文档需要补充的歧义](#附录-a架构文档需要补充的歧义)

---

## 第一部分：实现路线图

按依赖顺序划分 7 个 Milestone（M1 → M7）。每个 Milestone 给"交付物 / 依赖 / 验收口径"三件套。

### M1 — 内核骨架（Core Skeleton）

**交付物**
- `skills/codenook-core/` 仓库目录，含：
  - `core/shell.md`（≤3K，main session 唯一加载）
  - `agents/builtin/`（router / distiller / security-auditor / hitl-adapter / config-mutator 的 `*.agent.md`，先放占位）
  - `skills/builtin/`（orchestrator-tick / session-resume / config-resolve / config-validate / secrets-resolve / sec-audit / dispatch-audit / preflight / secret-scan / model-probe / task-config-set 的 `SKILL.md` 占位）
  - `plugins/generic/`（builtin generic plugin 的最小完整实现）
- `init.sh` 框架（命令分发能跑通，但 `--install-plugin` 还只是占位）
- `templates/CLAUDE.md`（指向 `.codenook/core/shell.md`）

**依赖**：无（起点）

**验收口径**
1. 在空目录跑 `./init.sh`，生成 `.codenook/` 完整骨架
2. `.codenook/core/shell.md` 行数实测 ≤ 3000 字符
3. `.codenook/plugins/generic/plugin.yaml` 通过 `yamllint`
4. `./init.sh --list-plugins` 输出唯一一行 `generic 0.1.0 builtin`

→ 设计依据：架构文档 §2.1、§3.1.5、§3.2.7、§6

**M1 简化口径**：M1 的 `config-resolve` 暂不读 plugin `config-schema.yaml` 的 `x-merge` 注解，统一按"deep-merge + 列表 replace"实现（足以通过 F-031）；schema-driven merge（`replace | deep | append` 三态）于 M5 启用，见 M5 DoD。M1 的 `model-probe` 必须实现"无 `--catalog` 时的默认位置解析与自动写回"算法（见 §3.5.1.2）。

---

### M2 — Plugin 安装管线（Install Pipeline）

**交付物**
- `init.sh --install-plugin <path-or-url>` 全功能：resolve → stage → 12 gates → 安全扫描 → mount
- `init.sh --remove-plugin <name>` / `--reinstall-plugin <name>` / `--list-plugins`
- `init.sh --scaffold-plugin <name>` / `--pack-plugin <dir>`
- `init.sh --uninstall-plugin <name>`（归档 `memory/<p>/`）
- `--force` 升级 + 旧版本归档到 `history/plugin-versions/`
- 12-gate validator（每 gate 一个独立函数，便于测试）
- 安全扫描器（复用 `skills/builtin/sec-audit/` + `secret-scan/`）
- `history/plugin-installs.jsonl` 记录

**依赖**：M1

**验收口径**
1. 用 `--scaffold-plugin foo` → `--pack-plugin ./foo-plugin/` 产出 `foo-0.1.0.tar.gz`
2. `--install-plugin ./foo-0.1.0.tar.gz` 成功，落到 `.codenook/plugins/foo/`
3. 故意构造 12 个失败用例（每 gate 一个），分别 abort 并输出对应错误码
4. 安全扫描的 7 类规则各有 1 个红用例可被拒绝
5. `--remove-plugin foo` 后 `memory/foo/` 被归档为 `memory/.archived/foo-<ts>/`
6. **`--install` 完成后自动触发 `model-probe`**（首次安装 / catalog 不存在时），写入 `state.json.model_catalog`；后续安装在 TTL 未到时跳过 probe

→ 设计依据：架构文档 §7.2 – §7.6、§3.2.8

---

### M3 — Router + 自扫描

**交付物**
- `agents/builtin/router.agent.md` 的完整 self-bootstrap 协议
- Router 输出 schema 校验（在 `skills/builtin/router-verdict-schema.json`）
- `config.yaml` 的 `router:` 段解析（confidence_threshold / auto_fallback）
- `history/router-decisions.jsonl` 落盘
- Main session 在 `shell.md` 中的"派 router"dispatch 模板

**依赖**：M1（agents 目录就位）、M2（至少要能装 plugin 来测多候选）

**验收口径**
1. 装 `development` + `writing` 两个 plugin 后，给出"写一篇关于 RAG 的博客"的输入，router 返回 `plugin: writing`，confidence ≥ 0.75
2. 输入"实现一个 Python CLI"，router 返回 `plugin: development`
3. 输入"今天天气不错"，router 返回 `plugin: generic`
4. 故意把 confidence 阈值调到 0.99，观察 main session 触发 ask_user

→ 设计依据：架构文档 §4 – §4.2

---

### M4 — Orchestrator-tick + Session-resume

**交付物**
- `skills/builtin/orchestrator-tick/SKILL.md` + 实现脚本（`tick.sh` 或被 sub-agent 直接执行的伪代码）
- `skills/builtin/session-resume/SKILL.md` + 实现脚本
- `tasks/T-NNN/state.json` 的写入/读取
- `queue/`、`locks/`、`hitl-queue/` entry schema
- `history/orchestrator-log.jsonl` 落盘
- HITL adapter（terminal.sh）打通

**依赖**：M1（builtin skills 目录）、M3（router 决定后才能创建 task）

**验收口径**
1. 创建 T-001（generic plugin），跑 1 次 tick → state.phase 从 `null` 推进到 `clarify` 并 dispatch 出 clarifier
2. 模拟 clarifier 写出 `phase-1-clarifier-summary.md`，再跑 tick → 推进到 `analyze`
3. 触发一次 HITL gate，hitl-queue/ 写入决策文件，approval 后 tick 推进
4. 关闭会话 → 重开 → main session 派 session-resume，输出 ≤500 字摘要含 `T-001`

→ 设计依据：架构文档 §3.1.3、§3.1.4、§3.1.7

---

### M5 — 模块化子系统落位（Memory / Skills / Config / History）

**交付物**
- `skills/builtin/config-resolve/SKILL.md` + 4 层合并算法 + **第 5 步 tier 符号展开** + `_provenance` 输出（§3.2.4.1 / §3.2.4.2）
- `skills/builtin/config-validate/SKILL.md` + plugin 的 `config-schema.yaml` 校验
- `skills/builtin/secrets-resolve/SKILL.md`（读 `.codenook/secrets.yaml` 注入 env）
- `skills/builtin/model-probe/SKILL.md`：探测来源（runtime API → env var → 兜底）+ 写 `state.json.model_catalog`（含 available[] + resolved_tiers，30 天 TTL）
- `skills/builtin/task-config-set/SKILL.md`：自然语言驱动 task 级 model override（get/set 两种模式；写 `tasks/T-NNN/state.json.config_overrides.models.<role>` + 同步 `history/config-changes.jsonl`）
- Memory 路由：distiller agent 按 `plugin.yaml.knowledge.produces` 决定写哪一层
- Skills 路由：plugin-shipped vs workspace-custom vs plugin-local 的查找顺序
- History 单时间线 + plugin tag 的 jsonl 工具函数
- Config-mutator agent 的实现

**依赖**：M4（tick 调用 config-resolve）

**验收口径**
1. 在 `config.yaml.plugins.development.overrides.models.reviewer` 设 `tier_balanced`，sub-agent self-bootstrap 拿到的 effective config `models.reviewer` 解析为 catalog 中 balanced 档第一个可用模型字面 id
2. distiller 在 development 下产出"使用 pytest 的约定"知识 → 落到 `memory/development/by-topic/`，不污染 writing
3. 故意在 overrides 里写一个 schema 不认识的 key → `config-validate` 报错并指出 path
4. config-mutator 修改 reviewer 模型 → `history/config-changes.jsonl` 追加一行带 `actor: distiller`
5. **`init.sh --refresh-models` 跑通** → `state.json.model_catalog` 写入 / 包含 `refreshed_at` / `runtime` / `available[]` / `resolved_tiers.{strong,balanced,cheap}` 三档全部解析；30 天后自动触发刷新
6. **`task-config-set set task=T-007 role=reviewer model=tier_cheap`** → `tasks/T-007/state.json.config_overrides.models.reviewer` 写入；`config-resolve task=T-007` 的 effective `models.reviewer` 反映该值；`history/config-changes.jsonl` 追加 `{actor:user, scope:task}` entry
7. **Router 默认模型解析**：在 mock catalog 下，默认 router agent 走 `tier_strong`，最终 literal id 等于 `model_catalog.resolved_tiers.strong`；用户在 `defaults.models.router` 显式写 `tier_cheap` 后，re-resolve 反映为 cheap 档
8. **`config-resolve` 输出含 `_provenance`**：每个 `models.<role>` 字段带 `{value, from_layer, symbol, resolved_via}`，多层覆盖时 `from_layer` 为最高层号

8. **`config-resolve` 升级为 schema-driven merge**：按 plugin `config-schema.yaml` 的 `x-merge` 注解执行 `replace | deep | append` 三态语义（替代 M1 的"deep-merge + 列表 replace"简化实现）；F-053（M5 deferred case）通过

→ 设计依据：架构文档 §3.2 全节、§3.2.4.1、§3.2.4.2

---

### M6 — 第一个真实 plugin：development（基于 v6 plugin 框架；历史上从 v5 codenook-v5-poc 设计提取，v5 源码已于 v0.11.1 移除）

**交付物**
- `plugins/development/` 完整目录（架构 §5.0 全套文件）
- `plugin.yaml` 含 keywords / examples / anti_examples / data_layout: external
- `phases.yaml`：clarify → design → plan → implement → test → accept → validate → ship
- `transitions.yaml`：v5 路由表的端口
- `roles/{clarifier,designer,planner,implementer,tester,reviewer,acceptor,validator}.md`
- `entry-questions.yaml` + `hitl-gates.yaml`
- `manifest-templates/phase-N-<role>.md`
- `validators/post-implement.sh` 等
- `skills/test-runner/`（plugin-shipped）
- `config-defaults.yaml` + `config-schema.yaml`
- `examples/` 至少 1 个种子任务
- 打成 tarball：`development-0.1.0.tar.gz`
- v5 E2E 压力测试在 v6 + development plugin 下可重放

**依赖**：M2（要能装）、M3（要能 router 命中）、M4（tick 要能驱动其 phase）、M5（config 路由要工作）

**验收口径**
1. `--install-plugin development-0.1.0.tar.gz` 成功，12 gates 全过
2. 输入"为 xueba CLI 添加 --tag 过滤"→ router 命中 development → 进入 clarify
3. 完整跑完 8 个 phase，最终 state.status = `done`
4. 与 v5 E2E 报告对照 artifacts 一致（phase 输出文件名、verdict 序列）

→ 设计依据：架构文档 §5、§9.2

---

### M7 — Generic plugin（实例化）+ Writing plugin（demo）

**交付物**
- `plugins/generic/`：4-phase（clarify → analyze → execute → deliver），data_layout: none
- `plugins/writing/` 完整 plugin：phases = outline → draft → edit → review → publish
  - `data_layout: workspace`，写到 `<workspace>/articles/`
  - hitl-gates: `[accept]`
  - 至少 1 个种子样例
- 多 plugin 共存的 E2E：在同一 workspace 同时跑 development + writing 任务

**依赖**：M6（同样的 plugin 框架）

**验收口径**
1. 不带任何业务关键字的输入（如"帮我列一下今天要做的事"）→ router 命中 generic
2. 给 writing 输入"写一篇关于 RAG 的中文博客"→ 进入 outline，最终 publish 到 `<workspace>/articles/<slug>.md`
3. 同时跑 T-007 (development) 和 T-008 (writing)，queue/ 中 entry 都带 plugin tag，dashboard `jq` 可分组
4. `init.sh --uninstall-plugin writing` 后 development 任务不受影响

→ 设计依据：架构文档 §6、§3.2.5、§3.2.6、§9.5

---

### M8 — Conversational Router Agent

> Replaces M3 `router-triage` + M7 `_lib/router_select.py` shim with a stateless
> subagent + file-backed memory that holds a multi-turn dialog, consults
> knowledge, drafts a task config for explicit user confirmation, and hands
> off to `orchestrator-tick` itself. Canonical spec:
> [`docs/router-agent.md`](./router-agent.md). Ratified decisions
> #46–#52 (architecture §12) are non-negotiable across all M8.x.

**依赖**：M4（tick contract stable）、M5（config-resolve / config-validate ready）、M7（`_lib/router_select.py` available for reuse）

#### M8.0 — Spec doc

**Scope**: Author the canonical router-agent spec; align architecture §4 / §12 and this implementation doc.

**Deliverables**:
- `docs/router-agent.md` — full spec (motivation, domain layering, lifecycle, schemas, prompt contract, concurrency, knowledge, handoff, termination, removal, open items).
- `docs/architecture.md` §4 — banner pointing at the new doc; new §4.3 "Domain layering"; decisions #46–#52 appended to §12.
- `docs/implementation.md` — this M8 section (M8.0–M8.8).

**DoD**:
1. New spec doc exists and is referenced from architecture §4 and §12.
2. Architecture §4.3 lists the four-layer table and the four hard rules.
3. Decisions #46–#52 present in architecture §12 with cross-references.
4. No code under `skills/` or `plugins/` is modified.

→ 设计依据：`docs/router-agent.md` §1–§11

#### M8.1 — Schemas + filesystem layout

**Scope**: Lock down the four task-local files (`router-context.md`, `draft-config.yaml`, `router-reply.md`, `router.lock`) and ship the read/write helpers.

**Deliverables**:
- JSON-Schema-lite definitions for `router-context.md` frontmatter and `draft-config.yaml` (validated via `_lib/jsonschema_lite.py`).
- `_lib/router_context.py`: read frontmatter + body; append a turn (atomic via temp-file + rename); mutate frontmatter (`turn_count++`, `decisions[].append`, `state` transitions); write/rewrite `draft-config.yaml` with `_draft_revision` bump.
- `_lib/router_reply.py`: write `router-reply.md` with optional `awaiting:` frontmatter.
- bats: schema validation (positive + negative); atomic-append survives concurrent readers; frontmatter integrity after `decisions[]` append; `_draft_revision` monotonicity.

**DoD**:
1. All four schemas in `docs/router-agent.md` §4 round-trip through the helpers without loss.
2. A malformed `state` value or unknown frontmatter key is rejected with a `path`-tagged error.
3. Concurrent append from two processes never produces a partial write (verified by a bats stress loop).

→ 设计依据：`docs/router-agent.md` §4

#### M8.2 — `router-agent` skill (subagent prompt + spawn entry)

**Scope**: The skill the main session invokes. Defines the subagent's system prompt and the dispatch entry point.

**Deliverables**:
- `skills/codenook-core/skills/builtin/router-agent/SKILL.md` — skill descriptor + invocation contract.
- `skills/codenook-core/skills/builtin/router-agent/spawn.sh` — main-session-callable CLI: `spawn.sh --task <tid>`. Acquires lock (delegated to `_lib/task_lock.py`, M8.4), dispatches the subagent, reads its JSON exit, releases lock, prints JSON to stdout.
- `skills/codenook-core/skills/builtin/router-agent/prompt.md` — long-form system prompt enforcing the §5 contract (read context → enumerate plugins → enumerate knowledge → decide → write reply → optionally handoff → exit JSON).
- `dispatch_subagent.sh` adapter abstraction (with at least a Claude-Task-tool adapter; Copilot CLI adapter stubbed; plain-shell adapter as fallback). Open item from §11.
- Pin per-turn caps in prompt: knowledge ≤20 docs/turn (§7.3), no extra `orchestrator-tick` invocations.
- bats: `spawn.sh` CLI contract (exit codes, JSON shape); prompt template renders without unbound vars; missing task dir → clear error.

**DoD**:
1. `spawn.sh --task T-XXX` returns within budget and prints exactly one JSON line on stdout matching `{action: reply|handoff|cancelled, …}`.
2. Prompt template covers all 9 items in §5 verbatim or by structural equivalent.
3. With a stub subagent that only echoes a fixed reply, end-to-end spawn → reply → release lock works.

→ 设计依据：`docs/router-agent.md` §3, §5, §11

#### M8.3 — Knowledge + plugin discovery within router agent

**Scope**: The two index helpers the router-agent calls during a turn. These helpers are router-private — main session must not import them (enforced by §M8.6 lint).

**Deliverables**:
- `_lib/plugin_manifest_index.py`: enumerate `<workspace>/.codenook/plugins/*/plugin.yaml`; expose `{id, summary, applies_to, keywords, examples, anti_examples, routing.priority, data_layout, data_root, config_schema_path}`. Skip plugins listed in `config.yaml.plugins.disabled`. Always include builtin `generic` last.
- `_lib/knowledge_index.py`: enumerate workspace + plugin-shipped knowledge (read-only ToC); on-demand body fetch via `read(path)`; raises `KnowledgeBudgetExceeded` after the 20th body fetch in a single helper-instance lifetime.
- `_lib/router_select.py`: M7 helper repurposed; CLI entry removed; Python API `score(input, catalog) → [{plugin, score, rationale}]` retained.
- bats: index correctness with 3 plugins installed (generic + 2 fixtures); disabled plugin omitted; per-turn knowledge cap raises after 20 reads; ToC fetch does not count against the cap.

**DoD**:
1. With `development` + `writing` + `generic` installed, the catalog returns three entries in priority+generic-last order.
2. ToC for a fixture workspace returns the expected paths and titles.
3. The 20-doc cap is enforced and surfaces a structured error to the router prompt.

→ 设计依据：`docs/router-agent.md` §5, §7

#### M8.4 — Concurrency + lock

**Scope**: Per-task fcntl lock with stale recovery; no cross-task blocking.

**Deliverables**:
- `_lib/task_lock.py`: `acquire(task_id, *, blocking=True, timeout=60, stale_after=300)` and `release(task_id)`. Lock target is `tasks/<tid>/router.lock`; payload is the JSON described in §4.4. Stale recovery: if `started_at` older than `stale_after` AND `pid` not alive on local `hostname`, force-release and retry once.
- Main-session-side wait budget: 60s default (configurable via `config.yaml.router.lock_wait_seconds`).
- bats: two parallel `spawn.sh` invocations on the **same** task → second blocks until first exits; two parallel invocations on **different** tasks → both run concurrently; killed-holder simulation → stale recovery succeeds after the 5-min threshold (test uses a low override).

**DoD**:
1. Concurrent same-task contention always serialises with no lost turns.
2. Cross-task contention never blocks.
3. Stale lock with dead pid is recovered automatically; stale lock with live pid is respected.

→ 设计依据：`docs/router-agent.md` §6

#### M8.5 — Handoff to orchestrator

**Scope**: The single turn on which the router-agent crosses from drafting to materialising state.

**Deliverables**:
- Handoff branch in `prompt.md` enforcing the §8.1 sequence (validate draft → strip `_draft*` → call `init-task` → update frontmatter → call `orchestrator-tick` once → capture status → write final `router-reply.md` → exit JSON with `action: handoff, tick_status, next_phase`).
- `init-task` invocation contract: `init-task --task <tid> --plugin <p> --config <path>` writes `state.json` with `phase: null, plugin: <p>, config: …, status: ready`.
- bats: full draft → confirm → handoff path. Asserts `state.json` materialised with the expected `config` block, `draft-config.yaml._draft` is no longer present in `state.json.config`, first tick status is captured in the exit JSON, and `router-context.md.state == confirmed`.

**DoD**:
1. After handoff, `tasks/<tid>/state.json` exists and validates against the M4 task schema.
2. Exactly one `orchestrator-tick` invocation occurs in the handoff turn.
3. The router-agent does not modify `state.json` after handoff (verified by mtime check across a no-op subsequent attempt).

→ 设计依据：`docs/router-agent.md` §8

#### M8.6 — Main session protocol (CLAUDE.md) + domain-layering linter

**Scope**: Update the main session's behavioural contract to be **domain-agnostic**, and add a lint test that mechanically enforces it.

**Deliverables**:
- `templates/CLAUDE.md` updates:
  - "New task" intent → MUST spawn `router-agent` (no plugin / knowledge inspection by main session).
  - User-turn relay protocol: write user turn to `router-context.md`, spawn, read `router-reply.md`, relay verbatim.
  - HITL relay: read `hitl-queue/*.json`, show prompt verbatim, capture user answer, call `hitl-adapter terminal.sh decide`. No interpretation of gate semantics.
  - Tick driver loop: after `action: handoff`, poll `orchestrator-tick`; treat `status` (`advanced` / `waiting` / `done` / `blocked`) opaquely; never read `state.json` or phase artifacts.
  - Termination: confirm / cancel / cap reached / lock timeout.
- `tests/m8-domain-lint.bats`: scans `templates/CLAUDE.md` (and any shipped `core/shell.md`) for forbidden domain tokens (`plugins/`, `applies_to`, `keywords:`, `examples:`, `anti_examples`, `knowledge/`, `phases.yaml`, `transitions.yaml`, `hitl-gates.yaml`, plugin ids by name: `development`, `writing`, `generic`, helper module names: `router_select`, `plugin_manifest_index`). Fails the suite on any match outside fenced quote blocks.
- bats: happy-path simulation script (no real LLM) — drives 3-turn dialog via a stub subagent, asserts main-session-side state transitions.

**DoD**:
1. `tests/m8-domain-lint.bats` passes against the updated template.
2. The lint test fails as expected when a forbidden token is intentionally introduced (negative test).
3. Happy-path simulation (3 turns, confirm on turn 3) ends with `state.json` materialised and exit JSON `action: handoff`.

→ 设计依据：`docs/router-agent.md` §2, §3, §9

#### M8.7 — Remove router-triage

**Scope**: Decommission the M3 one-shot router and the public M7 router-select CLI.

**Deliverables**:
- Delete `skills/codenook-core/skills/builtin/router-triage/` (skill dir + any helper).
- Delete `tests/m3-router-triage.bats` and any other tests that import `router-triage`.
- Drop `_lib/router_select.py`'s CLI entry (if any); retain Python API for router-agent's internal use.
- Search-and-update any docs / examples / scaffolding references to `router-triage` → `router-agent`.
- `history/router-decisions.jsonl` writer relocated into router-agent; entry schema gains `turn: int` and `kind: handoff|cancel`.

**DoD**:
1. `rg -n 'router-triage' skills/ plugins/ tests/` returns no hits.
2. Full bats suite passes (588 → adjusted count) with `router-triage` deleted.
3. `_lib/router_select.py` is no longer importable as a CLI entry.

→ 设计依据：`docs/router-agent.md` §10

#### M8.8 — Multi-turn E2E acceptance

**Scope**: Real CLI test in a clean workspace exercising the full conversational lifecycle alongside parallel tasks for isolation proof.

**Deliverables**:
- `tests/e2e/m8-router-agent.sh`:
  - Init a workspace; install `development` + `writing` plugins.
  - Simulate main session driving a 3-turn dialog for task A (development): clarification → draft review → "go".
  - In parallel, drive a 2-turn dialog for task B (writing) on a different task id.
  - Assert: both `state.json`s materialised; both `draft-config.yaml`s frozen (no leftover `_draft: true` in state.json); first tick of each task advances; per-task lock files created and released; no cross-task blocking observed (timing assertion).
- Latency / token budget logging for §11 open item #2 (knowledge ToC caching).

**DoD**:
1. E2E script exits 0.
2. `tasks/T-A/state.json.config.plugin == "development"` and `tasks/T-B/state.json.config.plugin == "writing"`.
3. `tasks/T-A/router-context.md.state == confirmed` and `turn_count == 3`; same shape for T-B.
4. Combined wall-clock for parallel run ≤ 1.2× the slower task's serial run (loose isolation check).

→ 设计依据：`docs/router-agent.md` §3, §6, §8, §9

---

### M9 — Memory Layer + LLM-driven Extraction

> 在 M8 conversational router-agent 之上引入**唯一可写的项目记忆层**
> （`<workspace>/.codenook/memory/`）+ **三类自动抽取器**（knowledge /
> skills / config），把任务执行中沉淀的资产以 patch-first 方式吸收回
> 项目。Canonical spec：
> [`docs/memory-and-extraction.md`](./memory-and-extraction.md)；
> 决策 #53–#59（架构 §13）非协商。M9 是 greenfield 子系统。

**依赖**：M4（tick contract）、M5（config-resolve / secret-scan）、M8（router-agent + spawn.sh）

#### M9.0 — Spec doc

**Scope**：交付 M9 单一规范源；同步架构 §13 与本文 M9 段。

**Deliverables**：
- `docs/memory-and-extraction.md`（≥ 600 行；14 节）
- `docs/architecture.md` §13「Memory Layer (M9)」+ 决策 #53–#59
- 本节（M9.0–M9.8）

**DoD**：
1. spec doc 存在并被架构 §13 引用
2. 决策 #53–#59 在架构 §12 / §13 中可定位
3. `skills/`、`plugins/` 下无代码改动
4. 关联 AC：AC-DOC-1, AC-DOC-2

→ 设计依据：`docs/memory-and-extraction.md` §1–§14

#### M9.1 — Memory 布局 + `_lib/memory_layer.py`

**Scope**：建立 memory 骨架与读 / 写 / 扫描 / patch 公共 API；引入元数
据索引（含 hash dedup 用）。

**Deliverables**：
- `skills/codenook-core/skills/builtin/_lib/memory_layer.py`：
  `init_memory_skeleton / scan_knowledge / read_knowledge / write_knowledge /
  patch_knowledge / replace_knowledge / promote_* / archive_* /
  scan_skills / read_skill / write_skill / patch_skill /
  read_config_entries / upsert_config_entry / match_entries_for_task /
  find_similar / has_hash / append_audit / scan_memory`（详见 spec §10）
- `skills/codenook-core/skills/builtin/_lib/memory_index.py`：
  mtime-cached 元数据索引；维护 hash 索引
- `init.sh`：在 init 时创建 `.codenook/memory/{knowledge,skills,history}/`
  + 空 `config.yaml`（`version: 1\nentries: []\n`）
- bats：`m9-memory-layer.bats`、`m9-memory-index.bats`
  - 原子写、并发写互斥
  - `find_similar` 阈值（tags 50% / title cosine 0.7）
  - 1000 文件下 `scan_memory` ≤ 500ms（NFR-PERF-1）
  - config.yaml 同 key 合并、重复 key 检测

**DoD**：
1. spec §3 / §4 schema round-trip 无损
2. AC-LAY-1 / AC-LAY-2 / AC-LAY-4 / AC-LAY-5 / AC-LAY-6 全绿
3. `_lib/workspace_overlay.py` 不再被任何运行时代码 import

→ 设计依据：spec §2、§3、§4、§10

#### M9.2 — 提取触发器（after_phase hook + 上下文水位协议）

**Scope**：把抽取调度接入 orchestrator-tick 与主会话；引入幂等键。

**Deliverables**：
- `skills/codenook-core/skills/builtin/orchestrator-tick/_tick.py`：在 phase
  进入 terminal 状态（done / blocked）后调用 `after_phase` hook
- `skills/codenook-core/skills/builtin/extractor-batch/extractor-batch.sh`：
  接受 `--task-id` 与 `--reason` 两参；按
  `(task_id, phase, reason)` 哈希幂等；异步派生子进程；返回 JSON
  `{enqueued_jobs: [...], skipped: [...]}`
- 根 `CLAUDE.md` 新段：主会话上下文 80% 水位监听协议（AC-TRG-3 / AC-DOC-3）
- bats：`m9-tick-after-phase.bats`、`m9-extractor-batch.bats`
  - hook 在 phase=done 后被调用一次（mock 验证）
  - 同 task 同 phase 重复触发只产生一次有效抽取（AC-TRG-2）
  - extractor 失败不阻塞 tick 退出（AC-TRG-4）
  - CLAUDE.md linter 通过（M8.6 词表已包含 memory token）

**DoD**：
1. AC-TRG-* 全绿
2. CLAUDE.md 通过域无关 linter
3. extractor-batch 调度即返回，不阻塞 orchestrator-tick

→ 设计依据：spec §5

#### M9.3 — Knowledge extractor（含 patch-or-create 决策流）

**Scope**：第一个抽取器，承载 patch-first 决策流的参考实现。

**Deliverables**：
- `skills/codenook-core/skills/builtin/knowledge-extractor/`：SKILL.md +
  CLI 入口 + LLM judge prompt 模板
- 强约束 frontmatter（summary ≤ 200，tags ≤ 8）+ slug 派生
- `find_similar()` + LLM judge merge / replace / create（默认 merge）
- per-task 上限 ≤ 3；hash dedup（前 512 chars）
- secret-scan 集成（fail-close）
- audit log 写 `memory/history/extraction-log.jsonl`
- bats：`m9-knowledge-extractor.bats`、`m9-knowledge-merge.bats`
  - 单 CLI 调用产出合规文件（AC-EXT-1）
  - mock LLM 抛错不阻塞任务（AC-EXT-4）
  - secret-scanner 命中拒绝写入（AC-EXT-5）
  - 已有 tags 重叠 ≥ 50% 时调 LLM 判定（AC-EXT-MERGE-1）
  - 判定理由进 audit log（AC-EXT-MERGE-2）
  - hash 命中直接 dedup（AC-EXT-MERGE-4）

**DoD**：
1. AC-EXT-1, AC-EXT-4, AC-EXT-5, AC-EXT-MERGE-1/2/4 全绿
2. patch 决策流可被 M9.4 / M9.5 共用（提取为 `_lib/extract_decision.py`）

→ 设计依据：spec §3.1、§6、§7

#### M9.4 — Skill extractor

**Scope**：检测重复脚本/命令模式 ≥ 3 次 → 提案 candidate skill。

**Deliverables**：
- `skills/codenook-core/skills/builtin/skill-extractor/`
- 复用 M9.3 的决策流；per-task 上限 ≤ 1
- bats：`m9-skill-extractor.bats`
  - ≥ 3 次重复才提案；< 3 次不提案（AC-EXT-2）
  - patch-first 行为同 M9.3

**DoD**：AC-EXT-2 + AC-EXT-MERGE-* 与 skill 相关条目全绿

→ 设计依据：spec §3.2、§6

#### M9.5 — Config extractor（单文件 entries 合并）

**Scope**：识别 `task-config-set` 调用产出的有效 fields → 落 config.yaml entries[]。

**Deliverables**：
- `skills/codenook-core/skills/builtin/config-extractor/`
- 同 key 合并为最新值（latest-wins，§4.2 规则）；per-task 上限 ≤ 5 entries
- 由 LLM 生成自然语言 `applies_when`（≤ 200 chars）
- bats：`m9-config-extractor.bats`
  - 同 key 合并不产生重复（AC-EXT-3 / AC-LAY-6）
  - applies_when 命中检测（与 router-agent mock 集成）
  - patch-first 决策流复用

**DoD**：AC-EXT-3 + AC-LAY-6 + 相关 AC-EXT-MERGE-* 全绿

→ 设计依据：spec §3.3、§4、§6

#### M9.6 — Router-agent 扫描升级 + Context 预算

**Scope**：router-agent 看见 memory；draft-config 加 `selected_memory`；
spawn.sh handoff 物化双层资产；引入 token 预算估算与裁剪。

**Deliverables**：
- `skills/codenook-core/skills/builtin/router-agent/prompt.md`：新增
  `## Memory index` section（§8 骨架）
- `skills/codenook-core/skills/builtin/_lib/token_estimate.py`：CJK 1:1、
  ASCII 1:4 启发式
- `draft-config.yaml` schema 扩展 `selected_memory.{knowledge,skills}` +
  `context_budget.{router_prompt_tokens,task_prompt_tokens}`（AC-SEL-3）
- `spawn.sh --confirm`：合成 plugins + memory 双层资产到任务 prompt
  context（AC-SEL-4 / spec §11.3）
- router-context 8 轮归档器 → `router-context-archive.md`（AC-BUD-3）
- knowledge ≤ 5、skills ≤ 3 默认上限（AC-SEL-6）
- config 中 `applies_when` 命中的 entry 无条件注入（AC-SEL-5）
- 自然语言修改选择集（FR-SEL-7）
- bats：`m9-router-memory-scan.bats`、`m9-context-budget.bats`
  - 100 fake knowledge + 50 turns 压力测试 router prompt ≤ 16K tokens
  - task prompt ≤ 32K，超出按 FR-BUD-3 优先级裁剪
  - 知识 body > 2KB 时只注入 summary + 路径（AC-BUD-4）

**DoD**：AC-SEL-* + AC-BUD-* 全绿；router 选择决策写
`memory/history/router-selection-log.jsonl`

→ 设计依据：spec §4.3、§8、§11

#### M9.7 — 插件只读 + linter 扩展

**Scope**：codify「plugins 运行时只读」+ 扩展主会话 linter 词表。

**Deliverables**：
- `skills/codenook-core/skills/builtin/_lib/plugin_readonly_check.py`：
  扫描代码路径中的写操作（`open(..., "w"|"a"|"x")`、`Path.write_*`、
  `shutil.copy`/`move` 等）目标是否在 `plugins/`
- M8.6 linter 词表扩展：禁止主会话 prompt / 回复出现 `memory/`、
  `extraction-log`、`MEMORY_INDEX` 等域 token
- bats：`m9-plugin-readonly.bats`、`m9-linter-memory.bats`
  - mock extractor 强行写 `plugins/` → 抛 `PermissionError`（AC-RO-2）
  - linter 拦截描述对 plugins/ 的写操作（AC-RO-3）

**DoD**：AC-RO-* 全绿

→ 设计依据：spec §2.1、§9

#### M9.8 — E2E + 发布 v0.9.0-m9.0

**Scope**：完整跑通 + 版本发布。

**Deliverables**：
- `tests/e2e/m9-e2e.bats`：
  - 用户 router 对话 → 任务 → tick → 自动抽取 → 二次任务 router 显示
    promoted 候选（AC-E2E-1）
  - 模拟 80% 信号 → extractor 异步运行 → memory 出现 candidate（AC-E2E-2）
  - 并行 3 任务 memory 写入互不冲突，audit log 完整（AC-E2E-3）
- `VERSION` → `0.9.0-m9.0`；`CHANGELOG.md` 完整记录 M9.0–M9.8
- tag `v0.9.0-m9.0`
- 全套 bats ≥ 760 全绿（M8 baseline 692 + M9 新增 ~70；AC-E2E-4）

**DoD**：spec §13 退出标准 1–7 全部满足

→ 设计依据：spec §1–§14

---

### M10 — Task Chains（父子链接 + 链感知 router 上下文）

> 在 M9 memory 层之上引入**任务父子链接**：新任务创建时由相似度
> 评分推荐 top-3 候选父任务；用户确认后，router-agent 在每次 spawn
> 时沿祖先链 LLM 摘要并注入 `{{TASK_CHAIN}}` slot。Canonical spec：
> [`docs/task-chains.md`](./task-chains.md)。M10 是 M9
> 的纯增量叠加：不修改 memory 语义、不改写 plugin 层、`parent_id` /
> `chain_root` 作为 `state.json` 的可选字段共存。

**依赖**：M4（state.json + tick）、M5（atomic / secret_scan）、
M8（router-agent + render_prompt 槽位机制）、M9（extract_audit logger
与 LLM mock 协议）

#### M10.0 — Spec doc

**Scope**：交付 M10 单一规范源；调研当前任务存储模型并锁定
schema 增量；在本文新增 M10 章节。

**Deliverables**：
- `docs/task-chains.md`（≥ 600 行；12 节 + 3 附录）
- 本节（M10.0–M10.7）

**DoD**：
1. spec doc 存在并完整覆盖 §1–§12 + 附录
2. greenfield grep 在新增 diff 上零命中（plan.md 列出的全部历史 token）
3. `skills/`、`plugins/`、`schemas/` 下无代码改动
4. 关联 AC：AC-CHAIN-MOD-1, AC-CHAIN-COMPAT-1（仅文档定义）

→ 设计依据：`docs/task-chains.md` §1–§12

#### M10.0.1 — Test cases doc

**Scope**：把 §12 acceptance criteria mapping 展开为可执行 bats
case 索引。

**Deliverables**：
- `docs/m10-test-cases.md`：每条 AC 对应 1+ TC-M10.x-NN，含
  前置条件、步骤、期望、对应 bats 文件名
- `helpers/m10_chain.bash`：M10 通用 bats helper（构造 fake task 树、
  断言 chain walk 顺序、断言 audit 行存在）

**DoD**：
1. 所有 AC-CHAIN-* 至少被一条 TC 覆盖
2. helper 暴露 `make_task <id> [parent_id]`、`assert_audit <outcome>`、
  `assert_chain_walk <id> <expected_csv>` 三组 API

→ 设计依据：spec §12

#### M10.1 — Chain primitives `_lib/task_chain.py`

**Scope**：实现 chain 的 CRUD + walk + cycle 检测；schema 增量落地。

**Deliverables**：
- `skills/codenook-core/skills/builtin/_lib/task_chain.py`：
  `get_parent / set_parent / walk_ancestors / chain_root / detach`
  + `CycleError / TaskNotFoundError / AlreadyAttachedError` +
  `__main__` CLI（`attach|detach|show`）
- `skills/codenook-core/schemas/task-state.schema.json`：追加
  `parent_id` 与 `chain_root` 两个可选属性（`required` 不变）
- `.codenook/.gitignore` 模板加入 `tasks/.chain-snapshot.json`
  （由 init.sh 写入）
- bats：`m10-task-chain.bats`、`m10-task-chain-cli.bats`、
  `m10-schema.bats`
  - 自环 / 间接环抛 `CycleError`（AC-CHAIN-MOD-2/3）
  - chain_root 沿父链终点（AC-CHAIN-MOD-4）
  - CLI attach/detach/show 行为契约（AC-CHAIN-LINK-*）
  - 缺字段的旧 state.json 仍通过 schema（AC-CHAIN-COMPAT-1）

**DoD**：
1. AC-CHAIN-MOD-* / AC-CHAIN-LINK-* / AC-CHAIN-COMPAT-1 全绿
2. 所有写操作走 `_lib/atomic.atomic_write_json`
3. `task_chain` 不 import `memory_layer`（仅 `extract_audit`）

→ 设计依据：spec §2、§3、§4

#### M10.2 — Similarity scorer `_lib/parent_suggester.py`

**Scope**：零依赖 token-set Jaccard 排名候选父任务；阈值 0.15、top-3。

**Deliverables**：
- `skills/codenook-core/skills/builtin/_lib/parent_suggester.py`：
  `Suggestion` NamedTuple + `suggest_parents(workspace, child_brief,
  *, top_k=3, threshold=0.15, exclude_ids=())`
- 内置 stopword 列表（≤ 50 词，中英混合）
- bats：`m10-parent-suggester.bats`
  - 排序 + top_k 截断（AC-CHAIN-SUG-1）
  - 阈值过滤（AC-CHAIN-SUG-2）
  - done/cancelled 不入候选（AC-CHAIN-SUG-3）
  - 损坏 state.json 异常 → 空列表 + audit（AC-CHAIN-SUG-4）

**DoD**：
1. AC-CHAIN-SUG-* 全绿
2. 50 任务规模下 `suggest_parents` ≤ 30 ms（NFR 性能验证）
3. 不引入任何第三方 NLP 依赖

→ 设计依据：spec §5

#### M10.3 — Creation-time UX hook（router-agent 集成）

**Scope**：把 suggester 接入 router-agent 提问流；在 `--confirm` 路径
落盘 `parent_id`。

**Deliverables**：
- `render_prompt.py` prepare 路径调用 `suggest_parents`，把候选
  注入 router-agent 的工具提示（不进 `{{TASK_CHAIN}}`，是 prompt
  辅助元信息）
- `render_prompt.py` `--confirm` 路径在 `freeze_to_state_json` 之后
  调用 `task_chain.set_parent`（来源于用户在对话中的确认；解析
  `draft-config.yaml` 的 `parent_id` 字段）
- `draft-config.yaml.schema.yaml` 扩展 `parent_id: string | null`
- bats：`m10-creation-flow.bats`
  - mock 用户选 "1"（top suggestion）→ state.json 含 parent_id
  - mock 用户选 "independent" → state.json 无 parent_id

**DoD**：
1. router-agent prompt 可见 top-3 候选 + score + reason
2. confirm 后落盘正确

→ 设计依据：spec §3.1、§3.2

#### M10.4 — Chain summarizer `_lib/chain_summarize.py`

**Scope**：两阶段 LLM 压缩；mock 协议复用 M9.0.1 §0.3。

**Deliverables**：
- `skills/codenook-core/skills/builtin/_lib/chain_summarize.py`：
  `summarize(workspace, task_id, *, max_tokens=8192)` → markdown
- pass-1：per-ancestor ≤ 1500 token；call_name=`chain_summarize`
- pass-2（仅当总和 > 8K）：保留最近 3 ancestor 原文 + 远祖压缩
- secret-scan + redact + audit
- 路径穿透防御（`assert_within`）
- bats：`m10-chain-summarize.bats`、`m10-chain-secret.bats`
  - 渲染含 H3 + artifacts（AC-CHAIN-CTX-4）
  - pass-1 token 上限（AC-CHAIN-BUD-1，mock 协议下验证）
  - pass-2 触发条件（AC-CHAIN-BUD-2/3）
  - LLM 抛错 → 空字符串 + audit（AC-CHAIN-NF-1）
  - secret 命中 → redact + audit（AC-CHAIN-NF-3）

**DoD**：
1. AC-CHAIN-CTX-4 / AC-CHAIN-BUD-* / AC-CHAIN-NF-1/3 全绿
2. 不写 `.codenook/memory/` 与 `.codenook/plugins/`

→ 设计依据：spec §6、§9

#### M10.5 — Router slot 集成（`{{TASK_CHAIN}}`）

**Scope**：把 chain 摘要注入 router-agent prompt 的固定 slot。

**Deliverables**：
- `skills/codenook-core/skills/builtin/router-agent/prompt.md`：在
  `{{MEMORY_INDEX}}` 之上新增 `{{TASK_CHAIN}}` slot
- `render_prompt.py`：新增 `_render_task_chain` + 2 个 import；
  `parent_id is None` → 空字符串；非 None → `cs.summarize(...)`
- token 预算文档化：router prompt 总额抬升至 ≤ 20K（保留 8K
  给 chain，其余与 M9.6 一致）
- bats：`m10-prompt-slots.bats`、`m10-render-prompt.bats`
  - prompt.md 含 slot 占位符（AC-CHAIN-CTX-1）
  - parent_id 缺失时 slot 为空（AC-CHAIN-CTX-2）
  - parent_id 非空 → 调用 chain_summarize（AC-CHAIN-CTX-3，mock 验证）
  - M9 既有 `m9-router-memory-scan.bats` 全部 regression 通过
    （AC-CHAIN-COMPAT-2）

**DoD**：
1. AC-CHAIN-CTX-* 全绿
2. M9 套件 regression 全绿
3. spawn.sh 无变更

→ 设计依据：spec §7

#### M10.6 — Snapshot 缓存 + audit + perf

**Scope**：实现 `.chain-snapshot.json` 缓存机制；扩展 audit logger
覆盖；性能验证。

**Deliverables**：
- `task_chain._build_snapshot / _read_snapshot / _invalidate_snapshot`：
  `(generation, mtime)`-based 失效协议（spec §8.1/8.2）
- `set_parent` / `detach` 自动 bump `generation`
- audit outcome 6 + diagnostic 4（spec §9.1）；asset_type=`"chain"`
- bats：`m10-chain-perf.bats`、`m10-chain-audit.bats`、
  `m10-chain-readonly.bats`
  - depth=10 walk < 100 ms snapshot 命中（AC-CHAIN-PERF-1）
  - N=200 重建 < 1 s（AC-CHAIN-PERF-2）
  - 6 个 outcome 全部可观察（AC-CHAIN-AUD-1）
  - audit 行通过 8-key schema（AC-CHAIN-AUD-2）
  - 强行写 `plugins/` → M9.7 guard 拦截（AC-CHAIN-RO-1）

**DoD**：
1. AC-CHAIN-PERF-* / AC-CHAIN-AUD-* / AC-CHAIN-RO-1 全绿
2. snapshot 文件在 `.gitignore` 内

→ 设计依据：spec §8、§9

#### M10.7 — E2E + 发布 v0.10.0-m10.0

**Scope**：完整跑通 + 版本发布。

**Deliverables**：
- `tests/e2e/m10-e2e.bats`：
  - 父任务实现 → 子任务测试任务 → suggester top-1 hit → confirm →
    state.json 含 parent_id（AC-CHAIN-E2E-1）
  - 子任务 spawn → prompt 含正确祖先 H3（AC-CHAIN-E2E-2）
  - depth=8 链 → pass-2 触发 → router prompt ≤ 20K（AC-CHAIN-E2E-3）
  - LLM error injection → spawn 仍退 0，prompt 含其它 slot
    （AC-CHAIN-E2E-4）
- `VERSION` → `0.10.0-m10.0`；`CHANGELOG.md` 完整记录 M10.0–M10.7
- tag `v0.10.0-m10.0`
- 全套 bats 全绿（M9 baseline + M10 新增 ~50）

**DoD**：spec §1–§12 全部目标 + AC-CHAIN-E2E-* 全绿；push 在用户
显式批准后单次执行（plan.md push policy）

→ 设计依据：spec §1–§12

---

## 第二部分：逐 Milestone 实现细节

### M1 — 内核骨架

#### M1.1 文件清单（新建）

```
skills/codenook-core/
├── init.sh                                      # 命令分发框架
├── VERSION                                      # 6.0.0
├── core/
│   └── shell.md                                 # ≤3K
├── templates/
│   └── CLAUDE.md                                # 指向 .codenook/core/shell.md
├── agents/builtin/
│   ├── router.agent.md
│   ├── distiller.agent.md
│   ├── security-auditor.agent.md
│   ├── hitl-adapter.agent.md
│   └── config-mutator.agent.md
├── skills/builtin/
│   ├── orchestrator-tick/SKILL.md
│   ├── session-resume/SKILL.md
│   ├── config-resolve/SKILL.md
│   ├── config-validate/SKILL.md
│   ├── secrets-resolve/SKILL.md
│   ├── sec-audit/SKILL.md      (复用 v5 security-audit.sh)
│   ├── secret-scan/SKILL.md
│   ├── dispatch-audit/SKILL.md
│   ├── preflight/SKILL.md
│   ├── queue-runner/SKILL.md
│   ├── model-probe/SKILL.md           # §3.2.4.2 探测 + 三档分级
│   └── task-config-set/SKILL.md       # §3.2.4.1 task 级 model override（自然语言驱动）
└── plugins/generic/
    ├── plugin.yaml
    ├── phases.yaml
    ├── transitions.yaml
    ├── entry-questions.yaml
    ├── hitl-gates.yaml
    ├── roles/{clarifier,analyzer,executor,deliverer}.md
    ├── manifest-templates/
    ├── config-defaults.yaml
    ├── config-schema.yaml
    ├── README.md
    └── CHANGELOG.md
```

#### M1.2 关键脚本签名

```bash
# init.sh 顶层分发
init_main()                                # 不带参数：seed workspace
cmd_install_plugin "$path_or_url" [--sha256 X] [--force]
cmd_remove_plugin "$name"
cmd_reinstall_plugin "$name"
cmd_uninstall_plugin "$name"
cmd_list_plugins
cmd_scaffold_plugin "$name"
cmd_pack_plugin "$dir"
```

```bash
# seed_workspace（init_main 调用）
seed_workspace() {
  ensure_dirs ".codenook"/{core,agents/builtin,skills/builtin,skills/custom,plugins,
                            knowledge,memory,tasks,queue,locks,hitl-queue,history,staging}
  copy_from_source "core/" "agents/builtin/" "skills/builtin/" "plugins/generic/"
  init_state_json
  init_config_yaml
  install_claude_md
}
```

#### M1.3 state.json（workspace 级）初始 schema

```json
{
  "schema_version": 1,
  "workspace_root": "/abs/path/to/workspace",
  "core_version": "6.0.0",
  "active_tasks": [],
  "current_focus": null,
  "installed_plugins": [
    {"name": "generic", "version": "0.1.0", "builtin": true, "installed_at": "..."}
  ]
}
```

→ 设计依据：架构文档 §2.1、§3.2.7、§7.1

---

### M2 — Plugin 安装管线

#### M2.1 主入口签名

```bash
cmd_install_plugin() {
  local src="$1"; shift
  local sha256_expected="" force=0 allow_warnings=0
  parse_install_flags "$@"

  local stage_dir; stage_dir=$(mktemp_under_workspace .codenook/staging)
  trap "cleanup_stage \"$stage_dir\" \"$?\"" EXIT

  resolve_source "$src" "$stage_dir"               # local copy or curl
  verify_sha256 "$stage_dir/pkg" "$sha256_expected"
  extract_archive "$stage_dir/pkg" "$stage_dir/extracted"
  validate_pipeline "$stage_dir/extracted"          # 12 gates + security
  mount_plugin "$stage_dir/extracted" "$force"
  append_install_log "$stage_dir/extracted"
}
```

#### M2.2 12-gate validator 实现清单

| Gate | 函数 | 失败码 | 实现要点 |
|---|---|---|---|
| 1 | `gate_manifest_present` | E_GATE_01 | `[ -f $ext/plugin.yaml ]` |
| 2 | `gate_manifest_parses` | E_GATE_02 | `yq -e '.' plugin.yaml` |
| 3 | `gate_required_fields` | E_GATE_03 | 检查 name/version/applies_to/codenook_core_version/summary/data_layout |
| 4 | `gate_name_pattern` | E_GATE_04 | `[[ $name =~ ^[a-z][a-z0-9-]{1,30}$ ]]` |
| 5 | `gate_core_version` | E_GATE_05 | semver 区间匹配，使用 `semver` 工具或 awk |
| 6 | `gate_required_files` | E_GATE_06 | phases/transitions/entry-questions + ≥1 roles/*.md |
| 7 | `gate_phases_role_refs` | E_GATE_07 | phase 引用的 role 必须有对应 `roles/<role>.md` |
| 8 | `gate_transitions_dag` | E_GATE_08 | 解析 transitions，DFS 检测可达性 + 终止性 |
| 9 | `gate_optional_schemas` | E_GATE_09 | entry-questions / hitl-gates 若存在则 schema 校验 |
| 10 | `gate_security_scan` | E_GATE_10 | 调 §M2.3 |
| 11 | `gate_reserved_name` | E_GATE_11 | `name ∉ {core,builtin,generic,codenook}`，generic 例外（来自 builtin 源） |
| 12 | `gate_size_limit` | E_GATE_12 | `du -sk` ≤ `plugins.max_size_mb`*1024（默认 10MB） |

#### M2.3 安全扫描规则清单（实现到 `skills/builtin/sec-audit/`）

```bash
sec_scan_plugin() {
  local root="$1"
  scan_no_symlinks "$root"               # find -type l → empty
  scan_hidden_files "$root"              # 仅允许 .gitignore .editorconfig .markdownlint.json
  scan_path_traversal_yaml "$root"       # 任何 yaml 中匹配 ../, /, ~ 的路径字段
  scan_executable_locations "$root"      # +x 仅允许在 skills/*/, validators/
  scan_world_writable "$root"            # find -perm -002 → empty
  scan_shebang_allowlist "$root"         # awk '/^#!/' 第一行匹配白名单 4 项
  scan_keyword_blacklist "$root"         # grep -E pattern_set
  scan_secrets "$root"                   # 调 secret-scan skill
  scan_data_glob_sanity "$root"          # data_glob 字段不能含 /, .., 绝对路径
}
```

**关键词黑名单 regex（写到 `skills/builtin/sec-audit/patterns.txt`）**：

```
# 网络下载即执行
curl[[:space:]]+[^|]*\|[[:space:]]*(sh|bash|zsh)
wget[[:space:]]+[^|]*\|[[:space:]]*(sh|bash|zsh)
# 危险 eval/exec
\beval[[:space:]]+["$]
\bexec[[:space:]]+\$\(
# 删除根
\brm[[:space:]]+-rf?[[:space:]]+/[[:space:]]*$
\brm[[:space:]]+-rf?[[:space:]]+/[[:space:]]
# 提权
\bsudo\b
# base64 解码后 pipe
base64[[:space:]]+(-d|--decode)[[:space:]]*\|[[:space:]]*(sh|bash)
```

**Shebang 白名单**（精确匹配首行）：

```
#!/usr/bin/env bash
#!/bin/bash
#!/usr/bin/env python3
#!/usr/bin/env node
```

**Secret regex 集合（`skills/builtin/secret-scan/patterns.txt`）**：

```
# Private keys
-----BEGIN (RSA|OPENSSH|DSA|EC|PGP) PRIVATE KEY-----
# AWS
AKIA[0-9A-Z]{16}
aws_secret_access_key[[:space:]]*=[[:space:]]*[A-Za-z0-9/+=]{40}
# GitHub
ghp_[A-Za-z0-9]{36}
gho_[A-Za-z0-9]{36}
github_pat_[A-Za-z0-9_]{82}
# Generic high-entropy
(api[_-]?key|secret|token|password)[[:space:]]*[:=][[:space:]]*['"]?[A-Za-z0-9+/]{32,}['"]?
# OpenAI / Anthropic
sk-[A-Za-z0-9]{32,}
sk-ant-[A-Za-z0-9-]{60,}
```

#### M2.4 mount_plugin 与 force 升级

```bash
mount_plugin() {
  local ext="$1" force="$2"
  local name; name=$(yq -r '.name' "$ext/plugin.yaml")
  local dest=".codenook/plugins/$name"

  if [ -d "$dest" ]; then
    [ "$force" -eq 1 ] || die "$E_ALREADY_INSTALLED: $name"
    archive_old_version "$dest"      # → history/plugin-versions/<name>/<old>/
  fi
  mv "$ext" "$dest"
}
```

#### M2.5 history/plugin-installs.jsonl entry schema

```json
{
  "ts": "2026-04-18T09:15:43Z",
  "event": "plugin_install",
  "plugin": "development",
  "version": "1.2.0",
  "source": "https://example.com/dev-plugin-1.2.0.tar.gz",
  "sha256": "9f86d0...",
  "force": false,
  "checks_passed": 12,
  "security_findings": 0,
  "size_kb": 142
}
```

→ 设计依据：架构文档 §7.2 – §7.6、§3.2.8

---

### M3 — Router + 自扫描

#### M3.1 文件清单

```
agents/builtin/router.agent.md             # 完整 self-bootstrap 协议
skills/builtin/router-verdict-schema.json  # 校验 router 输出
core/shell.md                              # 加上"派 router"模板
```

#### M3.2 router.agent.md 的 self-bootstrap 协议

见 [第三部分 §3.2](#32-routeragentmd-self-bootstrap-协议)。

#### M3.3 输出 JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "required": ["plugin", "confidence", "rationale"],
  "properties": {
    "plugin": {"type": "string", "pattern": "^[a-z][a-z0-9-]{1,30}$"},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "rationale": {"type": "string", "maxLength": 600},
    "alternates": {
      "type": "array",
      "maxItems": 3,
      "items": {
        "type": "object",
        "required": ["plugin", "confidence"],
        "properties": {
          "plugin": {"type": "string"},
          "confidence": {"type": "number"}
        }
      }
    }
  }
}
```

#### M3.4 history/router-decisions.jsonl entry schema

```json
{
  "ts": "...",
  "task_id": "T-007",
  "input_summary": "Add --tag filter to xueba CLI",
  "user_hint": null,
  "catalog_size": 3,
  "verdict": {"plugin": "development", "confidence": 0.92, "rationale": "...", "alternates": []},
  "user_override": null
}
```

→ 设计依据：架构文档 §4 – §4.2、§10.4

---

### M4 — Orchestrator-tick + Session-resume

#### M4.1 文件清单

```
skills/builtin/orchestrator-tick/SKILL.md
skills/builtin/session-resume/SKILL.md
skills/builtin/hitl-adapter/SKILL.md         (terminal.sh)
schemas/task-state.schema.json
schemas/queue-entry.schema.json
schemas/hitl-entry.schema.json
```

#### M4.2 tasks/T-NNN/state.json 完整 schema

```json
{
  "schema_version": 1,
  "task_id": "T-007",
  "title": "...",
  "summary": "...",
  "plugin": "development",
  "plugin_version": "1.2.0",
  "target_dir": "/abs/external/path",
  "phase": "implement",
  "phase_started_at": "...",
  "iteration": 2,
  "max_iterations": 3,
  "dual_mode": "serial",
  "status": "in_progress",
  "subtasks": [],
  "depends_on": [],
  "config_overrides": {},
  "in_flight_agent": {
    "agent_id": "ag_2026...",
    "role": "implementer",
    "dispatched_at": "...",
    "expected_output": "outputs/phase-3-implementer.md"
  },
  "history": [
    {"ts": "...", "phase": "clarify", "verdict": "ok"},
    {"ts": "...", "phase": "design",  "verdict": "ok"}
  ]
}
```

#### M4.3 queue/ entry schema（每个 task 一个 `T-NNN.json`）

```json
{
  "task_id": "T-007",
  "plugin": "development",
  "priority": 5,
  "ready_at": "...",
  "blocked_by": [],
  "next_action": "dispatch_role:implementer"
}
```

#### M4.4 hitl-queue/ entry schema（`<task>-<gate>.json`）

```json
{
  "id": "T-007-design_signoff",
  "task_id": "T-007",
  "plugin": "development",
  "gate": "design_signoff",
  "created_at": "...",
  "context_path": ".codenook/tasks/T-007/outputs/phase-2-designer-summary.md",
  "decision": null,
  "decided_at": null,
  "reviewer": null,
  "comment": null
}
```

#### M4.5 locks/ entry schema

```json
{
  "key": "/abs/target_dir/src/auth.py",
  "task_id": "T-007",
  "agent_id": "ag_...",
  "acquired_at": "...",
  "ttl_sec": 600
}
```

#### M4.6 关键算法

见 [第三部分 §3.3 – §3.4](#33-orchestrator-tick-skillmd-算法)。

→ 设计依据：架构文档 §3.1.3、§3.1.4、§8

---

### M5 — 模块化子系统落位

#### M5.1 config-resolve 算法（4 层合并）

见 [第三部分 §3.5](#35-config-resolve-skillmd-4-层合并算法)。

#### M5.2 config-validate

```bash
config_validate() {
  local plugin="$1"
  local schema=".codenook/plugins/$plugin/config-schema.yaml"
  local effective; effective=$(config_resolve plugin="$plugin")
  yq eval-all 'select(fileIndex==0) * select(fileIndex==1)' "$schema" - <<<"$effective" \
    | json-schema-validator   # 也可用 ajv-cli
}
```

未识别的 key 报错示例：
```
ERROR config-validate: plugins.development.overrides.models.reviever
  unknown key (did you mean: reviewer?)
  schema: plugins/development/config-schema.yaml#/properties/models/properties
```

#### M5.3 secrets-resolve

```bash
secrets_resolve() {
  local plugin="$1" task="$2"
  yq -r ".plugins.${plugin} // {} | to_entries | .[] | \"export \(.key)=\(.value)\"" \
     .codenook/secrets.yaml
}
# 用法：eval "$(secrets-resolve plugin=development task=T-007)"
```

#### M5.4 distiller 路由（按 plugin.yaml.knowledge.produces）

伪代码：

```python
def distill_and_route(plugin_name, knowledge_item):
    plugin_yaml = load(f".codenook/plugins/{plugin_name}/plugin.yaml")
    rules = plugin_yaml["knowledge"]["produces"]
    # 评估 promote_to_workspace_when 表达式
    if any(eval_expr(rule, knowledge_item) for rule in rules.get("promote_to_workspace_when", [])):
        target_root = ".codenook/knowledge"
    else:
        target_root = f".codenook/memory/{plugin_name}"
    write(f"{target_root}/{knowledge_item.subdir}/{knowledge_item.name}.md", knowledge_item.body)
    append_history("distillation-log.jsonl", {"plugin": plugin_name, "target": target_root, ...})
```

#### M5.5 Skills 查找顺序（被 sub-agent self-bootstrap 引用）

```python
def resolve_skill(name, active_plugin):
    # 顺序：plugin_local > plugin_shipped > workspace_custom > builtin
    candidates = [
        f".codenook/memory/{active_plugin}/skills/{name}",
        f".codenook/plugins/{active_plugin}/skills/{name}",
        f".codenook/skills/custom/{name}",
        f".codenook/skills/builtin/{name}",
    ]
    for c in candidates:
        if exists(f"{c}/SKILL.md"):
            return c
    raise SkillNotFound(name)
```

#### M5.6 config-mutator agent

输入：
```json
{"plugin": "development", "path": "models.reviewer", "new_value": "gpt-5.4-mini",
 "reason": "distiller observed reviewer takes 4x context vs implementer"}
```

行为：
1. `config-resolve` 拿 effective
2. 对比新值与现值，相同则 noop
3. 写到 `config.yaml.plugins.<p>.overrides.<path>`（深合并）
4. `history/config-changes.jsonl` 追加 `{ts, plugin, path, old, new, actor: "distiller"}`

→ 设计依据：架构文档 §3.2 全节

---

### M6 — development plugin（v5 → 包）

#### M6.1 源目录布局（在 `cintia09/codenook` 仓库内 `plugins/development/`）

```
plugins/development/
├── plugin.yaml
├── config-defaults.yaml
├── config-schema.yaml
├── phases.yaml
├── transitions.yaml
├── entry-questions.yaml
├── hitl-gates.yaml
├── roles/
│   ├── clarifier.md
│   ├── designer.md
│   ├── planner.md
│   ├── implementer.md
│   ├── tester.md
│   ├── reviewer.md
│   ├── acceptor.md
│   └── validator.md
├── manifest-templates/
│   ├── phase-1-clarifier.md
│   ├── phase-2-designer.md
│   ├── phase-3-planner.md
│   ├── phase-4-implementer.md
│   ├── phase-5-tester.md
│   ├── phase-6-reviewer.md
│   ├── phase-7-acceptor.md
│   └── phase-8-validator.md
├── skills/
│   └── test-runner/
│       ├── SKILL.md
│       └── runner.sh
├── validators/
│   ├── post-implement.sh
│   └── post-test.sh
├── prompts/
│   ├── criteria-implement.md
│   ├── criteria-test.md
│   └── criteria-accept.md
├── knowledge/                                # plugin-shipped knowledge
│   └── pytest-conventions.md
├── examples/
│   └── add-cli-flag/
│       └── seed.json
├── README.md
└── CHANGELOG.md
```

#### M6.2 plugin.yaml 完整样例

```yaml
name: development
version: 0.1.0
applies_to: ["software-engineering", "code"]
codenook_core_version: ">=6.0 <7.0"
summary: "Software development pipeline: clarify → design → plan → implement → test → accept → validate → ship"
keywords: [python, javascript, go, cli, api, implement, refactor, "fix bug", test, pytest]
examples:
  - "Add a --tag filter to the xueba CLI list command"
  - "Refactor the auth middleware to use JWT"
  - "Fix the off-by-one bug in pagination"
anti_examples:
  - "Write a blog post about RAG"
  - "Summarize the Q1 reading list"
supports_dual_mode: true
supports_fanout: true
supports_concurrency: true
data_layout: external
data_glob:
  - "**/*.py"
  - "**/*.js"
  - "**/*.ts"
  - "**/*.go"
  - "**/*.md"
data_excludes:
  - ".codenook/**"
  - ".git/**"
  - "node_modules/**"
  - "__pycache__/**"
entry_point: phases.yaml

knowledge:
  produces:
    default_target: plugin_local
    promote_to_workspace_when:
      - "topic in [environment, toolchain, conventions]"
  consumes: [workspace, plugin_shipped, plugin_local]
  retention:
    by-role: keep_last 50
    by-topic: keep_last 30

skills:
  produces:
    default_target: plugin_local
    promote_to_workspace_when:
      - "tags include [generic, format, file_op]"
  consumes: [workspace.builtin, workspace.custom, plugin_shipped, plugin_local]

config:
  schema: config-schema.yaml
  defaults: config-defaults.yaml
```

**配套 `plugins/development/config-defaults.yaml`（推荐用 tier 符号，不写死字面型号）**：

```yaml
# §3.2.4.2 — plugin 作者用 tier 符号，跨环境/新模型免改 plugin
models:
  planner:     tier_strong       # 当前 catalog 中 strong 档第一可用
  clarifier:   tier_balanced
  designer:    tier_strong
  implementer: tier_strong
  reviewer:    tier_strong
  tester:      tier_balanced
  acceptor:    tier_balanced
  validator:   tier_balanced
  distiller:   tier_cheap
  default:     tier_strong       # plugin 内未列出的 role 兜底
# 字面值也允许（强制锁定具体型号，跳过 tier 解析）：
# models:
#   reviewer: gpt-5.4
```

#### M6.3 v5 → development plugin 文件迁移

详见 [第四部分](#第四部分v5--v6-代码迁移映射表)。

#### M6.4 验收：v5 E2E 重放脚本

```bash
# tests/e2e/development-replay.sh
init_workspace ./e2e-ws
cd ./e2e-ws
../init.sh --install-plugin ../dist/development-0.1.0.tar.gz
../init.sh --install-plugin ../dist/writing-0.1.0.tar.gz   # 验证多 plugin 不串
echo '{"input":"Add --tag filter to xueba CLI list command"}' | feed_main_session
wait_for_task_done T-001 600
diff_against_v5_artifacts T-001 ../v5-baseline/
```

→ 设计依据：架构文档 §5、§9.2

---

### M7 — Generic + Writing plugin

#### M7.1 generic plugin（已在 M1 落位，此处补 transitions/hitl/role 内容）

```yaml
# plugins/generic/phases.yaml
phases:
  - {id: clarify,  role: clarifier,  produces: phase-1-clarifier-summary.md}
  - {id: analyze,  role: analyzer,   produces: phase-2-analyzer-summary.md}
  - {id: execute,  role: executor,   produces: phase-3-executor-output.md}
  - {id: deliver,  role: deliverer,  produces: phase-4-deliverable.md}
```

```yaml
# plugins/generic/transitions.yaml
transitions:
  clarify.clarifier.ok: analyze
  analyze.analyzer.ok: execute
  execute.executor.done: deliver
  deliver.deliverer.delivered: complete
```

#### M7.2 writing plugin

```yaml
# plugins/writing/plugin.yaml (摘)
name: writing
version: 0.1.0
applies_to: [content, writing]
summary: "Article authoring pipeline: outline → draft → edit → review → publish"
keywords: [article, blog, post, write, draft, essay, 文章, 博客, 写作]
examples:
  - "Write a blog post about RAG"
  - "Draft a newsletter about Q1 reading"
anti_examples:
  - "Implement a Python CLI"
  - "Fix bug in payment service"
data_layout: workspace
data_glob: ["articles/**/*.md"]
```

```yaml
# plugins/writing/phases.yaml
phases:
  - {id: outline, role: outliner}
  - {id: draft,   role: drafter, supports_iteration: true}
  - {id: edit,    role: editor,  dual_mode_compatible: true}
  - {id: review,  role: reviewer}
  - {id: publish, role: null, gate: pre_publish}
```

```yaml
# plugins/writing/hitl-gates.yaml
gates:
  pre_publish:
    trigger: before_phase=publish
    auto_approve_if: []
    required_reviewers: [human]
```

→ 设计依据：架构文档 §6、§3.2 多 plugin 共存

---

## 第三部分：关键文件骨架

### 3.1 `core/shell.md` 内容大纲

```markdown
# CodeNook Shell（main session loader）

> 这是 main session 的唯一加载文件。≤3K。

## 1. 你的角色
- 你是 CodeNook 的对话前端
- 你**只**做四件事：与用户对话、判别 chat vs task、ask_user 确认、把任务移交
- 你**不**：扫描 plugin、读 phases.yaml、构造 sub-agent prompt、读 state.json

## 2. 会话启动
首次接收用户输入前，dispatch session-resume：
  Profile: .codenook/skills/builtin/session-resume/SKILL.md
  返回 ≤500 字摘要后再开始对话

## 3. Chat vs Task 判别
- chat 标志：纯问答、闲聊、查文档、单步命令
- task 标志：含动词（实现/修复/重构/写/分析）+ 名词、用户用 /task 显式声明、提到目标目录
- 边界情况一律 ask_user

## 4. ask_user 确认模板
"看起来这是一个任务（{summary}）。要不要我创建一个 CodeNook 任务来跟踪？[是/否/再想想]"

## 5. Handoff 协议
### 5.1 派 router
  Execute router.
  Profile: .codenook/agents/builtin/router.agent.md
  User input: "<原话>"
  Workspace: <cwd>
  Optional hint: <用户显式提到的 plugin 名>

### 5.2 派 orchestrator-tick
  Execute tick.
  Profile: .codenook/skills/builtin/orchestrator-tick/SKILL.md
  Task: T-NNN

### 5.3 处理 router 返回
  - confidence ≥ config.router.confidence_threshold → 直接挂载
  - 否则 ask_user 确认建议的 plugin

### 5.4 何时 dispatch tick
  - 用户每发一次有意义输入（每个 active task 最多 1 次）
  - HITL approval 写入后
  - 用户说"继续 / 推进 T-NNN"

## 6. 你能给用户回什么
- session-resume 摘要（≤500 字）
- tick 摘要（≤200 字）
- ask_user 提问
- 不要用任何 sub-agent profile 的内容直接答用户

## 7. 禁止清单
- ❌ 读 .codenook/plugins/*/
- ❌ 读 .codenook/tasks/*/state.json
- ❌ 写 .codenook/queue/, locks/, hitl-queue/
- ❌ inline 任何 sub-agent 的指令内容
```

→ 设计依据：架构文档 §3.1.2、§3.1.5、§3.1.7

---

### 3.2 `router.agent.md` self-bootstrap 协议

```markdown
# Router Agent（builtin）

## 角色
把用户任务描述分类到一个 plugin。纯分类，不 dispatch 工作。

## 模型偏好
sonnet-4.5 或 haiku-4.5。

## Self-bootstrap 步骤
每次被 dispatch 时，按顺序执行：

### Step 1 读取输入
{ task_description: string, user_context: string, optional_user_hint?: string, workspace: path }

### Step 2 扫描 plugin 目录
- `ls .codenook/plugins/*/plugin.yaml`
- 对每个 manifest：
  ```python
  catalog.append({
    name:          yaml.name,
    version:       yaml.version,
    summary:       yaml.summary,
    applies_to:    yaml.applies_to,
    keywords:      yaml.keywords,
    examples:      yaml.examples or [],
    anti_examples: yaml.anti_examples or []
  })
  ```
- 跳过 `config.yaml.plugins.disabled` 中列出的
- 总是把 builtin `generic` 放最后

### Step 3 分类
评分顺序：
1. 显式 user_hint 命中某 plugin name → confidence +0.4
2. task_description 含 keywords 命中 → 每命中 +0.1（capped）
3. 命中 examples → +0.2
4. 命中 anti_examples → -0.3
5. applies_to 与任务领域吻合 → +0.1
6. 兜底：选 generic，confidence = 0.4

### Step 4 输出（严格 JSON）
{
  "plugin": "<name>",
  "confidence": 0.0-1.0,
  "rationale": "≤300 字",
  "alternates": [{"plugin": "<name>", "confidence": <num>}, ...]   // 最多 3 个
}

### Step 5 落盘记录
追加一条到 `.codenook/history/router-decisions.jsonl`

## 禁止清单
- ❌ 读 plugin 的 phases.yaml / roles/*.md / 任何内部文件
- ❌ dispatch 其他 agent
- ❌ 与用户对话（你的输出回到 main session）
```

→ 设计依据：架构文档 §4、§4.1、§4.2

---

### 3.3 `orchestrator-tick/SKILL.md` 算法

```markdown
# Orchestrator Tick（builtin skill）

## 输入
{ task_id: "T-NNN" }

## 输出（≤200 字 summary 给 main session）
{
  status: "advanced" | "waiting" | "blocked" | "done" | "error",
  next_action: "<人类可读>",
  dispatched_agent_id?: "ag_...",
  message_for_user?: "<≤200 字>"
}

## 算法（伪代码）

def tick(task_id):
    state    = read_json(f".codenook/tasks/{task_id}/state.json")
    plugin   = state.plugin
    pversion = state.plugin_version
    phases   = read_yaml(f".codenook/plugins/{plugin}/phases.yaml")
    trans    = read_yaml(f".codenook/plugins/{plugin}/transitions.yaml")
    cfg      = config_resolve(plugin=plugin, task=task_id)

    # ── 0. 终止态短路
    if state.status in ("done", "cancelled", "error"):
        return {status: state.status, next_action: "noop"}

    # ── 1. 当前 phase 未启动 → dispatch role
    if state.phase is None:
        first = phases[0]
        return dispatch_role(task_id, first, state, cfg)

    cur = find_phase(phases, state.phase)

    # ── 2. 有 in_flight agent → 检查产出
    if state.in_flight_agent:
        out = state.in_flight_agent.expected_output
        if not output_ready(task_id, out):
            return {status: "waiting", next_action: f"awaiting {state.in_flight_agent.role}"}
        # 产出就绪
        verdict = read_verdict(task_id, out)
        record_history(state, cur.id, verdict)
        clear_in_flight(state)

        # ── 3. 自动 validator
        if cur.get("post_validate"):
            run_validator(task_id, cur.post_validate)

        # ── 4. HITL gate
        if cur.gate or hitl_required(state, cur):
            write_hitl_entry(task_id, cur)
            return {status: "waiting", next_action: f"hitl:{cur.gate}"}

        # ── 5. transition
        next_phase = lookup_transition(trans, cur.id, cur.role, verdict)
        if next_phase == "complete":
            state.status = "done"
            persist(state)
            dispatch_distiller(task_id)
            return {status: "done", next_action: "noop"}

        # iteration 自循环
        if next_phase == cur.id:
            state.iteration += 1
            if state.iteration > state.max_iterations:
                state.status = "blocked"
                return {status: "blocked", next_action: "max_iterations exceeded"}

        state.phase = next_phase
        persist(state)
        return dispatch_role(task_id, find_phase(phases, next_phase), state, cfg)

    # ── 6. phase 已启动但无 in_flight（异常恢复）
    return dispatch_role(task_id, cur, state, cfg)


def dispatch_role(task_id, phase, state, cfg):
    # 6.1 entry-questions 检查
    eq = read_yaml(f".codenook/plugins/{state.plugin}/entry-questions.yaml")
    missing = check_required(eq.get(phase.id, {}), state)
    if missing:
        return {status: "blocked", next_action: f"missing: {missing}",
                message_for_user: f"请先回答：{missing}"}

    # 6.2 fanout 分支
    if phase.get("allows_fanout") and state.get("decomposed"):
        return seed_subtasks(task_id, state)

    # 6.3 dual_mode 路由
    if phase.get("dual_mode_compatible") and cfg.get("dual_mode") == "parallel":
        agents = dispatch_parallel(task_id, phase, state, cfg)
        return {status: "advanced", next_action: f"dispatched {len(agents)} parallel"}

    # 6.4 单一角色 dispatch
    manifest = render_manifest(task_id, phase, state, cfg)
    agent_id = dispatch_agent(role=phase.role, manifest=manifest, profile=role_profile(state.plugin, phase.role))
    state.in_flight_agent = {agent_id, role: phase.role, dispatched_at: now(),
                              expected_output: phase.produces}
    persist(state)
    append_log({task: task_id, event: "dispatch", role: phase.role, agent: agent_id})
    return {status: "advanced", next_action: f"dispatched {phase.role}",
            dispatched_agent_id: agent_id}
```

→ 设计依据：架构文档 §3.1.3、§3.1.7

---

### 3.4 `session-resume/SKILL.md` 算法

```markdown
# Session Resume（builtin skill）

## 输入
{ workspace: path }   # 通常就是 cwd

## 输出（≤500 字 summary 给 main session）
{
  active_tasks: [
    {task_id, plugin, phase, status, last_event_ts, one_liner}
  ],
  current_focus: <task_id|null>,
  last_session_summary: "<上一会话尾段 ≤300 字>",
  suggested_next: "<继续 T-007? / 开新任务 / 等用户>"
}

## 算法（伪代码）

def resume():
    ws_state = read_json(".codenook/state.json")
    active   = ws_state.get("active_tasks", [])
    current  = ws_state.get("current_focus")

    out = {active_tasks: [], current_focus: current}
    for tid in active:
        ts = read_json(f".codenook/tasks/{tid}/state.json")
        out.active_tasks.append({
            task_id: tid,
            plugin:  ts.plugin,
            phase:   ts.phase,
            status:  ts.status,
            last_event_ts: ts.history[-1].ts if ts.history else ts.created_at,
            one_liner: ts.title
        })

    latest = ".codenook/history/sessions/latest.md"
    out.last_session_summary = tail_chars(latest, 300) if exists(latest) else ""

    # 选择建议
    if current and any(t.task_id == current and t.status == "in_progress" for t in out.active_tasks):
        out.suggested_next = f"继续 {current}（{phase_of(current)}）？"
    elif out.active_tasks:
        out.suggested_next = f"有 {len(out.active_tasks)} 个 active task，要选哪个？"
    else:
        out.suggested_next = "无 active task，等待用户输入"

    return truncate_summary(out, 500)
```

→ 设计依据：架构文档 §3.1.4

---

### 3.5 `config-resolve/SKILL.md` 4 层合并算法

```markdown
# Config Resolve（builtin skill）

## 输入
{ plugin: string, task?: string }

## 输出
完整 effective config 树（YAML/JSON 二选一），含 `_provenance` 字段标注每个 leaf 来自哪一层。

## 算法（伪代码）

# 顶层 key 白名单（架构 §3.2.4 决议 #45）
KNOWN_TOP_KEYS = {
    "models", "hitl", "knowledge", "concurrency",
    "skills", "memory", "router",
    "plugins", "defaults", "secrets",
}

# Layer 0 builtin defaults（架构 §3.2.4.1 决议 #44）
BUILTIN_DEFAULTS = {
    "models": {
        "default": "tier_strong",
        "router":  "tier_strong",   # router 例外的兜底；plugin 不能覆盖
    },
    # 其它 builtin 兜底...
}

def resolve(plugin, task=None):
    # Layer 0: builtin defaults
    layer0 = BUILTIN_DEFAULTS

    # Layer 1: plugin baseline
    layer1 = read_yaml(f".codenook/plugins/{plugin}/config-defaults.yaml")

    # Layer 2: workspace defaults
    full = read_yaml(".codenook/config.yaml")
    validate_top_keys(full, KNOWN_TOP_KEYS)   # 未知 key → unknown_top_key 报错
    layer2 = full.get("defaults", {})

    # Layer 3: workspace per-plugin overrides
    layer3 = full.get("plugins", {}).get(plugin, {}).get("overrides", {})

    # Layer 4: task overrides
    layer4 = {}
    if task:
        ts = read_json(f".codenook/tasks/{task}/state.json")
        layer4 = ts.get("config_overrides", {})

    # M1: 简单 deep-merge + 列表 replace；M5 起按 schema x-merge 注解执行
    merged = deep_merge_with_strategy([layer0, layer1, layer2, layer3, layer4],
                                       schema=load_schema(plugin))

    # Step 5 — model symbol expansion (§3.2.4.2)
    catalog = load_catalog_default()   # 见 §3.5.1.2 默认位置解析
    for path, value in walk_models(merged):
        if isinstance(value, str) and value.startswith("tier_"):
            tier = value[len("tier_"):]
            literal = catalog.get("resolved_tiers", {}).get(tier)
            if literal is None:
                # 决议 #43：未知 tier → warn + fallback tier_strong，不抛错
                warn(f"unknown tier {value} at {path} (legal: strong|balanced|cheap); "
                     f"falling back to tier_strong")
                literal = catalog.get("resolved_tiers", {}).get("strong")
                set_at(merged, path, literal, symbol=value,
                       resolved_via="fallback:tier_strong")
            else:
                set_at(merged, path, literal, symbol=value,
                       resolved_via=f"model_catalog.resolved_tiers.{tier}")
        elif value not in (catalog.get("available", []) | {None}):
            # literal value not in catalog → warn + fall back to tier_strong
            warn(f"literal model {value} at {path} not in catalog; using tier_strong")
            set_at(merged, path, catalog["resolved_tiers"]["strong"],
                   symbol=None, resolved_via="fallback:tier_strong")

    annotate_provenance(merged, [layer0, layer1, layer2, layer3, layer4])
    return merged


def annotate_provenance(merged, layers):
    """
    For every leaf, write _provenance entry:
      _provenance["<path>"] = {
        value:        <final literal>,
        from_layer:   0..4,            # highest layer that wrote it
        symbol:       "tier_strong"    # or null if literal
        resolved_via: "model_catalog.resolved_tiers.strong" | "literal" | "fallback:..."
      }
    """
    ...


def deep_merge_with_strategy(layers, schema):
    """
    M1 简化口径：忽略 schema，统一按 deep-merge + 列表 replace（足以通过 F-031）。
    M5 起：按 schema 中字段的 `x-merge` 注解执行：
      - replace → 高层完全替换低层
      - deep    → 字典/列表递归深合并
      - append  → 列表追加去重
    未声明者按字段类型推断（标量=replace，map=deep，list=replace）。
    """
    result = {}
    for layer in layers:
        for path, value in walk(layer):
            strategy = schema_strategy_at(schema, path)   # M1: 始终视作默认
            apply(result, path, value, strategy)
    return result
```

**示例 schema 注解**：

```yaml
# plugins/development/config-schema.yaml
properties:
  hitl:
    type: object
    properties:
      gates:
        type: array
        x-merge: replace      # 用户列出的 gates 完全替换 plugin 默认
  models:
    type: object
    additionalProperties:
      type: string
      x-merge: replace        # 模型字段是单值，覆盖即可
```

→ 设计依据：架构文档 §3.2.4、§3.2.4.1、§3.2.4.2

---

### 3.5.1 模型路由与探测（model-probe + tier 解析 + provenance）

> 落地架构 §3.2.4.1（5 层链 + Router 例外 + task-config-set）+ §3.2.4.2（探测 + tier_strong/balanced/cheap + 30 天 TTL + `_provenance`）。

#### 3.5.1.1 5 层模型解析链（在标准 4 层 config 之上）

```
Layer 0  Builtin                models.default = "tier_strong"        # 兜底
Layer 1  Plugin baseline        plugins/<p>/config-defaults.yaml      # 作者推荐
Layer 2  Workspace defaults     config.yaml -> defaults.models        # 用户全局
Layer 3  Plugin overrides       config.yaml -> plugins.<p>.overrides.models
Layer 4  Task overrides         tasks/T-NNN/state.json.config_overrides.models
```

**Router 例外**：router 在 plugin 选定**之前**运行，只读 Layer 0 / Layer 2（`config.yaml.defaults.models.router`），永不读 Layer 1/3。默认 `tier_strong`（路由错误成本高）；用户可显式降档。

#### 3.5.1.2 `model-probe/SKILL.md` 算法（伪代码）

**默认 catalog 位置解析**（架构 §3.2.4.2；M1 必须实现）：

```python
def resolve_catalog_path(explicit_catalog=None):
    """
    `model-probe` / `config-resolve` 在未显式传 --catalog 时的统一解析。
    返回 (workspace_root, catalog_path, exists_bool)。
    """
    if explicit_catalog:
        # 显式 --catalog 总优先；不触发自动写回（避免污染只读 fixture）
        return (None, explicit_catalog, os.path.exists(explicit_catalog))

    # 1) 环境变量
    ws = os.environ.get("CODENOOK_WORKSPACE")
    if not ws:
        # 2) 从 cwd 向上搜索 .codenook/
        ws = find_upward(".codenook", start=os.getcwd())
    if not ws:
        # 极端兜底：无 workspace 上下文
        warn("no workspace catalog; using hardcoded fallback")
        return (None, None, False)

    catalog_path = os.path.join(ws, ".codenook", "state.json")
    return (ws, catalog_path, os.path.exists(catalog_path))


def load_catalog_default(explicit_catalog=None):
    ws, path, exists = resolve_catalog_path(explicit_catalog)
    if exists:
        cat = read_json(path).get("model_catalog")
        if cat:
            return cat
    # state.json 缺失或无 model_catalog → 即时探测 + 自动写回
    cat = probe()
    if ws and not explicit_catalog:
        write_json_at(path, "model_catalog", cat)   # 自动写回
    return cat
```

```python
# 触发：
#   - init.sh --install / --upgrade-core / --refresh-models
#   - state.json.model_catalog.refreshed_at < now - 30d
#   - main session："刷新模型"
def probe():
    available = []
    runtime = detect_runtime()                # claude-code | copilot-cli | api

    # 1) 运行时 API 探测
    try:
        if runtime == "claude-code":
            available = call_claude_list_models()
        elif runtime == "copilot-cli":
            available = read_copilot_model_registry()
        else:
            available = http_probe_api()
    except ProbeFailed:
        # 2) 环境变量覆盖
        env = os.environ.get("CODENOOK_AVAILABLE_MODELS")
        if env:
            available = parse_csv_models(env)
        else:
            # 3) 内置兜底
            available = BUILTIN_FALLBACK_MODELS

    # tier_priority 排名（builtin，可被 config.yaml.models.tier_priority 覆盖）
    priority = load_tier_priority()
    resolved = {}
    for tier in ("strong", "balanced", "cheap"):
        for candidate in priority[tier]:
            if any(m["id"] == candidate for m in available):
                resolved[tier] = candidate
                break
        else:
            resolved[tier] = None             # 该档无候选 → resolve 时退到 strong

    write_json_at(".codenook/state.json", "model_catalog", {
        "refreshed_at": now_iso(),
        "ttl_days": 30,
        "runtime": runtime,
        "available": available,               # [{id, tier, cost, provider}, ...]
        "resolved_tiers": resolved,
        "tier_priority": priority,            # 镜像，便于调试
    })
```

**默认 `tier_priority`**（写在 `BUILTIN_TIER_PRIORITY_YAML` 中，可被 `config.yaml.models.tier_priority` 全量替换）：

```yaml
tier_priority:
  strong:   [opus-4.7, opus-4.6, sonnet-4.6, gpt-5.4]
  balanced: [sonnet-4.6, sonnet-4.5, gpt-5.4, gpt-5.4-mini]
  cheap:    [haiku-4.5, gpt-5.4-mini, gpt-4.1, sonnet-4.5]
```

#### 3.5.1.3 Tier 优先级查找伪代码（在 `config-resolve` step 5 调用）

```python
def resolve_tier(symbol, catalog):
    assert symbol.startswith("tier_")
    tier = symbol[len("tier_"):]
    if tier not in ("strong", "balanced", "cheap"):
        raise UnknownTier(symbol)
    literal = catalog["resolved_tiers"].get(tier)
    if literal:
        return literal, f"model_catalog.resolved_tiers.{tier}"
    # 兜底：当前档无候选 → 顺位降级 strong → balanced → cheap
    for fallback in ("strong", "balanced", "cheap"):
        if catalog["resolved_tiers"].get(fallback):
            return catalog["resolved_tiers"][fallback], f"fallback:{fallback}"
    # 极端兜底：catalog 全空 → 硬编码
    return "opus-4.7", "fallback:hardcoded"
```

#### 3.5.1.4 `task-config-set/SKILL.md` 算法

```python
# 模式：set
# 输入：{task: "T-007", role: "reviewer", model: "tier_cheap" | literal_id, actor: "user"}
def set_task_model(task, role, model, actor="user"):
    state_path = f".codenook/tasks/{task}/state.json"
    state = read_json(state_path)
    old = state.get("config_overrides", {}).get("models", {}).get(role)
    state.setdefault("config_overrides", {}).setdefault("models", {})[role] = model
    write_json_atomic(state_path, state)
    append_jsonl(".codenook/history/config-changes.jsonl", {
        "ts": now_iso(),
        "actor": actor,                  # "user" | "distiller" | ...
        "scope": "task",
        "task": task,
        "path": f"models.{role}",
        "old": old, "new": model,
    })
    return {"ok": True, "old": old, "new": model}

# 模式：get
# 输入：{task: "T-007"} 或 {task, role}
# 输出：调 config-resolve(plugin=<task.plugin>, task=task)，返回 effective + _provenance
def get_task_model(task, role=None):
    eff = config_resolve(plugin=task_plugin(task), task=task)
    if role:
        return {
            "value": eff["models"][role],
            "provenance": eff["_provenance"][f"models.{role}"],
        }
    return {"models": eff["models"], "_provenance": eff["_provenance"]}

# 模式：unset（删除 task override → 落回 layer 3/2/1/0）
def unset_task_model(task, role, actor="user"):
    ... # 与 set 对称，删除 key 后追加 history（new=null）
```

**Main session 自然语言入口**（在 `core/shell.md` 中 dispatch 协议示例）：

```
用户："T-007 的 reviewer 用最便宜的"
MS：→ dispatch builtin skill `task-config-set`
       payload: {mode: "set", task: "T-007", role: "reviewer", model: "tier_cheap"}
    → 回 ≤200 字 confirm（带 old → new 对照）

用户："T-007 现在 reviewer 是哪个模型？"
MS：→ dispatch `task-config-set` payload: {mode: "get", task: "T-007", role: "reviewer"}
    → 回 effective literal id + provenance 链（"来自 layer 4 task override，符号 tier_cheap，
       展开为 model_catalog.resolved_tiers.cheap = haiku-4.5"）
```

#### 3.5.1.5 `_provenance` 输出结构

`config-resolve` 返回的 effective config 顶层带 `_provenance` 字段：

```json
{
  "models": {
    "planner": "opus-4.7",
    "reviewer": "haiku-4.5",
    "router":   "opus-4.7"
  },
  "_provenance": {
    "models.planner": {
      "value": "opus-4.7",
      "from_layer": 1,
      "symbol": "tier_strong",
      "resolved_via": "model_catalog.resolved_tiers.strong"
    },
    "models.reviewer": {
      "value": "haiku-4.5",
      "from_layer": 4,
      "symbol": "tier_cheap",
      "resolved_via": "model_catalog.resolved_tiers.cheap"
    },
    "models.router": {
      "value": "opus-4.7",
      "from_layer": 0,
      "symbol": "tier_strong",
      "resolved_via": "model_catalog.resolved_tiers.strong"
    }
  }
}
```

字段语义：

| 字段 | 含义 |
|---|---|
| `value` | 解析后的字面 model id（即 sub-agent 实际会用的型号） |
| `from_layer` | 0..4，写入该 leaf 的最高层（4 层 deep merge 后的胜出层） |
| `symbol` | 该层声明的原始符号（`tier_strong` 等）；若是字面值则为 `null` |
| `resolved_via` | 描述符号如何展开（`model_catalog.resolved_tiers.<tier>` / `literal` / `fallback:<tier>` / `fallback:hardcoded`） |

→ 设计依据：架构文档 §3.2.4.1、§3.2.4.2、§12 决议 #36–#42

---

### 3.6 `init.sh` 命令分发结构

```bash
#!/usr/bin/env bash
# init.sh — CodeNook v6 installer & plugin manager
set -euo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SELF_DIR/lib/log.sh"
source "$SELF_DIR/lib/yaml.sh"
source "$SELF_DIR/lib/sec-scan.sh"
source "$SELF_DIR/lib/gates.sh"
source "$SELF_DIR/lib/install.sh"

usage() {
  cat <<EOF
Usage:
  init.sh                                seed workspace in CWD
  init.sh --install-plugin <p|url> [--sha256 X] [--force] [--allow-warnings]
  init.sh --uninstall-plugin <name>
  init.sh --remove-plugin <name>         (alias of --uninstall-plugin)
  init.sh --reinstall-plugin <name>
  init.sh --list-plugins
  init.sh --scaffold-plugin <name>
  init.sh --pack-plugin <dir>
  init.sh --refresh-models                 force re-probe model catalog (resets 30d TTL)
  init.sh --version
  init.sh --help
EOF
}

main() {
  if [ $# -eq 0 ]; then
    seed_workspace; exit 0
  fi
  case "$1" in
    --install-plugin)    shift; cmd_install_plugin "$@" ;;
    --uninstall-plugin|--remove-plugin) shift; cmd_uninstall_plugin "$@" ;;
    --reinstall-plugin)  shift; cmd_reinstall_plugin "$@" ;;
    --list-plugins)      cmd_list_plugins ;;
    --scaffold-plugin)   shift; cmd_scaffold_plugin "$@" ;;
    --pack-plugin)       shift; cmd_pack_plugin "$@" ;;
    --refresh-models)    cmd_refresh_models ;;
    --version)           cat "$SELF_DIR/VERSION" ;;
    --help|-h)           usage ;;
    *)                   usage; exit 2 ;;
  esac
}
main "$@"
```

**`--scaffold-plugin <name>`**：在 CWD 之下创建 `<name>-plugin/`（不在 `.codenook/`），含 §7.2.1 列表。

**`--pack-plugin <dir>`**：复用 `validate_pipeline()`，通过后 `tar -czf <name>-<version>.tar.gz -C <parent> <dir>`，sha256 打到 stdout。

→ 设计依据：架构文档 §7.2、§7.2.1

---

### 3.7 完整 `plugin.yaml` schema（含三段 routing）

```yaml
# === 必填 ===
name:                 string  # ^[a-z][a-z0-9-]{1,30}$
version:              string  # semver
summary:              string  # 一行
applies_to:           [string, ...]
codenook_core_version: string  # semver range, e.g. ">=6.0 <7.0"
data_layout:          enum [external, workspace, none]
entry_point:          string  # 通常是 phases.yaml

# === Router 用（强烈推荐）===
keywords:             [string, ...]
examples:             [string, ...]
anti_examples:        [string, ...]

# === 能力声明 ===
supports_dual_mode:   bool
supports_fanout:      bool
supports_concurrency: bool

# === 数据范围（external/workspace 时强烈推荐）===
data_glob:            [string, ...]
data_excludes:        [string, ...]

# === Knowledge routing（§3.2.2）===
knowledge:
  produces:
    default_target: enum [plugin_local, workspace]
    promote_to_workspace_when:
      - <expr>            # 例如 "topic in [environment, toolchain]"
  consumes:
    - enum [workspace, plugin_shipped, plugin_local]
  retention:
    by-role:  string      # e.g. "keep_last 50"
    by-topic: string

# === Skills routing（§3.2.3）===
skills:
  produces:
    default_target: enum [plugin_local, workspace]
    promote_to_workspace_when:
      - <expr>
  consumes:
    - enum [workspace.builtin, workspace.custom, plugin_shipped, plugin_local]

# === Config（§3.2.4 / §3.2.4.1 / §3.2.4.2）===
config:
  schema:   string  # 文件名，相对 plugin 根
  defaults: string  # config-defaults.yaml；其中 models.<role> 推荐用 tier 符号
                    #   （tier_strong / tier_balanced / tier_cheap），由 model-probe
                    #   填充的 state.json.model_catalog 在 config-resolve step 5 展开。
                    #   字面型号（如 gpt-5.4）也允许，但会被打 warning 若不在 catalog。

# === 其他 ===
post_validate_default: string  # 可选，全局默认 validator
```

→ 设计依据：架构文档 §5.1、§3.2.2 – §3.2.4、§4.2

---

### 3.8 完整 state.json schema（汇总）

#### Workspace 级 `.codenook/state.json`

```json
{
  "schema_version": 1,
  "workspace_root": "/abs/path",
  "core_version": "6.0.0",
  "active_tasks": ["T-007", "T-008"],
  "current_focus": "T-007",
  "installed_plugins": [
    {"name": "generic", "version": "0.1.0", "builtin": true, "installed_at": "..."},
    {"name": "development", "version": "0.1.0", "builtin": false, "installed_at": "...",
     "source": "https://...", "sha256": "..."}
  ],
  "last_session_id": "S-2026-04-18-091543",
  "model_catalog": {
    "refreshed_at": "2026-04-18T09:15:43Z",
    "ttl_days": 30,
    "runtime": "claude-code",
    "available": [
      {"id": "opus-4.7",   "tier": "strong",   "cost": "high", "provider": "anthropic"},
      {"id": "sonnet-4.6", "tier": "balanced", "cost": "mid",  "provider": "anthropic"},
      {"id": "haiku-4.5",  "tier": "cheap",    "cost": "low",  "provider": "anthropic"},
      {"id": "gpt-5.4",    "tier": "balanced", "cost": "mid",  "provider": "openai"}
    ],
    "resolved_tiers": {
      "strong":   "opus-4.7",
      "balanced": "sonnet-4.6",
      "cheap":    "haiku-4.5"
    }
  }
}
```

#### Task 级 `.codenook/tasks/T-NNN/state.json`

见 [§M4.2](#m42-tasksT-NNNstatejson-完整-schema)。

#### `.codenook/queue/T-NNN.json`

见 [§M4.3](#m43-queue-entry-schema每个-task-一个-T-NNNjson)。

#### `.codenook/hitl-queue/<task>-<gate>.json`

见 [§M4.4](#m44-hitl-queue-entry-schemaT-NNN-gatejson)。

→ 设计依据：架构文档 §3.2.7、§8

---

## 第四部分：v5 → v6 代码迁移映射表（历史记录 — 已完成）

> **状态**：迁移已在 v0.10 / v0.11 完成，v5 源码已于 v0.11.1 从仓库移除。下文中的 `skills/codenook-v5-poc/` 路径已不存在，本表仅保留作为决策档案与设计回溯。
>
> 在 §3.1.6 给出了高层迁移；这里精确到代码文件层。源根（历史）：`skills/codenook-v5-poc/`。目标根：`skills/codenook-core/`（内核 + builtin）+ `plugins/development/`（领域）。

### 4.1 内核侧（v5 → codenook-core/）

| v5 文件 | v6 去向 | 操作 |
|---|---|---|
| `templates/CLAUDE.md` | `templates/CLAUDE.md` | **简化**：移除所有"状态机/路由表/HITL"段，仅保留指向 `core/shell.md` 的一行 |
| `templates/core/codenook-core.md` (~20K) | **拆 4 处** | （见下面 4.1.1） |
| `templates/queue-runner.sh` | `skills/builtin/orchestrator-tick/` | **内化**：tick 算法直接计算就绪队列；旧脚本保留为参考 |
| `templates/dispatch-audit.sh` | `skills/builtin/dispatch-audit/` | **抄过来**：包成 SKILL.md + 主脚本 |
| `templates/preflight.sh` | `skills/builtin/preflight/` | **抄过来**：tick 在 phase 推进前调用 |
| `templates/security-audit.sh` | `skills/builtin/sec-audit/` | **抄过来 + 强化**：增加 plugin 安装专用规则集 |
| `templates/secret-scan.sh` | `skills/builtin/secret-scan/` | **抄过来**：被 sec-audit 的 gate 10 调用 |
| `templates/subtask-runner.sh` | `skills/builtin/orchestrator-tick/` | **内化**：fan-out 分支并入 dispatch_role |
| `templates/distiller.sh` | `agents/builtin/distiller.agent.md` + `skills/builtin/distiller/` | **拆**：agent profile + 落盘 skill |
| `templates/keyring/` | `skills/builtin/secrets-resolve/` | **重构**：换成 `.codenook/secrets.yaml` 单文件 |
| `templates/agents/router.md` | `agents/builtin/router.agent.md` | **重写**：加自扫描协议（§3.2 第三部分） |
| `templates/agents/security-auditor.md` | `agents/builtin/security-auditor.agent.md` | **抄过来** |
| `templates/agents/hitl-adapter.md` | `agents/builtin/hitl-adapter.agent.md` | **抄过来** |
| `templates/agents/orchestrator.md` | **丢** | v5 的 orchestrator agent 概念被 tick skill 取代 |

#### 4.1.1 `codenook-core.md` 的 4-way 拆分

| v5 段 | 新位置 |
|---|---|
| §1-§2 角色与原则 | `core/shell.md` §1 |
| §3 状态机定义 + 10 阶段路由表 | **删**（领域知识，迁到 plugin 的 phases.yaml/transitions.yaml） |
| §4 dispatch 协议 + Task tool 模板 | `skills/builtin/orchestrator-tick/SKILL.md` 算法段 |
| §5 HITL gate 处理 | `skills/builtin/orchestrator-tick/` + `hitl-adapter` agent |
| §6 distill 触发规则 | `agents/builtin/distiller.agent.md` 自包含 |
| §7 context self-check | tick 内部检测 + 提示 main session（≤200 字 summary 字段） |
| §8 session bootstrap | `skills/builtin/session-resume/SKILL.md` |
| §9 PHASE_ENTRY_QUESTIONS YAML | **整体迁出**到 `plugins/development/entry-questions.yaml` |
| §10 模型路由表（字面型号 `opus-4.7` / `sonnet-4.5` / `gpt-5.4-mini`） | **拆 + 改符号**：内核默认 → `BUILTIN_DEFAULTS_YAML`（仅 `models.default = tier_strong` + router 默认）；plugin 默认 → `plugins/development/config-defaults.yaml`（**全部改用 tier 符号**，由 §3.2.4.2 model-probe 在运行时展开为字面 id） |

**v5 字面模型 → v6 tier 符号映射表**（迁移 §10 路由表时按此对照改写 plugin `config-defaults.yaml`）：

| v5 字面型号（来源 role） | v6 tier 符号 | 备注 |
|---|---|---|
| `opus-4.7`（planner / implementer / reviewer / designer） | `tier_strong` | 精度敏感 → 最强档 |
| `sonnet-4.6`（acceptor / validator） | `tier_balanced` | 性价比平衡 |
| `sonnet-4.5`（router 默认） | `tier_strong`（**升档**） | 路由错误成本高（架构 §3.2.4.1 决议 #37） |
| `gpt-5.4`（reviewer 备选 / tester） | `tier_balanced` | |
| `gpt-5.4-mini`（clarifier / distiller） | `tier_cheap` 或 `tier_balanced` | clarifier 用 balanced；distiller 用 cheap |
| `haiku-4.5`（极简任务） | `tier_cheap` | |

> **例外**：用户在 `config.yaml.defaults.models.<role>` 或 `config.yaml.plugins.<p>.overrides.models.<role>` 中显式写字面型号将**绕过 tier 解析**（被 `config-resolve` 直接采用，但若不在 `model_catalog.available` 中会打 warning 并回退到 `tier_strong`）。

### 4.2 领域侧（v5 → plugins/development/）

| v5 路径 | v6 路径 | 操作 |
|---|---|---|
| `templates/agents/planner.md` | `plugins/development/roles/planner.md` | **抄 + 调整 self-bootstrap 的相对路径** |
| `templates/agents/implementer.md` | `plugins/development/roles/implementer.md` | 同上 |
| `templates/agents/reviewer.md` | `plugins/development/roles/reviewer.md` | 同上 |
| `templates/agents/tester.md` | `plugins/development/roles/tester.md` | 同上 |
| `templates/agents/acceptor.md` | `plugins/development/roles/acceptor.md` | 同上 |
| `templates/agents/validator.md` | `plugins/development/roles/validator.md` | 同上 |
| `templates/agents/clarifier.md` | `plugins/development/roles/clarifier.md` | 同上 |
| `templates/agents/designer.md` | `plugins/development/roles/designer.md` | 同上 |
| `templates/prompts-templates/criteria-*.md` | `plugins/development/prompts/criteria-*.md` | **抄过来** |
| `templates/manifest-templates/phase-*.md` | `plugins/development/manifest-templates/phase-*.md` | **抄 + 用 `{target_dir}` 替换硬编码 cwd** |
| `templates/test-runner.sh` | `plugins/development/skills/test-runner/runner.sh` + `SKILL.md` | **包成 plugin-shipped skill** |
| `templates/validators/post-implement.sh` | `plugins/development/validators/post-implement.sh` | **抄过来** |
| `templates/codenook-core.md` §3 路由表 | `plugins/development/transitions.yaml` | **新写**（机器可读） |
| `templates/codenook-core.md` §3 phase 列表 | `plugins/development/phases.yaml` | **新写** |
| `templates/codenook-core.md` PHASE_ENTRY_QUESTIONS | `plugins/development/entry-questions.yaml` | **平移** |
| `templates/codenook-core.md` HITL gates 段 | `plugins/development/hitl-gates.yaml` | **平移** |
| `templates/knowledge/pytest-conventions.md` | `plugins/development/knowledge/pytest-conventions.md` | **抄过来**（plugin-shipped） |
| `templates/config.yaml` 的 development 段 | `plugins/development/config-defaults.yaml` | **拆出领域默认** |
| `reports/e2e-development-20260418-091543.md` | `tests/v5-baseline/e2e-development.md` | **作为 v6 重放基线** |

### 4.3 显式丢弃

- v5 中所有引用 `~/.codenook/` 的代码段：移除（v6 单 workspace 模型）
- v5 的 "subtask-phase 启发式"补丁：丢；v6 由 plugin 的 `allows_fanout` + `transitions.yaml` 显式声明
- v5 中 main session 持有的 sub-agent prompt 模板：全部丢；改为 main session 只持 dispatch 协议（§3.1.7）

→ 设计依据：架构文档 §3.1.6、§9.1 – §9.3

---

## 第五部分：依赖图

### 5.1 Milestone 之间

```
M1 (Core Skeleton)
 ├──▶ M2 (Install Pipeline)
 ├──▶ M3 (Router)
 └──▶ M4 (Tick + Resume)
                │
                ├──▶ M5 (Modular subsystems)
                │       │
                │       ▼
                └──▶ M6 (development plugin) ──▶ M7 (generic + writing)

注：M3 严格依赖 M2（无 plugin 不好测多候选）；
    M5 严格依赖 M4（tick 调 config-resolve）；
    M6 同时依赖 M2/M3/M4/M5；
    M7 同 plugin 框架，仅依赖 M6 完成的迁移路径范式。
```

### 5.2 同 Milestone 内部任务（重点列 M2 / M4）

**M2 内部依赖**：

```
gates.sh 实现 (1-12)  ─┐
sec-scan.sh 实现       ─┼─▶ install.sh resolve+stage+validate+mount
keyword/secret patterns─┘                                │
                                                         ▼
                                              cmd_install_plugin
                                                         │
            ┌────────────────────────────────────────────┤
            ▼                                            ▼
  cmd_uninstall_plugin                       cmd_scaffold_plugin
  cmd_reinstall_plugin                       cmd_pack_plugin
  cmd_list_plugins                                       │
                                              (复用 validate_pipeline)
```

**M4 内部依赖**：

```
schemas/*.json (state/queue/hitl)
        │
        ▼
queue ops + lock ops + hitl-queue ops
        │
        ▼
session-resume   (只读)
        │            │
        ▼            ▼
   shell.md       orchestrator-tick
   集成            (写状态机)
                       │
                       ▼
                hitl-adapter (terminal.sh)
                       │
                       ▼
              dispatch-audit / preflight 钩子
```

→ 设计依据：架构文档全文整体推断

---

## 第六部分：Definition of Done（验收脚本）

每个 Milestone 一条 e2e 验收脚本。脚本统一约定：在 `tests/e2e/` 下，bash 编写，依赖 `jq` `yq` `tar`。

### M1 DoD

```bash
# tests/e2e/m1-skeleton.sh
set -euo pipefail
WS=$(mktemp -d)
cp -r skills/codenook-core/* "$WS/.codenook-src/"
cd "$WS"
"$WS/.codenook-src/init.sh"

[ -f .codenook/core/shell.md ]
[ "$(wc -c < .codenook/core/shell.md)" -le 3072 ]
[ -f .codenook/plugins/generic/plugin.yaml ]
yq -e '.name == "generic"' .codenook/plugins/generic/plugin.yaml
[ "$(./.codenook-src/init.sh --list-plugins | wc -l)" -eq 1 ]
echo "✓ M1 OK"
```

### M2 DoD

```bash
# tests/e2e/m2-install.sh
set -euo pipefail
init_ws_with_core
./init.sh --scaffold-plugin foo
./init.sh --pack-plugin ./foo-plugin/
[ -f ./foo-0.1.0.tar.gz ]

./init.sh --install-plugin ./foo-0.1.0.tar.gz
[ -d .codenook/plugins/foo ]
jq -e '.event=="plugin_install" and .plugin=="foo"' \
   < <(tail -1 .codenook/history/plugin-installs.jsonl)

# 12 个红用例
for i in $(seq 1 12); do
  bash tests/fixtures/gate-fail-$i.sh && fail "gate $i should reject"
done

./init.sh --remove-plugin foo
[ ! -d .codenook/plugins/foo ]
ls .codenook/memory/.archived/foo-* >/dev/null

# (auto model-probe on first install)
jq -e '.model_catalog.refreshed_at and .model_catalog.runtime
       and (.model_catalog.available | length) >= 1' .codenook/state.json
echo "✓ M2 OK"
```

### M3 DoD

```bash
# tests/e2e/m3-router.sh
set -euo pipefail
init_ws_with_core
./init.sh --install-plugin dist/development-0.1.0.tar.gz
./init.sh --install-plugin dist/writing-0.1.0.tar.gz

verdict=$(dispatch_router_with "Write a blog post about RAG")
jq -e '.plugin=="writing" and .confidence>=0.75' <<<"$verdict"

verdict=$(dispatch_router_with "Implement a Python CLI for users")
jq -e '.plugin=="development"' <<<"$verdict"

verdict=$(dispatch_router_with "今天天气真不错")
jq -e '.plugin=="generic"' <<<"$verdict"

[ "$(wc -l < .codenook/history/router-decisions.jsonl)" -eq 3 ]
echo "✓ M3 OK"
```

### M4 DoD

```bash
# tests/e2e/m4-tick.sh
set -euo pipefail
init_ws_with_core_and_generic
TID=$(create_task plugin=generic title="test task")
[ "$(jq -r .phase .codenook/tasks/$TID/state.json)" = "null" ]

dispatch_tick "$TID"
[ "$(jq -r .phase .codenook/tasks/$TID/state.json)" = "clarify" ]
jq -e .in_flight_agent .codenook/tasks/$TID/state.json

# 模拟 clarifier 写产出
write_clarifier_output "$TID"
dispatch_tick "$TID"
[ "$(jq -r .phase .codenook/tasks/$TID/state.json)" = "analyze" ]

# session-resume
summary=$(dispatch_session_resume)
[ "$(echo -n "$summary" | wc -c)" -le 500 ]
jq -e ".active_tasks | map(.task_id) | index(\"$TID\")" <<<"$summary"
echo "✓ M4 OK"
```

### M5 DoD

```bash
# tests/e2e/m5-modular.sh
set -euo pipefail
init_ws_with_core_and_dev

# (a) model-probe 跑通 + catalog 写入
./init.sh --refresh-models
jq -e '.model_catalog.refreshed_at and .model_catalog.resolved_tiers.strong
       and .model_catalog.resolved_tiers.balanced
       and .model_catalog.resolved_tiers.cheap' .codenook/state.json

# (b) tier 解析正确
yq -i '.plugins.development.overrides.models.reviewer="tier_balanced"' .codenook/config.yaml
eff=$(config_resolve plugin=development task=T-NONE)
expected_balanced=$(jq -r .model_catalog.resolved_tiers.balanced .codenook/state.json)
jq -e --arg b "$expected_balanced" '.models.reviewer == $b' <<<"$eff"
jq -e '._provenance["models.reviewer"].symbol == "tier_balanced"' <<<"$eff"
jq -e '._provenance["models.reviewer"].from_layer == 3' <<<"$eff"

# (c) Router 默认走 tier_strong（mock catalog）
expected_strong=$(jq -r .model_catalog.resolved_tiers.strong .codenook/state.json)
eff=$(config_resolve plugin=__router__ task=T-NONE)
jq -e --arg s "$expected_strong" '.models.router == $s' <<<"$eff"

# (d) distiller 路由
fake_distill plugin=development topic=pytest-style
[ -f .codenook/memory/development/by-topic/pytest-style.md ]
[ ! -f .codenook/knowledge/by-topic/pytest-style.md ]

# (e) 未识别 key
yq -i '.plugins.development.overrides.models.reviever="x"' .codenook/config.yaml
! config_validate plugin=development 2>err.log
grep -q "unknown key" err.log

# (f) config-mutator
dispatch_config_mutator plugin=development path=models.reviewer new=tier_strong
jq -e '.actor=="distiller" and .path=="models.reviewer"' \
   < <(tail -1 .codenook/history/config-changes.jsonl)

# (g) task-config-set 写 task override + effective config 反映
TID=$(create_task plugin=development title="m5-task-override")
dispatch_skill task-config-set mode=set task="$TID" role=reviewer model=tier_cheap
jq -e --arg t "$TID" '.config_overrides.models.reviewer == "tier_cheap"' \
   .codenook/tasks/$TID/state.json
eff=$(config_resolve plugin=development task="$TID")
expected_cheap=$(jq -r .model_catalog.resolved_tiers.cheap .codenook/state.json)
jq -e --arg c "$expected_cheap" '.models.reviewer == $c' <<<"$eff"
jq -e '._provenance["models.reviewer"].from_layer == 4
       and ._provenance["models.reviewer"].symbol == "tier_cheap"' <<<"$eff"

jq -e '.actor=="user" and .scope=="task" and .path=="models.reviewer"' \
   < <(tail -1 .codenook/history/config-changes.jsonl)

echo "✓ M5 OK"
```

### M6 DoD

```bash
# tests/e2e/m6-development.sh
set -euo pipefail
init_ws_with_core
./init.sh --install-plugin dist/development-0.1.0.tar.gz

mkdir -p /tmp/xueba-cli && touch /tmp/xueba-cli/pyproject.toml
TID=$(create_task plugin=development \
                  title="Add --tag filter to xueba CLI list" \
                  target_dir=/tmp/xueba-cli)

# 推 8 个 phase
for i in $(seq 1 50); do
  out=$(dispatch_tick "$TID")
  status=$(jq -r .status <<<"$out")
  [ "$status" = "done" ] && break
  [ "$status" = "waiting" ] && simulate_role_or_hitl "$TID"
  [ "$status" = "error" ] && fail "tick error"
done

[ "$(jq -r .status .codenook/tasks/$TID/state.json)" = "done" ]
diff_against tests/v5-baseline/e2e-development/ .codenook/tasks/$TID/outputs/
echo "✓ M6 OK"
```

### M7 DoD

```bash
# tests/e2e/m7-multi-plugin.sh
set -euo pipefail
init_ws_with_core
./init.sh --install-plugin dist/development-0.1.0.tar.gz
./init.sh --install-plugin dist/writing-0.1.0.tar.gz

TDEV=$(create_task plugin=development title="fix bug" target_dir=/tmp/repo)
TWRT=$(create_task plugin=writing title="Write a blog post about RAG")

# 两条任务并行推几步
dispatch_tick "$TDEV"
dispatch_tick "$TWRT"

# queue entry 都带 plugin tag
jq -e 'select(.plugin=="development")' .codenook/queue/$TDEV.json
jq -e 'select(.plugin=="writing")'      .codenook/queue/$TWRT.json

# 跑完 writing 到 publish
run_until_done "$TWRT"
[ -f articles/*.md ]

# 卸载 writing 不影响 development
./init.sh --uninstall-plugin writing
[ ! -d .codenook/plugins/writing ]
[ -d .codenook/memory/.archived/writing-* ]
[ "$(jq -r .status .codenook/tasks/$TDEV/state.json)" != "error" ]

# 不带关键字 → generic
verdict=$(dispatch_router_with "帮我列一下今天要做的事")
jq -e '.plugin=="generic"' <<<"$verdict"
echo "✓ M7 OK"
```

→ 设计依据：架构文档 §9.5 + 各 Milestone 对应章节

---

## 附录 A：架构文档需要补充的歧义

落地时发现以下几处架构文档还应补充明确，以避免实现歧义：

1. **`config-defaults.yaml` 与 `plugin.yaml` 内嵌默认的关系**
   §3.2.4 描述了 4 层覆盖与 Layer 1（plugin baseline），但 §5.1 的 plugin.yaml 字段中也有诸如 `supports_*` 之类的"默认能力"。建议明确：能力声明放 `plugin.yaml`，可调参数放 `config-defaults.yaml`。

2. **`router-decisions.jsonl` 是否落 user_override**
   §10.4 提到要记录 `{task, chosen_plugin, user_override}`，但 main session 只读阈值结果，"user_override" 何时回写？建议在 router 决策被 main session ask_user 后由 main session 通过一个轻量 builtin skill `record-router-override` 回填。

3. **`orchestrator-tick` 是 builtin skill 还是 builtin agent？**
   §3.1.3 说"以 builtin skill 形式 invoke"且"helper agent 去执行 tick"，含义稍混。本文档按"skill = 算法说明 + 脚本；通过 dispatch helper agent 执行该 skill"理解。建议架构文档增一行术语界定。

4. **HITL adapter 接口契约**
   §3.2.1 表格出现 `hitl-adapter`，§5.5 给出 `hitl-gates.yaml`，但 adapter 与 hitl-queue 的双向 IO（写入 / 读取 decision）没有 schema。本文档在 §M4.4 给出了一个 entry schema，建议架构文档采纳或修正。

5. **`data_layout: workspace` 的具体目录约定**
   writing plugin 数据落 `<workspace>/articles/`——但这是 plugin 自己的硬编码还是要在 `plugin.yaml` 声明 `data_root: articles/`？建议加一个可选字段。

6. **`subtasks` 字段在 v6 MVP 的含义**
   §8 说"子任务继承父任务的 plugin/version/target_dir"，但没有给 subtask 与 parent task 的目录关系。建议规定 `tasks/T-007/subtasks/T-007.1/state.json` 这种嵌套结构（或拍平 + parent 字段）。

7. **`generic` plugin 的 transition 终态**
   §6 给的 phases 列表没配 transitions.yaml；本文档在 M7 补了一份默认。建议架构文档把这份默认也定稿。

8. **plugin uninstall 的归档保留策略**
   §3.2.8 说 `memory/<p>/` 归档为 `memory/.archived/<p>-<ts>/`，但未说 retention（多久清理 / 多少份）。建议加 `config.yaml.archive.retention_days` 默认值。

9. **shebang 白名单是否允许 `bun` / `deno` / `pwsh`**
   §7.4.1 列了 4 项；若希望 plugin 能用 TypeScript 跑 validator，需要扩展。建议把白名单本身做成 `config.yaml.security.shebang_allowlist`。

10. **`codenook_core_version` 检查与 plugin 升级**
    `--force` 升级时若新 plugin 要求 `>=7.0` 而当前 core 还是 6.x，gate 5 会拒绝；但用户可能就是想升 core——建议给出 core 版本升级路径（init.sh --upgrade-core？）或在文档里明确"core 升级走重新执行 install.sh"。
