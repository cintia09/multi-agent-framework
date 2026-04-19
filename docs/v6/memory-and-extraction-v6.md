# CodeNook v6 — Memory Layer 与 LLM-driven Extraction

> **Status**: Draft (M9.0). 本文是 M9 全系列里程碑（M9.0–M9.8）的规范来源。
> M9 在 M8 conversational router-agent 之上引入**统一可写的 memory 层**与
> **三类自动抽取器（knowledge / skills / config）**，把任务执行中沉淀的
> 知识、技能与配置以 patch-first 的方式持续吸收回项目记忆，而无需用户
> 显式编辑。M9 是**全新启动的子系统**：不复用、不继承、不读取任何历史
> 用户层目录；所有 M9.x 实现工作必须遵循本文。
>
> 配套交互式需求/验收/里程碑文档见 `~/.copilot/session-state/<sid>/files/m9-requirements-and-acceptance.html`。
> 本文与该 HTML 文档一一对应：每条 FR-XXX / NFR-XXX / AC-XXX / G-X 在本文中至少出现一次以阐明取舍。

---

## 1. 概述与设计动机

### 1.1 M8 留下的差距

M8 已交付 conversational router-agent + 四类资产分层
（plugin description / skills / knowledge / config）+ workspace 读层 + role
约束。但 M8 的读层只解决了**「项目级少量定制如何被 router 看见」**的问题，
没有解决以下三件事：

1. **沉淀路径**：任务执行中产生的有价值知识（一段 API 摘要、一份脚本、
   一组测试通过的配置）没有自动回流到 workspace；用户必须手工撰写并放
   到 plugin 目录或散落在 history 中。
2. **触发协议**：M8 的 distiller 只能 CLI 手动调起，没有 hook；主会话
   也没有上下文水位监听协议；结果是「记得提取就提取，不记得就丢失」。
3. **反膨胀**：现有 distiller 输出按 plugin 分桶并条件提升，缺少跨任务
   去重 / 合并机制；多次执行同类任务会累积大量近似条目，逐渐压垮 router
   的候选窗口。

### 1.2 M9 的目标（对应 G-1 … G-6）

| ID | 目标 | 验收来源 |
|---|---|---|
| G-1 | 三类资产（knowledge / skills / config）从任务执行中**自动**抽取 | AC-EXT-* |
| G-2 | 触发与主会话状态解耦：**任务到达 terminal phase** 或 **主会话上下文 ≥ 80%** | AC-TRG-* |
| G-3 | 用户积累统一存放于 `.codenook/memory/`，**按资产类型分目录**，不按插件分 | AC-LAY-* |
| G-4 | 插件目录运行时严格只读，linter + runtime 双重守护 | AC-RO-* |
| G-5 | router-agent 自主扫描 plugins + memory 两层，自主选择注入集合 | AC-SEL-* |
| G-6 | Context 预算可控（router prompt ≤ 16K tokens，task prompt ≤ 32K tokens；启发式估算） | AC-BUD-* |

### 1.3 设计原则（在所有取舍中胜出）

- **领域中立**：memory 不按插件 / 领域分桶；项目共享。检索靠 tag + LLM
  判定，不靠目录结构。
- **Patch-first / 反膨胀**（对应 FR-EXT-MERGE）：任何抽取器在落盘前必须
  先 `find_similar()` → 命中则**调用 LLM 判定 merge / replace / create
  三选一，默认 merge**。这是抑制 memory 无界增长的核心机制，借鉴自
  NousResearch hermes-agent 的实战经验（详见 §12）。
- **Prompt-driven，不做硬编码 detector**：抽取器由 LLM 判断「值得不值得
  沉淀」「该 patch 还是 create」，而不是编码大量启发式规则。
- **Best-effort，永不阻塞主流程**（对应 FR-EXT-5、FR-TRG-4）：抽取失败、
  超时、安全扫描拒绝等都只写审计日志，不让任务无法进入 done。
- **Greenfield**：M9 是子系统的全新启动；只认识 `.codenook/memory/` 这
  一条可写路径，不识别任何其它历史路径或别名。

---

## 2. 分层模型（plugins 只读 + memory 可写）

CodeNook v6 在 M9 之后，workspace 内运行时可见的两层资产：

```
<workspace>/.codenook/
├── plugins/                          # ★ 只读层（git-managed install 产物）
│   ├── development/
│   │   ├── plugin.yaml               # 领域声明
│   │   ├── (插件级背景文件，仅读)
│   │   ├── skills/<skill>/SKILL.md
│   │   ├── knowledge/<topic>.md
│   │   └── config-defaults.yaml
│   ├── writing/
│   └── generic/
└── memory/                           # ★ 可写层（用户积累；本文规范）
    ├── knowledge/
    │   └── <topic-slug>.md           # frontmatter: title/summary/tags/...
    ├── skills/
    │   └── <skill-name>/
    │       └── SKILL.md              # frontmatter: name/one_line_job/...
    ├── config.yaml                   # ※ 单文件，entries[] schema
    └── history/
        ├── extraction-log.jsonl      # 抽取审计
        └── router-selection-log.jsonl
```

### 2.1 硬规则（runtime + linter 双重守护）

1. **plugins/ 在运行时严格只读**。所有抽取器、router、orchestrator-tick
   均不允许写 `plugins/` 或 `.codenook/plugins/` 之下任何路径。违者由
   `_lib/plugin_readonly.py`（M9.7 实现，spec 早期草稿名为
   `plugin_readonly_check.py`）双层守护：
   - **运行时**：`assert_writable_path(path, workspace_root=…)` 在
     `memory_layer._atomic_write_text` 入口处调用；任何 resolved path
     的目录段含 `plugins` 即抛 `PluginReadOnlyViolation`（继承自
     `PermissionError`，AC-RO-2 / FR-RO-2）。违例同时触发
     `extract_audit.audit(outcome="plugin_readonly_violation",
     verdict="rejected")` 落 `extraction-log.jsonl`。
   - **静态扫描**：CLI `python3 _lib/plugin_readonly.py --target <dir>
     [--json]` 扫描所有 `*.py`，识别 `open(…plugins/…, "w|a|x")`、
     `Path("…plugins/…").write_text/_bytes`、`shutil.copy/move(…
     plugins/…)`，CI / pre-commit 直接拦截（FR-RO-1 / AC-RO-1）。
2. **memory/ 是可写层的唯一根**。memory 之下不允许再次按 plugin / 领域
   分子目录（FR-LAY-1）；任何资产只能落入 `knowledge/ | skills/ | config.yaml`
   三处。
3. **memory 没有项目级背景文件（不存在 `<root>.md` 之类全局描述）**。
   项目级背景由用户在 router 对话开场口述，由 router-agent / 抽取器
   沉淀为 knowledge 条目或 config entry（FR-LAY-5）。这一规则避免了
   「同一段背景说明散落在多个层级」的歧义。
4. **CLAUDE.md / 主会话不允许扫描 memory/**（NFR-LAYER）。主会话仍域无
   关；memory 的内容只对 router-agent 与 task agent 可见。该规则由
   `_lib/claude_md_linter.py` 的 M9.7 扩展词表执行：
   - 拦截写 plugins 描述：`(let me|I will|main session may) (write|edit|
     modify|update|create) … plugins/…`（FR-RO-3 / AC-RO-3 /
     TC-M9.7-04）。
   - 拦截扫 memory shell 命令：`grep|cat|ls|find|rg|head|tail|awk|sed`
     紧邻 `.codenook/memory`（NFR-LAYER / TC-M9.7-06）。
   - 校验 `CLAUDE.md` 自身必须含 `## 上下文水位监控` 章节（M9.2 契约，
     AC-DOC-3 / TC-M9.7-05）。CLI 自动启用：当目标路径解析到仓库根
     `CLAUDE.md`（即同级存在 `.git/` 或 `skills/codenook-core/`），或
     显式带 `--check-claude-md` flag 时生效；其余 fixtures 不受影响。

### 2.2 与 M8 读层的衔接（无任何沿用）

M9 工作树由 init 直接创建 `memory/` 空骨架。M9.1 引入新的
`_lib/memory_layer.py` 取代 M8 的读层模块；本子系统不读取、不识别
也不沿用任何 M8 时代的可写路径与文件命名（详见 §10、§11）。

---

## 3. 资产模型 — 三类

### 3.1 knowledge（事实/摘要/参考）

- **存储**：`memory/knowledge/<topic-slug>.md`
- **粒度**：一篇 = 一个 topic；topic-slug 由 LLM 从 title 派生（kebab-case）
- **frontmatter（强约束）**：

```yaml
---
title: <str ≤ 120>
summary: <str ≤ 200>             # 必填，FR-EXT-2
tags: [<str>]                    # ≤ 8，FR-EXT-2
created_from_task: T-NNN
created_at: ISO8601
status: candidate | promoted | archived
related_tasks: [T-NNN]
---
<markdown body>
```

- **状态机**（FR-EXT-3）：`candidate → (用户在 router 对话中确认) → promoted`；
  30 天未确认 → 由 GC CLI 标 `archived`（不删除，AC-EXT-6）。
- **selection 上限**：每次 router 选择最多注入 5 条 knowledge（FR-SEL-6 /
  AC-SEL-6）。

### 3.2 skills（可复用脚本 / CLI 模式）

- **存储**：`memory/skills/<skill-name>/SKILL.md`（+ 可选脚本文件）
- **粒度**：一个目录 = 一个 skill；skill-name 是文件夹名。
- **frontmatter**：

```yaml
---
name: <str>                      # = 目录名
one_line_job: <str ≤ 120>
applies_when: <natural-language hint, ≤ 200 chars>
created_from_task: T-NNN
status: candidate | promoted | archived
---
<SKILL body：步骤、示例、注意事项>
```

- **检测门槛**：FR-EXT-CAP / AC-EXT-2 — 同一类脚本/命令模式在任务中重复
  ≥ 3 次才被 skill_extractor 提案；< 3 次不提案。
- **selection 上限**：每次 router 选择最多注入 3 条 skills（FR-SEL-6）。

### 3.3 config（项目级隐式背景）

- **存储**：`memory/config.yaml`（**单文件，非目录**；FR-LAY-6 / AC-LAY-6）
- **粒度**：一个 entry = 一条 key/value + applies_when 自然语言提示
- **schema**：详见 §4。
- **selection 行为**：`applies_when` 命中当前任务的 entry **无条件注入**
  （FR-SEL-5），无独立选择上限。

### 3.4 明确的反规则（不会做的事）

- **没有项目级背景文件** — 见 §2.1 规则 3。
- **没有按 plugin 分子目录** — `memory/<plugin>/` 在 M9 中不存在。
- **没有跨 workspace 共享** — memory 严格 workspace-local（Out of Scope，
  推到 M10+）。

---

## 4. config.yaml 单文件 entries[] schema

### 4.1 完整 schema

```yaml
version: 1
entries:
  - key: <dotted-string>          # 唯一标识，如 build.test_runner
    value: <any YAML>              # 实际值（标量 / list / map 均可）
    applies_when: <str ≤ 200>      # 自然语言提示，由 router-agent LLM 评估
    summary: <str ≤ 120>           # 给 router 看的一行总结
    status: candidate | promoted | archived
    created_from_task: T-NNN
    created_at: ISO8601
    last_used_at: ISO8601          # 由 router 在选中注入时更新；GC 老化依据
```

### 4.2 同 key 合并语义（FR-EXT-MERGE / AC-EXT-3 / AC-LAY-6）

抽取器在写入新 entry 前必须按 `key` 查找已有 entry：

- **同 key 命中** → **合并为最新值**：
  - `value`：新值替换旧值（latest-wins）
  - `applies_when`：以新提示替换；如旧提示未失效，由 LLM 判定是否需要
    保留旧提示作为补充（在 summary 中说明）
  - `summary`：以新 summary 替换
  - `status`：保留为 `candidate`（即使原为 promoted，也降级为 candidate
    重新等待用户确认；这避免了静默改写已确认配置）
  - `created_from_task`：追加到 history 字段，原值不丢
  - `created_at`：保留旧值
  - `last_used_at`：保留旧值
- **同 key 未命中** → 直接 append 新 entry

> `config-validate` 工具拒绝出现重复 key（AC-LAY-6）；抽取器是唯一允许
> 写 `config.yaml` 的客户端，且实现严格按上面的合并语义。手工编辑请通
> 过 dedicated CLI（M9.5 提供 `config_extractor patch <key> --value ...`）。

### 4.3 applies_when 是**自然语言提示**，不是表达式

- M8 以及更早设计曾考虑用 `_lib/expr_eval.py` 在代码侧 evaluate
  `applies_when` 表达式。M9 **明确放弃这条路**。
- 决策：`applies_when` 是一段 ≤ 200 字符的自然语言描述（例如
  `"任务涉及 Python 项目且需要选择测试框架时"`），由 **router-agent 在
  LLM 推理中判断是否命中当前任务**。
- 理由：
  1. 表达式语法限制了表达力，写出来既不像 DSL 也不像自然语言。
  2. router-agent 已经在做 LLM 推理，让它顺手判断 applies_when 命中是
     零额外 token 成本。
  3. 自然语言提示对用户友好，可在 candidate→promoted 流程中直接编辑。
- router-agent prompt 中 `MEMORY_INDEX` section 会列出每个 config entry
  的 `key + summary + applies_when` 三元组，由 LLM 输出 `selected_config_keys`。
- `_lib/memory_layer.py` 不再提供 `evaluate_applies_when()`；它只提供
  `read_config_entries()` 与 `match_entries_for_task(task_brief)`，后者
  是给 router-agent 调用的、走 LLM 的辅助函数（见 §10）。

### 4.4 实例

```yaml
version: 1
entries:
  - key: build.test_runner
    value: pytest -q
    applies_when: 任务涉及 Python 单元测试时
    summary: Python 项目偏好用 pytest -q 跑测试
    status: promoted
    created_from_task: T-014
    created_at: 2026-06-01T08:14:22Z
    last_used_at: 2026-06-12T11:02:09Z

  - key: code.style.line_length
    value: 100
    applies_when: 任何 Python 代码生成任务
    summary: 项目内 Python 代码行宽 100
    status: candidate
    created_from_task: T-031
    created_at: 2026-06-12T09:51:00Z
```

---

## 5. 提取生命周期

### 5.1 两条触发路径

```
路径 A — 任务终态触发 (FR-TRG-1)
  orchestrator-tick(phase=done | phase=blocked)
    └─ after_phase hook
         └─ extractor-batch.sh --task-id T-NNN --reason phase-complete
              ├─ knowledge_extractor.sh
              ├─ skill_extractor.sh
              └─ config_extractor.sh

路径 B — 主会话上下文水位触发 (FR-TRG-2)
  主会话感知 context ≥ 80%
    └─ 调用 extractor-batch.sh --reason context-pressure
         └─ 同上三件套（不分任务，遍历当前 active tasks）
         └─ 触发后主会话可独立决定是否压缩 / 重置自身（CLAUDE.md 描述，§5.4）
```

### 5.2 异步 + 幂等

- **异步**（FR-TRG-4 / AC-TRG-4）：`extractor-batch.sh` 在子进程执行；
  orchestrator-tick 立即返回，不等抽取完成。
- **幂等**（FR-TRG-3 / NFR-IDEMP / AC-TRG-2）：
  - 路径 A：以 `(task_id, phase, reason)` 三元组哈希为去重键，写入
    `history/extraction-log.jsonl`；同键 24h 内重复触发直接 short-circuit
    返回 `skipped: duplicate`。
  - 路径 B：以 `(reason=context-pressure, hour-bucket)` 为去重键，避免
    主会话连续抖动时重复抽取。

### 5.3 best-effort 失败语义

- LLM 调用失败 / secret-scanner 拒绝 / 文件系统故障 → 写 audit log，**不**
  改变任务状态。
- AC-EXT-4：mock LLM 抛错时三类抽取器均能让任务正常进入 done。

### 5.4 主会话水位监听协议（CLAUDE.md 扩展点，AC-TRG-3 / AC-DOC-3）

M9.2 在根 `CLAUDE.md` 中新增一段（约 30 行）描述：

- 主会话需周期性自评估上下文使用率（启发式：本地估算 token，CJK 1:1，
  ASCII 1:4）。
- 当估算 ≥ 80% 时，主会话**必须**调用
  `extractor-batch.sh --reason context-pressure`（一次调用），然后
  根据返回的 `enqueued_jobs` 数量决定是否对自身做摘要 / 重置。
- 主会话**不允许**直接扫描 memory；只允许把 batch 命令的退出 JSON 当
  字符串转给用户。
- M8.6 linter 扩展词表新增 `memory/`、`extraction-log` 等域 token，确
  保主会话 prompt / 回复中不出现对 memory 内容的解读。

---

## 6. Patch-first 决策流程

### 6.1 流程伪代码

```python
def extract_one(task_id: str, candidate: ExtractCandidate) -> ExtractDecision:
    """处理一个候选条目（knowledge / skill / config entry）。"""
    # 步骤 1：硬性安全门
    if secret_scanner.scan(candidate.body).hit:
        audit("secret_blocked", task_id, candidate)
        return ExtractDecision(action="blocked", reason="secret-scanner")

    # 步骤 2：hash dedup（FR-EXT-DEDUP / AC-EXT-MERGE-4）
    h = sha256(candidate.body[:512])
    if memory_layer.has_hash(h):
        audit("dedup_skip", task_id, candidate, hash=h)
        return ExtractDecision(action="dedup-skip", reason="hash-match")

    # 步骤 3：相似度查找（FR-EXT-MERGE）
    similar = memory_layer.find_similar(
        kind=candidate.kind,
        title=candidate.title,
        tags=candidate.tags,
        # 阈值：tags 重叠 ≥ 50% OR title cosine ≥ 0.7
    )

    # 步骤 4：LLM 判定 merge / replace / create
    if similar:
        verdict = llm_judge_merge(
            existing=similar,
            new=candidate,
            preference="merge",     # 默认偏好
        )
        # verdict.action ∈ {"merge", "replace", "create"}
        # verdict.rationale: str
    else:
        verdict = LLMVerdict(action="create", rationale="no similar found")

    # 步骤 5：执行 + 审计
    if verdict.action == "merge":
        path = memory_layer.patch(similar.path, candidate, verdict)
    elif verdict.action == "replace":
        path = memory_layer.replace(similar.path, candidate, verdict)
    else:
        path = memory_layer.create(candidate)

    audit_log_entry = {
        "ts": now_iso(),
        "task_id": task_id,
        "kind": candidate.kind,
        "action": verdict.action,
        "rationale": verdict.rationale,
        "similar_path": similar.path if similar else None,
        "written_path": str(path),
        "hash": h,
    }
    memory_layer.append_audit(audit_log_entry)
    return ExtractDecision(action=verdict.action, path=path)
```

### 6.2 LLM 判定 prompt 骨架

```
你正在帮 CodeNook 决定如何把一条新提取的 {kind} 沉淀进项目 memory。
默认偏好「合并」（patch）；只有在新旧条目的核心事实存在显著矛盾时才
建议 replace；只有在主题确实不同（核心 tag 几乎不重叠）时才建议 create。

## 已存在条目
title: ...
summary: ...
tags: [...]
body (≤ 1.5K chars): ...

## 新候选条目
title: ...
summary: ...
tags: [...]
body (≤ 1.5K chars): ...

## 输出 JSON（严格）
{ "action": "merge"|"replace"|"create", "rationale": "<≤ 200 chars>" }
```

### 6.3 patch 执行细节

- **knowledge** patch：保留旧 frontmatter 的 `created_at` / `created_from_task`，
  新 task 追加进 `related_tasks[]`；`status` 在 promoted 条目被 patch 时
  保持 promoted（合并是知识增量，不像 config 那样是值替换）；body 由 LLM
  在 verdict 之外的同次调用产出（合并后的统一行文）。
- **skill** patch：以新版本完全替换 SKILL.md body；frontmatter 仅追加
  `created_from_task` 至 `history` 数组，不改 `name`。
- **config** patch：按 §4.2 的合并规则；hash dedup 在 entry-level 而非
  文件 level（dedup key = `sha256(yaml_dump(value)[:512])`）。

### 6.4 审计日志（FR-EXT-4 / NFR-OBS / AC-EXT-MERGE-2）

`memory/history/extraction-log.jsonl` 每行一条 JSON，字段固定：
`ts, task_id, kind, action, rationale, similar_path, written_path, hash, reason`。
该文件**只追加，不改写**；GC 在 90 天后滚到 `extraction-log.YYYY-QN.jsonl`。

---

## 7. Per-task 上限 + hash dedup

### 7.1 per-task 上限（FR-EXT-CAP / AC-EXT-MERGE-3）

| 资产 | 单次任务最多新条目 | 超出策略 |
|---|---|---|
| knowledge | **3** | 按信息密度排序，只保留前 3 |
| skills | **1** | 按重复次数排序，只保留 1 |
| config entries | **5** | 按 applies_when 命中范围排序，只保留前 5 |

「信息密度」启发式：`unique_tags * (1 - duplication_with_existing)`，由
`_lib/extract_density.py` 计算；超出条目写 audit log 标 `dropped: cap`。

### 7.2 hash 去重（FR-EXT-DEDUP / AC-EXT-MERGE-4）

- 候选 body 的前 512 chars 取 SHA-256，作为 `dedup_key`。
- `memory_layer.has_hash()` 查询当前 memory 中所有同类资产的 hash 索引
  （由 `memory_index.py` 维护，mtime-cached）。
- 命中即 short-circuit，**不调 LLM**，直接写 audit log
  `action: dedup-skip`。
- 这是反膨胀的「廉价第一道关」；LLM judge 只在通过 hash dedup 后才会
  被触发。

### 7.3 与 promoted 条目的关系

- candidate 与 promoted 共享同一 hash 索引；新候选 hash 与 promoted 一
  致也会被 dedup。
- candidate 30 天未 promote → archived；archived 条目**仍参与 hash
  index**（避免再次创建已被用户隐式拒绝的条目）。

---

## 8. MEMORY_INDEX 注入到 router-agent prompt

### 8.1 位置与渲染

router-agent 的 `prompt.md` 在 M9.6 升级，新增 `## Memory index` section，
位于现有 `## Available plugins` 之后、`## Workspace user context` 之前
（user context 段也由 M9.6 重命名 / 重写以反映 memory 来源）。

骨架：

```markdown
## Memory index (workspace-local user accumulation)

### Knowledge ({{KNOWLEDGE_COUNT}} promoted, {{KNOWLEDGE_CANDIDATE_COUNT}} candidate)

| id | title | summary | tags | status |
|----|-------|---------|------|--------|
{{KNOWLEDGE_ROWS}}

### Skills ({{SKILL_COUNT}} promoted)

| name | one_line_job | applies_when | status |
|------|--------------|--------------|--------|
{{SKILL_ROWS}}

### Config entries ({{CONFIG_COUNT}})

| key | summary | applies_when | status |
|-----|---------|--------------|--------|
{{CONFIG_ROWS}}

> 选择规则：
> - knowledge ≤ 5、skills ≤ 3 由你显式列入 selected_memory（按相关性）
> - config 中所有 applies_when 命中本任务的 entry 自动注入，无需你列出
> - 默认隐藏 candidate；用户在对话中明确说「试试 candidate XXX」才纳入
```

### 8.2 token 预算（FR-BUD-2 / FR-BUD-3 / AC-BUD-1）

- `MEMORY_INDEX` section 预算：≤ 4K tokens（router prompt 总额 16K 中
  的 1/4）。
- 超出时按 FR-BUD-3 顺序裁剪：`config 命中 entry > selected_memory >
  selected_plugins · 知识正文 > skills 正文`。
- 索引行按 `(status=promoted desc, last_used_at desc, created_at desc)`
  排序后取 top-K，K 由 `_lib/token_estimate.py` 二分逼近。

### 8.3 router 决策落 draft-config

`draft-config.yaml` 在 M9.6 扩展（AC-SEL-3）：

```yaml
selected_memory:
  knowledge: [<topic-slug>, ...]   # ≤ 5
  skills: [<skill-name>, ...]      # ≤ 3
  # config 不在此列出 — 由 applies_when 自动筛选
context_budget:
  router_prompt_tokens: 16000
  task_prompt_tokens: 32000
```

### 8.4 实例

```markdown
### Knowledge (4 promoted, 2 candidate)

| id | title | summary | tags | status |
|----|-------|---------|------|--------|
| pytest-fixture-best-practices | pytest fixture 最佳实践 | 用 yield 拆分 setup/teardown，scope 默认 function | [python, pytest, testing] | promoted |
| openapi-3.1-quirks | OpenAI API 3.1 quirks | discriminator 在 oneOf 下的解析差异 | [openapi, api, schema] | promoted |
```

---

## 9. 安全

### 9.1 secret-scanner 集成（NFR-SECURITY / AC-EXT-5）

- 复用 builtin `secret-scan` skill（M5 已交付）。
- 抽取器在 LLM judge 之前先扫候选 body；命中任意规则（API key / token /
  RSA private key block / DB connection string / 内网 IP / GitHub PAT）
  即 fail-close：
  - 不写 memory
  - 写 audit log `action: blocked, reason: secret-scanner, rule_id: <id>`
  - 通知 orchestrator-tick（不影响 phase 流转，仅写 history 提示）
- 内网 IP 模式包含但不限于：`10.*`、`172.16.*-172.31.*`、`192.168.*`、
  IPv6 ULA `fc00::/7`。

### 9.2 写入审计

- 所有写 memory 的操作（create / patch / replace / dedup-skip / blocked）
  写 `memory/history/extraction-log.jsonl`。
- 所有 router 选择决策写 `memory/history/router-selection-log.jsonl`，
  字段：`ts, task_id, turn, selected_memory{knowledge:[],skills:[]},
  applied_config_entries:[<key>], rationale`。

### 9.3 candidate → promoted 流程

- 抽取器产出默认 `status: candidate`（FR-EXT-3）。
- router-agent 在每个新对话开场扫描当前 task 相关 candidate（按
  `created_from_task` 或 tag 关联），主动询问：「上次我帮你做 T-014，
  我抽出了下面 2 条候选知识 / 1 条 skill / 3 条 config entry，你想
  promote 哪些？」
- 用户回应 → router 通过 `_lib/memory_layer.promote(path)` 把 status
  从 candidate 改为 promoted。
- 30 天未 promote → 由 daily GC CLI（`memory-gc.sh`）标 archived，不
  从磁盘删除（AC-EXT-6）。
- archived 条目不出现在 `MEMORY_INDEX` 中，但仍参与 hash dedup（§7.3）。

### 9.4 并发安全

- 所有写操作走 `_lib/atomic.py`：tmp-file + rename（POSIX 原子）。
- 多 extractor 并发写同一文件时，按 `_lib/file_lock.py`（fcntl 短锁）
  互斥；锁 hold 时间 < 200ms。
- 读不阻塞写、写不阻塞读：`memory_index.py` 读路径走 mtime-cached
  snapshot（NFR-CONC-2）。

---

## 10. 接口契约 — `_lib/memory_layer.py`

### 10.1 公共函数签名

> **签名形式说明（M9.1 实现校准）**：所有写入/变更接口统一采用
> `workspace_root` 作为首位参数 + 关键字参数 + mutator 回调的形式。
> 这样可以防止跨 workspace 误写，并让审计轨迹（哪个 workspace、哪个
> topic、哪种 verdict）永远显式可见，避免裸 `Path` 调用泄漏到错误目录。

```python
# ---- 路径与发现 ----
def memory_root(workspace_root: Path | str) -> Path: ...
def has_memory(workspace_root: Path | str) -> bool: ...
def init_memory_skeleton(workspace_root: Path | str) -> None:
    """创建空骨架：knowledge/、skills/、config.yaml(version:1, entries:[])、history/。"""

# ---- knowledge ----
def scan_knowledge(workspace_root) -> list[KnowledgeMeta]:
    """返回元数据列表（不读 body）；mtime-cached。"""
def read_knowledge(path: Path | str) -> KnowledgeDoc:
    """读 frontmatter + body。接受文件绝对路径。"""
def write_knowledge(
    workspace_root,
    *,
    topic: str,
    summary: str = "",
    tags: list[str] | None = None,
    body: str = "",
    frontmatter: dict | None = None,
    doc: KnowledgeDoc | None = None,   # 等价输入：{"topic","frontmatter","body"}
    status: str = "candidate",
    created_from_task: str = "",
    atomic: bool = True,
) -> Path:
    """原子写入；create 路径，返回最终文件路径。"""
def patch_knowledge(
    workspace_root,
    *,
    topic: str,
    mutator: Callable[[KnowledgeDoc], KnowledgeDoc],
    rationale: str,
) -> Path:
    """读-改-原子写；mutator 在 fcntl 临界区内被调用，返回新 doc。
    审计 verdict=merge。"""
def replace_knowledge(
    workspace_root,
    *,
    topic: str,
    frontmatter: dict,
    body: str,
    rationale: str,
) -> Path:
    """全量覆盖；审计 verdict=replace。"""
def promote_knowledge(workspace_root, path: Path | str) -> None: ...
def archive_knowledge(workspace_root, path: Path | str) -> None: ...

# ---- skills ----
def scan_skills(workspace_root) -> list[SkillMeta]: ...
def read_skill(workspace_root, name: str) -> SkillDoc: ...
def write_skill(
    workspace_root,
    *,
    name: str,
    frontmatter: dict,
    body: str,
    status: str = "candidate",
    created_from_task: str = "",
) -> Path: ...
def patch_skill(
    workspace_root,
    *,
    name: str,
    mutator: Callable[[SkillDoc], SkillDoc],
    rationale: str,
) -> Path: ...
def promote_skill(workspace_root, name: str) -> None: ...

# ---- config ----
def read_config_entries(workspace_root) -> list[ConfigEntry]: ...
def upsert_config_entry(workspace_root, *, entry: ConfigEntry, rationale: str) -> ConfigEntry:
    """同 key 命中则按 §4.2 合并；否则 append。"""
def match_entries_for_task(workspace_root, task_brief: str) -> list[ConfigEntry]:
    """走 LLM 判断 applies_when 命中；router-agent 在选择阶段调用。"""
def promote_config_entry(workspace_root, key: str) -> None: ...

# ---- 通用 ----
def find_similar(
    workspace_root,
    kind: Literal["knowledge", "skill", "config"],
    title: str,
    tags: list[str],
    *,
    tag_overlap_threshold: float = 0.5,
    title_cosine_threshold: float = 0.7,
) -> list[SimilarMatch]: ...

def has_hash(workspace_root, kind: str, dedup_key: str) -> bool: ...
def append_audit(workspace_root, entry: dict) -> None: ...

# ---- 索引 ----
def scan_memory(workspace_root) -> MemoryIndex:
    """聚合 knowledge / skills / config 元数据；NFR-PERF-1：1000 文件 ≤ 500ms。"""
```

### 10.2 数据类型

```python
@dataclass(frozen=True)
class KnowledgeMeta:
    path: Path
    title: str
    summary: str
    tags: tuple[str, ...]
    status: Literal["candidate", "promoted", "archived"]
    created_from_task: str
    created_at: str
    related_tasks: tuple[str, ...]
    dedup_hash: str

@dataclass(frozen=True)
class SkillMeta:
    name: str
    path: Path
    one_line_job: str
    applies_when: str
    status: str
    created_from_task: str

@dataclass(frozen=True)
class ConfigEntry:
    key: str
    value: Any
    applies_when: str
    summary: str
    status: str
    created_from_task: str
    created_at: str
    last_used_at: str | None
```

### 10.3 错误与异常

- `MemoryLayoutError` — 骨架缺失关键路径（不会自动创建以防误写到错误
  目录）
- `ConfigSchemaError` — config.yaml 顶层结构非法或出现重复 key
- `SecretBlockedError` — 候选触碰 secret-scanner（由 extractor 捕获并
  转为 audit log，不向上抛）
- `ConcurrentWriteError` — fcntl 等待超时（默认 5s）

### 10.4 不提供的接口

- ❌ `evaluate_applies_when(expr)` — 已废弃，见 §4.3。
- ❌ `merge_config_into_draft()` — 这是 user-overlay 时代的辅助；M9 中
  config entry 由 router-agent 直接选择并注入，不再 shallow-merge 到
  draft-config 顶层。

---

## 11. 与 M8 的关系

### 11.1 名字对照（greenfield；不沿用 M8 的可写路径）

| M8 概念 | M9 概念 | 备注 |
|---|---|---|
| `_lib/workspace_overlay.py` | `_lib/memory_layer.py` | M9.1 以全新模块替换 |
| `OVERLAY_DIRNAME = "user-overlay"` | `MEMORY_DIRNAME = "memory"` | 路径常量 |
| `overlay_root()` / `has_overlay()` | `memory_root()` / `has_memory()` | API 改名 |
| `read_description()` | （删除） | M9 不引入项目级背景文件，见 §2.1 规则 3 |
| `read_config()`（顶层 dict） | `read_config_entries()`（list） | schema 由 dict 改为 entries[] |
| `discover_overlay_skills()` | `scan_skills()` | 返回结构含 frontmatter 元数据 |
| `discover_overlay_knowledge()` | `scan_knowledge()` | 同上 |
| `overlay_bundle()` | `scan_memory() → MemoryIndex` | 元数据-only，不再含 body |
| `merge_config_into_draft()` | （删除） | 见 §10.4 |

### 11.2 router-agent prompt 结构演进

- M8 prompt：`PLUGINS_SUMMARY → ROLES → OVERLAY → CONTEXT → USER_TURN`
- M9 prompt：`PLUGINS_SUMMARY → ROLES → MEMORY_INDEX → PLUGIN_DESC → CONTEXT → USER_TURN`
  - `PLUGIN_DESC` 仅指 plugin 自带的、只读的插件级背景文件；memory 内
    没有对应物
  - `MEMORY_INDEX` 是元数据-only 的注入；命中 config entry 的 value 在
    handoff 阶段才物化进 task prompt（§8.3）

### 11.3 spawn.sh handoff 物化

M9.6 在 `spawn.sh --confirm` 阶段把 plugins + memory 双层资产合成进
任务 prompt context（FR-SEL-4 / AC-SEL-4）：

```
task prompt context = (
    plugin role profiles (from selected plugin)
  + selected_memory.knowledge full body (≤ 2KB direct embed, 否则注入路径 + summary)
  + selected_memory.skills full body
  + matched config entries (key=value 列表 + summary)
)
```

### 11.4 Decisions 追加（拟在架构 §13 落地）

- **#53** Memory layer = workspace-local 唯一可写积累层；plugins/ 严格
  只读。
- **#54** memory 不引入项目级背景文件 / 不按 plugin 分桶。
- **#55** config 为单文件 entries[] schema；同 key 合并；applies_when 是
  自然语言提示，由 router LLM 判断命中。
- **#56** 抽取器三件套（knowledge / skills / config）共用 patch-first
  决策流程（find_similar → LLM judge → audit log），默认偏好合并。
- **#57** Per-task 上限：knowledge ≤ 3、skills ≤ 1、config ≤ 5；hash
  dedup（前 512 chars SHA-256）。
- **#58** 触发由 orchestrator-tick after_phase hook + 主会话 80% 上下文
  水位双路驱动；抽取异步、best-effort、幂等。
- **#59** `_lib/workspace_overlay.py` 在 M9.1 由全新的
  `_lib/memory_layer.py` 替换；M9 是 greenfield 子系统。

---

## 12. Hermes Agent 借鉴

NousResearch 的开源 [`hermes-agent`](https://github.com/NousResearch/hermes-agent)
（v0.2.0，MIT，> 3K stars）实现了类似的 self-improving / 自动技能管理
闭环。其核心设计与 M9 高度同构。下表是关键借鉴点（来自交互式需求文档
§11，转译为本仓库可引用的 markdown 表格）：

| Hermes 机制 | 来源 / 文件 | M9 对应设计 |
|---|---|---|
| **Prompt-driven 触发**：不做硬编码「重复模式检测」启发式，而是在 system prompt 注入 `SKILLS_GUIDANCE`：「complete 5+ tool 调用 / 修复非平凡错误后 → 调 `skill_manage` 保存」 | `agent/prompt_builder.py` 中 `SKILLS_GUIDANCE` 块 | FR-TRG（after_phase hook + CLAUDE.md 80% 水位）等价于 Hermes 的「prompt 引导 + 工具暴露」方案，不需要复杂的运行时 detector |
| **Patch-first 反膨胀**：「skill 过时即调用 `skill_manage(action='patch')` —— 不要等被问。未维护的 skill 会变成负担」 | 同上 SKILLS_GUIDANCE 第二段 | **FR-EXT-MERGE**（M9 核心反膨胀原则）：先 `find_similar()` → LLM 判定 merge / replace / create，默认偏好 merge |
| **统一 Skill Manager 工具**：暴露 6 个 action 给 agent：`create / edit / patch / delete / write_file / remove_file` | `tools/skill_manager_tool.py` | FR-LAY-4 `_lib/memory_layer.py` 的接口（`scan_* / read_* / write_* / patch_* / promote_* / archive_*`）；M9.6 把语义对等的 patch-or-create 操作暴露给 router-agent 的 LLM |
| **Skills index 注入**：所有 skill 的 `name + description`（不含 body）在每轮 system prompt 中可见；agent 自然知道「已有什么」，从而主动选择合并而非新建 | `agent/prompt_builder.py` 的 `_build_skills_manifest` + cache | FR-SEL-1 / FR-SEL-2 `_lib/memory_index.py` + router prompt 渲染 `MEMORY_INDEX`（§8）。设计完全一致 |
| **验证守门**：name ≤ 64、description ≤ 1024、SKILL.md ≤ 100K chars、单文件 ≤ 1MB；YAML frontmatter 必含 name/description；写入后过 `skills_guard` 安全扫描 | `tools/skill_manager_tool.py` 的 `_validate_*` 系列 | FR-EXT-2（summary ≤ 200，tags ≤ 8）+ NFR-SECURITY 的 secret-scanner 集成。M9 直接复用 hermes 的 schema 思路 |
| **Skills snapshot 缓存**：把扫描结果按 mtime 持久化到 `.skills_prompt_snapshot.json`，加速冷启动 | `agent/prompt_builder.py` 的 `_SKILLS_PROMPT_CACHE` / snapshot 文件 | NFR-PERF-1（≤ 500ms）的具体实现技巧；M9 的 `memory_index.py` 采用 mtime-based snapshot |
| **外部目录只读**：`_is_local_skill()` 区分 `SKILLS_DIR` 内可写 vs `external_dirs` 只读 | `tools/skill_manager_tool.py` 的 `_is_local_skill` | FR-RO 完全对应：`plugins/` 只读、`memory/` 可写；`_lib/plugin_readonly_check.py` 是工程级守护 |

### 12.1 核心结论

M9 不需要重新发明启发式 detector。**沿用 Hermes 的「prompt 引导 + 暴露
patch 工具 + 索引注入让 LLM 自决」三件套即可**，工程量大幅降低。Hermes
已用 200+ 个 production skill 验证此模式可行。

### 12.2 与 Hermes 的差异点

- **Hermes 是单 agent**；CodeNook 是 **router + task 双层 + 离线 extractor**。
  我们的抽取器必须在「无对话上下文」下做提取决策（任务终态触发或上下文
  水位触发），所以需要 **LLM 判定步骤（FR-EXT-MERGE）显式化**——M9 把
  「该 patch 还是 create」这一步从 hermes 的「让对话中 agent 凭 system
  prompt 自决」固化成抽取器内嵌的一次 LLM 调用。
- **Hermes 没有 candidate → promoted 流程**；M9 引入两阶段确认（FR-EXT-3）
  以应对自动抽取的噪声风险——抽取器是「offline daemon」，没法当面让
  用户确认，所以默认 candidate + 下次 router 对话开场提议 promote 是
  更稳的折中。
- **Hermes 的 skill 是单类资产**；M9 拆出 knowledge / skills / config
  三类，它们的 patch 语义不同（知识合并、技能替换、配置 latest-wins），
  在 §6.3 中独立刻画。

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| **Memory 无界增长** | router 索引耗时、context 超预算 | FR-BUD 预算裁剪 + 30 天 archived 逻辑归档 + GC CLI；§7 per-task cap + hash dedup 是第一道防线 |
| **Extractor LLM 误抽取（噪声）** | 用户被无用 candidate 淹没 | FR-EXT-3 的 candidate→promoted 流程；router 默认隐藏 candidate；用户在对话中显式 promote |
| **插件目录被意外写入** | git diff 噪声、用户 install 产物被破坏 | FR-RO 双重守护（runtime check + linter）；bats 测试模拟违例 |
| **主会话泄漏域信息** | 违反 M8.6 layering | NFR-LAYER：linter 词表扩展，主会话不允许提及 memory 内容；只能透传 batch 命令的 JSON 输出 |
| **Context 估算不准** | 真 LLM 调用 token 超额 | FR-BUD-1 启发式偏保守（CJK 1:1）；E2E 用真实 prompt 校准；超预算自动裁剪 |
| **抽取器串行阻塞任务** | 用户感知任务延迟 | FR-EXT-5 best-effort + FR-TRG-4 异步执行；orchestrator-tick 不等抽取完成 |
| **applies_when 自然语言被 LLM 误判** | config 漏注入或错误注入 | router 选择决策写 `router-selection-log.jsonl`；用户可在对话中 override；候选 entry 的 last_used_at 暴露在 MEMORY_INDEX，便于发现长期未命中的「死配置」 |
| **patch 决策错误覆盖有价值旧条目** | 知识丢失 | knowledge patch 只追加 `related_tasks`、合并 body，不清空旧 frontmatter；replace 路径需 LLM 给出明确「核心事实矛盾」理由（写入 audit log，可回滚） |
| **secret-scanner 漏判** | 凭据进入 memory | scanner 规则集 fail-close；新规则在 M9.3 与 secret-scan skill 同步；写入路径只有 extractor 一条，便于审计收口 |
| **并发抽取竞态** | config.yaml 半写 | NFR-CONC-1 原子写 + fcntl 短锁；bats 并发压力测试在 M9.1 落地 |

---

## 14. 术语表

| 术语 | 定义 |
|---|---|
| **Memory layer** | `<workspace>/.codenook/memory/`，运行时用户积累层，按资产类型分目录（knowledge / skills / config.yaml） |
| **Plugin layer** | `<workspace>/.codenook/plugins/`，git-managed 安装产物，运行时严格只读 |
| **Extractor** | 一类 builtin skill（knowledge_extractor / skill_extractor / config_extractor）：分析任务输出、判定 patch / create、沉淀到 memory |
| **extractor-batch** | 编排三类 extractor 的 shell 入口；接受 `--task-id` 与 `--reason` 两个参数；幂等；异步 |
| **after_phase hook** | orchestrator-tick 在 phase 进入 terminal 状态（done / blocked）后调用的回调点；M9.2 引入 |
| **Context pressure** | 主会话上下文 ≥ 80% 时触发 extractor-batch 的事件类型（`reason=context-pressure`） |
| **candidate** | extractor 产出的初始状态；router 默认隐藏；30 天未 promote → archived |
| **promoted** | 用户在 router 对话中确认有效的 memory 条目；参与 router 默认选择 |
| **archived** | 30 天未 promote 的 candidate 的逻辑状态；不出现在 MEMORY_INDEX，但仍参与 hash dedup |
| **find_similar** | `_lib/memory_layer` 提供的相似度查找函数；阈值 tags 重叠 ≥ 50% 或 title cosine ≥ 0.7 |
| **patch-first** | M9 反膨胀核心原则：抽取时先尝试合并已有条目，不轻易 create |
| **applies_when** | 一段 ≤ 200 字符的自然语言提示，描述 config entry 在何种任务场景下生效；由 router-agent LLM 推理判断命中 |
| **MEMORY_INDEX** | router-agent prompt 中渲染 memory 元数据的 section（§8） |
| **selected_memory** | `draft-config.yaml` 中 router 写入的、user 确认的 memory 注入清单（knowledge / skills 两段） |
| **dedup_key** | 候选 body 前 512 chars 的 SHA-256；用于 §7.2 廉价 dedup |
| **extraction-log.jsonl** | `memory/history/` 下的写入审计日志；append-only，季度滚动 |
| **router-selection-log.jsonl** | `memory/history/` 下的选择决策审计日志；记录每次 router 注入了哪些 memory 条目 |

---

> **本文档不是什么**：不是用户操作手册（M9.8 时再写）；不是测试规划
> （见 `docs/v6/test-plan-v6.md` 或 m9-bats 套件）；不是 v6 总体架构
> （见 `architecture-v6.md`）。它是 M9 子系统的**单一规范源**。
