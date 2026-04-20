# CodeNook — 插件架构

> **历史说明**：本文档在设计阶段被内部称为 "v6 设计草案"；该设计已实现于 v0.11.0（`skills/codenook-core/` + `plugins/`），文档保留为设计共识与决策档案。v5 单体 POC 已于 v0.11.1 从仓库移除（见顶层 CHANGELOG）；本节及 §9 的迁移描述仅作历史记录。
>
> **v0.11.2 状态附注（DR-003）**：本文档中所有 `init.sh --install-plugin` / `--pack-plugin` / `--scaffold-plugin` / `--upgrade-core` 等子命令均为**目标态设计**。截至 v0.11.2，`skills/codenook-core/init.sh` 仅 `--version`、`--help`、`--refresh-models` 三项已落地（`✅ live`），其余子命令保留 `exit 2: TODO` 占位（`🚧 planned for v0.12`）。当前可用的安装路径为顶层 `bash install.sh <workspace_path>`（见 README §Quick Start），其内部委派 `skills/codenook-core/install.sh` 执行同样的 12 个安装关卡。

## 1. v5 的问题

v5 把所有东西打包进一个 skill 中：
- Orchestrator（编排器）机制（dispatch、队列、锁、HITL、状态、distiller、安全审计）——**领域无关**
- 软件开发流水线（6 个阶段、7 个角色、pytest 验收、review 迭代）——**领域相关**

希望将 CodeNook 的纪律应用于非编码工作（写作、研究、内容生产）的用户没有干净的扩展点。反过来，领域演进（例如新增一个 "product-spec" plugin）需要 fork 整个 POC。

## 2. 分层模型

```
┌──────────────────────────────────────────────────────────────────┐
│  Main session = orchestrator                                     │
│    ─ Classifies input: chat vs task candidate                    │
│    ─ Asks user to confirm before spawning the machinery          │
│    ─ Delegates plugin selection to router agent                  │
│    ─ Mounts selected plugin + drives its phase pipeline          │
└───────────────┬──────────────────┬─────────────────┬─────────────┘
                │                  │                 │
        ┌───────▼────────┐   ┌─────▼─────┐    ┌──────▼──────┐
        │ builtin agents │   │ builtin   │    │ plugin      │
        │  ─ router      │   │ skills    │    │ <active>    │
        │  ─ distiller   │   │ ─ sec-    │    │  phases/    │
        │  ─ security-   │   │   audit   │    │  roles/     │
        │    auditor     │   │ ─ queue-  │    │  skills/    │
        │  ─ hitl-adapter│   │   runner  │    │  validators │
        └────────────────┘   └───────────┘    └─────────────┘
                                                    │
                                                    ▼
                                      ┌──────────────────────────────────┐
                                      │ <workspace>/.codenook/plugins/   │
                                      │  ├── development/                │
                                      │  ├── writing/                    │
                                      │  └── generic/  ★builtin (seeded) │
                                      └──────────────────────────────────┘
```

> **单工作区模型**：**没有全局的 `~/.codenook/`** 安装。用户在机器上挑选一个目录作为 *那个* CodeNook 节点（例如 `~/Documents/workspace/development/`）；core、builtin 的 agents/skills、plugins、tasks、queue、history 全都位于该 workspace 的 `.codenook/` 之下。任务可以通过 `target_dir` 操作外部代码/数据目录（见 §8），但 CodeNook 本身永远不会被全局安装。

### 2.1 各层

| 层 | 职责 | 位置 | 版本管理 |
|---|---|---|---|
| **Core** | 编排机制、状态机、dispatch 协议、任务/子任务树、阶段转换、verdict 语义、模型路由、配置加载 | `<workspace>/.codenook/core/`（由 `init.sh` 从 `skills/codenook-core/` 安装） | Git 仓库版本 |
| **Builtin agents** | 与 core 一起发布的领域无关角色代理 | `<workspace>/.codenook/agents/builtin/` | 与 core 绑定 |
| **Builtin skills** | 领域无关的运维能力：security-audit、queue-runner、distiller、dispatch-audit、keyring、preflight、secret-scan、HITL adapter | `<workspace>/.codenook/skills/builtin/` | 与 core 绑定 |
| **Plugin** | 领域流水线定义（phases/roles/entry-questions/HITL gates）+ 可选的 plugin 本地 skills 与 validators | `<workspace>/.codenook/plugins/<name>/` | 每个 plugin 独立打包并独立版本管理 |

### 2.2 Core vs plugin —— 决策矩阵

一项内容属于 **core**，如果它：
- 是领域无关的（适用于代码、文章、研究、设计……）
- 关注的是任务运行的*机制*（dispatch、状态、审计、锁、并发）
- 移除后会破坏*所有*领域中的任务

一项内容属于 **plugin**，如果它：
- 假设了某种特定的输出格式 / 验证方式
- 命名了具体的 phase 或角色期望
- 仅对一个领域族有用

具体例子归类：

| 关注点 | 层 | 理由 |
|---|---|---|
| `dual_mode: serial/parallel` 标志 | Core | 机制；适用于任何 iterate-then-review 循环 |
| Phase 名 `clarify/design/implement/test/accept/validate` | Plugin（development） | 写作会使用 `outline/draft/edit/review/publish` |
| 角色 "planner"、"implementer"、"reviewer" | Plugin —— **除了** router/distiller/security-auditor 是 builtin | 插件特定的执行角色 |
| 安全审计（preflight/secret-scan/keyring） | Core（builtin skill） | 无论领域如何，每个 workspace 都需要 |
| Session distiller | Core（builtin skill + builtin agent） | 上下文卫生是普适的 |
| `max_iterations`、`start_phase`、`status` 等 OPT-7 字段 | Core | 机制——plugin 的 phase 接入这些字段 |
| Queue runtime、locks/ | Core | 并发原语与领域无关 |
| HITL 门*策略*（在哪里触发、自动通过规则） | Plugin | 不同领域在不同位置设门 |
| HITL *adapter*（terminal.sh、queue 格式、决策文件） | Core（builtin skill） | 普适机制 |
| `integration-test` 清单的命名（用于 fanout） | Plugin | 仅当 plugin 定义了 "test" phase 时才有意义 |

## 3. Main session 控制流

```
┌─────────────────────────────────────────────────────────────────┐
│ User input received                                             │
└────────────┬────────────────────────────────────────────────────┘
             ▼
     ┌───────────────┐     no     ┌──────────────────────┐
     │ Chat or task? ├──chat ────▶│ Answer inline, no    │
     └───────┬───────┘            │ task created         │
             │ task candidate     └──────────────────────┘
             ▼
     ┌─────────────────────────────────────────┐    no    ┌───────────────┐
     │ ask_user: "Looks like a task (<sum>).   ├─────────▶│ Decline → chat│
     │  Create a CodeNook task tracking for it?│          └───────────────┘
     └────────────┬────────────────────────────┘
                  │ yes
                  ▼
     ┌─────────────────────────────────────────┐
     │ Hand off to router agent (builtin)      │
     │ Pass: { task_description, user_context }│
     │ Main session is DONE — router takes over│
     └────────────┬────────────────────────────┘
                  ▼
     ┌─────────────────────────────────────────────────────────────────┐
     │ Router agent (autonomous):                                      │
     │   1. Scans <workspace>/.codenook/plugins/*/plugin.yaml          │
     │   2. Builds plugin catalog                                      │
     │   3. Classifies task → picks plugin (or generic fallback)       │
     │   4. Returns {plugin, confidence, rationale, alternates}        │
     └────────────┬────────────────────────────────────────────────────┘
                  ▼
     ┌─────────────────────────────────────────┐  low conf  ┌────────────────────┐
     │ Confidence ≥ threshold?                 ├──────────▶│ ask_user to confirm │
     └────────────┬────────────────────────────┘           │ suggested plugin    │
                  │ high conf                              └──────┬──────────────┘
                  │                                               │
                  ▼                                               ▼
     ┌──────────────────────────────────────────────────────────────┐
     │ Mount plugin (load phases.yaml, roles/, entry-questions.yaml)│
     │ Create task T-NNN, write state.plugin = <name>, run preflight│
     │ Enter first phase of plugin pipeline                         │
     └──────────────────────────────────────────────────────────────┘
```

**Main session 的纪律（严格）**：
- Main session 只做：(a) 与用户对话，(b) 判断输入是否值得创建一个被追踪的 task，(c) 通过 `ask_user` 确认，(d) 把任务描述移交给 router。**仅此而已。**
- Main session 不扫描 plugin、不构建 catalog、不挑选 plugin。这些全部是 router 的工作。
- 如果用户显式指定了 plugin（例如 "create a writing task to ..."），main session 会把它作为提示放在移交载荷中；router 仍然做决定（可能采纳提示，也可能用理由覆盖之）。
- Router 总会返回*某个* plugin —— 如果没有领域匹配，它会选择 `generic`（builtin 的 fallback plugin）。

### 3.1 Main session 加载了什么？（v5 → v6 编排器分解）

> **关键改动**：v5 中 main session 加载的是完整的 `codenook-core.md`（约 20K，含状态机、路由表、dispatch 协议、HITL 处理、distill 调用、context 自检……）。这与"main session 只做对话"的纪律根本冲突。v6 必须把编排器从 main session **拆出去**。

#### 3.1.1 v5 的现状（要被替换）

```
CLAUDE.md → 加载 codenook-core.md (20K)
  ├─ 状态机定义 + 10 阶段路由表
  ├─ dispatch 协议（Task tool 调用模板）
  ├─ HITL gate 处理逻辑
  ├─ distill 触发规则
  ├─ context self-check + 建议 /clear
  └─ session bootstrap（读 latest.md / state.json / 决定继续哪个 task）

Main session 既是路由器、又是状态机执行器、还是 HITL 处理器、distiller 触发器。
```

#### 3.1.2 v6 拆分后

Main session 只加载一个**极薄**的引导文件——`codenook-shell.md`（目标 ≤ 3K），只描述四件事：

```
1. 会话礼仪（"你是 CodeNook 的对话前端，不要直接干活"）
2. chat-vs-task 判别启发式（关键词、显式指令 /task）
3. ask_user 确认模板
4. handoff 协议：如何把任务描述传给 orchestrator-tick（见下）
```

原 `codenook-core.md` 的内容被分成四块，分别外置：

| v5 中的角色 | v6 中的归宿 | 形态 |
|---|---|---|
| 状态机、路由表 | **plugin 的 `phases.yaml` + `transitions.yaml`** | 插件契约 |
| dispatch 协议、tick 算法、HITL 队列处理、并发限额 | **builtin skill `orchestrator-tick`** | 无状态脚本 |
| Session bootstrap（哪个 task 继续？） | **builtin skill `session-resume`** | main session 在新会话首次发言前调用 |
| distill 触发、context self-check、安全审计调度 | **builtin agents（distiller / security-auditor）** + tick 自动调度 | 由 orchestrator-tick 内部触发 |

#### 3.1.3 `orchestrator-tick`（替代 v5 主循环）

核心想法：**编排是无状态的**。所有真相都在 `<workspace>/.codenook/state.json`、`tasks/T-NNN/state.json`、`queue/*.json` 里。一次 "tick" 就是：读状态 → 决定下一步 → 执行一步 → 写状态 → 返回。

```
orchestrator-tick.sh <task_id>
  1. 读 .codenook/tasks/<task_id>/state.json
  2. 读 .codenook/plugins/<state.plugin>/phases.yaml + transitions.yaml
  3. 计算下一步动作：
       - 若当前 phase 未启动 → 派发该 phase 的 role agent
       - 若有 agent 进行中 → 检查 output_path 是否就绪
       - 若 phase 输出就绪、未校验 → 派 validator agent
       - 若 verdict pass、当前是 HITL gate → 写入 hitl-queue
       - 若 HITL approved → 推进到下一 phase（查 transitions.yaml）
       - 若 task 完成 → 标记 done、触发 distiller
  4. 更新 state.json，写一行到 history/orchestrator-log.jsonl
  5. 返回 JSON：{ status, next_action, dispatched_agent_id?, message_for_user? }
```

Main session 在以下时机调用 `orchestrator-tick`（**不是循环，而是事件驱动**）：

- 用户每发一次有意义的输入后（默认每轮调用一次，最多每个 active task 一次）
- HITL approval 写入后（用户点了"批准"）
- 用户显式说 "继续 / 推进 T-007"

调用方式：以 builtin skill 形式 invoke（main session 写一个超短的 prompt manifest，dispatch 一个 helper agent 去执行 tick；helper 完成后只回 ≤200 字 summary 给 main session）。Main session 自己**绝不**直接执行 tick 逻辑。

**术语界定（v6 决议 #I-3）**：本文中 "builtin skill" = 算法说明（`SKILL.md`）+ 可执行脚本/模板，**不**是常驻 agent；运行时由 main session 通过 dispatch helper agent（fresh context）拉起执行。"builtin agent" 才是有 profile（`agent.md`）的角色（如 router、distiller）。`orchestrator-tick`、`session-resume`、`config-resolve` 等都是 **skill**，每次执行都是无状态、由 helper agent 临时承载。

**多任务触发语义（v6 决议 #T-1）**：
- 默认每个用户回合最多对**当前 focus task** 派 1 次 tick；
- 若用户显式说 "全部继续" / "推进所有任务"，main session 按 `state.json.active_tasks` 列表 fan-out，**每个 active task 各派 1 次 tick**（并发上限读 `config.yaml.concurrency`，未启用时串行）；
- HITL approval 写入只触发被 approval 的那一个 task 的 tick；
- 同一 task 在同一回合内重复触发被 dedup（tick 自身在 `state.json.last_tick_ts` 判断）。

#### 3.1.4 `session-resume`（替代 v5 bootstrap）

新会话第一次接收用户输入前，main session（按 `codenook-shell.md` 指示）派一个 `session-resume` helper agent：

```
session-resume agent 任务：
  1. 读 .codenook/state.json（active_tasks, current_focus）
  2. 读 .codenook/history/sessions/latest.md
  3. 为每个 active task 读 tasks/<id>/state.json，生成一行状态摘要
  4. 返回 ≤500 字摘要给 main session
```

Main session 拿到这 500 字后才开始与用户对话（"上次我们在做 T-007 的 implement 阶段，要继续吗？"）。这样 main session 永远不直接读 `state.json` 之类的状态文件。

**实现形态（v6 决议 #T-2）**：MVP 阶段 `session-resume` 是**确定性脚本**（bash + jq + 模板 string interpolation），读 `state.json` + `history/sessions/latest.md` 后直接产出固定格式的摘要，**不调 LLM**——理由：信息汇总是机械任务，避免 LLM 飘忽与 token 成本。未来若需要更聪明的"上次到哪了"自然语言总结，可升级为 LLM 路径，但摘要长度上限固定为 ≤500 token。

#### 3.1.5 Main session context 预算（稳态）

```
codenook-shell.md            ~3K       常驻
session-resume 摘要           ~500      首次对话前一次性
每次 orchestrator-tick 摘要    ~200      每用户回合 1 次
─────────────────────────────────────
固定上下文（5K 红线）：≤ 5K
对话历史                       变化      独立累积，不计入 5K 红线
（v5 中是 ≥ 20K + 每 phase 累积，v6 把累积彻底外置）
```

**5K 红线的精确定义（v6 决议 #T-11）**：5K 红线**只**约束 main session 加载的固定上下文（`shell.md` + `session-resume` 摘要 + 每跳 tick 摘要）。**对话历史不计入**——它独立累积，由 sub-agent（distiller）按需触发蒸馏；main session 自身**永不**自我 distill（避免吞掉用户最近的指令）。当对话历史过长时，distiller 蒸馏到 `history/sessions/` 后，main session 由用户 `/clear` 显式重置。

#### 3.1.6 这意味着 v5 → v6 的代码迁移

| v5 文件 | v6 去向 |
|---|---|
| `templates/core/codenook-core.md` (20K) | 拆为：`shell.md` (3K，留在 core 加载) + `orchestrator-tick` skill + `session-resume` skill + 各 plugin 的 `phases.yaml/transitions.yaml` |
| `templates/CLAUDE.md` | 简化为只指向 `shell.md`；移除所有"状态机/路由表/HITL 处理"的引用 |
| `templates/queue-runner.sh` | 内化进 `orchestrator-tick`（tick 调用时计算就绪队列） |
| `templates/dispatch-audit.sh` | 保留为 builtin skill，由 orchestrator-tick 调用 |
| `templates/preflight.sh` | 保留为 builtin skill，由 orchestrator-tick 在 phase 推进前调用 |
| `templates/subtask-runner.sh` | 内化进 `orchestrator-tick`（fan-out phase 的处理分支） |

#### 3.1.7 Dispatch 协议 vs Prompt 模板（重要纪律）

**Main session 不持有任何 sub-agent 的 prompt 模板**——只持有 dispatch 约定。

```
Main session 端（在 shell.md 里固化）
├── dispatch 协议：知道"派 X agent 时该写哪一行指令"
└── 回包 schema：知道收到的 JSON 字段名

Sub-agent 端（agent 自己读）
├── 自己的 profile（agents/builtin/<name>.agent.md）
├── 自己的 role 模板（plugins/<p>/roles/<role>.md，如适用）
└── 任务上下文（state.json、上游 summary、引用文件）
```

**示例：派 router**

Main session 发出（≤100 字）：
```
Execute router.
Profile: .codenook/agents/builtin/router.agent.md
User input: "<原话>"
Workspace: <cwd>
```

Router agent fresh context 内自己完成：
1. 读 `router.agent.md`（self-bootstrap 协议在里面）
2. `ls .codenook/plugins/*/plugin.yaml` 建 catalog
3. 决策
4. 返回 `{plugin, confidence, rationale, alternates}`（≤300 字）

**示例：派 orchestrator-tick**

Main session 发出：
```
Execute tick.
Profile: .codenook/skills/builtin/orchestrator-tick/SKILL.md
Task: T-NNN
```

Tick agent 自己读 plugin 的 `transitions.yaml`、`state.json`、`queue/`，计算下一步，dispatch 下一个 worker，回 ≤200 字 summary。

**纪律重申**：
- Main session 永远不 inline sub-agent 的指令内容
- Main session 永远不读 plugin 的 `phases.yaml / roles/*.md`
- Main session 永远不构造 prompt manifest（那是 planner agent 或 tick agent 的活）
- 一切 "agent 该做什么" 的知识，由该 agent 自己 pull

这是 v5 已经定下的 Push → Pull 纪律，v6 继续严格执行。

**Dispatch payload 字数硬上限（v6 决议 #T-3）**：main session 发出的任何单次 dispatch payload **硬上限 500 字**（含 profile path、task_id、user input quote、上游 summary path 等所有字段），推荐 ≤200 字。超限时 main session 必须把长内容落盘为引用文件（如 `tasks/T-NNN/dispatch/<ts>.md`），dispatch 中只传路径。这是 main session 不"携带知识"的兜底约束。

### 3.2 子系统模块化策略

v6 把 v5 的平铺子系统按"是否需要按 plugin 隔离"重新组织。

#### 3.2.1 总览

| 子系统 | 模块化？ | 隔离机制 | 路径骨架 |
|---|---|---|---|
| memory (knowledge) | ✅ 3 层 | shipped / workspace-shared / plugin-local | `plugins/<p>/knowledge/` + `knowledge/` + `memory/<p>/` |
| skills | ✅ 3 层 | builtin / plugin-shipped / workspace-custom / plugin-local-custom | `skills/builtin/` + `plugins/<p>/skills/` + `skills/custom/` + `memory/<p>/skills/` |
| config | ✅ 4 层覆盖 | 单文件分段 + plugin baseline + task overrides | `plugins/<p>/config-defaults.yaml` + `config.yaml` + `tasks/T-*/state.json` |
| history | ❌ 单时间线 | entry 加 `plugin:` 字段 | `history/*.jsonl` |
| tasks | ❌ 单池 | `state.json.plugin` 字段（§8 已定） | `tasks/T-*/` |
| queue / locks / hitl-queue | ❌ 单池 | entry 加 `plugin:` 字段 | `queue/` `locks/` `hitl-queue/` |

**判断原则**：可累积、可遗忘、可隔离的 → 模块化；线性记录、跨域协调的 → 单池 + 标签。

#### 3.2.2 Memory（知识）模块化

```
Layer A · plugin-shipped       plugins/<p>/knowledge/         只读，随 plugin 升级
Layer B · workspace-shared     knowledge/                     跨 plugin 通用沉淀
Layer C · plugin-local         memory/<p>/by-role/by-topic/   本工作区在该 plugin 下蒸馏
Layer D · task-scoped          tasks/T-NNN/memory/            （v5 已存在）
```

Plugin 在 `plugin.yaml` 声明 routing：

```yaml
knowledge:
  produces:
    default_target: plugin_local
    promote_to_workspace_when:
      - "topic in [environment, toolchain, conventions]"
  consumes:
    - workspace          # 默认读 workspace-shared
    - plugin_shipped
    - plugin_local
  retention:
    by-role: keep_last 50
    by-topic: keep_last 30
```

Distiller 不再写死 `by-role/by-topic`——按当前 plugin 的 `knowledge.produces` 决定写哪一层。Sub-agent self-bootstrap 按 `consumes` 顺序读取，上限仍 ≤5K。

#### 3.2.3 Skills 模块化

```
builtin            skills/builtin/                 内核技能（orchestrator-tick、session-resume、config-resolve、…）
plugin-shipped     plugins/<p>/skills/             plugin 自带（如 development 自带 sec-audit）
workspace-custom   skills/custom/                  显式提升为跨 plugin 共享的蒸馏技能
plugin-local       memory/<p>/skills/              本工作区在该 plugin 下蒸馏（如 dev 下的 deploy-to-prod）
```

Plugin 在 `plugin.yaml` 声明 routing：

```yaml
skills:
  produces:
    default_target: plugin_local
    promote_to_workspace_when:
      - "tags include [generic, format, file_op]"
  consumes:
    - workspace.builtin
    - workspace.custom
    - plugin_shipped
    - plugin_local
```

切 plugin 时 `memory/<plugin>/skills/` 自动隔离——"小红书发布"和"部署生产"不会混在一起。

#### 3.2.4 Config 4 层覆盖

解析顺序（低 → 高，高覆盖低）：

```
Layer 0  Builtin defaults                       内核硬编码兜底
Layer 1  plugins/<p>/config-defaults.yaml       plugin 自带 baseline（只读）
Layer 2  config.yaml -> defaults:               跨 plugin workspace 默认
Layer 3  config.yaml -> plugins.<p>.overrides:  本工作区对该 plugin 的微调
Layer 4  tasks/T-NNN/state.json -> config_overrides:  本任务一次性覆盖
```

`config.yaml` 形态（单文件聚合）：

```yaml
schema_version: 1
defaults:
  models:
    main: opus-4.7
    reviewer: gpt-5.4
  concurrency: { enabled: false }
  hitl: { adapter: terminal }

plugins:
  development:
    enabled: true
    overrides:
      models: { reviewer: gpt-5.4-mini }
      hitl:   { gates: [design, accept] }
  writing:
    enabled: true
    overrides:
      hitl: { gates: [accept] }
  ops:
    enabled: false
```

**Schema 校验**：plugin 自带 `config-schema.yaml` 声明它认得的 key；用户改 overrides 时由 builtin skill `config-validate` 对照校验，不识别的 key 报错（防静默失效）。

**顶层 key 白名单（v6 决议 #45）**：`config.yaml` 顶层只允许以下 10 个 key，其它一律由 `config-validate` 报错（`unknown_top_key`）：

| Key | 用途 |
|---|---|
| `models` | 模型分配（见 §3.2.4.1） |
| `hitl` | HITL adapter / gates |
| `knowledge` | 知识层路由 |
| `concurrency` | 并发开关 |
| `skills` | skill 路由配置 |
| `memory` | 记忆/蒸馏配置 |
| `router` | router 阈值与策略 |
| `plugins` | 各 plugin 启停与 overrides |
| `defaults` | 跨 plugin 的 workspace 默认（Layer 2） |
| `secrets` | secret 引用占位（实际值在 `.codenook/secrets.yaml`） |

**`config-defaults.yaml` vs `plugin.yaml` 内嵌字段（v6 决议 #I-1）**：
- **能力声明 / catalog 字段** → `plugin.yaml`（如 `name / summary / keywords / supports_*` / `data_layout`）。这些是 router 与安装器要读的元数据，**不参与配置覆盖链**。
- **可调参数** → `config-defaults.yaml`（如默认 model、HITL gates 列表、`max_iterations`、`concurrency.enabled`）。这些进入 §3.2.4 的 Layer 1，可被 workspace / task 覆盖。
- 判别原则：**用户会想改的**放 `config-defaults.yaml`；**plugin 工作前提**放 `plugin.yaml`。

**`merge:` 合并策略注解（v6 决议 #T-4）**：`config-schema.yaml` 中每个字段可声明合并语义，默认 `deep`：

```yaml
# plugins/development/config-schema.yaml 片段
hitl:
  gates:
    type: list
    merge: replace      # 列表整体替换；不会与下层合并去重
models:
  reviewer:
    type: string
    merge: replace      # 标量本就只能 replace
knowledge:
  consumes:
    type: list
    merge: append       # 追加到下层列表末尾，去重保序
default_question_set:
  type: map
  merge: deep           # 默认行为，可省略；按 key 递归合并
```

合法值：`replace | deep | append`。不声明时按字段类型推断（标量=replace，map=deep，list=replace 以避免歧义堆叠）。

**M1 阶段简化口径**：M1 的 `config-resolve` 实现 **不读** `config-schema.yaml` 的 `x-merge` 注解，统一按"deep-merge + 列表 replace"处理，足以覆盖 M1 全部用例（含 F-031）。**M5 起**（模块化子系统落位完成时）`config-resolve` 升级为 schema-driven merge，按字段 `x-merge` 注解执行 `replace | deep | append` 三态语义；届时 `merge: deep`（list）与 `merge: append` 才真正生效。

**自动 mutator 并发裁决（v6 决议 #T-5）**：当 distiller 的 `config-mutator` 与 task 写入 `config_overrides` 可能并发时：
1. **fs-level advisory lock**：写 `config.yaml` / `tasks/T-NNN/state.json` 前 `flock` 对应文件；
2. **乐观并发版本号**：每个被写文件首段含 `_version: <int>`，mutator 读时记录 `expected_version`，写时若实际 `_version != expected_version` 则 abort，重读、重算、重试（最多 3 次）；
3. 重试失败写 `history/config-changes.jsonl` 一条 `mutation_aborted` 并放弃本次自动调整（不阻塞主流程）。

**解析时机**：main session 不解析 config；sub-agent self-bootstrap 时调 `config-resolve plugin=<p> task=<T>` 拿 merged 视图。深合并按字段 `merge:` 注解为准，未声明者按类型默认（见 #T-4）。

**Secrets**：`config.yaml` 不放 API key。Secrets 走独立路径 `.codenook/secrets.yaml`（git ignore），由 builtin skill `secrets-resolve` 注入到 sub-agent 环境变量。

**自动配置**：Distiller 蒸馏出"建议把 reviewer 换 mini"→ 派 builtin agent `config-mutator`：读 effective config → 若与现值不同则写到 `plugins.<p>.overrides` → 同步追加 history 条目（含 reason）。无需人工确认（与 skills 自动蒸馏口径一致）。

##### 3.2.4.1 模型分配（Model Routing）

模型选择是 config 系统的一个**专项约定**，单独点出，避免歧义。

**Key path 约定**：所有 agent / role 的模型走统一 path：

```
models.<role>           # 如 models.planner / models.reviewer / models.implementer
models.default          # 任何未列出 role 的兜底
```

**5 层解析链**（在标准 4 层 config 之上明示）：

```
Layer 0  Builtin                models.default = "tier_strong"     硬编码兜底
                                models.router  = "tier_strong"     router 例外的兜底（决议 #44）
Layer 1  Plugin baseline        plugins/<p>/config-defaults.yaml   plugin 作者推荐
Layer 2  Workspace defaults     config.yaml -> defaults.models     用户全局口味
Layer 3  Plugin overrides       config.yaml -> plugins.<p>.overrides.models
Layer 4  Task overrides         tasks/T-NNN/state.json -> config_overrides.models
```

**Layer 0 同时发布两个 key**（v6 决议 #44）：`models.default` 与 `models.router` 都默认 `tier_strong`。原因：router 例外只读 Layer 0/2，若 Layer 0 仅暴露 `models.default`，任何 plugin 在 `config-defaults.yaml.models.router` 写值都会因合并链顺序意外被 plugin 影响；显式发布 `models.router` 让"plugin 写的 router 值被忽略"成为可机械化测试的不变量（见 test-plan M-016）。

**Plugin 作者声明**（`plugins/<p>/config-defaults.yaml`）：

```yaml
models:
  planner:     opus-4.7
  clarifier:   gpt-5.4-mini
  implementer: opus-4.7
  reviewer:    gpt-5.4
  distiller:   gpt-5.4-mini
  default:     opus-4.7        # plugin 内未列出的 role 兜底
```

**Plugin 不声明 / 字段缺省**：fall through 到 Layer 0 → `opus-4.7`。

**Router 模型例外**：router 在 plugin 选定**之前**运行，不能由 plugin 控制。Router 模型只读 Layer 0 / Layer 2（`config.yaml -> defaults.models.router`），默认 `tier_strong`（路由决策有放大效应——错选 plugin 整条流程都偏，值得用强模型）。

**Main session 显式覆盖单任务模型**（用户在主会话中说一句话即可）：

```
用户："T-007 的 reviewer 用 gpt-5.4-mini"
Main session：→ dispatch builtin skill `task-config-set`
              → 写 tasks/T-007/state.json.config_overrides.models.reviewer = "gpt-5.4-mini"
              → 同步追加 history/config-changes.jsonl（actor: user, scope: task）
              → 回 ≤200 字 confirm
```

`task-config-set` 也支持读：用户问"T-007 现在用啥模型"→ 调 `config-resolve task=T-007` 列出每个 role 的最终模型 + 来源 layer。

**优先级示例**：

| 场景 | reviewer 用什么 |
|---|---|
| 全部走默认 | Layer 0：`opus-4.7` |
| development plugin 装好 | Layer 1：`gpt-5.4`（plugin baseline） |
| 用户在 config.yaml 改 dev 的 reviewer | Layer 3：用户写的值 |
| 用户对 T-007 单独指定 | Layer 4：T-007 单独值（其他任务不受影响） |

（v6 决议 #36 模型分配走 5 层链；#37 router 模型仅 Layer 0/2；#38 task-config-set 支持自然语言驱动 task 级 override）

##### 3.2.4.2 模型探测与分级（Model Discovery & Tiering）

**问题**：`opus-4.7` 这种字面模型号写死在 plugin 里 → plugin 跨环境不可移植；新模型出来要 plugin 都改一遍。

**解决**：探测 + 分级 + 符号引用。

**1) 探测（Capability Discovery）**

由 builtin skill `model-probe` 完成：

```
触发：
  - init.sh --install / --upgrade-core / --refresh-models
  - 工作区 state.json.model_catalog.refreshed_at 早于 TTL（默认 30 天）
  - 用户在主会话说"刷新模型"

探测来源（按可用性顺序）：
  1. 运行时 API（如 Claude Code 的 list_models()、Copilot CLI 的模型注册表）
  2. 环境变量 CODENOOK_AVAILABLE_MODELS（手动覆盖，逗号分隔）
  3. 内置兜底列表（仅当上述都不可用，给出最小可用集）

输出：
  workspace_root/.codenook/state.json -> model_catalog: {
    refreshed_at: "...",
    runtime: "claude-code | copilot-cli | api",
    available: [
      {id: "opus-4.7",   tier: "strong",   cost: "high",   provider: "anthropic"},
      {id: "sonnet-4.6", tier: "balanced", cost: "mid",    provider: "anthropic"},
      {id: "haiku-4.5",  tier: "cheap",    cost: "low",    provider: "anthropic"},
      {id: "gpt-5.4",    tier: "balanced", cost: "mid",    provider: "openai"},
      ...
    ],
    resolved_tiers: {
      strong:   "opus-4.7",      # 当前可用最强
      balanced: "sonnet-4.6",
      cheap:    "haiku-4.5"
    }
  }
```

**2) 分级（Tier）**

固定三档：

| Tier | 含义 | 典型用途 |
|---|---|---|
| `tier_strong` | 当前 catalog 中可用的最强模型 | implementer / planner / reviewer（精度敏感） |
| `tier_balanced` | 性价比平衡档 | clarifier / orchestrator-tick |
| `tier_cheap` | 最便宜可用 | distiller / config-mutator（决策廉价） |

排名规则（builtin，可被 `config.yaml.models.tier_priority` 覆盖）：

```yaml
tier_priority:
  strong:   [opus-4.7, opus-4.6, sonnet-4.6, gpt-5.4]
  balanced: [sonnet-4.6, sonnet-4.5, gpt-5.4, gpt-5.4-mini]
  cheap:    [haiku-4.5, gpt-5.4-mini, gpt-4.1, sonnet-4.5]
```

`model-probe` 取每档第一个 catalog 中存在的，写到 `resolved_tiers`。

**3) Plugin 用符号声明**

```yaml
# plugins/development/config-defaults.yaml
models:
  planner:     tier_strong       # 符号 → 当前最强
  clarifier:   tier_balanced
  implementer: tier_strong
  reviewer:    tier_strong
  distiller:   tier_cheap
  default:     tier_strong
```

也允许字面值混用（用户/作者强制指定）：

```yaml
models:
  reviewer: gpt-5.4              # 字面，不走 tier
  planner:  tier_strong          # 符号
```

**4) 解析（在 5 层链解析之后再做一次符号展开）**

```
config-resolve 流程：
  1. 4 层 deep merge（§3.2.4）→ 得到 effective config
  2. 扫 models.* 字段
  3. 值 startswith "tier_" → 查 state.json.model_catalog.resolved_tiers → 替换为字面 id
  4. 字面值 → 校验在 catalog.available 中（不在则报 warning，回退到 tier_strong）
  5. 返回最终 {role: literal_model_id} 字典
```

**未知 tier 符号的统一口径**（v6 决议 #43）：

- 若 `models.<role>` 形如 `tier_<unknown>`（如 `tier_super_strong`），**不抛错**；
- 行为：向 stderr 打 warning（含合法 tier 列表 `[strong, balanced, cheap]`）+ **回退到 `tier_strong`** 解析；
- `_provenance.resolved_via` 标记为 `"fallback:tier_strong"`、`symbol` 保留原始未知符号便于回溯；
- 理由：与字面值不在 catalog 时的 fallback、与 router 例外的优雅降级口径一致；避免一个写"前瞻型" tier 名（为未来新档预留）的 plugin 把工作区整条流程 hard-block。

**5) Layer 0 兜底改写**

之前 §3.2.4.1 写的 "Layer 0: opus-4.7"——修订为：

```
Layer 0  Builtin                models.default = "tier_strong"
                                 models.router  = "tier_strong"   # 决议 #44，router 例外的兜底
                                 → 解析时展开为 catalog.resolved_tiers.strong
                                 → 若 catalog 缺失（极端兜底）才硬编码 "opus-4.7"
```

Router 默认模型同步：之前的 `sonnet-4.5` 改为 `tier_strong`——路由错误成本高（整条流程跑偏），值得用最强模型。用户可在 `config.yaml -> defaults.models.router` 显式降档省钱。

**6) 升级体验**

新模型出来后用户只需：

```bash
init.sh --refresh-models
# 或主会话："刷新模型"
```

→ `model-probe` 重跑 → catalog 更新 → 所有用 tier 符号的 plugin 自动用上更强模型，**无需改任何 plugin**。

**Catalog 默认位置与自动写回**：`model-probe` 与 `config-resolve` 都需要读 catalog。当 CLI 未显式传 `--catalog <path>` 时，按以下顺序解析：

```
1. 环境变量 CODENOOK_WORKSPACE（若设）→ <CODENOOK_WORKSPACE>/.codenook/state.json
2. 否则从 cwd 向上搜索首个含 .codenook/ 的目录作为 workspace_root
3. 读 <workspace_root>/.codenook/state.json -> model_catalog
4. 若 state.json 不存在 / 无 model_catalog → model-probe 即时探测一次，
   并把结果 **写回** <workspace_root>/.codenook/state.json -> model_catalog
5. 若 1/2 均失败（无 workspace 上下文）→ 退到极端兜底：硬编码 opus-4.7（同 Layer 0），
   并 stderr warning "no workspace catalog; using hardcoded fallback"
```

显式 `--catalog <path>` 总是优先于上述自动解析。自动写回只发生在自动解析路径，避免 `--catalog` 临时指向只读 fixture 时被污染。

**7) 可观测性**

`config-resolve` 返回里带 `_provenance` 字段：

```json
{
  "models": {
    "planner": "opus-4.7"
  },
  "_provenance": {
    "models.planner": {
      "value": "opus-4.7",
      "from_layer": 1,
      "symbol": "tier_strong",
      "resolved_via": "model_catalog.resolved_tiers.strong"
    }
  }
}
```

主会话用户问"T-007 的 reviewer 是怎么来的" → `task-config-set get` 返回 provenance 链。

（v6 决议 #39 模型走探测 + 三档分级，不写死字面型号；#40 引入 `tier_strong/balanced/cheap` 符号 + `tier_priority` 可配；#41 `init.sh --refresh-models` + catalog 缓存 30 天 TTL；#42 `config-resolve` 输出 `_provenance` 用于回溯模型来源）

#### 3.2.5 History 单时间线 + tag

不模块化。理由：history 是审计与回放，单一时间线比"分领域时间线"更有价值；一个 session 可能跨多 plugin。

每条 entry 加 `plugin:` 字段：

```jsonl
{"ts":"...","event":"phase_advance","task":"T-003","plugin":"development","phase":"impl→test"}
{"ts":"...","event":"task_create","task":"T-004","plugin":"writing"}
{"ts":"...","event":"plugin_install","plugin":"ops","version":"0.1.0"}
{"ts":"...","event":"config_change","plugin":"development","path":"models.reviewer","old":"gpt-5.4","new":"gpt-5.4-mini","actor":"distiller"}
```

文件保持在 `.codenook/history/`：
- `sessions/*.md`（session 跨 plugin，本就该共享）
- `distillation-log.jsonl`（带 plugin tag）
- `plugin-installs.jsonl`（天然跨 plugin）
- `config-changes.jsonl`
- `skills-audit.jsonl`

按 plugin 看时：`jq 'select(.plugin=="development")' history/distillation-log.jsonl`。

#### 3.2.6 Queue / Locks / HITL-queue

同 history 处理：不分目录，entry 上加 `plugin:` 字段。理由：调度器要看全局并发与依赖，分目录反而难做跨 plugin 协调（用户在 dev 任务做着的同时 writing 任务的 HITL 也排着队）。

Dashboard 渲染时按 `plugin:` 字段分组显示。

**HITL queue entry schema（v6 决议 #I-4）**：每条 hitl-queue 文件是一个 JSON 对象：

```json
{
  "task": "T-007",
  "plugin": "development",
  "gate": "design_signoff",
  "phase": "design",
  "payload": { "summary_path": "tasks/T-007/outputs/phase-2-designer-summary.md", "diff_path": null },
  "decision": null,                  // null | "approve" | "reject" | "revise"
  "decision_reason": null,
  "decided_at": null,                // ISO8601
  "decided_by": null,                // "human:<user>" | "auto:<rule>"
  "created_at": "2026-04-18T09:15:43Z",
  "expires_at": null                 // optional, hitl-gates.yaml 可声明
}
```

入队由 `orchestrator-tick` 写；出队（写 `decision`）由 `hitl-adapter` builtin agent（terminal / web / queue）写；tick 下一轮检测 `decision != null` 即推进或回退。

**HITL queue 文件命名规范（v6 决议 #T-10）**：

```
hitl-queue/<plugin>--<task>--<gate>--<ts>.json

# 例
hitl-queue/development--T-007--design_signoff--20260418T091543Z.json
hitl-queue/writing--T-012--accept--20260418T093200Z.json
```

双横 `--` 作为分隔符，便于 `awk -F-- '{print $1,$2,$3}'` 一行解析；`<ts>` 为 ISO8601 紧凑格式（无 `:`）保证文件名合法且天然有序。同 task 同 gate 多次入队（如先 reject 再 revise）以 ts 区分，最新决策由 `created_at` 最大者为准。

#### 3.2.7 完整工作区布局（v6 + 模块化）

```
<workspace>/
├── CLAUDE.md
└── .codenook/
    ├── core/
    │   └── shell.md                              ≤3K，main session 唯一加载
    ├── agents/builtin/                           router / distiller / security-auditor / hitl-adapter / config-mutator
    ├── skills/
    │   ├── builtin/                              orchestrator-tick / session-resume / config-resolve / config-validate / secrets-resolve / sec-audit / queue-runner / dispatch-audit / preflight
    │   └── custom/                               (3.2.3) workspace-custom 蒸馏技能
    ├── plugins/
    │   ├── development/
    │   │   ├── plugin.yaml                       含 knowledge/skills/config 的 routing 段
    │   │   ├── config-defaults.yaml              (3.2.4 Layer 1)
    │   │   ├── config-schema.yaml                校验用
    │   │   ├── knowledge/                        (3.2.2 Layer A) shipped knowledge
    │   │   ├── skills/                           (3.2.3) plugin-shipped skills
    │   │   ├── phases.yaml / transitions.yaml
    │   │   ├── roles/<role>.md
    │   │   └── ...                               (§5.0 文件清单)
    │   ├── writing/
    │   └── generic/
    ├── knowledge/                                (3.2.2 Layer B) workspace-shared
    │   ├── INDEX.md
    │   ├── ENVIRONMENT.md
    │   ├── CONVENTIONS.md
    │   └── by-role / by-topic
    ├── memory/                                   (3.2.2 Layer C + 3.2.3 plugin-local)
    │   ├── development/
    │   │   ├── by-role/
    │   │   ├── by-topic/
    │   │   └── skills/
    │   └── writing/
    │       └── ...
    ├── tasks/T-NNN/                              不模块化，state.json.plugin 标记
    ├── queue/  locks/  hitl-queue/               不模块化，entry 带 plugin tag
    ├── history/                                  不模块化，entry 带 plugin tag
    ├── config.yaml                               (3.2.4 Layer 2 + 3)
    ├── secrets.yaml                              git-ignored
    └── state.json                                workspace 级索引
```

#### 3.2.8 升级 / 卸载 plugin 的影响

| 操作 | 影响范围 |
|---|---|
| `init.sh --install-plugin` 升级 | 覆盖 `plugins/<p>/`（含 shipped knowledge/skills/config-defaults）；不动 `memory/<p>/` 与用户的 `config.yaml.plugins.<p>.overrides` |
| `init.sh --uninstall-plugin <p>` | 删 `plugins/<p>/`；`memory/<p>/` 归档为 `memory/.archived/<p>-<ts>/`；从 `config.yaml.plugins` 删掉该段；history 保留（带 tag） |
| `--force` 重装 | 同升级，但允许跨大版本；变更写到 `history/plugin-installs.jsonl` |

**归档 retention（v6 决议 #I-8）**：`memory/.archived/<p>-<ts>/` 与 `history/plugin-versions/<name>/<old>/` 的保留期由 `config.yaml.archive.retention_days` 控制，**默认 90 天**；超期由 builtin skill `archive-gc`（init.sh / tick 启动时机会触发）按 mtime 删除。设为 `0` = 永不删除；设为 `-1` = 卸载/升级时立即删除。

> **M8 update (2026-05)**: The Router section below describes the **M3 / M7
> one-shot router** (`router-triage` + `_lib/router_select.py`). Starting in
> milestone M8, that one-shot router is replaced by a **conversational
> router-agent** that drafts a task config across multiple turns, consults
> knowledge, and hands off to `orchestrator-tick` itself. The full spec is
> in [`docs/router-agent.md`](./router-agent.md). The catalog-scan
> protocol described in §4.1 still applies, but is now performed by the
> router-agent (not by `router-triage`); `_lib/router_select.py` survives
> as an **internal scoring helper** of the router-agent and is no longer a
> public skill. M3 `router-triage` is removed in **M8.7**.

**角色**：把任务分类到对应 plugin。

**画像**：
- 内置 agent（`<workspace>/.codenook/agents/builtin/router/agent.md`）
- 模型：`tier_strong`（路由错误成本高——错选 plugin 整条流程偏，值得用强模型；用户可在 config 显式降档）
- 输入：
  - 任务描述（或触发任务创建的那一轮用户输入）
  - **Plugin catalog**（每次 dispatch 时新构建，见 §4.1）
- 输出（严格 JSON）：
  ```json
  {
    "plugin": "development",
    "confidence": 0.92,
    "rationale": "User asked to implement a Python CLI; matches development plugin's keywords (CLI, Python, src/).",
    "alternates": [{"plugin": "writing", "confidence": 0.05}]
  }
  ```
- 自身从不 dispatch 工作。纯分类。

**`user_override` 回写（v6 决议 #I-2）**：当 main session 在 `confidence < threshold` 时通过 `ask_user` 让用户确认/改选 plugin，**确认后**main session 调 builtin skill `record-router-override` 把这次决定回填到 `history/router-decisions.jsonl`：

```jsonl
{"ts":"...","task":"T-007","router_pick":"writing","router_confidence":0.55,"user_override":"development","reason":"user_chose_alternate"}
```

Router 自身**不**写回；router 只产出原始 verdict。回写仅在 main session 确认环节发生（router 不确认就跳过）。这构成了未来调优 router 的离线训练语料（见 §10 #4）。

### 4.1 Router 如何感知 plugin（catalog）

Router agent 在自身的 self-bootstrap 中**自己扫描 plugin 目录**。Main session 永远不会触碰 plugin 文件。

```
Router agent self-bootstrap (each dispatch):
  1. Read input: { task_description, user_context, optional_user_hint }
  2. Scan <workspace>/.codenook/plugins/*/plugin.yaml
  3. For each manifest:
       catalog.append({
         name:          plugin.yaml.name,
         version:       plugin.yaml.version,
         summary:       plugin.yaml.summary,        # one line
         applies_to:    plugin.yaml.applies_to,
         keywords:      plugin.yaml.keywords,
         examples:      plugin.yaml.examples or [],
         anti_examples: plugin.yaml.anti_examples or []
       })
     Skip plugins listed in config.yaml `plugins.disabled`.
     Always include builtin `generic` last.
  4. Classify task against catalog → pick plugin
  5. Return JSON verdict
```

Catalog 在 router 自身的上下文中构建，从不返回给 main session。即使有 5 个以上 plugin，典型的 catalog 也 <2 KB。Router 从不读 `phases.yaml`、角色提示或任何其他 plugin 内部文件 —— 这让分类既廉价又抗篡改。

**为什么是 router-scans 而不是 main-session-scans**：
- Main session 保持为纯对话前端（不做用于 plugin 发现的文件 IO）
- Catalog 在每次 dispatch 时都是新鲜的 —— 新装的 plugin 立刻可见，main session 无需缓存
- Router agent 的画像是 "如何感知 plugin" 的唯一真相来源
- 替换 router（例如尝试不同模型）不需要修改 main session

**为什么是 catalog 而不是完整的 plugin 文件**：迫使 plugin 作者在 `plugin.yaml` 中写出清晰的 `summary` + `keywords` + `examples`。如果一个 plugin 在这些字段中说不清自己，那么任何 router 都无法对它正确分类。这一点会作为 validation 检查强制执行（§7.4 已经要求 `summary`；将额外要求未声明 `data_layout: none` 的 plugin 必须有非空的 `keywords`）。

### 4.2 Router 使用的 `plugin.yaml` 字段

```yaml
# Required (router-relevant)
name: development
summary: "Software development pipeline: clarify → design → plan → implement → test → accept → ship"
applies_to: ["software-engineering", "code"]
keywords: ["python", "javascript", "go", "cli", "api", "implement", "refactor", "fix bug"]

# Recommended (router-relevant)
examples:
  - "Add a --tag filter to the xueba CLI list command"
  - "Refactor the auth middleware to use JWT"
  - "Fix the off-by-one bug in pagination"
anti_examples:                 # tasks this plugin should NOT claim
  - "Write a blog post about RAG"
  - "Summarize the Q1 reading list"
```

`anti_examples` 是可选但推荐的 —— 当多个 plugin 拥有重叠关键字时，anti-examples 能帮助 router（以及用户在含糊选择时）消除歧义。

**Main session 阈值策略**（config.yaml）：
```yaml
router:
  confidence_threshold: 0.75     # below this, ask_user confirms
  auto_fallback: generic          # what to use if confidence is very low AND user declines alternatives
```

**比较语义（v6 决议 #T-12）**：判定为 `confidence < threshold` 时触发 `ask_user`——**严格小于**；`confidence == threshold` 视为通过，直接 mount。理由：阈值是"够好就放行"的下界，等号语义偏向减少打扰。

### 4.3 Domain layering（M8 introduces; binding from M8 onward）

CodeNook v6 has four layers, each with a tightly scoped domain awareness budget. The full rationale and lint rules live in [`docs/router-agent.md`](./router-agent.md) §2. Summary:

| Layer | Component | Domain awareness | Reads |
|-------|-----------|------------------|-------|
| **Conductor** | Main session (`shell.md` / `CLAUDE.md`) | **NONE** — protocol + UX only | Spawn responses, HITL prompt strings, `router-reply.md` (opaque) |
| **Specialist** | Router agent (M8) | **FULL** — picks plugin, builds config, consults knowledge | `plugins/*/plugin.yaml`, plugin + workspace `knowledge/`, `applies_to / keywords / examples / anti_examples` |
| **Metronome** | `orchestrator-tick`, `session-resume`, `hitl-adapter` | **NONE** — driven by plugin yaml | `phases.yaml`, `transitions.yaml`, `hitl-gates.yaml`, `state.json` |
| **Performers** | Phase agents (implementer, designer, …) | **FULL** per role | Role profile + manifest template + criteria |

**Hard rules** (enforced by an M8.6 lint test that scans `templates/CLAUDE.md` / `core/shell.md`):

1. Main session must NEVER read `plugins/*/plugin.yaml`, `knowledge/`, `applies_to`, `keywords`, `examples`, `anti_examples`, or any plugin id by name.
2. Router-agent is the **sole** domain interpreter on the task-creation side.
3. `orchestrator-tick` / `hitl-adapter` / `session-resume` are protocol surfaces; main session may invoke them but treats their output opaquely.
4. Plugin / skill discovery from main session is forbidden — main session only knows that the `router-agent` skill exists and how to spawn it.

This subsection supersedes any earlier prose that suggested main session may read plugin manifests for routing or HITL decisions.

## 5. Plugin 契约

一个 plugin 以**包**（tarball 或 zip）的形式分发，布局如下。安装后，它解压在 `<workspace>/.codenook/plugins/<name>/` 下。

```
<plugin>/
├── plugin.yaml                    # metadata (name, version, applies_to, codenook_core_version, ...)
├── phases.yaml                    # ordered phase list
├── roles/                         # role prompts
│   ├── planner.md
│   ├── implementer.md
│   └── ...
├── transitions.yaml               # phase → roles → verdicts → next_phase
├── entry-questions.yaml           # required fields before entering each phase
├── hitl-gates.yaml                # which transitions require HITL
├── skills/                        # (optional) plugin-bundled skills
│   └── test-runner/
├── validators/                    # (optional) domain check scripts
│   └── post-implement.sh
├── manifest-templates/            # (optional) per-phase manifest scaffolds
│   └── phase-N-<role>.md
├── README.md
└── CHANGELOG.md
```

`plugin.yaml` 中的 `name` 字段**就是安装目录名** —— 安装器在解压后读取它，并挂载到 `.codenook/plugins/<name>/`。归档顶层文件夹名无关紧要（由 `name` 字段解析，而非归档布局）。

### 5.0 一个 plugin 里有什么（逐文件说明）

| 文件 / 目录 | 必需？ | 用途 | 使用方 |
|---|---|---|---|
| `plugin.yaml` | ✅ | manifest：name、version、summary、keywords、examples、anti_examples、applies_to、codenook_core_version、supports_*、data_layout、data_glob、entry_point | 安装器（校验）、main session（catalog）、router |
| `phases.yaml` | ✅ | 有序的 phase 列表，每个含 `id`、`role`，可选 `produces` / `dual_mode_compatible` / `supports_iteration` / `allows_fanout` / `gate` | Orchestrator 主循环 |
| `transitions.yaml` | ✅ | 映射 `phase.role.verdict → next_phase`（状态机的边） | 在每个代理给出 verdict 之后由 orchestrator 使用 |
| `roles/<role>.md` | ✅（≥1） | 角色代理的提示模板 —— 完全自包含，包含其 self-bootstrap 协议、输出 schema、知识加载规则 | Sub-agent dispatch（每个角色 = 一种 agent 类型） |
| `entry-questions.yaml` | ✅ | 每个 phase 开始前所需字段（OPT-7 的泛化）；也包含 `creation:` 块，列出任务创建时所需字段 | Preflight + 任务创建流 |
| `hitl-gates.yaml` | ⬜ | 哪些 transition 需要 HITL 审批；自动通过规则；所需 reviewer 角色 | HITL adapter / queue |
| `manifest-templates/phase-N-<role>.md` | ⬜ | 每个 phase 的 manifest 脚手架，orchestrator 在 dispatch 角色代理之前用任务特定值填充（变量：`{task_id}`、`{target_dir}`、`{iteration}`、`{upstream_summary_path}`、……） | Orchestrator dispatch |
| `skills/<skill>/` | ⬜ | Plugin 自带的 skills（例如 `development` 的 `test-runner`）—— 形态与 builtin skills 相同，但命名空间为 `<plugin>/<skill>`，仅在该 plugin 是当前任务激活 plugin 时可用 | 引用它们的 sub-agents |
| `validators/<name>.sh` | ⬜ | 在特定 phase 后自动调用的领域校验脚本（在 `phases.yaml` 中通过 `post_validate: validators/<name>.sh` 声明）；必须以 0 退出（通过）/ 非零（失败） | 在 phase 输出写入后由 orchestrator 调用 |
| `prompts/criteria-<phase>.md` | ⬜ | validator agent 用来评分输出的验收标准（被 validator agent manifest 引用） | Validator agent |
| `examples/<task-name>/` | ⬜ | Plugin 作者随包提供的样例已完成任务，作为参考 / 测试种子 | 人类（如果 plugin 定义了相应种子，会被 init 的 `--scaffold-task` 拉入） |
| `README.md` | ✅ | 人类文档：plugin 做什么、如何为它编写任务、它的 phase 如何组合 | 人类 |
| `CHANGELOG.md` | ⬜ | 版本历史 | 人类、plugin 升级 UI |

**关注点的关键分离**：
- **`phases.yaml` + `transitions.yaml`** = 状态机
- **`roles/*.md`** = 每个角色*说什么*、*做什么*
- **`entry-questions.yaml` + `hitl-gates.yaml`** = orchestrator 在状态机周围所执行的*门*
- **`manifest-templates/`** = orchestrator 如何把 "为 phase Y dispatch 角色 X" 转成具体的提示
- **`skills/` + `validators/`** = plugin 自带的可选自动化

### 5.1 plugin.yaml

```yaml
name: development
version: 1.2.3
applies_to: ["software-engineering", "code"]
codenook_core_version: ">=6.0 <7.0"
summary: "Software development pipeline: clarify → design → plan → implement → test → accept → validate → ship"
keywords: ["code", "python", "javascript", "cli", "api", "test", "implement", "refactor", "bug"]
supports_dual_mode: true
supports_fanout: true
supports_concurrency: true
entry_point: phases.yaml

# 可选：data_layout=workspace 时的 data_root（v6 决议 #I-5）
# data_root 是 plugin 在 workspace 内固定使用的子目录（相对 <workspace>/）
# 仅当 data_layout: workspace 时生效；不写时默认为 <workspace>/<name>/
# data_root: notes
```

**`data_root` 字段（v6 决议 #I-5）**：当 plugin 声明 `data_layout: workspace` 时（典型如 writing、notes），可在 `plugin.yaml` 通过可选字段 `data_root: <relative_path>` 指定数据目录，路径相对 `<workspace>/`，必须**不以 `.codenook/` 开头**且**不含 `..`**（安装器在 §7.4 校验）。未声明时默认 `<workspace>/<plugin.name>/`。所有该 plugin 的 task 共享此 root；task 的 `target_dir` 字段被 ignore。

### 5.2 phases.yaml

```yaml
phases:
  - id: clarify
    role: clarifier
    produces: phase-1-clarifier-summary.md
  - id: design
    role: designer
    produces: phase-2-designer-summary.md
  - id: plan
    role: planner
    produces: decomposition/plan.md
    allows_fanout: true
  - id: implement
    role: implementer
    dual_mode_compatible: true
    supports_iteration: true
    produces: outputs/phase-3-implementer.md
  - id: test
    role: tester
  - id: accept
    role: acceptor
  - id: validate
    role: validator
  - id: ship
    role: null               # ship is an orchestrator-only step
    gate: pre_ship_review
```

### 5.3 transitions.yaml

```yaml
# Which verdict from which role at which phase causes what next_phase
transitions:
  clarify.clarifier.ok → design
  design.designer.ok → plan
  plan.planner.decomposed → fanout  # triggers subtask-runner.sh seed
  plan.planner.single → implement
  implement.implementer.done → [review | test]   # depends on dual_mode
  review.reviewer.looks_good → test
  review.reviewer.needs_fixes → implement (next iteration)
  test.tester.pass → accept
  test.tester.fail → implement (next iteration)
  accept.acceptor.accepted → validate
  validate.validator.pass → ship
  ship → complete
```

### 5.4 entry-questions.yaml

```yaml
# Required answers before a phase may begin (generalization of OPT-7 fields + per-phase checklists)
creation:
  required_fields: ["title", "summary", "priority", "dual_mode", "max_iterations"]
clarify:
  required_fields: []
design:
  required_fields: ["constraints", "non_goals"]
implement:
  required_fields: ["test_strategy"]
```

### 5.5 hitl-gates.yaml

```yaml
gates:
  pre_ship_review:
    trigger: before_phase=ship
    auto_approve_if: []
    required_reviewers: ["human"]
  design_signoff:
    trigger: after_phase=design
    auto_approve_if: ["task.priority in [low]"]
    required_reviewers: ["human"]
```

## 6. 内置 generic plugin

当 router 无法自信匹配时的 fallback。定义最不带主观偏好但仍然有用的流水线：

```yaml
# generic/phases.yaml
phases:
  - {id: clarify,  role: clarifier}
  - {id: analyze,  role: analyzer}
  - {id: execute,  role: executor}
  - {id: deliver,  role: deliverer}
```

无领域专属角色，默认无 fan-out，不预期测试。适用于临时任务（研究、摘要、规划）。

**默认 transitions（v6 决议 #I-7）**：generic 只走 3 段最小闭环：

```yaml
# generic/transitions.yaml
transitions:
  clarify.clarifier.ok    → implement
  implement.executor.done → accept
  accept.acceptor.accepted → complete   # 终态
```

terminal phase 为 `accept` 后即 `complete`，**不**走 test/validate/ship（generic 没有验证语义）。如果用户希望更严格的流程，应改用领域 plugin（development / writing 等）。

## 7. Plugin 的安装与发现

### 7.1 布局（全部位于一个 workspace 下）

```
<workspace>/                           ← e.g. ~/Documents/workspace/development/
├── CLAUDE.md                          ← bootloader pointing at .codenook/core/codenook-core.md
└── .codenook/
    ├── core/                          ← installed by init.sh (copy of skills/codenook-core/)
    ├── agents/builtin/                ← router, distiller, security-auditor, hitl-adapter
    ├── skills/builtin/                ← sec-audit, queue-runner, distiller, dispatch-audit, ...
    ├── plugins/
    │   ├── development/               ← installed via init.sh --install-plugin
    │   ├── writing/
    │   └── generic/                   ← shipped with core, seeded by init.sh
    ├── tasks/
    │   └── T-NNN/state.json           ← includes `plugin` and `target_dir` fields
    ├── queue/  locks/  hitl-queue/  history/
    ├── config.yaml
    └── state.json
```

每台机器**只有一个 workspace**（按用户约定）。外部代码/数据目录由任务通过 `target_dir` 引用（见 §8）；它们绝不是 CodeNook 的安装位置。

### 7.2 安装接口 —— `init.sh --install-plugin`

Plugin 以包（tarball `.tar.gz` 或 zip）方式分发。安装器是 `init.sh` 的一部分，可接受本地路径或远端 URL。

```
# Inside the workspace directory
./init.sh --install-plugin <path-or-url> [--sha256 <hex>] [--force]

# Examples
./init.sh --install-plugin ./dev-plugin-1.2.0.tar.gz
./init.sh --install-plugin https://example.com/dev-plugin-1.2.0.tar.gz
./init.sh --install-plugin https://example.com/dev-plugin-1.2.0.tar.gz \
          --sha256 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08
```

配套子命令（同样通过 `init.sh` 暴露）：

```
./init.sh --list-plugins                      # show installed plugins (name, version, status)
./init.sh --remove-plugin <name>              # uninstall (cannot remove builtin `generic`)
./init.sh --remove-plugin <name> --force-orphan   # 见下面 #T-6
./init.sh --reinstall-plugin <name>           # validate + remount existing package

# Authoring
./init.sh --scaffold-plugin <name>            # create a skeleton at ./<name>-plugin/ for editing
./init.sh --pack-plugin <dir>                 # validate + tar.gz the directory into ./<name>-<version>.tar.gz
```

**`--remove-plugin` 与 active task（v6 决议 #T-6）**：默认**阻止**删除——若 `tasks/` 中存在 `state.plugin == <name>` 且 `status in [in_progress, blocked]` 的 task，安装器报错并列出 task id。提供 `--force-orphan` 绕过：所有此类 task 的 `state.json.status` 被改为 `orphaned`（不可继续 tick），plugin 目录随后被删除；这些 task 仍可被人工查看与归档，但 orchestrator 不再调度。`orphaned` 状态写入 `history/plugin-installs.jsonl`（`action: uninstall_orphaned, orphaned_tasks: [...]`）。

> **不 git clone，不全局安装。** 每个 plugin 都落在 *当前* workspace 的 `.codenook/plugins/` 下。如果用户在不同目录里运行 `init.sh`，那个目录会成为另一个独立的 CodeNook 节点。

### 7.2.1 Plugin 脚手架（`--scaffold-plugin`）

为了降低 plugin 编写门槛，`init.sh --scaffold-plugin <name>` 会在 workspace 之外生成一个完整骨架（这样作者可以迭代而不污染 `.codenook/plugins/`）：

```
./<name>-plugin/                              # created in the user's CWD, NOT in .codenook
├── plugin.yaml                               # pre-filled: name=<name>, version=0.1.0, TODO markers
├── phases.yaml                               # one example phase (clarify) with TODO
├── transitions.yaml                          # one example transition with TODO
├── entry-questions.yaml                      # creation block with required core fields
├── hitl-gates.yaml                           # empty gates: {}
├── roles/
│   └── clarifier.md                          # role template stub with self-bootstrap protocol
├── manifest-templates/
│   └── phase-1-clarifier.md                  # variable scaffold
├── skills/                                   # empty
├── validators/                               # empty
├── examples/                                 # empty
├── README.md                                 # template with sections to fill
└── CHANGELOG.md                              # 0.1.0 entry
```

然后作者编辑、打包：

```
./init.sh --pack-plugin ./<name>-plugin/
```

`--pack-plugin` 在源目录上运行的**校验流水线与 `--install-plugin` 完全相同**（§7.4），然后才生成 tarball —— 因此作者在打包阶段就能发现 schema/安全错误，而不是到安装阶段才发现。输出：

```
✓ Validated <name>-plugin/ (12/12 checks, 0 security findings)
✓ Wrote ./<name>-0.1.0.tar.gz (sha256: 9f86d0...)
Distribute by URL or local path; install with:
  ./init.sh --install-plugin ./<name>-0.1.0.tar.gz
```

这让 plugin 编写循环在 `init.sh` 内部成为一个完整闭环：scaffold → edit → pack → install。

### 7.3 安装流水线（`--install-plugin` 做了什么）

```
1. Resolve source
   ├─ local path → verify exists, is .tar.gz / .zip
   └─ URL → curl into staging dir under .codenook/staging/<rand>/
2. (Optional) sha256 verify if --sha256 provided
3. Extract to .codenook/staging/<rand>/extracted/
4. Locate plugin.yaml (must be at extracted root; reject otherwise)
5. Validation pipeline — see §7.4
6. If all checks pass:
     name := plugin.yaml.name
     dest := .codenook/plugins/<name>/
     If dest exists and not --force → abort with "already installed; use --force or --remove-plugin"
     mv extracted → dest
     append entry to .codenook/history/plugin-installs.jsonl
7. Cleanup staging
```

### 7.4 完整校验 + 安全扫描

每次安装都会运行下述流水线（任一失败都会以编号错误码中止安装；失败时 staging 目录会保留以便检查）。**错误码命名（v6 决议 #T-7）**：固化为 `G01..G12`，与测试文档一致；任何报错信息必须以 `[Gxx] <message>` 起首。

| # | 错误码 | 检查 | 失败 → |
|---|---|---|---|
| 1 | G01 | `plugin.yaml` 存在于解压根目录 | 中止 |
| 2 | G02 | `plugin.yaml` 可解析为合法 YAML | 中止 |
| 3 | G03 | 必需字段齐全：`name`、`version`（semver）、`applies_to`、`codenook_core_version`、`summary`、`data_layout` | 中止 |
| 4 | G04 | `name` 匹配 `^[a-z][a-z0-9-]{1,30}$` | 中止 |
| 5 | G05 | 当前 core 版本满足 `codenook_core_version` 约束 | 中止；提示 `./init.sh --upgrade-core`（见 §9 / #I-10） |
| 6 | G06 | 必需文件存在：`phases.yaml`、`transitions.yaml`、`entry-questions.yaml`，至少一个 `roles/*.md` | 中止 |
| 7 | G07 | `phases.yaml` schema 合法；`transitions.yaml` 中引用的每个 phase id 都存在；`phases.yaml` 中引用的每个角色文件都存在于 `roles/` 下 | 中止 |
| 8 | G08 | `transitions.yaml` schema 合法；无孤立 phase；终止 phase 可达 | 中止 |
| 9 | G09 | `entry-questions.yaml` 与 `hitl-gates.yaml` schema 合法（如果存在） | 中止 |
| 10 | G10 | **安全扫描** —— 见 §7.4.1 | 中止 |
| 11 | G11 | 保留名检查：`name` 不在 `{core, builtin, generic, codenook}` 中（除了由 core 自带的 builtin `generic`） | 中止 |
| 12 | G12 | Plugin 解压总大小 ≤ 10 MB（可在 `config.yaml` 中通过 `plugins.max_size_mb` 配置） | 中止 |

#### 7.4.1 安全扫描

安装器会拒绝可疑文件。实现复用现有的 `security-audit.sh`（已经是 builtin skill），并使用更严格的 plugin 规则集：

- 包内**任何位置都不允许 symlink**（`find -type l` → 拒绝）
- **不允许除 `.gitignore`、`.editorconfig`、`.markdownlint.json` 之外的隐藏文件**（白名单）
- 任何 `*.yaml` 中声明的路径**不允许 path traversal**（`../`、绝对路径、`~`）
- **`skills/*/` 与 `validators/` 之外不允许可执行文件**；即使在那里，权限也不得为全局可写
- 可执行脚本的 **shebang 白名单**：`#!/usr/bin/env bash`、`#!/bin/bash`、`#!/usr/bin/env python3`、`#!/usr/bin/env node`（其他被拒绝）。**可配置（v6 决议 #I-9）**：白名单 token 列表读 `config.yaml.security.shebang_allowlist`，默认 `[bash, sh, python3, node]`，可扩展为 `[bash, sh, python3, node, bun, deno, pwsh]`；形式上比较"shebang 末位 basename"。
- 对所有脚本文件做高风险模式的**静态关键字扫描**：`curl … | sh`、`wget … | sh`、`eval`、对动态字符串的 `exec`、`rm -rf /`、`sudo`、base64 解码后的 shell、`validators/` 之外的网络调用（可配置白名单）
- 通过现有的 `secret-scan` builtin skill 对所有文本文件做 **secret 扫描**（私钥、AWS 凭证等）→ 命中即拒绝
- **manifest 合理性**：`data_glob` 模式不得包含 `/`、`..` 或绝对路径

失败时会在 `staging/<rand>/security-report.md` 中输出逐文件的发现；用户可检查后修复包内容，或以 `--allow-warnings` 重跑（仅会降级非关键警告；关键发现始终阻止）。

**Critical vs warning 划分（v6 决议 #T-8）**：

| 级别 | 类别 | `--allow-warnings` 行为 |
|---|---|---|
| **Critical**（始终阻止） | symlink、path traversal、secret 命中、危险关键词（`curl…\|sh`、`eval` 动态、`rm -rf /`、`sudo`、base64→shell）、shebang 越界 | 永远拒绝，无视 flag |
| **Warning**（可降级） | 文件权限非 0644/0755、UTF-8 BOM、CRLF 行尾、未声明的隐藏文件之外的杂项、`README.md`/`CHANGELOG.md` 缺失 | `--allow-warnings` 时降级为 warning，安装继续；否则中止 |

报告中每条发现标 `[CRITICAL]` 或 `[WARN]`；CI 可基于此分级。

#### 7.4.2 校验结果

成功时安装器打印摘要：

```
✓ Plugin "development" v1.2.0 installed at .codenook/plugins/development/
  - 8 phases, 6 roles
  - 2 plugin-local skills, 1 validator
  - data_layout: external (operates on tasks' target_dir)
  - codenook_core_version: >=6.0 <7.0  (current: 6.0.1) ✓
  - security scan: clean (12 files, 0 findings)
  - record appended to .codenook/history/plugin-installs.jsonl
Run `./init.sh --list-plugins` to see all installed plugins.
```

### 7.5 Workspace 可用性

由于一切都本地化于 workspace，"可用" 仅意味着 "已解压在 `.codenook/plugins/` 下"。列举逻辑：

```
For each subdir of .codenook/plugins/:
  if subdir/plugin.yaml exists and parses → list
  else → mark as "broken" (don't auto-load)
```

`config.yaml` 可以在不删除已安装 plugin 的前提下 *禁用* 它：

```yaml
plugins:
  disabled: ["writing"]   # installed but won't be offered to router
```

### 7.6 升级流程

不存在 `git pull`，因为这里 plugin 不是 git 仓库 —— 它们是包。要升级：

```
./init.sh --install-plugin ./dev-plugin-1.3.0.tar.gz --force
```

`--force` 在通过同样的校验流水线之后覆盖现有目录。旧版本会被移到 `.codenook/history/plugin-versions/<name>/<old-version>/` 以便回滚（保留策略可配置）。

### 7.7 Plugin 数据布局声明

Plugin 在 `plugin.yaml` 里声明它与数据的关系，以便安装器 / preflight 可以校验，并让 orchestrator 知道去哪里找输入：

```yaml
data_layout: external       # data lives in an external dir per task (set by task.target_dir) — typical for `development`
# alternatives:
# data_layout: workspace    # data lives inside the workspace itself (e.g. a `notes` plugin where notes go under <workspace>/notes/)
# data_layout: none         # no persistent data (ad-hoc plugins like `scratch`)
data_glob:                  # (optional) what files this plugin considers part of its data, evaluated against target_dir or workspace
  - "**/*.md"
  - "src/**/*.py"
data_excludes:
  - ".codenook/**"
  - ".git/**"
```

CodeNook 工具链使用 `data_glob` 来圈定安全扫描、distillation 上下文窗口、validator 输入等的范围，从而避免读取整个目标树。

## 8. 任务级 plugin 绑定与 target_dir

一个任务绑定到：
- 恰好**一个** plugin（记录在 `.codenook/tasks/T-NNN/state.json` 的 `plugin` 字段）
- 恰好**一个**目标目录（记录在 `state.json` 的 `target_dir` 字段），如果 plugin 的 `data_layout` 为 `external`

### 8.1 任务的 `state.json`（相关字段）

```json
{
  "task_id": "T-007",
  "title": "Add --tag filter to xueba CLI list",
  "plugin": "development",
  "plugin_version": "1.2.0",
  "target_dir": "/Users/me/Documents/project/xueba-cli",
  "target_status": "ok",
  "phase": "implement",
  "dual_mode": "serial",
  "max_iterations": 3,
  "status": "in_progress",
  "parent_task": null,
  "subtasks": [],
  "depends_on": []
}
```

**`target_status` 字段（v6 决议 #T-9）**：取值 `ok | target_missing | tampered`。`orchestrator-tick` 在每次 tick 开头检测：
- `target_dir` 不存在或不是目录 → `target_missing`（典型：用户外部 `mv` / `rm`）；
- `target_dir` 存在但 plugin 要求的标志文件（如 `pyproject.toml`）已不存在或被替换 → `tampered`；
- 否则 → `ok`。

非 `ok` 状态下 tick 立刻 return，不派 worker，写一条 `target_check_failed` 到 history，并把 `status` 置为 `blocked`，同时入 hitl-queue（`gate: target_recovery`）请用户决定 relocate / abort。

**子任务目录结构（v6 决议 #I-6）**：

```
tasks/
└── T-007/
    ├── state.json                  # parent_task: null
    ├── outputs/ ...
    └── subtasks/
        ├── T-007.1/
        │   └── state.json          # parent_task: "T-007"
        └── T-007.2/
            └── state.json          # parent_task: "T-007"
```

`state.json` 的 `parent_task` 字段：parent 为 `null`；subtask 为父 `task_id`。`subtasks` 字段（在 parent 中）列出直接子 task id。子任务继承 `plugin / plugin_version / target_dir`（§8.2 末段不变）。多级嵌套递归（`T-007/subtasks/T-007.1/subtasks/T-007.1.a/`）。

### 8.2 规则

- **`target_dir`** 是绝对路径，在任务创建时被校验：
  - 存在且是目录
  - **位于** `<workspace>/.codenook/` **之外**（绝不操作 CodeNook 自身的文件）
  - 用户可读 + 可写
  - 如果 plugin 要求特定标志文件（例如 Python plugin 要求 `pyproject.toml`），该标志文件必须存在
- 所有 sub-agent dispatch 都会收到 `target_dir` 的绝对路径。Agent 不得 `cd` 离开 `target_dir` 进行工作；manifest、state 与 HITL 记录仍然写在 `<workspace>/.codenook/` 之下。
- 任务创建后，其 `plugin` 与 `target_dir` **不可变**。如果其中任何一个发生变化，请重建任务。
- **`plugin_version`** 在任务创建时被捕获；即使后续安装了更新版本，orchestrator 在该任务的整个生命周期里仍使用所捕获的版本。
- v6 MVP 中，子任务继承父任务的 `plugin`、`plugin_version`、`target_dir`。跨 plugin / 跨 target 的子任务延后到 MVP 之后。

### 8.3 Workspace 并发

单个 workspace 可以同时承载许多面向不同外部目录的任务。queue runtime、locks 与 HITL queue 都以 `task_id`（以及对于文件锁，以每个 `target_dir` 下的绝对路径）为键，因此跨 target 的冲突自然被分开。

## 9. 从 v5 到 v6 的迁移路径（历史记录 — 已完成）

> 本章节记录了 v5 → v6 的迁移设计。迁移已在 v0.10 / v0.11 完成，v5 源码已于 v0.11.1 从仓库移除。下文中的 `skills/codenook-v5-poc/` 路径已不存在，仅保留作为决策档案。

### 9.1 重命名 / 重组

```
skills/codenook-v5-poc/         →  skills/codenook-core/     (keep history; rename)
skills/codenook-v5-poc/templates/agents/  →  split:
  ├─ generic/orchestrator/distiller/router/security-auditor → skills/codenook-core/agents/builtin/
  └─ development-specific: planner/implementer/reviewer/tester/acceptor/validator → plugin
```

### 9.2 抽出 development plugin（作为包，而非仓库）

- 构建发布 tarball：`dev-plugin-0.1.0.tar.gz`
- 源布局（在 `cintia09/codenook` 仓库的 `plugins/development/` 中维护用于开发；`make plugin-dev` 产出 tarball）
- 从 `skills/codenook-v5-poc/templates/` 移动：
  - 角色 agent 的所有 `prompts-templates/` → plugin 的 `roles/`
  - `core/codenook-core.md` §3 中的 phase 名与路由表 → plugin 的 `phases.yaml` + `transitions.yaml`
  - `integration-test`/`integration-accept` 命名约定 → plugin
- 在归档根写 `plugin.yaml`；设置 `data_layout: external`
- 初始版本：`0.1.0`（预发布）
- 分发：GitHub release asset；用户拿到 URL 后运行 `./init.sh --install-plugin <url> --sha256 <hex>`

### 9.3 Core 清理

- 从 `codenook-core.md` §路由表移除所有 phase 名 —— 替换为 "plugin-defined"
- 保留机制（§1-§5、§17-§24）不变
- 把 §3 路由表重写为 plugin 实现的*规范*，而非具体表格
- **拆分 `codenook-core.md`（见 §3.1.6）**：抽出 `shell.md`（≤3K，仅 main session 加载）+ `orchestrator-tick` builtin skill + `session-resume` builtin skill；剩余的 phase/role/transition 内容迁入 plugin
- `init.sh` 增加 `--install-plugin <path-or-url>`（见 §7.2）以及 `--list-plugins` / `--remove-plugin` / `--reinstall-plugin` / `--scaffold-plugin` / `--pack-plugin`
- `init.sh`（无 plugin 参数）只 seed core + builtin agents/skills + builtin `generic` plugin
- `PHASE_ENTRY_QUESTIONS` YAML 段从 core 的 `config.yaml` 移到 plugin 的 `entry-questions.yaml`
- 从 core 中移除所有对 `~/.codenook/` 的引用；一切都是 workspace 相对路径

### 9.4 构建 generic plugin

- 内置 plugin 中的最小 4-phase 流水线
- 与 core 仓库一同发布，位于 `skills/codenook-core/plugins/generic/`（既然是 fallback，就不需要单独仓库）
- 自动包含在每个 workspace 中

### 9.5 校验

- 重跑 E2E 压力测试（刚刚完成的那个）针对 development plugin → 应该产出相同的 artifacts
- 新的 E2E 测试：触发 generic fallback（使用 dev 关键字之外的 prompt）→ 验证 4-phase 流水线运行
- 第三个 E2E 测试：writing plugin（用最小 writing phases 作种子）→ 在一个 workspace 中验证多 plugin 共存

**v5 → v6 e2e 通过判据（v6 决议 #T-13）**：**语义等价**而非 byte-level diff。判据：
1. **phase 数相同**（v5 development 跑出 N 个 phase → v6 也是 N 个）；
2. **verdict 序列相同**（每个 phase 的 verdict 按时序与 v5 一致：`clarify.ok → design.ok → ... → ship`）；
3. **最终 task `state.json` 关键字段相同**（`status, phase, plugin, target_dir, max_iterations`，以及 `outputs/` 下的文件清单与各 phase 的 `produces`）。

**不**要求：manifest 文件 byte 一致、LLM 自由文本输出 byte 一致、时间戳一致、agent dispatch 顺序在并发模式下一致。E2E 比对脚本固化在 `skills/codenook-core/tests/e2e-equivalence.sh`。

### 9.6 Core 升级路径（v6 决议 #I-10）

Core 自身（`<workspace>/.codenook/core/` 与 `agents/builtin/`、`skills/builtin/`）通过 `init.sh --upgrade-core` 升级：

```bash
./init.sh --upgrade-core                      # 拉最新 codenook-core 包并替换；保留 plugins/ 与 tasks/ 与 config.yaml
./init.sh --upgrade-core --to 6.1.0           # 钉版本
./init.sh --upgrade-core --dry-run            # 预演：列出会被覆盖的文件 + 兼容性检查
```

升级流程：备份 `core/` 与 `agents/builtin/`、`skills/builtin/` 到 `history/core-versions/<old>/`（受 §3.2.8 retention 控制）→ 解压新版本 → 跑兼容性检查（每个已安装 plugin 的 `codenook_core_version` 是否仍满足）→ 不兼容则中止并列出需要升级/降级的 plugin。

**与 plugin 安装的耦合**：当 plugin 安装在 G05 (`codenook_core_version` 不匹配) 失败时，错误信息必须给出指引：

```
[G05] Plugin "writing" requires codenook_core_version >=6.1, but current core is 6.0.1.
Run `./init.sh --upgrade-core` (recommended) or install a compatible plugin version.
```

## 10. 开放问题（在设计稳定前推迟）

> 标记 ✅ 的项已在 v6 决议中解决（标注决议号），其余仍待办。

1. ✅ **Q4 —— 版本钉死**（由单工作区模型解决）：每个 workspace 拥有自己的 plugin 集合。`plugin_version` 在任务创建时就被捕获（§8.1），因此即便后续 `--install-plugin … --force`，同一 plugin 上并发的任务仍会继续使用各自捕获的版本。跨 workspace 的版本钉死并不需要，因为每个 workspace 都有自己的 `.codenook/plugins/`。
2. **Plugin skills 与 builtin skills 命名冲突**：如果两边都提供了 `test-runner`，谁优先？建议：plugin 本地 skill 命名空间为 `<plugin>/<skill>`，并在该 plugin 激活时优先；builtin skill 始终保持 `builtin/<skill>`。（待办：在 §3.2.3 落实"激活时优先"的解析顺序细节。）
3. **跨 plugin 子任务交接**：延后到 MVP 之后。设计草图：父任务在某个特定子任务上声明 `handoff_to: writing`，子任务加载 writing plugin 而不是继承父任务的。
4. ✅ **Router 训练信号**：router 是纯分类 agent；`user_override` 回写机制已定（v6 决议 #I-2，见 §4 末段）。`history/router-decisions.jsonl` 从 v6 第 1 天起即存在。未来分类器训练仍是开放方向。
5. **Plugin marketplace / registry**：v6 范围之外。Tarball 安装（本地路径或 URL）已经足够。公开 registry（类似 npm）是 v7+ 的想法；sha256 校验是供应链卫生的种子。
6. **一台机器上多个 workspace**：技术上允许（在另一目录运行 `init.sh` 即可），但每个都完全独立 —— 不共享状态、plugin 或历史。跨 workspace 的知识共享在 MVP 之后，并需要在 `config.yaml` 中显式声明 `external_references:` 段。

**已并入正文的歧义清单**（来自 v6 落地反馈，详见 §12）：
- I-1..I-10：实现文档反馈，均已就地落入对应章节。
- T-1..T-13：测试文档反馈，均已就地落入对应章节。

剩余开放：#2（命名冲突解析顺序细节）、#3（跨 plugin 子任务）、#5（marketplace）、#6（多 workspace 共享）。

## 11. 本文档不是什么

- 不是代码。没有实现。
- 不是时间表。没有截止日期。
- 不是终稿。预期会随着 v6 POC 在具体集成问题中演化而修订。
- 不是 `codenook-core.md` 的替代品。该文档将作为 v6 实现的一部分被重写；本草案只是为方向搭脚手架。

## 12. Provenance（出处）

> 本文最初以英文起草并随后翻译为简体中文。

捕获自 2026-04-18 一次实时的 Copilot CLI 会话，紧接在 E2E 压力测试（`skills/codenook-v5-poc/reports/e2e-development-20260418-091543.md`）之后。该测试揭示了许多 "摩擦" 项（例如 "subtask-phase 启发式"、"PHASE_ENTRY_QUESTIONS 未定义"）其实是单体 v5 架构的症状，而不是孤立的 bug。已应用的 v5 修复（`reports/fixes-applied-20260418-093334.md`）只是修补表面；v6 的 plugin 拆分才是结构性答案。

本次会话与用户共同确认的决策点：
1. ✅ core/builtin/plugin 分离的分层模型
2. ✅ **单工作区模型** —— 没有全局的 `~/.codenook/`；一切位于一个被选定目录的 `.codenook/`
3. ✅ Plugin 以**包**（tarball / zip）分发，通过 `init.sh --install-plugin <path-or-url>` 安装，可选 `--sha256` 校验
4. ✅ Plugin 安装目的地为 `<workspace>/.codenook/plugins/<name>/`，其中 `<name>` 来自 `plugin.yaml`
5. ✅ 每次安装都执行**完整校验流水线**：schema 检查（12 道关卡）+ 安全扫描（symlink / path-traversal / shebang 白名单 / 关键字扫描 / secret 扫描）；失败时中止并保留 staging 目录
6. ✅ 多 plugin 工作区，绑定在任务级别（每个任务一个 plugin + 一个 `target_dir`；`plugin_version` 在创建时捕获）
7. ✅ Router 是独立的内置 agent；**router 自己扫描 plugin 目录构建 catalog**，main session 不参与
8. ✅ Main session 在显式用户确认之后才创建任务；**main session 是纯对话前端，不加载编排器**
9. ✅ **编排器从 main session 拆出**：v5 的 `codenook-core.md` 拆为 `shell.md`(≤3K) + `orchestrator-tick` builtin skill + `session-resume` builtin skill + plugin 的 `phases.yaml/transitions.yaml`（见 §3.1）
10. ✅ `init.sh` 同时承担**插件作者循环**：`--scaffold-plugin` / `--pack-plugin`（复用安装校验流水线）
11. ✅ 未匹配的任务回落到 builtin 的 `generic` plugin
12. ✅ 在设计文档（本文件）中归档；草案被认可之前不做代码改动

**v6 落地反馈追加决议**（来自实现 / 测试文档落地反馈，2026-04-18）：

13. ✅ **#I-1**（§3.2.4 / §5.1）能力声明放 `plugin.yaml`，可调参数放 `config-defaults.yaml`
14. ✅ **#I-2**（§4 / §10.4）`user_override` 由 main session 在 ask_user 后调 builtin skill `record-router-override` 回填
15. ✅ **#I-3**（§3.1.3）术语：skill = 算法 + 脚本，由 dispatch helper agent 执行；agent 才是有 profile 的角色
16. ✅ **#I-4**（§3.2.6）补 hitl-queue entry schema：`{task, plugin, gate, payload, decision, decided_at, decided_by, ...}`
17. ✅ **#I-5**（§5.1）`plugin.yaml` 增可选字段 `data_root: <relative_path>`（仅 `data_layout: workspace` 生效）
18. ✅ **#I-6**（§8）嵌套子任务目录 `tasks/T-007/subtasks/T-007.1/`；`state.json` 加 `parent_task` 字段
19. ✅ **#I-7**（§6）generic plugin 默认 transitions：`clarify → implement → accept → complete`
20. ✅ **#I-8**（§3.2.8）卸载/升级归档 retention：`config.yaml.archive.retention_days`，默认 90
21. ✅ **#I-9**（§7.4.1）shebang 白名单可配：`config.yaml.security.shebang_allowlist`，默认 `[bash, sh, python3, node]`
22. ✅ **#I-10**（§9.6）core 升级路径 `init.sh --upgrade-core`；G05 失败提示中给出指引
23. ✅ **#T-1**（§3.1.3）OT 触发：默认 focus task 1 次/回合；"全部继续"按 active_tasks fan-out
24. ✅ **#T-2**（§3.1.4）SR MVP 为确定性脚本（无 LLM）；未来可升级，token ≤500
25. ✅ **#T-3**（§3.1.7）dispatch payload 硬上限 500 字，推荐 ≤200，超出落盘传路径
26. ✅ **#T-4**（§3.2.4）`merge: replace|deep|append` schema 注解，默认按字段类型推断
27. ✅ **#T-5**（§3.2.4）自动 mutator 用 fs advisory lock + `_version` 乐观并发，最多 retry 3 次
28. ✅ **#T-6**（§7.2）`--remove-plugin` 默认阻止 active task；`--force-orphan` 标记 orphaned 后允许卸载
29. ✅ **#T-7**（§7.4）12 gates 错误码固化为 `G01..G12`，报错前缀 `[Gxx]`
30. ✅ **#T-8**（§7.4.1）`--allow-warnings` 仅降级 warning（权限/BOM/CRLF/杂项）；critical（symlink/穿越/secret/关键词/shebang）始终拒绝
31. ✅ **#T-9**（§8.1）`state.json` 加 `target_status: ok|target_missing|tampered`；OT 在 tick 开头检测
32. ✅ **#T-10**（§3.2.6）hitl-queue 文件命名 `<plugin>--<task>--<gate>--<ts>.json`
33. ✅ **#T-11**（§3.1.5）5K 红线只算固定上下文（shell + resume + tick 摘要）；对话历史独立累积，main session 不自我 distill
34. ✅ **#T-12**（§4.2）`confidence < threshold` 严格小于触发 ask_user；等于阈值视为通过
35. ✅ **#T-13**（§9.5）v5→v6 e2e 通过判据：语义等价（phase 数 + verdict 序列 + 关键 state.json 字段），不要求 byte-level diff
36. ✅ **#36**（§3.2.4.1）模型分配走 5 层链：Builtin → Plugin baseline → Workspace defaults → Plugin overrides → Task overrides；Layer 0 兜底 `opus-4.7`；plugin 在 `config-defaults.yaml.models.<role>` 声明
37. ✅ **#37**（§3.2.4.1）Router 模型例外——只读 Layer 0/2，不能由 plugin 控制（router 在 plugin 选定前运行）；默认 `tier_strong`（路由错误成本高，强模型值得；用户可在 config 显式降档）
38. ✅ **#38**（§3.2.4.1）Main session 支持自然语言改 task 级模型 override（"T-007 的 reviewer 用 X"），落到 builtin skill `task-config-set` → 写 task state.json + history
39. ✅ **#39**（§3.2.4.2）模型不写死字面型号——走 builtin skill `model-probe` 探测 + 三档分级
40. ✅ **#40**（§3.2.4.2）引入 `tier_strong / tier_balanced / tier_cheap` 符号；`tier_priority` 排名可在 `config.yaml.models.tier_priority` 覆盖
41. ✅ **#41**（§3.2.4.2）`init.sh --refresh-models` + 主会话"刷新模型"触发；catalog 缓存 30 天 TTL，存 `state.json.model_catalog`
42. ✅ **#42**（§3.2.4.2）`config-resolve` 输出 `_provenance` 字段，可回溯每个 role 的最终模型来自哪一层 / 哪个符号
43. ✅ **#43**（§3.2.4.2）未知 tier 符号（如 `tier_super_strong`）→ stderr warning + 回退 `tier_strong`，**不抛错**；`_provenance.resolved_via="fallback:tier_strong"`，与字面值不在 catalog 时的 fallback 口径一致，避免 plugin 用前瞻型 tier 名 hard-block 工作区
44. ✅ **#44**（§3.2.4.1 / §3.2.4.2）Layer 0 同时发布 `models.default = tier_strong` **和** `models.router = tier_strong`；router 例外只读 Layer 0/2，使"plugin 写的 router 值被忽略"成为可机械化测试的不变量
45. ✅ **#45**（§3.2.4）`config.yaml` 顶层 key 白名单固化为 10 项：`models / hitl / knowledge / concurrency / skills / memory / router / plugins / defaults / secrets`；其它 key 由 `config-validate` 报 `unknown_top_key` 错误

**M8 ratified decisions** (router-agent spec, 2026-05; full detail in [`docs/router-agent.md`](./router-agent.md)):

46. ✅ **#46** (router-agent §3, §5) Router-agent is a **stateless real subagent + file-backed memory**. Each user turn re-spawns a fresh subagent that reads `tasks/<tid>/router-context.md` to reconstitute the conversation; no in-process state survives across turns.
47. ✅ **#47** (router-agent §4.1) `router-context.md` is **YAML frontmatter + markdown chat body**. Frontmatter is the source of truth for router state (`state`, `turn_count`, `draft_config_path`, `selected_plugin`, `decisions[]`); body is the alternating `### user` / `### router` chat log.
48. ✅ **#48** (router-agent §8) On user confirmation, the **router-agent itself** invokes `init-task` (writing `state.json`) and the first `orchestrator-tick`, then exits with `{action:"handoff", task_id, tick_status, next_phase}`. Main session does not call `init-task` directly.
49. ✅ **#49** (router-agent §7) Router-agent reads **workspace knowledge** (`.codenook/knowledge/**/*.md`) **+ plugin-shipped knowledge** (`plugins/<installed>/knowledge/**/*.md`). `memory/<plugin>/` is excluded in M8. Per-turn cap: **20 documents**.
50. ✅ **#50** (router-agent §6) **Per-task `fcntl` exclusive lock** on `tasks/<tid>/router.lock`, acquired by main session before each spawn. Stale lock recovery threshold pinned at **300 seconds** (5 min); lock file carries `{pid, hostname, started_at, task_id}` JSON for stale detection.
51. ✅ **#51** (router-agent §2; architecture §4.3) **Domain layering** — main session is **domain-agnostic** (Conductor); router-agent is the **sole domain interpreter** on the task-creation side (Specialist); `orchestrator-tick` / `hitl-adapter` / `session-resume` are protocol surfaces (Metronome); phase agents are domain-aware per role (Performers). Enforced by an M8.6 lint test scanning `templates/CLAUDE.md` for forbidden domain tokens.
52. ✅ **#52** (router-agent §10) M3 `router-triage` skill and its bats are **removed in M8.7**. M7 `_lib/router_select.py` is **repurposed** as an internal scoring helper of router-agent (Python API only; no CLI entry). `history/router-decisions.jsonl` continues to be written, now by the router-agent, with added `turn` field and `kind: handoff|cancel` records.

---

## 13. Memory Layer (M9)

> **Status**: Spec ratified at M9.0. Full design in
> [`docs/memory-and-extraction.md`](./memory-and-extraction.md).
> Implementation work (M9.1–M9.8) is tracked in `implementation.md`.

M9 在 M8 conversational router-agent 之上引入**唯一可写的项目记忆层** +
**三类自动抽取器**，让任务执行中沉淀的知识 / 技能 / 配置以 patch-first
的方式持续吸收回项目记忆。

### 13.1 分层硬规则（runtime + linter 双重守护）

1. **`<workspace>/.codenook/plugins/` 在运行时严格只读**。所有抽取器、
   router、orchestrator-tick 都不允许写 plugin 目录；由
   `_lib/plugin_readonly_check.py` + bats 守护。
2. **`<workspace>/.codenook/memory/` 是唯一可写积累层**，按资产类型分
   `knowledge/ | skills/ | config.yaml` 三处；不再按 plugin / 领域分桶。
3. **主会话不允许扫描 `memory/`**（NFR-LAYER）；M8.6 linter 词表在 M9.7
   扩展以拦截违例。

### 13.2 三类资产 + 单文件 config

- **knowledge**：`memory/knowledge/<topic>.md`（frontmatter:
  title/summary/tags/status/...）
- **skills**：`memory/skills/<name>/SKILL.md`（frontmatter:
  name/one_line_job/applies_when/status/...）
- **config**：`memory/config.yaml` 单文件，schema 为
  `{version: 1, entries: [{key, value, applies_when, summary, status, ...}]}`；
  同 key 自动合并（latest-wins）。
- `applies_when` 是**自然语言提示**，由 router-agent LLM 推理判断命中，
  **不**是表达式。

### 13.3 触发与流程

- **触发 A**：orchestrator-tick `after_phase` hook 在 phase 进入 terminal
  状态时调度 `extractor-batch.sh --reason phase-complete`。
- **触发 B**：主会话感知上下文 ≥ 80% 时调用
  `extractor-batch.sh --reason context-pressure`（CLAUDE.md 描述协议）。
- 抽取异步执行、best-effort、按 `(task_id, phase, reason)` 哈希幂等。
- 抽取流程：secret-scan → hash dedup → `find_similar()` → **LLM 判定
  merge / replace / create**（默认偏好 merge） → 原子写入 → audit log。

### 13.4 反膨胀 — patch-first

- per-task 上限：knowledge ≤ 3、skills ≤ 1、config ≤ 5 entries（超出按
  信息密度排序丢弃）
- hash dedup：候选 body 前 512 chars 的 SHA-256，作为廉价第一道关
- candidate → promoted 两阶段：抽取产出默认 candidate；router 在下一次
  对话开场提议 promote；30 天未 promote → archived（不删除）

### 13.5 router-agent 升级

- prompt 新增 `MEMORY_INDEX` section（元数据-only，token 预算 ≤ 4K）
- `draft-config.yaml` 新增 `selected_memory.{knowledge,skills}` 段；
  config entries 由 applies_when 自动筛选
- `spawn.sh --confirm` 物化时合成 plugins + memory 双层资产到 task prompt
- `_lib/token_estimate.py` + 预算裁剪保证 router prompt ≤ 16K、task
  prompt ≤ 32K（启发式）

### 13.6 Hermes Agent 借鉴

M9 沿用 NousResearch [hermes-agent](https://github.com/NousResearch/hermes-agent)
的「prompt 引导 + 暴露 patch 工具 + 索引注入让 LLM 自决」三件套；不再
重新发明启发式 detector。完整对照表见 memory-and-extraction.md §12。

**M9 ratified decisions** (memory + extraction spec, 2026-06; full detail
in [`docs/memory-and-extraction.md`](./memory-and-extraction.md)):

53. ✅ **#53** Memory layer = workspace-local 唯一可写积累层；plugins/
    严格只读，runtime + linter 双重守护。
54. ✅ **#54** memory 不引入项目级背景文件 / 不按 plugin 分桶；仅
    `knowledge/ | skills/ | config.yaml` 三类。
55. ✅ **#55** config 为单文件 entries[] schema；同 key 合并（latest-wins）；
    `applies_when` 是自然语言提示，由 router LLM 判断命中。
56. ✅ **#56** 抽取器三件套（knowledge / skills / config）共用 patch-first
    决策流程：find_similar → LLM judge → audit log，默认偏好合并。
57. ✅ **#57** Per-task 上限：knowledge ≤ 3、skills ≤ 1、config ≤ 5；
    hash dedup（前 512 chars SHA-256）。
58. ✅ **#58** 触发由 orchestrator-tick `after_phase` hook + 主会话 80%
    上下文水位双路驱动；抽取异步、best-effort、按 `(task_id, phase, reason)`
    幂等。
59. ✅ **#59** M9 是 greenfield 子系统：M9.1 引入全新的
    `_lib/memory_layer.py`，由 init 直接创建 memory 空骨架。
