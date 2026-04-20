# CodeNook v0.10 需求规格说明书 (SRS)

> 版本：v0.10.0-m10.0  
> 状态：反向工程式需求收集（基于已实现源码 + v6 设计文档 + bats 测试）  
> 编写日期：2026-04  
> 文档维护者：CodeNook Core Team

---

## 1. 文档概述

### 1.1 目的

本文档对 **CodeNook v0.10 当前已实现的全部能力** 进行反向工程式收集，把"代码中已存在的行为"重新表述为"用户/集成方可验证的需求"，作为后续：

- 验收测试基线（每条 FR 必有可测试条件）；
- 设计文档与源码偏差审计（greenfield 一致性回归）；
- 后续版本（M11+）增量需求的对比基准；
- 终端用户与插件作者的功能参考。

### 1.2 范围

**包含**：

- CodeNook Core（`skills/codenook-core/`）的全部 builtin skill（34 个）与 `_lib/` 共享模块（27 个）；
- 任务编排闭环（router-agent → orchestrator-tick → 抽取批次 → 内存 GC）；
- v6 epoch 内的 **M1 ~ M10** 全部里程碑能力（含 M9.x 子里程碑与 M10.1~M10.6 任务链）；
- 安装管线 12 道闸门（G01~G12）；
- 4 层配置系统、4 层 skill 解析、5 层 task 状态机；
- 内存层（knowledge/skills/config）+ 抽取审计（8-key schema）+ 任务链 snapshot v2。

**不包含**：

- 任何具体业务插件（如 `codenook-podcast/`, `xueba-knowledge/`），仅当其作为 plugin 范例被 core 测试引用时附带提及；
- v5 及更早 epoch 的废弃逻辑（已在 greenfield 重写中删除）；
- 未实现但出现在 backlog 的能力（统一归入 §7 已知限制 / 未来工作）；
- HTML / podcast / slides 生成（本仓库的展示物，不属于代码功能）。

### 1.3 术语 / 缩写

| 术语 | 定义 |
|------|------|
| Workspace | 用户工程根目录，内含 `.codenook/` 子目录 |
| Plugin | 第三方安装单元，置于 `.codenook/plugins/<id>/`，**只读**（FR-RO-1） |
| Skill | 可调用单元（builtin / plugin-shipped / plugin-local / workspace-custom） |
| Task | 一次完整意图执行实例，对应 `.codenook/tasks/<T-NNN>/` |
| Tick | 任务推进一次（orchestrator-tick 一次调用） |
| Phase | 任务在状态机中的阶段（start → implement → test → review → distill → accept → done） |
| Iteration | 同一 phase 的重试次数（受 max_iterations 限制） |
| Dual Mode | `serial` 单线推进 vs. `parallel` 多分身并行 |
| Chain | 父子 task 链路（M10.1 引入 parent_id / chain_root） |
| Memory Layer | `.codenook/memory/`，工作区可写知识/技能/配置存储（M9） |
| Distiller | LLM-less 路由器，把成果归档到 workspace 知识或 plugin 私域（M3） |
| Extractor | 阶段后异步抽取器（knowledge / skill / config 三种，M9） |
| Audit | `.codenook/memory/history/extraction-log.jsonl`，8-key schema |
| HITL | Human-in-the-loop 审批闸门 |
| Tier 符号 | `tier_strong` / `tier_balanced` / `tier_cheap`，由 model-probe 解析为具体模型 ID |
| Greenfield | "彻底重写、不保兼容" 的 epoch 内置原则 |

### 1.4 文档版本

| 版本 | 日期 | 变更 |
|------|------|------|
| v0.10-DRAFT | 2026-04 | 反向工程首版，覆盖 M1~M10 全功能 |

---

## 2. 系统总览

### 2.1 产品定位

CodeNook 是一个 **基于 Claude Code / Copilot CLI 的多代理任务编排平台**。它把"自然语言意图 → 多代理协同执行 → 知识沉淀"包装成可在终端工程仓库中本地运行的状态机：

- **零中心服务**：全部状态以文件形式存在 `.codenook/` 中，便于 Git 跟踪、便于审计；
- **无锁主动 tick**：用户对话产生 `router-agent` 一次推进，工作循环由 `orchestrator-tick` 显式驱动；
- **可插拔 plugin**：插件通过 12 道闸门安装为只读子树，宣告 subsystem / 提供 skills、roles、phases；
- **抽取闭环**：每个 phase 完成后异步抽取知识/技能/配置，写入工作区私域并以 8-key 审计；
- **任务可链化**（M10）：父子任务通过 `parent_id` 形成链路，`chain_summarize` 给出可注入 prompt 的祖先摘要。

### 2.2 核心概念

```
┌─────────────────────────────────────────────────────────┐
│ User input                                              │
│       │                                                 │
│       ▼                                                 │
│ router (M1) → router-agent (M8.2: prepare → confirm)    │
│       │                                                 │
│       ▼ writes draft-config.yaml + state.json           │
│ orchestrator-tick (M4) ───► dispatches sub-agent        │
│       │                                                 │
│       ├─ phase done? ─► extractor-batch (M9.2)          │
│       │                    ├─ knowledge-extractor       │
│       │                    ├─ skill-extractor           │
│       │                    └─ config-extractor          │
│       │                         │                       │
│       │                         ▼  patch-or-create      │
│       │                  memory-layer (M9.1)            │
│       │                         │                       │
│       │                         ▼                       │
│       │                   extraction-log.jsonl (8-key)  │
│       ▼                                                 │
│ chain primitives (M10): parent_id / chain_root          │
│ chain-snapshot.json v2 + chain_summarize                │
└─────────────────────────────────────────────────────────┘
```

数据流四要点：

1. **状态以文件落盘**：state.json, draft-config.yaml, router-context.md, extraction-log.jsonl, .chain-snapshot.json, .index-snapshot.json；
2. **写入皆原子**：tempfile + os.replace（`_lib/atomic.py`），并发写以 fcntl.flock 串行化；
3. **subprocess 边界**：CLI skill 之间通过 fork+JSON 通讯，绝不 in-proc 调用；
4. **审计先于副作用**：所有可观测变更都先 append-only 写 audit，再执行真实变更。

### 2.3 顶层架构图

```
         [Core/Builtin Skills]            [Plugins (read-only)]
               │                                  │
               ▼                                  ▼
   ┌─────────────────────────┐         .codenook/plugins/<id>/
   │ install-orchestrator    │         ├── plugin.yaml
   │  (12 gates: G01-G12)    │         ├── skills/
   │                         │         ├── roles/
   │ router / router-agent   │         ├── phases/
   │ orchestrator-tick       │         └── knowledge/
   │ extractor-batch         │
   │ knowledge / skill /     │         .codenook/memory/      (writable)
   │  config-extractor       │         ├── knowledge/<topic>.md
   │ memory_gc / memory_index│         ├── skills/<name>/
   │ chain primitives        │         ├── config.yaml
   │ HITL adapter            │         └── history/
   │ sec-audit / secret-scan │              ├── extraction-log.jsonl
   │ config-resolve / mutator│              ├── dispatch.jsonl
   │ skill-resolve           │              ├── distillation-log.jsonl
   │ distiller               │              └── config-changes.jsonl
   │ session-resume          │
   │ model-probe / preflight │         .codenook/tasks/<T-NNN>/
   │ queue-runner            │         ├── state.json
   └─────────────────────────┘         ├── router-context.md
                                       ├── draft-config.yaml
                                       ├── router.lock
                                       └── phase-logs/
```

### 2.4 用户角色

| 角色 | 描述 | 主要接触点 |
|------|------|-----------|
| **终端用户** | 在自己的项目中跑 `init.sh` 后通过自然语言驱动任务 | router-agent（对话式起单）、HITL 终端 |
| **插件作者** | 编写 `plugin.yaml` + skills/roles/phases，发布安装包 | 12 闸门规范、plugin schema、SemVer |
| **运维 / Ops** | 维护 workspace（GC、HITL 决策、sec-audit 周期扫描） | memory_gc CLI、hitl-adapter、sec-audit |
| **Core 开发者** | 维护 `_lib/` 与 builtin skill | 本文档 §3 / §5 / §6 |

---

## 3. 功能需求 (FR)

> **格式约定**  
> 每条 FR 含：标题、描述、验收标准（可执行/可观测）、源代码引用、当前状态。  
> 状态枚举：✅ 已实现 / 🟡 部分实现 / 🔴 未实现（仅出现在 §7）。  
> 源引用格式：`源：相对路径:LN`，行号以本快照为准。

### 3.1 安装与初始化

#### FR-INIT-1：工作区骨架初始化

- **描述**：用户在任意目录运行 `init` 应得到完整 `.codenook/memory/` 骨架与 `.gitignore` 条目，且重复运行幂等。
- **验收标准**：
  - 执行后存在目录 `.codenook/memory/{knowledge,skills,history}/` 与空 `config.yaml`（version 字段 = 1）；
  - 写入 `.gitignore` 包含 `.codenook/memory/.index-snapshot.json` 与 `.codenook/.chain-snapshot.json`；
  - 重复执行不报错，已有内容保持不变；
  - 退出码 0。
- **源**：`skills/codenook-core/skills/builtin/init/init.sh:10`；`_lib/memory_layer.py:118 init_memory_skeleton`。
- **状态**：✅

#### FR-INIT-2：仓库级安装脚本

- **描述**：仓库根 `install.sh`（v0.11.2 起）接受位置参数 `<workspace_path>`，委派 `skills/codenook-core/install.sh` 跑 12 关安装把 `plugins/<id>/` 原子写入 `<ws>/.codenook/plugins/<id>/`，并调用 `skills/codenook-core/skills/builtin/_lib/claude_md_sync.py` 在 `<ws>/CLAUDE.md` 上幂等地维护 `<!-- codenook:begin --> ... <!-- codenook:end -->` 引导块（DR-002 / DR-006）。**v4.9.5 legacy `codenook-init` 全局 skill 已于 v0.11.2 删除**；`sync-skills.sh` 同步移除。
- **验收标准**：
  - `bash install.sh <ws>` exit 0 且 `bash install.sh --check <ws>` 显示 plugin 与 CLAUDE.md 引导块均已落地；
  - 二次运行（`bash install.sh <ws>`）必须幂等：`CLAUDE.md` diff 为空；
  - `bash install.sh --dry-run <ws>` 仅跑 12 关、不提交。
- **源**：`install.sh`；`skills/codenook-core/install.sh`；`skills/codenook-core/skills/builtin/_lib/claude_md_sync.py`；bats 套件 `tests/v011_2-install-claude-md.bats`。
- **状态**：✅（v0.11.2 重写）
- **注**：v0.10 验收时分工为"全局 skill + 工作区骨架"；v0.11.2 重写为"工作区插件安装 + CLAUDE.md 引导块"，与 v6 plugin-architecture 对齐，legacy v4.9.5 `codenook-init` 路径整体删除（CHANGELOG v0.11.2）。

#### FR-INSTALL-1：12 闸门插件安装管线

- **描述**：`install-orchestrator` 必须按固定顺序运行 G01~G12，任一闸门失败即整体失败，仅在全部通过后原子提交到 `.codenook/plugins/<id>/`。
- **验收标准**：
  - 闸门顺序：G01 format → G02 schema → G03 id-validate → G04 version → G05 signature → G06 deps → G07 subsystem-claim → G08 sec-audit → G09 size → G10 shebang → G11 path-normalize → G12 atomic-commit；
  - 任一 gate 输出 `ok=false` → 整体 exit 1，不写入 `.codenook/plugins/`；
  - G12 通过 `os.replace()` 把 staging dir 原子重命名到目标位置；
  - 已存在同 id 且未传 `--upgrade` 时退出码 = 3；
  - `--dry-run` 走完所有闸门但跳过 commit；
  - 提交后 append `state.json.installed_plugins[]`。
- **源**：`skills/codenook-core/skills/builtin/install-orchestrator/orchestrator.sh:1`；`_orchestrator.py`。
- **状态**：✅

#### FR-INSTALL-2 ~ FR-INSTALL-13：单闸门规范

详见 §3.7 与 §6 CLI 清单（每个 plugin-* skill 对应一条 FR）。

---

### 3.2 任务生命周期

#### FR-TASK-1：state.json 标准 schema

- **描述**：每个 `.codenook/tasks/<tid>/state.json` 必须符合 `task-state.schema.json`，包含 schema_version、task_id、plugin、phase、iteration、max_iterations、status、history、in_flight_agent、config_overrides、subtasks、depends_on、role_constraints、parent_id（M10 新增）、chain_root（M10 新增）。
- **验收标准**：
  - `preflight` 在不合规 JSON 上返回 `{"ok": false, "reasons": [...]}` 退出 1；
  - 含 `parent_id` 时其值要么 `null`，要么对应一个存在的 task 目录；
  - status ∈ {pending, in_progress, waiting_hitl, blocked, done, cancelled, error}；
  - phase ∈ {start, implement, test, review, distill, accept, done}（M4 默认集合）；
  - iteration ≤ max_iterations。
- **源**：`schemas/task-state.schema.json`；`builtin/preflight/_preflight.py`。
- **状态**：✅

#### FR-TASK-2：任务状态原子写入

- **描述**：所有 state.json 写入必须经过 `_lib/atomic.atomic_write_json`（tempfile → fsync → os.replace）。
- **验收标准**：
  - 多进程并发写入不会出现半截文件；
  - 任何中断（kill -9）后文件要么是旧版要么是新版完整 JSON；
  - 写失败时不留下临时文件残骸（finally 清理）。
- **源**：`_lib/atomic.py`（atomic_write_json）；广泛被 task-config-set / orchestrator-tick / hitl-adapter 调用。
- **状态**：✅

#### FR-TASK-3：dual_mode 与并行分支

- **描述**：任务可声明 `dual_mode ∈ {serial, parallel}`；`parallel` 需要 fanout 子任务时由 orchestrator-tick 创建。
- **验收标准**：
  - **可选字段**：缺省视为 `serial`（v0.11 SPEC-PATCH A1-1）；
  - max_iterations > 1 时 dual_mode 必须显式存在（preflight 检查）；
  - max_iterations == 1 时缺字段允许并按 serial 推进；
  - parallel 模式下 tick 输出 `{"status": "advanced", "fanout": [...]}`；
  - serial 模式下永不 fanout。
- **源**：`builtin/preflight/_preflight.py`；`builtin/orchestrator-tick/_tick.py`。
- **状态**：✅

#### FR-TASK-4：phase 终态触发抽取

- **描述**：phase 进入 done / accept 后，orchestrator-tick 必须调用 extractor-batch（reason=after_phase）。
- **验收标准**：
  - tick 输出 `next_action` 含 `extractor-batch` 调用记录；
  - 同一 (task, phase, after_phase) 组合按 trigger-key 持久幂等（v0.11 SPEC-PATCH A1-4：键写入 `.trigger-keys` 文件，**不自动过期**；操作员清空文件即可重抽。v0.10 spec 误称 "24h 内幂等"）。
- **源**：`builtin/orchestrator-tick/_tick.py`；`builtin/extractor-batch/extractor-batch.sh:40`（idempotency hash）。
- **状态**：✅

---

### 3.3 任务编排循环（orchestrator-tick）

#### FR-TICK-1：单次推进语义

- **描述**：每次 tick 把任务从 N → N+1 步推进；输出 ≤500 字节 JSON；不会自动连续推进。
- **验收标准**：
  - JSON 形如 `{"status": "advanced|waiting|blocked|done|error", "next_action": "...", "dispatched_agent_id": "...", "message_for_user": "..."}`；
  - UTF-8 字节数 ≤ 500（CJK 安全）；
  - status=done/cancelled/error 时不再做任何派发。
- **源**：`builtin/orchestrator-tick/tick.sh:1`；`_tick.py` §3.3 伪代码。
- **状态**：✅

#### FR-TICK-2：post_validate 与重试

- **描述**：sub-agent 输出文件必须含 `verdict ∈ {ok, needs_revision, blocked}`；needs_revision 触发同 phase 重试（受 max_iterations 限制）。
- **验收标准**：
  - verdict=ok → 进入下一 phase；
  - verdict=needs_revision 且 iteration < max → iteration+1；
  - verdict=needs_revision 且 iteration ≥ max → status=error；
  - verdict=blocked → status=waiting_hitl 并写 HITL 队列。
- **源**：`builtin/orchestrator-tick/_tick.py`（post_validate + iteration 检查）。
- **状态**：✅

#### FR-TICK-3：写历史

- **描述**：每次 tick 必须把派发记录追加到 `history/dispatch.jsonl`，使用 dispatch-audit 走 redact 流程。
- **验收标准**：
  - 每条记录含 ts / role / payload_size / payload_sha256 / payload_preview（≤80 字符已脱敏）；
  - 文件 append-only，从不重写。
- **源**：`builtin/dispatch-audit/_emit.py`；tick 内调用。
- **状态**：✅

---

### 3.4 路由代理（router-agent）

#### FR-ROUTER-1：交互式起单（prepare 模式）

- **描述**：用户在终端发起意图后，router-agent 在锁内 append router-context.md 用户回合，渲染 prompt，输出 handoff 信封供上层 LLM 接管对话。
- **验收标准**：
  - 第一次调用（无 router-context.md）创建 task 目录、state.json status=draft、frontmatter state=drafting；
  - 后续每次 `--user-turn` / `--user-turn-file` 追加为 `### user (<iso>)` 段；
  - 每次都会产生 `.router-prompt.md`（最新 prompt 快照）；
  - JSON envelope action ∈ {prompt, handoff, error}；
  - 锁超时（30s 默认）→ exit 3。
- **源**：`builtin/router-agent/spawn.sh:1`；`render_prompt.py`；`_lib/router_context.py:243 initial_context`。
- **状态**：✅

#### FR-ROUTER-2：确认起单（confirm 模式）

- **描述**：传 `--confirm` 时，router-agent 验证 draft-config.yaml，写入 state.json 并触发首次 tick。
- **验收标准**：
  - **exit 4 = `confirm 不可继续`，覆盖 4 类原因**（v0.11 SPEC-PATCH A1-7）：(a) task 目录缺失；(b) draft-config.yaml 缺失/为空；(c) draft yaml 解析失败；(d) draft 必填字段缺失；(e) `parent_id` attach 失败 (CycleError/CorruptChainError/TaskNotFoundError/AlreadyAttachedError)；
  - 任一 exit 4 路径不污染 state.json；
  - 通过后 state.frontmatter.state = "confirmed" / state.json.status="pending"；
  - `--user-turn-file -` 从 stdin 读取 user turn（v0.11 SPEC-PATCH A2-7）；
  - 自动 spawn `orchestrator-tick --task <tid>` 一次。
- **源**：`builtin/router-agent/render_prompt.py`；`_lib/draft_config.py:_REQUIRED_KEYS`。
- **状态**：✅

#### FR-ROUTER-3：fcntl 锁

- **描述**：每个任务的 router-agent 调用串行化在 `tasks/<tid>/router.lock`，禁止重入。
- **验收标准**：
  - 同一进程二次 acquire 同一锁 → LockTimeout；
  - 死进程 stale-lock 可恢复，**判定阈值 = pid 不存在 或 `started_at` 超过 300 秒**（v0.11 SPEC-PATCH A2-3，明确 300s 常量）；
  - **不可解析 payload → 永不 unlink（保守策略，避免误删活锁）**（v0.11 SPEC-PATCH A2-3）。
- **源**：`_lib/task_lock.py:188 acquire`；reentrancy 检查 line 202-206。
- **状态**：✅

#### FR-ROUTER-4：路由打分（router_select）

- **描述**：M7 keyword + applies_to 评分，挑选目标 plugin。
- **验收标准**：
  - score = `keyword_hits*10 + applies_to_hits*5`；
  - 平分时按 routing.priority desc → id alpha；
  - 全 0 时退到 applies_to 含 `*` 的兜底插件；
  - 大小写不敏感。
- **源**：`_lib/router_select.py:82 select`、`:110 select_with_score`。
- **状态**：✅

#### FR-ROUTER-5：dispatch payload 500B 硬限

- **描述**：router-dispatch-build 输出的 envelope 必须 ≤500 UTF-8 字节，user_input 超 200 字符截断 + "..."；仍超限即失败。
- **验收标准**：
  - 输出 JSON 字节数 ≤ 500；
  - 超限时 exit 1；
  - dispatch-audit 在写入前 redact 9 类已知 secret 模式。
- **源**：`builtin/router-dispatch-build/build.sh:1`；`builtin/dispatch-audit/_emit.py`；`_lib/secret_scan.py:21`。
- **状态**：✅

---

### 3.5 任务链（M10 task-chains）

#### FR-CHAIN-1：parent_id 写入与守卫

- **描述**：`task_chain.set_parent` 写入 child.state.json.parent_id；必须拒绝 cycle、拒绝重复 attach（除非 force=True）。
- **验收标准**：
  - 创建 A→B→A 循环 → CycleError；
  - 已有 parent 再 attach → AlreadyAttachedError（非 force）；
  - target task 不存在 → TaskNotFoundError；
  - 成功后 emit `chain_attached` audit；失败 emit `chain_attach_failed`。
- **源**：`_lib/task_chain.py`；spec §3。
- **状态**：✅

#### FR-CHAIN-2：walk_ancestors 边界

- **描述**：从任意 task 沿 parent_id 走到根，受 max_depth / max_tokens 双重保护。
- **验收标准**：
  - **library 层** (`task_chain.walk_ancestors`) 默认 `max_depth=None`（无上限）以便组合复用；
  - **router 调用站点**默认传 `max_depth=100` 作为安全护栏（v0.11 SPEC-PATCH A1-2；推荐值见 task-chains.md §6）；
  - 超出 max_depth → emit `chain_walk_truncated` audit；
  - max_tokens 累计估算（token_estimate）超限即截断；
  - 中途 state 文件损坏 → CorruptChainError。
- **源**：`_lib/task_chain.py:417 walk_ancestors`；`_lib/token_estimate.py:21`。
- **状态**：✅

#### FR-CHAIN-3：chain-snapshot.json v2

- **描述**：`.codenook/.chain-snapshot.json` 缓存全 workspace 的 (task → parent_id, chain_root, state_mtime)；schema_version=1，generation 单调递增。
- **验收标准**：
  - 冷启动 / mtime 漂移 → 重建该条目；
  - 重建耗时 >100ms（P95 预算）→ emit `chain_snapshot_slow_rebuild` audit；
  - 过期 chain_root → emit `chain_root_stale` 并刷新；
  - 写入走 atomic_write_json + fcntl。
- **源**：`_lib/task_chain.py`（snapshot v2 §4.1）。
- **状态**：✅

#### FR-CHAIN-4：chain_summarize

- **描述**：把祖先链路压缩为可注入 child prompt 的摘要；遵循 brief / doc 双预算。
- **验收标准**：
  - 默认 brief 字节预算 ≤ `_BRIEF_BYTES`，doc 预算 ≤ `_DOC_BYTES`；
  - 超长祖先按 token_estimate 截断；
  - LLM 调用走 `_lib/llm_call.py`（mock-friendly）；
  - 结果可注入 router-agent prompt 的 `chain_summary` 字段。
- **源**：`_lib/chain_summarize.py`（≈360 LOC）。
- **状态**：✅

#### FR-CHAIN-5：parent suggester (token-Jaccard)

- **描述**：基于 child brief 与 open task title/summary/router-context 计算 Jaccard 评分，给出 top-K 父任务候选。
- **验收标准**：
  - 评分公式 `|A∩B|/|A∪B|`；
  - 默认 top_k=3, threshold=0.15；
  - 内置 EN+ZH ~70 词 stopword 表（权威清单见 `_lib/parent_suggester.py:STOPWORDS`，v0.11 SPEC-PATCH A2-2 公开为 plugin 调参依据）+ <2 字符 token 过滤；
  - 单候选 IO 错误 emit `parent_suggest_skip` 且继续；
  - 池枚举失败 emit `parent_suggest_failed` 并返回空列表；
  - `done` / `cancelled` 状态的任务不进入候选池；
  - CLI 退出码：0 / 2 / 1。
- **源**：`_lib/parent_suggester.py:249 suggest_parents`；spec §5。
- **状态**：✅

---

### 3.6 内存与抽取

#### FR-MEM-1：memory_layer 三类存储

- **描述**：Workspace 提供 knowledge（topic.md）、skills（SKILL.md）、config（config.yaml entries[]）三类可写存储；皆以 atomic + fcntl 保护。
- **验收标准**：
  - knowledge：summary ≤ 200 字符、tags ≤ 8、topic 匹配 `^[A-Za-z0-9][A-Za-z0-9_\-.]*$`；
  - config.yaml 不允许重复 key；
  - 任何写入若目标路径在 `.codenook/plugins/` 下 → PluginReadOnlyViolation；
  - 写入后 invalidate `.index-snapshot.json` 对应条目。
- **源**：`_lib/memory_layer.py:260+`；`_lib/plugin_readonly.py:104`。
- **状态**：✅

#### FR-MEM-2：内存索引快照（M9.1）

- **描述**：`.index-snapshot.json` 对 frontmatter 做 mtime 缓存，使 1000-file 索引扫描 P95 < 200ms（warm）/ 500ms（cold）。
- **验收标准**：
  - 冷启动 1000 文件构建 < 500ms；
  - mtime/size 一致即跳过解析；
  - 并发写以 fcntl.flock 串行；
  - 失效 API：`memory_index.invalidate(ws, path)`。
- **源**：`_lib/memory_index.py:131 build_index`、`:215 invalidate`。
- **状态**：✅

#### FR-MEM-3：8-key 抽取审计

- **描述**：所有抽取/链路/GC/dispatch 事件统一写 `extraction-log.jsonl`，行级 JSON，含 8 个必需 key。
- **验收标准**：
  - 必需 key：ts, task_id, plugin, kind, action, target, rationale, source；
  - 子事件 kind 例：`knowledge_proposed`, `skill_promoted`, `config_patched`, `gc_pruned`, `chain_attached`, `parent_suggest_skip` 等；
  - append-only 写入；
  - schema 不通过 → extract_audit 抛错。
- **源**：`_lib/extract_audit.py`；`_lib/memory_layer.py:430 append_audit`。
- **状态**：✅

#### FR-EXTRACT-1：knowledge-extractor

- **描述**：阶段后从 phase log 中由 LLM 提取最多 3 条可复用知识；走 secret-scan → dedup → similarity → judge → atomic write 流水线。
- **验收标准**：
  - 命中 secret 模式 → 整次抽取 exit 非 0；
  - 其他失败 best-effort exit 0；
  - 写入路径在 `.codenook/memory/by-topic/` 或 `<plugin>/by-topic/`；
  - 单 task knowledge 总数 ≤ 3（GC 强制）。
- **源**：`builtin/knowledge-extractor/extract.sh:1`、`extract.py`；spec M9.3。
- **状态**：✅

#### FR-EXTRACT-2：skill-extractor

- **描述**：检测 phase 内重复 shell 调用（≥3 次）→ 提取一条候选 skill；per-task cap = 1。
- **验收标准**：
  - 输出位置 `.codenook/skills/{custom,task}/<skill>/`；
  - secret-blocked → exit 非 0；其他 best-effort。
- **源**：`builtin/skill-extractor/extract.sh:1`。
- **状态**：✅

#### FR-EXTRACT-3：config-extractor

- **描述**：log 中检测 ≥2 个 KEY=VALUE 信号 → 提议配置变更，patch-or-create；per-task cap = 5。
- **验收标准**：与 FR-EXTRACT-1 类同，仅 cap、信号源与判定逻辑不同。
- **源**：`builtin/config-extractor/extract.sh:1`。
- **状态**：✅

#### FR-EXTRACT-4：extractor-batch fan-out

- **描述**：`extractor-batch` 并行触发三种抽取器，按 (task,phase,reason) SHA256 幂等。
- **验收标准**：
  - 重复同 key → 仅返回 `skipped` 列表；幂等键持久化在 `.codenook/memory/history/.trigger-keys`，**不自动过期**（v0.11 SPEC-PATCH A1-4，同 NFR-REL-4 修订）；
  - extractor 通过 `nohup` 分离派发（v0.11 SPEC-PATCH A2-9，明确 detach 机制）；
  - 任一 extractor 失败不影响其他；
  - 接受 reason ∈ {after_phase, context-pressure}。
- **源**：`builtin/extractor-batch/extractor-batch.sh:1-141`。
- **状态**：✅

#### FR-EXTRACT-5：dispatch-audit redact

- **描述**：dispatch payload 写日志前去除 9 类常见密钥（v0.11 SPEC-PATCH A1-5/A2-6：实现复用 `_lib/secret_scan.SECRET_PATTERNS`；权威清单 = aws-access-key, openai-key, github-pat, rsa-private-key, internal-ip-10/172/192, internal-ipv6-ula, connection-string）。
- **验收标准**：
  - 模式：完全等同 `_lib/secret_scan.SECRET_PATTERNS` 9 条（不重复维护）；
  - 命中即替换为 `[REDACTED]`；
  - 未命中保持原文（仅截 80 字符 preview）。
- **源**：`builtin/dispatch-audit/_emit.py`；`_lib/secret_scan.py:21 SECRET_PATTERNS`（9 条）。
- **状态**：✅

#### FR-MEM-4：memory_gc 容量上限

- **描述**：CLI GC 按 created_from_task 维度限制：knowledge ≤3、skill ≤1、config ≤5；超出按时间淘汰。
- **验收标准**：
  - `python -m memory_gc --workspace <ws>` exit 0 时正常 / 1 出错 / 2 参数错；
  - **promoted=true 条目永不被淘汰**（v0.11 SPEC-PATCH A2-4，明确豁免规则）；
  - 删除前 emit `gc_pruned` audit；
  - rebuild index snapshot 一次。
- **源**：`_lib/memory_gc.py`；spec M9.8 decision #5。
- **状态**：✅

#### FR-DIST-1：distiller LLM-less 路由

- **描述**：基于 plugin.yaml.knowledge.produces.promote_to_workspace_when 表达式决定归档目标。
- **验收标准**：
  - 表达式禁用 `__` 与 `import` 子串（v0.11 SPEC-PATCH A2-8：sandbox 黑名单 token，命中即拒绝执行）；
  - 任一规则真 → workspace（`.codenook/knowledge/`）；
  - 全假 → plugin 私域（`.codenook/memory/<plugin>`）；
  - 表达式语法非法 → exit 1；
  - 写 `distillation-log.jsonl` 一行。
- **源**：`builtin/distiller/distill.sh:1`；`_lib/expr_eval.py`（手写文法）。
- **状态**：✅

---

### 3.7 技能 / 插件管理

#### FR-SKILL-1：4-tier skill 解析

- **描述**：skill-resolve 按 plugin_local → plugin_shipped → workspace_custom → builtin 顺序查找。
- **验收标准**：
  - 找到任一 → exit 0 + JSON `{"found": true, "tier": "..."}`；
  - 找不到 → exit 1 + JSON `{"found": false, "candidates": [...]}`；
  - `--name` 含 `/`、`..`、非允许字符 → exit 2；
  - 路径必须落在 workspace 或 core 内（防越权）。
- **源**：`builtin/skill-resolve/resolve-skill.sh:1`；`_resolve_skill.py`。
- **状态**：✅

#### FR-SKILL-2：plugin 只读不变量

- **描述**：任何 builtin / extractor / 编辑路径若试图写入 `.codenook/plugins/<id>/...` 必须抛 PluginReadOnlyViolation 并 emit audit。
- **验收标准**：
  - 运行时：`assert_writable_path` 阻断写；
  - **静态扫描器（standalone CLI 模式）**：`python plugin_readonly.py --target <dir> [--json] [--exclude GLOB]...` 扫到 `open(...,'w')` / `write_*` / `shutil.copy*` 等危险写模式 → exit 1（v0.11 SPEC-PATCH A2-1）；
  - 默认 `--exclude` 集合包含 `*/tests/fixtures/*`（test fixture 不参与扫描）；
  - 未声明 `--target` → exit 2。
- **源**：`_lib/plugin_readonly.py:104,263`。
- **状态**：✅

#### FR-PLUGIN-G01 ~ G12：12 闸门细则

| Gate | Skill | 关键规则 | 源 |
|------|-------|---------|----|
| G01 format | plugin-format | plugin.yaml 存在；**允许 plugin 子树内的相对 symlink，仅禁越界（指向树外）**（v0.11 SPEC-PATCH A1-8） | `plugin-format/format-check.sh` |
| G02 schema | plugin-schema | required: id/version/type/entry_points/declared_subsystems | `plugin-schema/schema-check.sh` |
| G03 id-validate | plugin-id-validate | `^[a-z][a-z0-9-]{2,30}$`、保留集 {core,builtin,codenook,generic}、非升级时禁同 id | `plugin-id-validate/id-validate.sh` |
| G04 version | plugin-version-check | SemVer 2.0；升级时严格大于 | `plugin-version-check/version-check.sh` |
| G05 signature | plugin-signature | 默认可选；CODENOOK_REQUIRE_SIG=1 强制；sha256(plugin.yaml) 比对，**`plugin.yaml.sig` 文件取首个非空白 token 作 hash（允许内嵌注释/换行）**（v0.11 SPEC-PATCH A1-3） | `plugin-signature/signature-check.sh` |
| G06 deps | plugin-deps-check | requires.core_version SemVer 约束（逗号 AND） | `plugin-deps-check/deps-check.sh` |
| G07 subsystem-claim | plugin-subsystem-claim | declared_subsystems 全局唯一 | `plugin-subsystem-claim/subsystem-claim.sh` |
| G08 sec-audit | sec-audit | secret/permission/world-writable | `sec-audit/audit.sh` |
| G09 size | install-orchestrator 内联 | 单文件 ≤1MB / 整包 ≤10MB | `install-orchestrator/_orchestrator.py` |
| G10 shebang | plugin-shebang-scan | 仅允许 sh/bash/env bash/env python3 | `plugin-shebang-scan/shebang-scan.sh` |
| G11 path-normalize | plugin-path-normalize | **禁所有 symlink（无论是否越界，比 G01 更严）**；YAML 不得含绝对/`~`/`..`（v0.11 SPEC-PATCH A1-8 双闸门防御纵深） | `plugin-path-normalize/path-normalize.sh` |
| G12 atomic-commit | install-orchestrator 内联 | os.replace 提交；失败回滚 | `install-orchestrator/_orchestrator.py` |

每个 gate 都满足：`{"ok": bool, "gate": "<name>", "reasons": [...]}` 输出格式 + exit 0/1/2 三态。

#### FR-PLUGIN-MANIFEST：manifest_load + manifest_index

- **描述**：`_lib/manifest_load.list_installed_ids` 与 `plugin_manifest_index.discover_plugins` 是唯一的插件枚举入口。
- **验收标准**：
  - 缺 intent_patterns 自动设 `[]`，不报错；
  - 损坏 manifest 携 `_error` 标记返回，不阻塞批量枚举；
  - 输出按 id 排序保证路由确定性；
  - `routing.priority` 缺省 = `DEFAULT_PRIORITY = 100`（v0.11 SPEC-PATCH A2-10，与 §5.6 保持一致）。
- **源**：`_lib/manifest_load.py:41,53,78`；`_lib/plugin_manifest_index.py:35`。
- **状态**：✅

#### FR-ROLE-1：role 发现与约束

- **描述**：`role_index` 解析 `<plugin>/roles/*.md` 的 frontmatter 并支持 include/exclude 约束。
- **验收标准**：
  - frontmatter 必须含 name/plugin/phase/manifest/one_line_job；
  - constraints 空 → identity；
  - is_role_allowed 谓词正确反映 included/excluded。
- **源**：`_lib/role_index.py:78,97,126,149`。
- **状态**：✅

---

### 3.8 配置管理

#### FR-CONFIG-1：4 层 deep-merge 解析

- **描述**：config-resolve 按 builtin → plugin defaults → workspace defaults → workspace overrides → task overrides 顺序合并；输出 `_provenance` 映射。
- **验收标准**：
  - 任意 dotted path 可在 `_provenance` 中找到 from_layer；
  - top-key 限定 10 个白名单（models/hitl/knowledge/concurrency/skills/memory/router/plugins/defaults/secrets）；
  - 未知 top-key → exit 1；
  - 兜底链：strong → balanced → cheap → 硬编码 opus-4.7。
- **源**：`builtin/config-resolve/resolve.sh:1`；`_resolve.py`。
- **状态**：✅

#### FR-CONFIG-2：tier 符号展开

- **描述**：`tier_strong` / `tier_balanced` / `tier_cheap` 通过 model-probe catalog 展开为具体模型 ID。
- **验收标准**：
  - catalog 缺失目标 tier → 走 fallback chain；
  - 全失败 → 硬编码 opus-4.7 并 stderr 警告；
  - 解析后 _provenance.symbol = `tier_*`、resolved_via = `catalog|fallback|hardcoded`。
- **源**：`builtin/config-resolve/_resolve.py`；`builtin/model-probe/_probe.py`。
- **状态**：✅

#### FR-CONFIG-3：config-mutator 层间写入

- **描述**：把单个 dotted path 写入 workspace（layer3）或 task（layer4）层，并记录 `history/config-changes.jsonl`。
- **验收标准**：
  - top segment 必须在 §45 白名单；
  - leading `_` 或 `..` 拒绝；
  - actor ∈ {distiller, user, hitl}；
  - `__router__` 插件不允许覆盖 `models.router`（§44）；
  - no-op（值未变）不写日志。
- **源**：`builtin/config-mutator/mutate.sh:1`。
- **状态**：✅

#### FR-CONFIG-4：task-config-set 简写

- **描述**：终端用户用 `set.sh --task --key models.executor --value tier_strong` 调整任务级模型；可 `--unset` 清除。
- **验收标准**：
  - 允许 key：models.{default,router,planner,executor,reviewer,distiller}, hitl.mode；
  - 任务不存在 → exit 1；
  - 写入走 atomic。
- **源**：`builtin/task-config-set/set.sh:1`。
- **状态**：✅

#### FR-CONFIG-5：config-validate

- **描述**：对 config-resolve 输出执行字段级 schema 校验（types/ranges/enums/deprecated）。
- **验收标准**：
  - errors 非空 → exit 1，warnings 不阻断；
  - `--json` 输出 `{"ok": bool, "errors": [...], "warnings": [...]}`。
- **源**：`builtin/config-validate/validate.sh:1`。
- **状态**：✅

#### FR-CONFIG-6：draft_config helpers

- **描述**：`_lib/draft_config` 提供 router-agent 的 draft 校验与序列化（必填字段 + tier 白名单）。
- **验收标准**：
  - 缺必填 / tier 不合法 → ValueError；
  - YAML 序列化稳定排序便于 diff。
- **源**：`_lib/draft_config.py:_REQUIRED_KEYS, _VALID_TIERS`。
- **状态**：✅

---

### 3.9 LLM 调用层

#### FR-LLM-1：mock 优先解析顺序

- **描述**：`llm_call(prompt, *, name)` 在测试模式下按以下顺序解析响应：CN_LLM_MOCK_DIR/<name>.json|.txt → CN_LLM_MOCK_<NAME> → CN_LLM_MOCK_RESPONSE → CN_LLM_MOCK_FILE → fallback（"[mock-llm:<name>] " + prompt[:80]）。
- **验收标准**：
  - prompt 不是 string → TypeError；
  - mode 未识别 → ValueError；
  - 注入 `CN_LLM_MOCK_ERROR_*` → RuntimeError；
  - real 模式 shell out `claude --print --no-stream`。
- **源**：`_lib/llm_call.py:9-15, 50-57`。
- **状态**：✅

#### FR-LLM-2：模型探测与 TTL

- **描述**：`model-probe` 输出 catalog（refreshed_at, ttl_days, runtime, available, resolved_tiers, tier_priority），可 `--check-ttl` 判定缓存过期。
- **验收标准**：
  - probe 失败 stderr 以 `probe failed:` 开头；
  - `--check-ttl <file> --ttl-days N` 在 N 天内 exit 0，否则 exit 1；
  - 内置 fallback：opus-4.7 / sonnet-4.5 / haiku-4.5。
- **源**：`builtin/model-probe/probe.sh:1`。
- **状态**：✅

#### FR-LLM-3：token_estimate 启发

- **描述**：deterministic 4-char/token 估算用于 chain_summarize 等预算控制。
- **验收标准**：
  - estimate(text) = max(1, ceil(len/4))；
  - 无外部依赖；
  - 对 CJK 偏低估（设计权衡）。
- **源**：`_lib/token_estimate.py:21`。
- **状态**：✅

---

### 3.10 安全

#### FR-SEC-1：sec-audit 工作区扫描

- **描述**：扫描 secret 模式 + secrets.yaml 权限（应为 600）+ `.codenook/` 下 world-writable 文件。
- **验收标准**：
  - 尊重 `.gitignore`、跳 `.git/` 与 vendor 目录；
  - findings 非空 → exit 1；
  - severity ∈ {high, medium}；
  - patterns.txt 可外置。
- **源**：`builtin/sec-audit/audit.sh:1`。
- **状态**：✅

#### FR-SEC-2：secret_scan 共享检测器

- **描述**：9 条 fail-close 模式（AWS/OpenAI/GitHub PAT/PEM/RFC1918/IPv6 ULA/connection string）。
- **验收标准**：
  - `scan_secrets(text)` → `(hit, rule_id)`；
  - `redact(text)` 替换为 `***`。
- **源**：`_lib/secret_scan.py:21-51`。
- **状态**：✅

#### FR-SEC-3：secrets-resolve 占位符展开

- **描述**：`${env:NAME}` / `${file:path}` 两种占位符；nested 占位符禁止；missing env 默认硬失败。
- **验收标准**：
  - stderr 仅含 placeholder key，绝不含解析后值（`m1-secrets-resolve.bats::SECURITY` 强制）；
  - `--allow-missing` 时缺 env → "" + warning；
  - missing file 永远硬失败；
  - nested → exit 1。
- **源**：`builtin/secrets-resolve/resolve.sh:1`。
- **状态**：✅

#### FR-SEC-4：claude_md_linter

- **描述**：CLAUDE.md 规则检查器，禁止某些 token / M9.7 规则集。
- **验收标准**：
  - exit 0/1/2；
  - 默认禁词：`FORBIDDEN_TOKENS`；
  - M9.7 规则集 `_M97_RULES` 可独立开关。
- **源**：`_lib/claude_md_linter.py`（355 LOC，cli_main）。
- **状态**：✅

#### FR-SEC-5：plugin-shebang 限制

- **描述**：可执行文件首行只能是 4 种 shebang 之一。
- **验收标准**：见 G10 表格。
- **源**：`builtin/plugin-shebang-scan/shebang-scan.sh:1`。
- **状态**：✅

---

### 3.11 队列与会话

#### FR-QUEUE-1：通用 FIFO 队列

- **描述**：`queue-runner` 在 `.codenook/queues/<name>.jsonl` 上提供 enqueue/dequeue/peek/list/size，使用 fcntl 串行化。
- **验收标准**：
  - dequeue / peek 在空队列 → exit 1；
  - list 可选 `--filter <jq-expr>`；
  - 多并发 enqueue 不丢条目。
- **源**：`builtin/queue-runner/queue.sh:1-59`。
- **状态**：✅

#### FR-SESS-1：session-resume ≤500B 摘要

- **描述**：新 / 恢复会话时返回紧凑摘要（active_tasks、current_focus、last_session_summary、suggested_next）+ M1 兼容 keys。
- **验收标准**：
  - 输出 ≤500 UTF-8 字节；
  - 截断优先级：tail → one_liner → secondary → legacy keys（保结构完整）；
  - state.json 缺失时退化扫 tasks/。
- **源**：`builtin/session-resume/resume.sh:1`。
- **状态**：✅

#### FR-HITL-1：terminal HITL adapter

- **描述**：`hitl-adapter terminal.sh list/show/decide` 在终端模式下查看与决策 HITL 队列；决策不可重写。
- **验收标准**：
  - 已决策再 decide → exit 1（immutable replay）；
  - 决策同步写 `history/hitl.jsonl`；
  - decision ∈ {approve, reject, needs_changes}；
  - 互动 REPL 留给 M6+。
- **源**：`builtin/hitl-adapter/terminal.sh:1`。
- **状态**：✅

---

### 3.12 上下文扫描

#### FR-CTX-1：router-context-scan O(n) 摘要

- **描述**：返回安装插件、活动 task（封顶 max-tasks）、HITL pending、fanout pending、workspace warnings。
- **验收标准**：
  - 输出 ≤2KB；
  - 工作区 >100MB 或 >10K 文件 → 加入 workspace_warnings；
  - active_task 的判定：status ∉ {done, cancelled}；
  - 缺 workspace → exit 2。
- **源**：`builtin/router-context-scan/scan.sh:1-45`。
- **状态**：✅

#### FR-CTX-2：preflight 推进前体检

- **描述**：tick 之前必跑 preflight；六大检查（task 目录 / state JSON / dual_mode / phase 白名单 / HITL 阻塞 / config_overrides 合法）。
- **验收标准**：
  - 任一失败 → exit 1 + reasons；
  - reasons 排序去重。
- **源**：`builtin/preflight/preflight.sh:1`。
- **状态**：✅

---

## 4. 非功能需求 (NFR)

### 4.1 性能

| ID | 需求 | 验收预算 | 源 |
|----|------|---------|-----|
| NFR-PERF-1 | 内存索引冷构建 | 1000 文件 < 500ms (P95) | `_lib/memory_index.py`（AC-LAY-4） |
| NFR-PERF-2 | 内存索引 warm hit | < 200ms | 同上 |
| NFR-PERF-3 | chain walk depth ≤10 | P95 < 100ms | `_lib/task_chain.py`；spec §4.1 |
| NFR-PERF-4 | chain-snapshot 命中 | < 5ms | 同上 |
| NFR-PERF-5 | session-resume | 单次执行 < 200ms | `builtin/session-resume/_resume.py` |
| NFR-PERF-6 | dispatch payload | ≤500 UTF-8 字节硬限 | `builtin/router-dispatch-build/_build.py` |
| NFR-PERF-7 | router-context-scan 输出 | ≤2KB | `builtin/router-context-scan/_scan.py` |
| NFR-PERF-8 | 单插件 size | ≤1MB / 文件，≤10MB / 包 | G09 |

### 4.2 可靠性

- **NFR-REL-1**：所有写入走 atomic_write_json（tempfile + os.replace + fsync）。中断后文件要么旧要么新。源：`_lib/atomic.py`。
- **NFR-REL-2**：跨进程 RMW 使用 fcntl.flock，超时 5s（memory_layer）/30s（router.lock）。源：`_lib/memory_layer.py:58 LOCK_TIMEOUT_S`、`_lib/task_lock.py`。
- **NFR-REL-3**：extractor 全部 best-effort：失败 emit audit + exit 0（仅 secret-blocked 例外）。源：`extractor-batch/extractor-batch.sh`。
- **NFR-REL-4**：extractor 幂等键 = SHA256(task|phase|reason)；持久化在 `.codenook/memory/history/.trigger-keys`，**不自动过期**（v0.11 SPEC-PATCH A1-4 — 与 FR-EXTRACT-4 保持一致；v0.10 文档误称 "24h"）。
- **NFR-REL-5**：HITL decision 不可变（重决直接 exit 1）。源：`builtin/hitl-adapter/_hitl.py`。

### 4.3 可观测性

- **NFR-OBS-1**：8-key audit schema 强制（ts/task_id/plugin/kind/action/target/rationale/source）。源：`_lib/extract_audit.py`。
- **NFR-OBS-2**：audit log 文件 append-only，永不重写：`extraction-log.jsonl`、`dispatch.jsonl`、`distillation-log.jsonl`、`config-changes.jsonl`、`hitl.jsonl`。
- **NFR-OBS-3**：M10 引入 4 类 chain 诊断 audit：`chain_walk_truncated`、`chain_root_stale`、`chain_snapshot_slow_rebuild`、`chain_attach_failed`。
- **NFR-OBS-4**：dispatch-audit 始终 redact + 取 80 字符 preview，永不写明文 secret。

### 4.4 可扩展性

- **NFR-EXT-1**：plugin 通过 `plugin.yaml` 声明 entry_points / declared_subsystems，安装后 router 自动可见。
- **NFR-EXT-2**：skill 4 层查找允许 plugin 覆盖、workspace 覆盖、core 兜底。
- **NFR-EXT-3**：config 4 层覆盖允许 task 级最细粒度调参。

### 4.5 兼容性

- **NFR-COMPAT-1**：greenfield 原则——v6 epoch 内不保证向后兼容；旧数据自行迁移。
- **NFR-COMPAT-2**：fcntl 仅 POSIX 可用 → Windows **不支持**（task_lock 在 import 时报 ImportError）。源：`_lib/task_lock.py`。
- **NFR-COMPAT-3**：macOS / Linux 主目标；CI 在 macOS 与 Ubuntu 上跑 bats。

### 4.6 安全

- **NFR-SEC-1**：plugin 子树只读（FR-RO-1）。
- **NFR-SEC-2**：所有 dispatch payload 经 secret redact。
- **NFR-SEC-3**：secrets-resolve 输出明文密钥仅入 stdout，stderr 仅含 key 名。
- **NFR-SEC-4**：sec-audit 周期扫描 secrets.yaml 权限 + world-writable。
- **NFR-SEC-5**：路径 normalize 拒绝 symlink、绝对路径、`~`、`..`（G11）。

---

## 5. 数据模型

### 5.1 state.json 字段表

| 字段 | 类型 | 必需 | 说明 | 引入版本 |
|------|------|------|------|---------|
| schema_version | int | ✅ | 当前 = 1 | M4 |
| task_id | string | ✅ | `T-NNN` 格式 | M4 |
| plugin | string | ✅ | 选定 plugin id | M4 |
| phase | string | ✅ | start / implement / test / review / distill / accept / done | M4 |
| iteration | int | ✅ | 当前 phase 重试计数 | M4 |
| max_iterations | int | ✅ | 重试上限 | M4 |
| status | string | ✅ | pending / in_progress / waiting_hitl / blocked / done / cancelled / error | M4 |
| history | array | ✅ | 历史 phase 记录 | M4 |
| in_flight_agent | string\|null | – | 正在派发的 sub-agent id | M4 |
| config_overrides | object | – | layer4 task 覆盖 | M4 |
| subtasks | array | – | 子任务 id 列表 | M4 |
| depends_on | array | – | 阻塞前置任务 id | M4 |
| role_constraints | object | – | included/excluded role 列表 | M8.10 |
| dual_mode | string | – | serial \| parallel | M4 |
| **parent_id** | string\|null | – | 父任务 id | **M10.1** |
| **chain_root** | string\|null | – | 根任务 id（缓存） | **M10.1** |

源：`schemas/task-state.schema.json`。

### 5.2 extraction-log.jsonl 8-key 规范

```jsonc
{
  "ts": "2026-04-18T12:34:56Z",
  "task_id": "T-007",
  "plugin": "podcast",
  "kind": "knowledge_proposed | skill_promoted | config_patched | gc_pruned | chain_attached | parent_suggest_skip | ...",
  "action": "create | patch | merge | skip | promote | prune | attach | detach",
  "target": "memory/knowledge/<topic>.md | memory/skills/<name>/SKILL.md | tasks/<tid>/state.json | ...",
  "rationale": "<≤200 char>",
  "source": "knowledge-extractor | skill-extractor | config-extractor | memory_gc | task_chain | dispatch-audit"
}
```

### 5.3 .chain-snapshot.json v2

```jsonc
{
  "schema_version": 1,
  "generation": 42,
  "built_at": "2026-04-18T12:00:00Z",
  "entries": {
    "T-001": { "parent_id": null, "chain_root": "T-001", "state_mtime": "2026-04-18T11:50:12Z" },
    "T-007": { "parent_id": "T-001", "chain_root": "T-001", "state_mtime": "2026-04-18T11:55:30Z" }
  }
}
```

源：`_lib/task_chain.py:135-149`。

### 5.4 .index-snapshot.json (M9.1)

```jsonc
{
  "version": 1,
  "knowledge": { "<abs-path>": { "mtime": 1.7e9, "size": 1234, "frontmatter": {...} } },
  "skills":    { "<abs-path>": { "mtime": ..., "size": ..., "frontmatter": {...} } }
}
```

源：`_lib/memory_index.py`。

### 5.5 draft-config.yaml schema

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| plugin | string | ✅ | 目标 plugin |
| user_intent | string | ✅ | 一句话意图 |
| models.default | string (tier 或 model id) | ✅ | 必须在 _VALID_TIERS 或具体 id |
| models.executor | string | – | 可选 |
| models.reviewer | string | – | 可选 |
| hitl.mode | string | – | enum |
| dual_mode | string | – | serial / parallel |
| max_iterations | int | – | 默认 3 |

源：`_lib/draft_config.py:_REQUIRED_KEYS, _VALID_TIERS`。

### 5.6 plugin manifest schema（plugin.yaml）

| 字段 | 必需 | 说明 |
|------|------|------|
| id | ✅ | 匹配 `^[a-z][a-z0-9-]{2,30}$` |
| version | ✅ | SemVer 2.0 |
| type | ✅ | plugin / role-bundle / skill-bundle |
| entry_points | ✅ | 非空 mapping |
| declared_subsystems | ✅ | 列表，可为空 |
| requires.core_version | – | SemVer 约束串 |
| routing.keywords | – | 字符串列表 |
| routing.applies_to | – | 列表，可含 `*` |
| routing.priority | – | 默认 100 |
| knowledge.produces.promote_to_workspace_when | – | 表达式列表 |

源：`schemas/`、`_lib/manifest_load.py`、`_lib/plugin_manifest_index.py`。

---

## 6. CLI 接口清单

> 以下表格列出所有 builtin skill 的入口、参数、退出码。详细行为见 §3 与源文件。

### 6.1 安装与初始化

| Skill | 入口 | 关键参数 | 退出码 |
|-------|------|---------|-------|
| init | init.sh | `[<workspace_dir>]` | 0 |
| install-orchestrator | orchestrator.sh | `--src --workspace [--upgrade] [--dry-run] [--json]` | 0/1/2/3 |
| plugin-format | format-check.sh | `--src [--json]` | 0/1/2 |
| plugin-schema | schema-check.sh | `--src [--json]` | 0/1/2 |
| plugin-id-validate | id-validate.sh | `--src [--workspace] [--upgrade] [--json]` | 0/1/2 |
| plugin-version-check | version-check.sh | `--src [--workspace] [--upgrade] [--json]` | 0/1/2 |
| plugin-signature | signature-check.sh | `--src [--json]` (env: CODENOOK_REQUIRE_SIG) | 0/1/2 |
| plugin-deps-check | deps-check.sh | `--src [--core-version] [--json]` | 0/1/2 |
| plugin-subsystem-claim | subsystem-claim.sh | `--src [--workspace] [--upgrade] [--json]` | 0/1/2 |
| plugin-shebang-scan | shebang-scan.sh | `--src [--json]` | 0/1/2 |
| plugin-path-normalize | path-normalize.sh | `--src [--json]` | 0/1/2 |

### 6.2 任务编排

| Skill | 入口 | 关键参数 | 退出码 |
|-------|------|---------|-------|
| router | bootstrap.sh | `--user-input [--workspace] [--task] [--json]` | 0/1/2 |
| router-agent | spawn.sh | `--task-id --workspace [--user-turn\|--user-turn-file] [--confirm]` | 0/2/3/4 |
| router-context-scan | scan.sh | `[--workspace] [--max-tasks N] [--json]` | 0/2 |
| router-dispatch-build | build.sh | `--target --user-input [--task] [--workspace] [--json]` | 0/1/2 |
| orchestrator-tick | tick.sh | `--task [--workspace] [--dry-run] [--json]` | 0/1/2/3 |
| preflight | preflight.sh | `--task [--workspace] [--json]` | 0/1/2 |
| dispatch-audit | emit.sh | `--role --payload [--workspace]` | 0/1/2 |

### 6.3 抽取与内存

| Skill | 入口 | 关键参数 | 退出码 |
|-------|------|---------|-------|
| extractor-batch | extractor-batch.sh | `--task-id --reason [--workspace] [--phase]` | 0 |
| knowledge-extractor | extract.sh | `--task-id --workspace --phase --reason [--input]` | 0 / non-zero (secret) |
| skill-extractor | extract.sh | 同上 | 同上 |
| config-extractor | extract.sh | 同上 | 同上 |
| distiller | distill.sh | `--plugin --topic --content --workspace` | 0/1/2 |
| memory_gc (CLI) | `python -m memory_gc` | `--workspace [--dry-run] [--json]` | 0/1/2 |

### 6.4 配置与 LLM

| Skill | 入口 | 关键参数 | 退出码 |
|-------|------|---------|-------|
| config-resolve | resolve.sh | `--plugin --workspace --task [--catalog]` | 0/1/2 |
| config-validate | validate.sh | `--config [--schema] [--json]` | 0/1/2 |
| config-mutator | mutate.sh | `--plugin --path (--value\|--value-json) --reason --actor --workspace [--scope --task]` | 0/1/2 |
| task-config-set | set.sh | `--task --key --value [--unset] [--workspace]` | 0/1/2 |
| model-probe | probe.sh | `[--output] [--output-state-json] [--tier-priority] [--check-ttl --ttl-days]` | 0 / non-zero |

### 6.5 安全 / 队列 / 会话 / 链路

| Skill | 入口 | 关键参数 | 退出码 |
|-------|------|---------|-------|
| sec-audit | audit.sh | `--workspace [--json]` | 0/1/2 |
| secrets-resolve | resolve.sh | `--config [--allow-missing]` | 0/1/2 |
| skill-resolve | resolve-skill.sh | `--name --plugin --workspace [--json]` | 0/1/2 |
| queue-runner | queue.sh | `<subcmd> --queue [--payload] [--filter] [--workspace]` | 0/1/2 |
| session-resume | resume.sh | `[--workspace] [--json]` | 0 |
| hitl-adapter | terminal.sh | `list\|show\|decide --id --decision --reviewer [--comment]` | 0/1/2 |
| plugin_readonly (CLI) | `python plugin_readonly.py` | `--target [--json] [--exclude GLOB]...` | 0/1/2 |
| parent_suggester (CLI) | `python -m parent_suggester` | `--workspace --brief [--top-k] [--threshold] [--exclude TID]...` | 0/1/2 |
| claude_md_linter (CLI) | cli_main | path / flags | 0/1/2 |

---

## 7. 已知限制 / 未来工作

### 7.1 平台限制

- **L-1**：fcntl 依赖 → **Windows 不支持** task_lock，相关功能禁用（NFR-COMPAT-2）。
- **L-2**：plugin-signature **仅 sha256 baseline**；M5 计划接入真实 GPG / Sigstore。
- **L-3**：HITL 仅终端模式；REPL / Web UI 留给 M6+。

### 7.2 抽取与内存

- **L-4**：knowledge similarity 用简单 SHA-256 前 512 字符 dedup + LLM judge，未引入 embedding 向量库（M11 候选）。
- **L-5**：memory_gc 仅按 created_from_task 维度，不做跨 task 全局合并。
- **L-6**：extractor 调用 LLM 时未做并发限速；高频 phase 完成可能造成 API rate limit 抖动。

### 7.3 任务链

- **L-7**：chain_summarize LLM 兜底 mock 字符串；real-mode 调用如失败仅写一次 audit 不重试。
- **L-8**：parent_suggester 评分仅 token-set Jaccard；未支持语义检索。
- **L-9**：router 调用站点默认 chain depth 护栏 = 100（library 层 `walk_ancestors` 默认 `None`，见 FR-CHAIN-2 v0.11 patch）；超长链路被截断（emit `chain_walk_truncated`）但无人工接管入口。

### 7.4 配置

- **L-10**：config-validate schema 仍偏 M1；plugin-specific schema 由 plugin 自行交付，core 不强校。
- **L-11**：config-mutator 不支持批量事务，多 path 修改需多次调用。

### 7.5 安全

- **L-12**：secret_scan 9 条 fail-close 模式不可扩展（要修源码）；M11 计划支持 patterns.txt 注入。
- **L-13**：plugin_readonly 静态扫只覆盖 Python；shell / JS 待补。

### 7.6 路由

- **L-14**：router_select 仅子串匹配 + priority；无 intent embedding。
- **L-15**：router-context-scan 字节预算 2KB 在大型 monorepo 容易触发 truncation，需要逐渐替换 warnings。

---

## 8. 附录

### 8.1 文件 / 模块速查表

#### 8.1.1 `_lib/` 共享模块（27 个）

| 模块 | 行数 | 关键 API | CLI |
|------|------|---------|-----|
| atomic.py | ~50 | atomic_write_json | – |
| builtin_catalog.py | 23 | BUILTIN_SKILLS, BUILTIN_INTENTS | – |
| chain_summarize.py | ~360 | summarize_chain | – |
| claude_md_linter.py | ~355 | lint() | cli_main |
| draft_config.py | 293 | parse, validate, dumps | – |
| expr_eval.py | 260 | safe_eval (no `__`/`import`) | – |
| extract_audit.py | 56 | append_audit | – |
| jsonschema_lite.py | 112 | validate | _cli |
| knowledge_index.py | 186 | scan_knowledge | – |
| llm_call.py | 135 | call(prompt, name) | – |
| manifest_load.py | 89 | list_installed_ids, load_manifest, load_all | – |
| memory_gc.py | 303 | – | `python -m memory_gc` |
| memory_index.py | 226 | get_hash, build_index, invalidate | – |
| memory_layer.py | ~775 | init_memory_skeleton, scan/read/write/patch | – |
| parent_suggester.py | 377 | suggest_parents | `python -m parent_suggester` |
| plugin_manifest_index.py | 190 | discover_plugins, summary_for_router | – |
| plugin_readonly.py | 321 | assert_writable_path | cli_main |
| role_index.py | 174 | discover_roles, filter_roles | – |
| router_context.py | 334 | initial_context, append_turn, update_frontmatter | – |
| router_select.py | 133 | select, select_with_score | – |
| secret_scan.py | 57 | scan_secrets, redact | – |
| semver.py | 77 | parse, satisfies | – |
| task_chain.py | 500+ | get_parent, set_parent, walk_ancestors, chain_root, detach | cli_main (隐含) |
| task_lock.py | 327 | acquire, inspect, force_release | – |
| token_estimate.py | 26 | estimate(text) | – |
| workspace_overlay.py | 192 | discover_overlay_skills/knowledge, merge_config_into_draft | – |

#### 8.1.2 builtin/ 子目录（34 个 skill）

详见 §6 CLI 表格；分类：
- **安装管线**：install-orchestrator + 11 plugin-* gates
- **路由**：router, router-agent, router-context-scan, router-dispatch-build
- **任务循环**：orchestrator-tick, preflight, dispatch-audit
- **抽取**：extractor-batch, knowledge-extractor, skill-extractor, config-extractor, distiller
- **配置**：config-resolve, config-validate, config-mutator, task-config-set, model-probe
- **内存 / 队列 / 会话**：memory_gc(CLI), queue-runner, session-resume
- **安全**：sec-audit, secrets-resolve, plugin_readonly(CLI)
- **HITL**：hitl-adapter
- **解析**：skill-resolve
- **初始化**：init

### 8.2 术语表

见 §1.3。

### 8.3 参考文档清单

- `CLAUDE.md`, `README.md`, `CHANGELOG.md`, `PIPELINE.md`, `VERSION`
- `docs/architecture.md`
- `docs/implementation.md`
- `docs/router-agent.md`
- `docs/memory-and-extraction.md`
- `docs/task-chains.md`
- `docs/test-plan.md`
- `docs/m9-test-cases.md`
- `docs/m10-test-cases.md`
- `skills/codenook-core/tests/*.bats`

---

## 附：审计发现（代码 vs. 文档差异）

> 本节记录在反向工程中发现的、与 spec 文档不完全一致的实现点，作为后续验收阶段的优先核查项。
> **v0.11 状态**：除 A.1#6 标记 [DEFER-v0.12]、MEDIUM-04 部分项延后，其他全部 patched（详见 `docs/m11-decisions.md` 与 `CHANGELOG.md` v0.11.0）。

### A.1 代码与文档不一致

1. **dual_mode 默认值**：spec 多处隐含默认 `serial`，但 preflight 仅在 `total_iterations > 1` 时检查 dual_mode 存在；当 max_iterations=1 时缺字段也通过 → 文档应明确"可选 + 缺省视为 serial"。源：`builtin/preflight/_preflight.py`。 **✅ v0.11 SPEC-PATCH（FR-TASK-3）**
2. **chain max_depth 默认 10**：spec §4.1 提"默认 10"，task_chain.py 实现允许 `max_depth=None` 走另一分支（无截断），与 spec 的"必有截断"叙述存在边界差异。源：`_lib/task_chain.py:417`。 **✅ v0.11 SPEC-PATCH（FR-CHAIN-2 + L-9 + task-chains.md §6）**
3. **plugin.yaml.sig 比较语义**：实现允许"first non-blank token"宽松对比（即文件内可包含注释/换行），spec 未说明此宽松。源：`plugin-signature/_signature_check.py`。 **✅ v0.11 SPEC-PATCH（G05 表格）**
4. **extractor 24h 幂等窗口**：代码用 SHA-256 key 但未显式过期；当前理解的"24h 内幂等"实际取决于 audit 文件的轮转策略（未实现轮转）→ 严格说"永久幂等"。源：`extractor-batch/extractor-batch.sh`。 **✅ v0.11 SPEC-PATCH（FR-TASK-4 + FR-EXTRACT-4 + NFR-REL-4）**
5. **secret patterns 数量**：spec 提"多类 secret 模式"，secret_scan.py 实测为 9 条；与某些文档处提到的"10 条"不符。源：`_lib/secret_scan.py:21`。 **✅ v0.11 SPEC-PATCH（FR-EXTRACT-5）**
6. **session-resume M1 兼容键**：实现保留了一组"M1-compat keys"（active_task / phase / iteration / summary / hitl_pending / next_suggested_action / last_action_ts / total_iterations）—— v6 spec 已声明 greenfield，理论上可删除，但代码仍保留并占预算。 **🟡 [DEFER-v0.12]**：删除需同时改写 m1-session-resume.bats（10 条 assert），单独成 epic（schema v2）。
7. **router-agent --confirm 的退出码 4**：spec 中标记为"validation failure"，但实现把 draft yaml 解析错误也归在 4；与文档枚举 0/2/3/4 描述粒度不一致。 **✅ v0.11 SPEC-PATCH（FR-ROUTER-2）**
8. **plugin-format 与 plugin-path-normalize 的 symlink 策略不同**：G01 允许内部相对 symlink、仅禁越界；G11 禁止所有 symlink。spec 在两处都用"symlink 受限"模糊描述，未明确双闸门差异。 **✅ v0.11 SPEC-PATCH（G01 + G11 表格）**

### A.2 代码已实现但 spec 未文档化

1. **plugin_readonly 静态 CLI 模式**：spec 仅描述运行时 guard，未提"独立扫描器" + 默认排除 test-fixture。源：`_lib/plugin_readonly.py:263`。 **✅ v0.11 SPEC-PATCH（FR-SKILL-2）**
2. **parent_suggester 内置 EN+ZH stopwords 表**（~70 词）：spec §5 写"分词 + jaccard"但未公开停用词清单，可作为 plugin 调参依据。 **✅ v0.11 SPEC-PATCH（FR-CHAIN-5）**
3. **task_lock stale 判定阈值 300s + 不可解析 payload 永不 unlink**：spec 提"恢复死锁"但未规定 300s 阈值与"保守不删"策略。 **✅ v0.11 SPEC-PATCH（FR-ROUTER-3）**
4. **memory_gc 对 promoted 条目的跳过逻辑**：spec 仅提"caps"，未提 `promoted=true` 的条目永不被淘汰。 **✅ v0.11 SPEC-PATCH（FR-MEM-4）**
5. **config-resolve 兜底链 strong→balanced→cheap→opus-4.7 硬编码**：spec 提 fallback 但未规定具体顺序与最末兜底模型 ID。 **✅ 已存（FR-CONFIG-1 / FR-CONFIG-2）— 无需 patch**
6. **dispatch-audit redaction 名单**：实现含 9 类常见密钥模式，spec 仅提"redact secrets"未列具体模式表。 **✅ v0.11 SPEC-PATCH（FR-EXTRACT-5）**
7. **router-agent 在 --user-turn-file 模式下的 stdin 行为**：实现支持 `-` 读 stdin，文档未提。 **✅ v0.11 SPEC-PATCH（FR-ROUTER-2）**
8. **distiller 表达式 sandbox 禁用 `__` 与 `import`**：spec 提"安全表达式"未给禁用清单。 **✅ v0.11 SPEC-PATCH（FR-DIST-1）**
9. **extractor-batch 通过 `nohup` 分离派发**：spec 仅提"detached"未明确机制，影响 ops 排查。 **✅ v0.11 SPEC-PATCH（FR-EXTRACT-4）**
10. **plugin_manifest_index DEFAULT_PRIORITY = 100**：spec 提 priority 平分但未给默认。 **✅ v0.11 SPEC-PATCH（FR-PLUGIN-MANIFEST + §5.6）**

### A.3 待验收阶段确认事项

- A.1 项目应在下一次 spec patch 中明确化；**v0.11 已完成 7/8（A.1#6 → DEFER-v0.12）**。
- A.2 项目应判定是否补入 spec 或保留为内部细节；**v0.11 决策：全部补入 spec（10/10）**。
- 需要评估是否新增 NFR-COMPAT-4 明确"Windows = unsupported"（避免误装）。**v0.11 已通过 NFR-COMPAT-2 措辞强化覆盖。**

### A.4 v0.11 后新增 backlog（→ v0.12）

- **A1-6 session-resume schema v2**：删除 8 个 M1-compat keys + 改写 m1-session-resume.bats。
- **MEDIUM-04 真实 `fcntl.flock` snapshot 锁**：与多进程 orchestration 一并设计。
- **AT-LLM-2.1 / AT-COMPAT-1 / AT-COMPAT-3 / AT-REL-1**：reviewer 手册 + Linux CI matrix + jq 缺失诊断 bats。

