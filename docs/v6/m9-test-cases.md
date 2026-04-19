# M9 测试用例集 — Memory Layer & LLM-Driven Extraction

> 版本：M9.0.1（紧随 M9.0 设计文档之后交付的 TDD 输入合同）
>
> 适用范围：M9.1 – M9.8 全部里程碑
>
> 关联文档：
> - `docs/v6/memory-and-extraction-v6.md`（设计 / 接口 / 数据模型）
> - `docs/v6/architecture-v6.md` §13（Memory Layer 决策 #53–#59）
> - `docs/v6/implementation-v6.md` §M9（per-milestone 文件 / 测试 / 工时拆解）
> - `m9-requirements-and-acceptance.html`（需求 / FR / AC / NFR 源）
>
> 本文档是 M9 TDD 阶段的**唯一**测试合同：所有 M9.x 的 bats / 集成 / E2E
> 用例必须先在此文档登记（编号 + 关联 FR/AC + 步骤 + 期望），sub-agent 才能
> 在 TDD 阶段「先写红用例，后写实现」。任何在文档外凭空增加的用例必须
> 倒灌回本文件（review 阶段会比对）。

---

## 0. 概述与测试策略

### 0.1 与设计 / 需求文档的对应关系

| 维度 | 来源 | 在本文档中的体现 |
|------|------|------------------|
| 数据模型 / schema | spec §3 §4 | 每个 case 的 fixture 段引用 schema |
| 接口契约 | spec §10 (`memory_layer.py` 函数签名) | unit case 的步骤直接 import 验证 |
| 触发流程 | spec §5 (after_phase / 80% 水位) | M9.2 全部 case |
| 决策流（patch-or-create） | spec §6 + Hermes 对照表 | M9.3 / M9.4 / M9.5 共用 |
| Router 整合 | spec §8 §11 | M9.6 全部 case |
| 安全 | spec §9 + NFR-SECURITY | M9.3 secret 拦截 + M9.7 readonly |
| 验收 | HTML doc 的 AC-LAY/EXT/TRG/RO/SEL/BUD/DOC/E2E | 0.4 节覆盖矩阵 |

### 0.2 测试分层

M9 在三层进行测试，所有层使用 bats 框架以与 M1–M8 baseline 一致：

| 层级 | 范围 | 典型用例数 | 触达边界 |
|------|------|------------|----------|
| **unit** | 单 Python 模块 / shell 函数 | ~45 | 进程内；mock 文件系统 + mock LLM |
| **integration** | 多模块协作 / skill CLI | ~20 | 临时 workspace；mock LLM；真 fs |
| **E2E** | 完整 router → tick → extractor 链路 | ~8 | 隔离 `/tmp` workspace；mock LLM 全程 |

每个测试 case 在「类型」字段标注层级。`property` 标注的 case 需要参数化输入
（Hypothesis 风格），但保留在 bats 内通过循环构造。

### 0.3 通用测试约定

1. **Fixture 路径**：所有用例使用 `mktemp -d` 创建的 `$WS` 临时 workspace，
   测试结束 `rm -rf "$WS"`。永远不写 `/tmp` 之外的磁盘（已被规则禁用，使用
   仓库内 `tests/.tmp/` 子目录代替；helper 提供 `make_ws()`）。
2. **Mock LLM 协议**：
   - 默认在测试启动前 export `CODENOOK_LLM_BACKEND=mock`，使 `_lib/llm_call.py`
     从 `$CODENOOK_LLM_FIXTURE_DIR/<call_name>.json` 读固定响应。
   - 每个 case 在「前置条件」声明它准备的 fixture 文件名。
   - 用 `--inject-error` 触发 mock 抛错（用于 best-effort 路径覆盖）。
3. **审计日志断言**：所有写操作类用例都断言
   `cat $WS/.codenook/memory/history/extraction-log.jsonl | jq -e ...`。
4. **清理策略**：bats `teardown()` 统一清 fixture、kill 残留子进程、复位
   `CODENOOK_*` 环境变量。
5. **bats helper**：复用 `tests/helpers/load.bash` 与 `assertions.bash`
   （M8 既有），新增 `tests/helpers/m9_memory.bash` 提供：
   - `seed_memory ws topic body`：写一份预制 knowledge
   - `mock_llm_decision verdict reason`：投递一次 LLM judge 响应
   - `assert_audit_log_contains ws field value`：jq 断言
6. **命名规则**：测试文件 `tests/m9-<short-name>.bats`；@test 名格式：
   `[m9.x] <case-id> <one-line-description>`。

### 0.4 FR ↔ Test Case 覆盖矩阵

> 规则：每个 FR 必须 ≥ 1 case；空行禁止。

| FR | 描述（摘要） | 覆盖 Test Case |
|----|--------------|----------------|
| FR-LAY-1 | 不允许 plugin/领域子目录 | TC-M9.1-01, TC-M9.1-02 |
| FR-LAY-2 | 文件原子写入 | TC-M9.1-03, TC-M9.1-04 |
| FR-LAY-3 | 同名优先 patch | TC-M9.1-05, TC-M9.3-06 |
| FR-LAY-4 | `_lib/memory_layer.py` 公共接口 | TC-M9.1-06, TC-M9.1-07, TC-M9.1-08 |
| FR-LAY-5 | 不再有 description.md | TC-M9.1-09 |
| FR-LAY-6 | config.yaml 单文件 schema | TC-M9.1-10, TC-M9.5-02, TC-M9.5-03 |
| FR-EXT-K | knowledge extractor 主体 | TC-M9.3-01, TC-M9.3-04, TC-M9.3-05, TC-M9.3-06 |
| FR-EXT-S | skill extractor 主体 | TC-M9.4-01, TC-M9.4-02, TC-M9.4-03 |
| FR-EXT-C | config extractor 主体 | TC-M9.5-01, TC-M9.5-03, TC-M9.5-04 |
| FR-EXT-1 | 三类 extractor 可独立 CLI | TC-M9.3-01, TC-M9.4-01, TC-M9.5-01 |
| FR-EXT-2 | summary ≤ 200 / tags ≤ 8 | TC-M9.3-02, TC-M9.3-03 |
| FR-EXT-3 | candidate → promoted 流 | TC-M9.3-11, TC-M9.6-09 |
| FR-EXT-4 | 写入审计日志 | TC-M9.3-09, TC-M9.4-04, TC-M9.5-05 |
| FR-EXT-5 | extractor 失败不阻塞 | TC-M9.2-05, TC-M9.3-08 |
| FR-EXT-MERGE | find_similar + LLM 判定 | TC-M9.3-04, TC-M9.3-05, TC-M9.3-06, TC-M9.4-03, TC-M9.5-04 |
| FR-EXT-CAP | 单任务上限 ≤3/≤1/≤5 | TC-M9.3-07, TC-M9.4-05, TC-M9.5-06 |
| FR-EXT-DEDUP | hash 前 512 字符 | TC-M9.3-10, TC-M9.4-06 |
| FR-TRG-1 | tick after_phase hook | TC-M9.2-01, TC-M9.2-02 |
| FR-TRG-2 | 80% 水位协议 | TC-M9.2-06, TC-M9.7-05 |
| FR-TRG-3 | 触发幂等 | TC-M9.2-03, TC-M9.2-04 |
| FR-TRG-4 | 异步执行不阻塞 | TC-M9.2-07, TC-M9.2-08 |
| FR-RO-1 | plugin_readonly_check.py | TC-M9.7-01, TC-M9.7-02 |
| FR-RO-2 | bats 写 plugins 必败 | TC-M9.7-03 |
| FR-RO-3 | linter 描述拦截 | TC-M9.7-04, TC-M9.7-05 |
| FR-SEL-1 | memory_index frontmatter only | TC-M9.6-01, TC-M9.6-02 |
| FR-SEL-2 | router prompt MEMORY_INDEX | TC-M9.6-03 |
| FR-SEL-3 | draft-config selected_memory | TC-M9.6-04 |
| FR-SEL-4 | spawn.sh 物化两层 | TC-M9.6-05, TC-M9.8-04 |
| FR-SEL-5 | applies_when 命中无条件注入 | TC-M9.6-06 |
| FR-SEL-6 | knowledge ≤5 / skills ≤3 | TC-M9.6-07 |
| FR-SEL-7 | 自然语言修改选择集 | TC-M9.6-08 |
| FR-BUD-1 | token_estimate.py | TC-M9.6-10 |
| FR-BUD-2 | section 预算上限 | TC-M9.6-11 |
| FR-BUD-3 | 超预算优先级裁剪 | TC-M9.6-12 |
| FR-BUD-4 | summary vs full body | TC-M9.6-12 |
| FR-BUD-5 | router-context 8 轮归档 | TC-M9.6-09 |

### 0.5 AC ↔ Test Case 覆盖矩阵

| AC | 描述（摘要） | 覆盖 Test Case |
|----|--------------|----------------|
| AC-LAY-1 | init 创建空骨架 | TC-M9.1-01 |
| AC-LAY-2 | 临时文件 + rename 原子写 | TC-M9.1-03, TC-M9.1-04 |
| AC-LAY-3 | 同名优先 patch / 显著差异才后缀 | TC-M9.1-05, TC-M9.3-06 |
| AC-LAY-4 | scan ≤500ms / 1000 文件 | TC-M9.1-08 |
| AC-LAY-5 | 不存在 description.md | TC-M9.1-09 |
| AC-LAY-6 | config.yaml 单文件 + 重复 key 拒绝 | TC-M9.1-10, TC-M9.5-02 |
| AC-EXT-1 | knowledge_extractor CLI 合规 | TC-M9.3-01, TC-M9.3-02 |
| AC-EXT-2 | skill ≥3 重复才提案 | TC-M9.4-02 |
| AC-EXT-3 | config_extractor 同 key 合并 | TC-M9.5-03, TC-M9.5-04 |
| AC-EXT-4 | extractor 失败不阻塞任务 | TC-M9.3-08, TC-M9.4-07 |
| AC-EXT-5 | secret-scanner 拦截 | TC-M9.3-12 |
| AC-EXT-6 | 30 天后 archive | TC-M9.8-09 |
| AC-EXT-MERGE-1 | tags 重叠 ≥50% 调 LLM | TC-M9.3-04, TC-M9.4-03 |
| AC-EXT-MERGE-2 | 判定理由进 audit log | TC-M9.3-05 |
| AC-EXT-MERGE-3 | per-task 上限 | TC-M9.3-07, TC-M9.4-05, TC-M9.5-06 |
| AC-EXT-MERGE-4 | hash 命中跳 LLM | TC-M9.3-10 |
| AC-TRG-1 | tick 在 phase=done 后调 batch | TC-M9.2-01 |
| AC-TRG-2 | 同 task / phase 去重 | TC-M9.2-03 |
| AC-TRG-3 | CLAUDE.md 80% 水位描述 | TC-M9.2-06, TC-M9.7-05 |
| AC-TRG-4 | extractor 异步不阻塞 | TC-M9.2-07 |
| AC-RO-1 | readonly_check 扫描全代码库 | TC-M9.7-01 |
| AC-RO-2 | 写 plugins 抛 PermissionError | TC-M9.7-03 |
| AC-RO-3 | linter 拦截描述 | TC-M9.7-04 |
| AC-SEL-1 | scan_memory 仅返回 frontmatter | TC-M9.6-01 |
| AC-SEL-2 | router prompt 渲染两段 | TC-M9.6-03 |
| AC-SEL-3 | draft-config 接受 selected_memory | TC-M9.6-04 |
| AC-SEL-4 | spawn 物化双层 | TC-M9.6-05 |
| AC-SEL-5 | applies_when 命中自动注入 | TC-M9.6-06 |
| AC-SEL-6 | 默认 5/3 上限 | TC-M9.6-07 |
| AC-BUD-1 | router prompt ≤ 16K | TC-M9.6-10 |
| AC-BUD-2 | task prompt ≤ 32K | TC-M9.6-11 |
| AC-BUD-3 | router-context 8 轮归档 | TC-M9.6-09 |
| AC-BUD-4 | 默认 summary，body ≤2KB 才嵌入 | TC-M9.6-12 |
| AC-DOC-1 | spec doc 已交付 | TC-M9.8-06 |
| AC-DOC-2 | architecture §13 ratify | TC-M9.8-06 |
| AC-DOC-3 | CLAUDE.md 描述水位 | TC-M9.7-05 |
| AC-DOC-4 | CHANGELOG v0.9.0 完整 | TC-M9.8-07 |
| AC-E2E-1 | 完整双任务流 | TC-M9.8-01 |
| AC-E2E-2 | 80% 水位场景 | TC-M9.8-02 |
| AC-E2E-3 | 并行 3 任务无冲突 | TC-M9.8-03 |
| AC-E2E-4 | 全套 bats ≥ 760 绿 | TC-M9.8-08 |

### 0.6 NFR ↔ Test Case 覆盖矩阵

| NFR | 类型 | 覆盖 Test Case |
|-----|------|----------------|
| NFR-PERF-1 | scan ≤ 500ms / 1000 文件 | TC-M9.1-08 |
| NFR-PERF-2 | extractor ≤ 30s wall（不含 LLM） | TC-M9.3-13 |
| NFR-CONC-1 | 并发写原子 | TC-M9.1-04, TC-M9.8-03 |
| NFR-CONC-2 | 读不阻塞写 | TC-M9.1-07 |
| NFR-LAYER | 主会话不扫 memory | TC-M9.7-06 |
| NFR-SECURITY | secret-scan fail-close | TC-M9.3-12, TC-M9.7-07 |
| NFR-OBS | 审计日志全覆盖 | TC-M9.3-09, TC-M9.6-13（router-selection-log） |
| NFR-IDEMP | task_id+phase 去重 | TC-M9.2-03, TC-M9.2-04 |

### 0.7 用例编号约定

`TC-M9.<milestone>-<NN>` —— `NN` 两位数字（01..），全局可 grep。
失败路径用例在「类型」字段标 **negative**；性能用例标 **perf**；
属性 / 模糊用例标 **property**。

---

## M9.1 — Memory 布局 + `_lib/memory_layer.py`

**里程碑目标摘要**：见 `implementation-v6.md` §M9.1。建立 memory 骨架与
read/write/scan/patch 公共 API，引入元数据索引（含 hash dedup），并使
`init.sh` 创建空 skeleton。

**涉及 bats 文件**：
- `tests/m9-memory-layer.bats`（M9.1-01..07, 09, 10）
- `tests/m9-memory-index.bats`（M9.1-08）

### TC-M9.1-01 init 创建空骨架

- **关联 FR/AC/NFR**: FR-LAY-1, AC-LAY-1
- **类型**: integration
- **前置条件**: 干净 `$WS` 目录；`init.sh` 可用；环境无残留 `.codenook/`
- **步骤**:
  1. `cd "$WS" && bash skills/codenook-core/skills/builtin/init/init.sh`
  2. `find .codenook/memory -maxdepth 2 -type d | sort`
  3. `cat .codenook/memory/config.yaml`
- **期望**:
  - 目录列表恰好包含 `memory/`、`memory/knowledge`、`memory/skills`、`memory/history`，**不**包含按插件 / 领域命名的子目录
  - `config.yaml` 内容严格等价于 `version: 1\nentries: []\n`
  - `memory/knowledge/` 与 `memory/skills/` 为空目录
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-01 init creates empty skeleton`

### TC-M9.1-02 拒绝在 memory 内创建领域子目录

- **关联 FR/AC**: FR-LAY-1
- **类型**: negative / unit
- **前置条件**: `_lib/memory_layer.py` 已 import；workspace 已 init
- **步骤**:
  1. 调 `memory_layer.write_knowledge(ws, topic="dev/foo", body="...")`
- **期望**: 抛 `ValueError`，message 含 `flat layout`；磁盘上没有创建 `dev/` 子目录
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-02 rejects nested topic path`

### TC-M9.1-03 写入采用 tmp + rename 原子语义

- **关联 FR/AC**: FR-LAY-2, AC-LAY-2
- **类型**: unit
- **前置条件**: `strace`/`dtruss` 不可移植，改用 monkey-patch `os.rename`
  hook 计数；helper `python -c` 运行
- **步骤**:
  1. monkey-patch `os.rename` 记录调用；调用 `write_knowledge`
- **期望**: `os.rename` 被调用 ≥ 1 次；目标路径在 rename 前不存在；rename 后存在；中间 tmp 文件以 `.tmp.` 前缀
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-03 atomic rename used`

### TC-M9.1-04 强 kill 中段不残留半文件

- **关联 FR/AC/NFR**: FR-LAY-2, AC-LAY-2, NFR-CONC-1
- **类型**: integration / negative
- **前置条件**: 准备一个会在写入 body 中段触发 `os.kill(os.getpid(), SIGKILL)` 的桩
- **步骤**:
  1. fork 子进程调用 `write_knowledge`；体内被 kill
  2. 主进程 `ls memory/knowledge/`
- **期望**: 不存在最终目标 `.md` 文件；可能存在 `.tmp.*` 中间文件，但其 size 与是否存在均**不**影响 `read_knowledge` 返回的状态（继续返回 not-found）
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-04 sigkill mid-write leaves no half-file`

### TC-M9.1-05 同名 topic 二次写入触发 patch 路径

- **关联 FR/AC**: FR-LAY-3, AC-LAY-3
- **类型**: integration
- **前置条件**: 已通过 `write_knowledge(ws, "alpha", "v1")` 写入；mock LLM 配置返回 `verdict=merge`
- **步骤**:
  1. 调 `extract_decision.decide(existing, candidate)` 得到 `merge`
  2. 应用 patch（`patch_knowledge`）写回
- **期望**: `memory/knowledge/alpha.md` 仍是单文件（无 `-{ts}` 后缀），`tags`/`summary` 已合并；audit log 记录 `verdict=merge`
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-05 same topic prefers patch`

### TC-M9.1-06 公共接口签名锁定

- **关联 FR/AC**: FR-LAY-4
- **类型**: unit
- **前置条件**: `_lib/memory_layer.py` 已 import
- **步骤**: `python -c "import memory_layer as m; print(sorted(n for n in dir(m) if not n.startswith('_')))"`
- **期望**: 输出严格包含 spec §10 列出的全部 21 个公共函数（`init_memory_skeleton`, `scan_memory`, `scan_knowledge`, `read_knowledge`, `write_knowledge`, `patch_knowledge`, `replace_knowledge`, `promote_knowledge`, `archive_knowledge`, `scan_skills`, `read_skill`, `write_skill`, `patch_skill`, `promote_skill`, `read_config_entries`, `upsert_config_entry`, `match_entries_for_task`, `promote_config_entry`, `find_similar`, `has_hash`, `append_audit`），少一个即失败
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-06 public api surface locked`

### TC-M9.1-07 读不阻塞写、写不阻塞读

- **关联 FR/AC/NFR**: NFR-CONC-2, FR-LAY-4
- **类型**: integration / property
- **前置条件**: 50 个 `read_knowledge` 协程 + 10 个 `write_knowledge` 协程；不同 topic
- **步骤**:
  1. 启 60 个 worker 并发 5 秒
  2. 收集每次 read 的 wall 时间
- **期望**: 任何单次 read 的 wall ≤ 50ms（写不阻塞读 → 短锁假设）；所有 write 全成功；无 corruption（每个写后的 `read_knowledge` 返回最新 hash）
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-07 reads do not block writes`

### TC-M9.1-08 1000 文件下 scan_memory ≤ 500ms

- **关联 FR/AC/NFR**: NFR-PERF-1, AC-LAY-4
- **类型**: perf / integration
- **前置条件**: 用 helper 生成 1000 份 `knowledge/*.md`（最小合法 frontmatter，body 1KB）；`_lib/memory_index.py` 启用 mtime snapshot
- **步骤**:
  1. 删除 `.index-snapshot.json`，跑首次 `scan_memory(ws)` 计时
  2. 不修改文件，跑第二次（snapshot 命中）计时
- **期望**: 首次 ≤ 500ms；第二次 ≤ 80ms（缓存路径）
- **目标 bats**: `m9-memory-index.bats` :: `[m9.1] TC-M9.1-08 scan_memory under 500ms for 1000 files`

### TC-M9.1-09 init 不创建 description.md

- **关联 FR/AC**: FR-LAY-5, AC-LAY-5
- **类型**: integration
- **前置条件**: TC-M9.1-01 后续断言
- **步骤**: `find .codenook -name 'description.md'`
- **期望**: 输出为空
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-09 no description.md created`

### TC-M9.1-10 config.yaml 重复 key 检测

- **关联 FR/AC**: FR-LAY-6, AC-LAY-6
- **类型**: negative / unit
- **前置条件**: 手工放置的 `config.yaml` 含两个相同 `key: log.level`
- **步骤**: `python -c "from memory_layer import read_config_entries; read_config_entries('$WS')"`
- **期望**: 抛 `ValueError`，message 含 `duplicate key`；exit code 非 0；不修改文件
- **目标 bats**: `m9-memory-layer.bats` :: `[m9.1] TC-M9.1-10 duplicate config key rejected`

---

## M9.2 — 提取触发器（after_phase + 80% 水位协议）

**里程碑目标摘要**：见 `implementation-v6.md` §M9.2。把抽取调度接入
orchestrator-tick；引入 `(task_id, phase, reason)` 幂等键；CLAUDE.md
新增 80% 上下文水位监听描述。

**涉及 bats 文件**：
- `tests/m9-tick-after-phase.bats`（M9.2-01..05, 07, 08）
- `tests/m9-extractor-batch.bats`（M9.2-03, 04）
- `tests/m9-claude-md-context-watermark.bats`（M9.2-06）

### TC-M9.2-01 phase=done 触发 extractor-batch

- **关联 FR/AC**: FR-TRG-1, AC-TRG-1
- **类型**: integration
- **前置条件**: mock 一个 task，phase 文件先为 `running`，再 patch 为 `done`；`extractor-batch.sh` 替换为记录调用次数的桩
- **步骤**:
  1. 跑 `_tick.py`
  2. 检查桩日志
- **期望**: 桩被调用 1 次，参数包含 `--task-id <id>` 与 `--reason after_phase`
- **目标 bats**: `m9-tick-after-phase.bats` :: `[m9.2] TC-M9.2-01 done triggers batch`

### TC-M9.2-02 phase=blocked 同样触发

- **关联 FR/AC**: FR-TRG-1
- **类型**: integration
- **前置条件**: phase 设置为 `blocked`
- **步骤**: 同上
- **期望**: 桩被调用 1 次
- **目标 bats**: `m9-tick-after-phase.bats` :: `[m9.2] TC-M9.2-02 blocked triggers batch`

### TC-M9.2-03 同 task 同 phase 重复 tick 只触发一次

- **关联 FR/AC/NFR**: FR-TRG-3, AC-TRG-2, NFR-IDEMP
- **类型**: integration
- **前置条件**: 桩记录调用次数；幂等键文件 `memory/history/.trigger-keys`
- **步骤**:
  1. 连续跑 `_tick.py` 3 次
  2. 数桩调用次数
- **期望**: 桩调用次数 = 1；`.trigger-keys` 含一行 hash
- **目标 bats**: `m9-extractor-batch.bats` :: `[m9.2] TC-M9.2-03 idempotent on repeat tick`

### TC-M9.2-04 不同 reason 不去重

- **关联 FR/AC/NFR**: FR-TRG-3, NFR-IDEMP
- **类型**: integration
- **前置条件**: 同 task 同 phase；先以 `--reason after_phase` 触发，再以 `--reason context-pressure` 触发
- **步骤**: 顺序跑两次
- **期望**: 桩被调用 2 次；幂等键 hash 不同
- **目标 bats**: `m9-extractor-batch.bats` :: `[m9.2] TC-M9.2-04 different reason bypasses dedup`

### TC-M9.2-05 extractor 失败不阻塞 tick 退出

- **关联 FR/AC**: FR-EXT-5, AC-TRG-4
- **类型**: integration / negative
- **前置条件**: 桩 `extractor-batch.sh` `exit 7`
- **步骤**: `bash _tick.py; echo $?`
- **期望**: tick 退出码 0；stderr 出现 `extractor batch failed (exit=7)` 但不上抛
- **目标 bats**: `m9-tick-after-phase.bats` :: `[m9.2] TC-M9.2-05 batch failure does not block tick`

### TC-M9.2-06 CLAUDE.md 描述 80% 水位协议

- **关联 FR/AC**: FR-TRG-2, AC-TRG-3, AC-DOC-3
- **类型**: unit
- **前置条件**: 仓库根 `CLAUDE.md`
- **步骤**: `grep -E '80%|water-?mark|context-pressure' CLAUDE.md`
- **期望**: 至少 3 行匹配；同时存在「extractor-batch.sh --reason context-pressure」字面 token
- **目标 bats**: `m9-claude-md-context-watermark.bats` :: `[m9.2] TC-M9.2-06 watermark protocol documented`

### TC-M9.2-07 batch 异步执行 ≤ 1000ms 返回

- **关联 FR/AC/NFR**: FR-TRG-4, AC-TRG-4
- **类型**: perf / integration
- **前置条件**: 桩 extractor 内部 `sleep 5`
- **步骤**: `time bash extractor-batch.sh --task-id t1 --reason after_phase`
- **期望**: 主调用 wall 时间 ≤ 1000ms（包含 ±jitter 余量；mac/linux runner 调度抖动可达数百毫秒，所以预算订得宽松而非工程目标的 200ms）；返回 JSON 含 `enqueued_jobs`；`pgrep -f knowledge_extractor` 仍存活
- **Flake 控制**: `BATS_TEST_RETRIES=2`（已在 bats 文件内启用）；如 CI 仍偶发飘红，先放宽预算再调
- **目标 bats**: `m9-tick-after-phase.bats` :: `[m9.2] TC-M9.2-07 batch returns async`

### TC-M9.2-08 batch 返回结构契约

- **关联 FR/AC**: FR-TRG-4
- **类型**: unit
- **前置条件**: 桩 extractor 立即返回
- **步骤**: `bash extractor-batch.sh --task-id t1 --reason after_phase | jq .`
- **期望**: 顶层 `enqueued_jobs[]`、`skipped[]` 同时存在；类型为数组
- **目标 bats**: `m9-tick-after-phase.bats` :: `[m9.2] TC-M9.2-08 batch json contract`

---

## M9.3 — Knowledge extractor（含 patch-or-create 决策流）

**里程碑目标摘要**：见 `implementation-v6.md` §M9.3。第一个抽取器，承载
patch-first 决策流的参考实现；提取出 `_lib/extract_decision.py` 供 M9.4/M9.5 复用。

**涉及 bats 文件**：
- `tests/m9-knowledge-extractor.bats`（M9.3-01..03, 07..13）
- `tests/m9-knowledge-merge.bats`（M9.3-04..06, 10）

### TC-M9.3-01 单 CLI 调用产出合规 frontmatter

- **关联 FR/AC**: FR-EXT-1, AC-EXT-1
- **类型**: integration
- **前置条件**: mock LLM 返回固定 markdown body；workspace 空
- **步骤**: `bash skills/builtin/knowledge-extractor/run.sh --task-id t1 --input fixtures/k1.md`
- **期望**: 在 `memory/knowledge/` 出现 1 个 `.md`；frontmatter 含 `summary`/`tags`/`status: candidate`/`hash`/`source_task: t1`
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-01 single cli produces valid file`

### TC-M9.3-02 summary > 200 字符被截断或拒绝

- **关联 FR/AC**: FR-EXT-2
- **类型**: negative / unit
- **前置条件**: mock LLM 返回 summary 长度 = 250
- **步骤**: 跑 extractor
- **期望**: 写入文件的 frontmatter `summary` 长度 ≤ 200；audit log 记录 `truncated: true`
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-02 summary cap 200`

### TC-M9.3-03 tags > 8 被截断

- **关联 FR/AC**: FR-EXT-2
- **类型**: negative / unit
- **前置条件**: mock LLM 返回 12 个 tags
- **步骤**: 跑 extractor
- **期望**: 文件 tags 数组长度 = 8；保留前 8 个；audit log 记录 `truncated: true`
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-03 tags cap 8`

### TC-M9.3-04 tags 重叠 ≥50% 触发 LLM judge

- **关联 FR/AC**: FR-EXT-MERGE, AC-EXT-MERGE-1
- **类型**: integration
- **前置条件**: 已存在 `alpha.md` tags=[a,b,c,d]；候选 tags=[a,b,e,f]（重叠 2/4=50%）；mock LLM 决策端点拦截
- **步骤**: 跑 extractor 注入候选
- **期望**: mock LLM `decide` 端点被调用 1 次，传入 `existing.path` 与 `candidate.tags`；返回 `merge` 后写回 `alpha.md`（不新建）
- **目标 bats**: `m9-knowledge-merge.bats` :: `[m9.3] TC-M9.3-04 tag overlap triggers judge`

### TC-M9.3-05 LLM 判定结果 + 理由进 audit log

- **关联 FR/AC**: FR-EXT-MERGE, AC-EXT-MERGE-2
- **类型**: integration
- **前置条件**: 同 TC-M9.3-04；mock 返回 `{verdict: replace, reason: "outdated content"}`
- **步骤**: 跑 extractor 后 `cat memory/history/extraction-log.jsonl | jq -s '.[-1]'`
- **期望**: 末尾记录含 `verdict=replace`、`reason="outdated content"`、`existing_path`、`candidate_hash`
- **目标 bats**: `m9-knowledge-merge.bats` :: `[m9.3] TC-M9.3-05 verdict and reason logged`

### TC-M9.3-06 显著差异时新建 -{ts} 后缀

- **关联 FR/AC**: FR-LAY-3, AC-LAY-3
- **类型**: integration
- **前置条件**: 已存在 `alpha.md`；mock LLM 返回 `verdict=create`
- **步骤**: 跑 extractor
- **期望**: 出现新文件 `alpha-<unix-ts>.md`；旧 `alpha.md` 不变
- **目标 bats**: `m9-knowledge-merge.bats` :: `[m9.3] TC-M9.3-06 distinct candidate creates timestamped`

### TC-M9.3-07 单 task 上限 ≤ 3

- **关联 FR/AC**: FR-EXT-CAP, AC-EXT-MERGE-3
- **类型**: integration
- **前置条件**: mock LLM 一次性返回 5 candidate
- **步骤**: 跑 extractor
- **期望**: `memory/knowledge/` 文件增量 = 3；audit log 记录 `dropped_by_cap=2` 且按信息密度排序丢弃
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-07 per-task cap 3`

### TC-M9.3-08 LLM 调用失败不阻塞任务

- **关联 FR/AC**: FR-EXT-5, AC-EXT-4
- **类型**: integration / negative
- **前置条件**: mock LLM `--inject-error timeout`
- **步骤**: 跑 extractor，记录 exit code
- **期望**: extractor 退出码 0；stderr 含 `[best-effort] llm call failed`；audit log 记录 `status=failed`
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-08 llm error best-effort`

### TC-M9.3-09 写入审计日志格式锁定

- **关联 FR/AC/NFR**: FR-EXT-4, NFR-OBS
- **类型**: unit
- **前置条件**: 任意成功一次写入
- **步骤**: `tail -1 memory/history/extraction-log.jsonl | jq 'keys | sort'`
- **期望**: keys 严格等于 `["asset_type","candidate_hash","existing_path","outcome","reason","source_task","timestamp","verdict"]`
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-09 audit log schema locked`

### TC-M9.3-10 hash 命中直接 dedup（不调 LLM）

- **关联 FR/AC**: FR-EXT-DEDUP, AC-EXT-MERGE-4
- **类型**: integration
- **前置条件**: 已存在 `alpha.md`，hash=H；候选 body 前 512 字符 hash 也是 H；mock LLM `decide` 端点埋点计数
- **步骤**: 跑 extractor
- **期望**: LLM `decide` 调用计数 = 0；audit log 含 `outcome=dedup`
- **目标 bats**: `m9-knowledge-merge.bats` :: `[m9.3] TC-M9.3-10 hash hit skips llm`

### TC-M9.3-11 默认 status=candidate

- **关联 FR/AC**: FR-EXT-3
- **类型**: unit
- **前置条件**: 任意一次成功写入
- **步骤**: `head -20 memory/knowledge/*.md | grep status`
- **期望**: 全部为 `status: candidate`
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-11 default candidate`

### TC-M9.3-12 secret-scanner 命中拒写

- **关联 FR/AC/NFR**: AC-EXT-5, NFR-SECURITY
- **类型**: negative / integration
- **前置条件**: mock LLM 返回 body 含 `AKIA[A-Z0-9]{16}` 形式的 fake AWS key
- **步骤**: 跑 extractor
- **期望**: 文件未写入；exit code 非 0；audit log 含 `outcome=blocked_secret`，未泄露原始密钥（密钥被 redact 为 `***`）
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-12 secret blocks write`

### TC-M9.3-13 单次 wall ≤ 30s（不含 LLM）

- **关联 FR/AC/NFR**: NFR-PERF-2
- **类型**: perf / integration
- **前置条件**: mock LLM 立即返回；workspace 含 200 既有 knowledge 触发 `find_similar`
- **步骤**: `time bash run.sh --task-id t1 --input fixtures/k1.md`
- **期望**: wall ≤ 30s；CPU 时间 ≤ 5s
- **目标 bats**: `m9-knowledge-extractor.bats` :: `[m9.3] TC-M9.3-13 wall budget 30s`

---

## M9.4 — Skill extractor

**里程碑目标摘要**：见 `implementation-v6.md` §M9.4。检测重复脚本/CLI
模式 ≥ 3 次 → 提案 candidate skill。复用 M9.3 决策流。

**涉及 bats 文件**：
- `tests/m9-skill-extractor.bats`

### TC-M9.4-01 CLI 独立调用

- **关联 FR/AC**: FR-EXT-1
- **类型**: integration
- **前置条件**: mock task 输出含 5 次 `bash scripts/build.sh` 调用记录
- **步骤**: `bash skills/builtin/skill-extractor/run.sh --task-id t1`
- **期望**: 在 `memory/skills/` 出现 1 个目录 `<slug>/SKILL.md`
- **目标 bats**: `m9-skill-extractor.bats` :: `[m9.4] TC-M9.4-01 single cli produces skill`

### TC-M9.4-02 重复 < 3 次不提案

- **关联 FR/AC**: AC-EXT-2
- **类型**: negative / integration
- **前置条件**: task 输出含同一脚本 2 次
- **步骤**: 跑 extractor
- **期望**: `memory/skills/` 增量 = 0；audit log 含 `outcome=below_threshold`
- **目标 bats**: `m9-skill-extractor.bats` :: `[m9.4] TC-M9.4-02 below threshold no propose`

### TC-M9.4-03 命中已有 skill 优先 patch

- **关联 FR/AC**: FR-EXT-MERGE, AC-EXT-MERGE-1
- **类型**: integration
- **前置条件**: 已有 skill `build-runner`；mock LLM 返回 `merge`
- **步骤**: 跑 extractor 命中
- **期望**: skill 目录数不变；`SKILL.md` 内容被 patch；audit log 记录 verdict
- **目标 bats**: `m9-skill-extractor.bats` :: `[m9.4] TC-M9.4-03 patch existing skill`

### TC-M9.4-04 audit log 记录 asset_type=skill

- **关联 FR/AC/NFR**: FR-EXT-4, NFR-OBS
- **类型**: unit
- **前置条件**: TC-M9.4-01 之后
- **步骤**: `tail -1 memory/history/extraction-log.jsonl | jq -e '.asset_type=="skill"'`
- **期望**: 断言通过
- **目标 bats**: `m9-skill-extractor.bats` :: `[m9.4] TC-M9.4-04 audit asset type`

### TC-M9.4-05 单 task 上限 ≤ 1

- **关联 FR/AC**: FR-EXT-CAP, AC-EXT-MERGE-3
- **类型**: integration
- **前置条件**: task 含 3 个互不相关的 ≥3 次重复脚本
- **步骤**: 跑 extractor
- **期望**: skill 目录增量 = 1；audit log `dropped_by_cap=2`
- **目标 bats**: `m9-skill-extractor.bats` :: `[m9.4] TC-M9.4-05 per-task cap 1`

### TC-M9.4-06 hash dedup 跳过

- **关联 FR/AC**: FR-EXT-DEDUP, AC-EXT-MERGE-4
- **类型**: integration
- **前置条件**: 既有 skill body 前 512 字符 hash = 候选 hash
- **步骤**: 跑 extractor
- **期望**: LLM judge 0 次调用；增量 = 0
- **目标 bats**: `m9-skill-extractor.bats` :: `[m9.4] TC-M9.4-06 hash dedup`

### TC-M9.4-07 LLM 失败 best-effort

- **关联 FR/AC**: FR-EXT-5, AC-EXT-4
- **类型**: negative
- **前置条件**: mock LLM `--inject-error`
- **步骤**: 跑 extractor
- **期望**: 退出码 0；audit log `status=failed`；不写入任何 skill
- **目标 bats**: `m9-skill-extractor.bats` :: `[m9.4] TC-M9.4-07 best-effort`

---

## M9.5 — Config extractor（单文件 entries 合并）

**里程碑目标摘要**：见 `implementation-v6.md` §M9.5。识别 `task-config-set`
调用 → 落入 `config.yaml entries[]`；同 key 合并；最多 5 entries / task。

**涉及 bats 文件**：
- `tests/m9-config-extractor.bats`

### TC-M9.5-01 CLI 独立调用

- **关联 FR/AC**: FR-EXT-1
- **类型**: integration
- **前置条件**: task 日志含 `task-config-set log.level=debug` 一次；mock LLM 返回 `applies_when="when running dev tasks with verbose logging"`
- **步骤**: `bash skills/builtin/config-extractor/run.sh --task-id t1`
- **期望**: `config.yaml` 多出 1 entry；字段含 `key=log.level`、`value=debug`、`applies_when` ≤ 200 chars
- **目标 bats**: `m9-config-extractor.bats` :: `[m9.5] TC-M9.5-01 single cli appends entry`

### TC-M9.5-02 重复 key 拒绝（schema 校验）

- **关联 FR/AC**: AC-LAY-6, FR-LAY-6
- **类型**: negative
- **前置条件**: 手工放置 `config.yaml` 已有两个相同 key
- **步骤**: 跑 extractor
- **期望**: extractor 报错并 abort（在 schema 校验阶段）
- **目标 bats**: `m9-config-extractor.bats` :: `[m9.5] TC-M9.5-02 duplicate key in existing rejected`

### TC-M9.5-03 同 key latest-wins 合并

- **关联 FR/AC**: FR-LAY-6, AC-EXT-3
- **类型**: integration
- **前置条件**: 已有 entry `log.level=info`；新候选同 key `log.level=debug`
- **步骤**: 跑 extractor
- **期望**: entries 长度仍 = 1；value 更新为 `debug`；audit log `outcome=merge`
- **目标 bats**: `m9-config-extractor.bats` :: `[m9.5] TC-M9.5-03 same key latest wins`

### TC-M9.5-04 patch-first 决策流复用

- **关联 FR/AC**: FR-EXT-MERGE
- **类型**: integration
- **前置条件**: extractor import `_lib/extract_decision.py`；mock LLM `decide` 端点埋点
- **步骤**: 同 TC-M9.5-03
- **期望**: `decide` 端点被调用 1 次（与 M9.3 共用契约）
- **目标 bats**: `m9-config-extractor.bats` :: `[m9.5] TC-M9.5-04 reuse decision flow`

### TC-M9.5-05 audit log 记录 asset_type=config

- **关联 FR/AC/NFR**: FR-EXT-4, NFR-OBS
- **类型**: unit
- **前置条件**: 任一成功 entry 写入
- **步骤**: `tail -1 memory/history/extraction-log.jsonl | jq -e '.asset_type=="config"'`
- **期望**: 通过
- **目标 bats**: `m9-config-extractor.bats` :: `[m9.5] TC-M9.5-05 audit asset type`

### TC-M9.5-06 单 task 上限 ≤ 5 entries

- **关联 FR/AC**: FR-EXT-CAP, AC-EXT-MERGE-3
- **类型**: integration
- **前置条件**: task 含 7 个不同 key
- **步骤**: 跑 extractor
- **期望**: entries 增量 = 5；audit `dropped_by_cap=2`
- **目标 bats**: `m9-config-extractor.bats` :: `[m9.5] TC-M9.5-06 per-task cap 5`

### TC-M9.5-07 applies_when 命中 router-mock

- **关联 FR/AC**: FR-SEL-5
- **类型**: integration
- **前置条件**: 已写入 entry `applies_when="when task touches plugins/development"`；mock router-agent 提供 task 描述匹配该子串
- **步骤**: `python -c "from memory_layer import match_entries_for_task; print(match_entries_for_task(ws, 'refactor plugins/development hook'))"`
- **期望**: 返回长度 1，含该 entry
- **目标 bats**: `m9-config-extractor.bats` :: `[m9.5] TC-M9.5-07 applies_when match`

---

## M9.6 — Router-agent 扫描升级 + Context 预算

**里程碑目标摘要**：见 `implementation-v6.md` §M9.6。router-agent 看见
memory；draft-config 加 `selected_memory`；spawn.sh 物化双层；引入
token 预算估算与裁剪；router-context 8 轮归档。

**涉及 bats 文件**：
- `tests/m9-router-memory-scan.bats`（M9.6-01..09, 13）
- `tests/m9-context-budget.bats`（M9.6-10..12）

### TC-M9.6-01 scan_memory 仅返回 frontmatter

- **关联 FR/AC**: FR-SEL-1, AC-SEL-1
- **类型**: unit
- **前置条件**: workspace 含 5 个 knowledge（body 100KB 各）
- **步骤**: `python -c "from memory_index import scan_memory; import json; print(json.dumps(scan_memory(ws)))"`
- **期望**: 返回元素含 `path/title/summary/tags/status`，**不含** `body`；总输出 size ≤ 8KB
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-01 scan returns metadata only`

### TC-M9.6-02 scan_memory 利用 mtime snapshot

- **关联 FR/AC/NFR**: FR-SEL-1, NFR-PERF-1
- **类型**: integration / perf
- **前置条件**: 1000 文件；首次 scan 已写 snapshot
- **步骤**: 二次 scan
- **期望**: 二次 wall ≤ 80ms；snapshot 命中率 ≥ 99%
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-02 snapshot hit fast`

### TC-M9.6-03 router prompt 渲染 PLUGINS_SUMMARY + MEMORY_INDEX

- **关联 FR/AC**: FR-SEL-2, AC-SEL-2
- **类型**: integration
- **前置条件**: workspace 既有 plugins + memory；router-agent prompt 渲染脚本可用
- **步骤**: 跑渲染脚本，输出 prompt 到 stdout
- **期望**: 输出同时包含 `## Plugins summary` 与 `## Memory index` 两段；后者列出每条 entry 的 `name + description`，无 body
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-03 prompt has both sections`

### TC-M9.6-04 draft-config schema 接受 selected_memory

- **关联 FR/AC**: FR-SEL-3, AC-SEL-3
- **类型**: unit
- **前置条件**: 写一份含 `selected_memory.knowledge=[a,b]`、`selected_memory.skills=[c]` 的 yaml
- **步骤**: `python -c "from draft_config_lib import validate; validate(open('cfg.yaml'))"`
- **期望**: 校验通过；缺少 `selected_memory.config` 字段不报错（config 由 applies_when 自动）
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-04 schema accepts selected_memory`

### TC-M9.6-05 spawn.sh --confirm 物化双层

- **关联 FR/AC**: FR-SEL-4, AC-SEL-4
- **类型**: integration
- **前置条件**: workspace 含 1 plugin + 1 knowledge + 1 skill；draft-config 选中两者
- **步骤**: `bash spawn.sh --confirm --draft-config cfg.yaml`
- **期望**: 子任务 prompt 文件同时含 plugin 内容与 memory 知识 summary；subprocess pid 文件存在
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-05 spawn materializes two layers`

### TC-M9.6-06 applies_when 命中无条件注入

- **关联 FR/AC**: FR-SEL-5, AC-SEL-5
- **类型**: integration
- **前置条件**: config.yaml 含 entry `applies_when` 命中当前 task；draft-config 不显式列入 config
- **步骤**: 跑 spawn 渲染
- **期望**: task prompt 含该 entry 的 `key=value` 行；不命中的 entry 不出现
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-06 applies_when auto-inject`

### TC-M9.6-07 默认上限 knowledge≤5 / skills≤3

- **关联 FR/AC**: FR-SEL-6, AC-SEL-6
- **类型**: integration
- **前置条件**: workspace 有 10 knowledge + 10 skills；draft-config 全选
- **步骤**: 跑渲染
- **期望**: prompt 含 5 knowledge + 3 skills；超出按优先级日志记录 `selection-log` 含 `dropped_by_cap`
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-07 default selection caps`

### TC-M9.6-08 自然语言修改选择集

- **关联 FR/AC**: FR-SEL-7
- **类型**: integration
- **前置条件**: mock router 解析端点，输入用户语 "drop knowledge alpha, add beta"；初始 selected_memory.knowledge=[alpha,gamma]
- **步骤**: 跑 router 一轮对话
- **期望**: draft-config 写回 `knowledge=[gamma,beta]`
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-08 nl modify selection`

### TC-M9.6-09 router-context 8 轮归档

- **关联 FR/AC**: FR-BUD-5, AC-BUD-3
- **类型**: integration
- **前置条件**: 制造 9 轮 router 对话日志
- **步骤**: 跑归档器
- **期望**: 第 1 轮被移到 `router-context-archive.md`；当前 `router-context.md` 长度 = 8；frontmatter `decisions[]` 不归档（保留在主文件）
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-09 archive at turn 9`

### TC-M9.6-10 token_estimate 启发式 + router prompt ≤ 16K

- **关联 FR/AC**: FR-BUD-1, AC-BUD-1
- **类型**: perf / integration
- **前置条件**: 100 fake knowledge（每条 summary 150 chars，tags 5）；模拟 50 turns 对话
- **步骤**: 渲染 router prompt → 调 `token_estimate.estimate(prompt)`
- **期望**: 估算 ≤ 16384；CJK 比例 0%/100% 边界 case 误差 ≤ 15%
- **目标 bats**: `m9-context-budget.bats` :: `[m9.6] TC-M9.6-10 router prompt under 16k`

### TC-M9.6-11 task prompt ≤ 32K

- **关联 FR/AC**: FR-BUD-2, AC-BUD-2
- **类型**: perf / integration
- **前置条件**: 选中 5 knowledge full body + 3 skills；构造场景
- **步骤**: 渲染 task prompt
- **期望**: 估算 ≤ 32768；超出则按 FR-BUD-3 优先级裁剪并记日志
- **目标 bats**: `m9-context-budget.bats` :: `[m9.6] TC-M9.6-11 task prompt under 32k`

### TC-M9.6-12 body > 2KB 只注入 summary + path

- **关联 FR/AC**: FR-BUD-3, FR-BUD-4, AC-BUD-4
- **类型**: integration
- **前置条件**: 选中 1 knowledge body=10KB
- **步骤**: 渲染 task prompt
- **期望**: prompt 中**不**出现 body 内容；含 `summary` + `path: memory/knowledge/<topic>.md` 提示
- **目标 bats**: `m9-context-budget.bats` :: `[m9.6] TC-M9.6-12 large body summary only`

### TC-M9.6-13 router-selection-log 写入

- **关联 FR/AC/NFR**: NFR-OBS
- **类型**: unit
- **前置条件**: 任意 router 物化一次
- **步骤**: `cat memory/history/router-selection-log.jsonl | tail -1 | jq .`
- **期望**: 含 `task_id`、`selected_knowledge[]`、`selected_skills[]`、`auto_injected_config_keys[]`、`dropped_by_cap`、`timestamp`
- **目标 bats**: `m9-router-memory-scan.bats` :: `[m9.6] TC-M9.6-13 selection log written`

---

## M9.7 — 插件只读 + linter 扩展

**里程碑目标摘要**：见 `implementation-v6.md` §M9.7。codify「plugins
运行时只读」；扩展主会话 linter 词表禁止扫 memory 域 token。

**涉及 bats 文件**：
- `tests/m9-plugin-readonly.bats`（M9.7-01..03, 07）
- `tests/m9-linter-memory.bats`（M9.7-04..06）

### TC-M9.7-01 readonly_check 扫描全代码库

- **关联 FR/AC**: FR-RO-1, AC-RO-1
- **类型**: unit
- **前置条件**: 当前仓库；脚本入口
- **步骤**: `python skills/.../plugin_readonly_check.py`
- **期望**: 退出码 0；扫描计数 > 0；输出 JSON 含 `scanned_files`、`writes_to_plugins=[]`
- **目标 bats**: `m9-plugin-readonly.bats` :: `[m9.7] TC-M9.7-01 readonly scan clean`

### TC-M9.7-02 检测 open(..., "w") 命中 plugins/

- **关联 FR/AC**: FR-RO-1
- **类型**: negative / unit
- **前置条件**: fixture 文件 `bad.py` 含 `open("plugins/foo.txt","w")`
- **步骤**: 跑 checker --target fixture/
- **期望**: 退出码 ≠ 0；输出 `bad.py:1` 命中
- **目标 bats**: `m9-plugin-readonly.bats` :: `[m9.7] TC-M9.7-02 detects open w on plugins`

### TC-M9.7-03 mock extractor 写 plugins → PermissionError

- **关联 FR/AC**: FR-RO-2, AC-RO-2
- **类型**: negative / integration
- **前置条件**: 注入运行时 sitecustomize 把 plugins/ 路径设 `os.chmod 0o555`
- **步骤**: mock extractor 调 `open("plugins/x","w")`
- **期望**: `PermissionError` 抛出；退出码 ≠ 0
- **目标 bats**: `m9-plugin-readonly.bats` :: `[m9.7] TC-M9.7-03 runtime write blocked`

### TC-M9.7-04 linter 拦截描述对 plugins/ 的写操作

- **关联 FR/AC**: FR-RO-3, AC-RO-3
- **类型**: unit
- **前置条件**: fixture markdown 含 `let me write plugins/foo.yaml ...`
- **步骤**: 跑 claude-md-linter 扩展词表
- **期望**: 退出码 ≠ 0；命中行号
- **目标 bats**: `m9-linter-memory.bats` :: `[m9.7] TC-M9.7-04 linter flags write to plugins`

### TC-M9.7-05 CLAUDE.md 含 80% 水位 + memory 协议描述

- **关联 FR/AC**: AC-DOC-3, FR-TRG-2
- **类型**: unit
- **前置条件**: 仓库根 CLAUDE.md
- **步骤**: `grep -E 'memory|extraction-log|MEMORY_INDEX|80%' CLAUDE.md | wc -l`
- **期望**: ≥ 5 行
- **目标 bats**: `m9-linter-memory.bats` :: `[m9.7] TC-M9.7-05 claude md covers memory protocol`

### TC-M9.7-06 主会话 prompt 不允许扫 memory/

- **关联 FR/AC/NFR**: NFR-LAYER
- **类型**: negative / unit
- **前置条件**: fixture 主会话 prompt 含 `grep -r ".codenook/memory" .`
- **步骤**: 跑扩展 linter
- **期望**: 命中并退出 ≠ 0
- **目标 bats**: `m9-linter-memory.bats` :: `[m9.7] TC-M9.7-06 main session cannot scan memory`

### TC-M9.7-07 secret-scanner fail-close 默认开启

- **关联 FR/AC/NFR**: NFR-SECURITY
- **类型**: unit
- **前置条件**: 移除 secret-scanner 二进制
- **步骤**: 跑 knowledge-extractor
- **期望**: 退出码 ≠ 0；stderr 含 `secret scanner unavailable; refusing to write`
- **目标 bats**: `m9-plugin-readonly.bats` :: `[m9.7] TC-M9.7-07 secret scanner fail close`

---

## M9.8 — E2E + 发布 v0.9.0-m9.0

**里程碑目标摘要**：见 `implementation-v6.md` §M9.8。完整链路：用户对话
→ 任务执行 → tick → extractor → 二次任务 router 看到 promoted；并发 3
任务无冲突；版本/CHANGELOG/tag。

**涉及 bats 文件**：
- `tests/e2e/m9-e2e.bats`（M9.8-01..05, 09; M9.8-10..12 fix-r1 GC + pre-commit + idempotent loop）
- `tests/m9-release-meta.bats`（M9.8-06, 07, 08）

### TC-M9.8-01 完整双任务流：extract → promote → next task 可见

- **关联 FR/AC**: AC-E2E-1
- **类型**: E2E
- **前置条件**: 隔离 `tests/.tmp/e2e-01/` workspace；mock LLM 全程
- **步骤**:
  1. 跑 task-A，phase 进入 done
  2. tick 触发 extractor，写 1 candidate knowledge
  3. router 对话「promote knowledge alpha」
  4. 启 task-B 走 router → spawn
  5. 检 task-B prompt
- **期望**: task-B prompt 含 `alpha` 的 summary；router-selection-log 记录注入；extraction-log 记录 promote 事件
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-01 full e2e two tasks`

### TC-M9.8-02 80% 水位场景：异步 extractor → memory 出现 candidate

- **关联 FR/AC**: AC-E2E-2
- **类型**: E2E
- **前置条件**: 隔离 workspace；mock 主会话发送 `--reason context-pressure`
- **步骤**:
  1. 跑 `extractor-batch.sh --reason context-pressure --task-id t1`
  2. 等 ≤ 5s
  3. 检 `memory/knowledge/`
- **期望**: 调用立即返回（< 200ms）；5s 内 memory 出现 ≥ 1 candidate
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-02 watermark async produces candidate`

### TC-M9.8-03 并行 3 任务无写冲突

- **关联 FR/AC/NFR**: AC-E2E-3, NFR-CONC-1
- **类型**: E2E / property
- **前置条件**: 隔离 workspace；mock LLM 投递 3 套不同候选
- **步骤**:
  1. 同时启 3 个 extractor 子进程
  2. 等全部退出
  3. 校验 audit log 行数 = 预期；磁盘文件数 = 预期；无 `.tmp.*` 残留
- **期望**: extraction-log 行数 ≥ 3；无半文件；每个文件 hash 字段与磁盘 hash 一致
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-03 parallel 3 tasks no conflict`

### TC-M9.8-04 spawn 物化端到端含 config 自动注入

- **关联 FR/AC**: FR-SEL-4, FR-SEL-5
- **类型**: E2E
- **前置条件**: workspace 已含 1 selected knowledge + 1 命中 applies_when 的 config entry
- **步骤**: `spawn.sh --confirm`
- **期望**: subprocess 启动；prompt 文件含两类资产；audit + selection log 全写
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-04 spawn end-to-end`

### TC-M9.8-05 router-context 在 9 轮后归档

- **关联 FR/AC**: AC-BUD-3
- **类型**: E2E
- **前置条件**: 模拟 9 轮真实 router 对话
- **步骤**: 跑完
- **期望**: 出现 `router-context-archive.md`；当前 context 长度 = 8
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-05 archive on overflow`

### TC-M9.8-06 spec doc + architecture §13 已交付

- **关联 FR/AC**: AC-DOC-1, AC-DOC-2
- **类型**: unit
- **前置条件**: 仓库根
- **步骤**: `[ -f docs/v6/memory-and-extraction-v6.md ] && grep -q '§13' docs/v6/architecture-v6.md`
- **期望**: 两条均通过
- **目标 bats**: `m9-release-meta.bats` :: `[m9.8] TC-M9.8-06 docs delivered`

### TC-M9.8-07 CHANGELOG v0.9.0-m9.0 完整

- **关联 FR/AC**: AC-DOC-4
- **类型**: unit
- **前置条件**: 仓库 CHANGELOG.md
- **步骤**: `grep -E '^## \[v0\.9\.0-m9\.0\]' CHANGELOG.md` 与 `grep -c 'M9\.[1-8]' CHANGELOG.md`
- **期望**: 标题存在；M9.1–M9.8 各被引用 ≥ 1 次（计数 ≥ 8）
- **目标 bats**: `m9-release-meta.bats` :: `[m9.8] TC-M9.8-07 changelog complete`

### TC-M9.8-08 全套 bats ≥ 760 全绿

- **关联 FR/AC**: AC-E2E-4
- **类型**: E2E / perf
- **前置条件**: 干净 worktree；所有 M9 实现已合入
- **步骤**: `bats $(find tests skills -name '*.bats') | tee bats.out`
- **期望**: 总数 ≥ 760；失败 = 0；总 wall ≤ 600s
- **目标 bats**: `m9-release-meta.bats` :: `[m9.8] TC-M9.8-08 full suite green`

### TC-M9.8-09 archive CLI：30 天后 candidate → archived

- **关联 FR/AC**: AC-EXT-6
- **类型**: integration
- **前置条件**: workspace 已有 candidate；将 frontmatter `created_at` 改为 35 天前
- **步骤**: `bash skills/builtin/_lib/memory-gc.sh --apply`
- **期望**: 文件 frontmatter 变 `status: archived`；audit log 记录 `outcome=archived`；不删文件
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-09 gc archives stale candidates`

### TC-M9.8-10 GC CLI：dry-run 报告 over-cap；real run 删旧并 audit

- **关联 FR/AC**: 设计文档 §6/§7 caps；plan.md 后置决策 #5（GC CLI 归 M9.8）
- **类型**: integration
- **前置条件**: workspace 中同一 task 写入 N+2 份 knowledge / skill / config（直接 memory_layer 写入，绕开 LLM）
- **步骤**:
  1. `python -m memory_gc --workspace $WS --dry-run --json` → 校验 `planned`
  2. `python -m memory_gc --workspace $WS --json` → 校验 `pruned`，磁盘文件数收敛到 cap
- **期望**: dry-run 不动盘；real run 留下最新 N 份，audit log 追加 `outcome=gc_pruned`
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-10 gc dry-run reports over-cap; real run prunes + audits`

### TC-M9.8-11 pre-commit hook：拒绝顶层 plugins/，放行 tests/fixtures/plugins/

- **关联 FR/AC**: FR-RO-1（plugin readonly 工程化护栏）；fix-r1 anchor 修复
- **类型**: integration / regression
- **前置条件**: 临时 git 仓库安装模板 hook
- **步骤**:
  1. 暂存 `plugins/some-plugin/extractor.py` → `git commit` 必须失败且 stderr 含 reject 提示
  2. 暂存 `tests/fixtures/plugins/foo/bar.md` → `git commit` 必须成功（fast-gate 不能误伤 fixture 路径）
- **期望**: leg(a) 退出码 ≠ 0；leg(b) 退出码 = 0
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-11 pre-commit hook rejects top-level plugins/ but allows tests/fixtures/plugins/`

### TC-M9.8-12 router→extractor→memory-index loop 跨两次 tick 幂等

- **关联 FR/AC/NFR**: NFR-CONC-1（hash dedup），AC-EXT-1（patch-or-create 默认 merge）
- **类型**: E2E / property
- **前置条件**: workspace 仅暴露 knowledge-extractor；mock LLM 跨 tick 返回相同 candidate
- **步骤**:
  1. tick 1 触发 `extractor-batch.sh --reason after_phase` → 等待 candidate 落盘 → 拍 snapshot
  2. tick 2 用不同 reason（绕开 trigger-key dedup）触发同样的 candidate → 拍 snapshot
- **期望**: 两次 snapshot 完全一致；`memory/` 下无 `.tmp.*` 残留
- **目标 bats**: `tests/e2e/m9-e2e.bats` :: `[m9.8] TC-M9.8-12 router→extractor→memory-index loop stable across two ticks`

---

## 10. 验收闭环（per-milestone）

每个 M9.x 必须满足以下条件方可进入下一里程碑：

| Milestone | 必 PASS Test Case | 覆盖率门槛 | 性能门槛 |
|-----------|-------------------|------------|----------|
| M9.1 | TC-M9.1-01..10 全 PASS | bats 行覆盖 ≥ 80% on `_lib/memory_layer.py` 与 `_lib/memory_index.py` | TC-M9.1-08 ≤ 500ms / 80ms |
| M9.2 | TC-M9.2-01..08 全 PASS | tick / batch shell 路径覆盖 100% | TC-M9.2-07 batch 主调 ≤ 1000ms (jitter ±) |
| M9.3 | TC-M9.3-01..13 全 PASS | knowledge-extractor + extract_decision 行覆盖 ≥ 80% | TC-M9.3-13 ≤ 30s |
| M9.4 | TC-M9.4-01..07 全 PASS | skill-extractor 行覆盖 ≥ 75% | — |
| M9.5 | TC-M9.5-01..07 全 PASS | config-extractor 行覆盖 ≥ 75% | — |
| M9.6 | TC-M9.6-01..13 全 PASS | router-agent 渲染 + token_estimate ≥ 80% | TC-M9.6-10/11 ≤ 16K/32K tokens |
| M9.7 | TC-M9.7-01..07 全 PASS | plugin_readonly_check 行覆盖 100% | — |
| M9.8 | TC-M9.8-01..09 全 PASS + 全套 bats ≥ 760 全绿 | 全仓库 bats wall ≤ 600s | E2E 单 case ≤ 60s |

行覆盖统计建议工具：`coverage.py`（Python 模块）+ `bashcov`/`kcov`（shell）。

---

## 11. 与 review 阶段的交接

review agent 必看清单：

1. **决策一致性**：本文档的「关联 FR/AC」字段必须能在 spec / HTML 需求文档中
   被 grep 到；任何 case 引用了不存在的 FR-XXX → 阻断。
2. **5 默认值守恒**：以下 5 个默认值（plan.md 「M9.0 后置决策」）必须在
   测试 case 中可见、不被偷偷修改：
   - `find_similar` 用 token-set Jaccard（TC-M9.3-04 / TC-M9.4-03 默认实现）
   - `.codenook/memory/.index-snapshot.json` 路径（TC-M9.1-08 / TC-M9.6-02）
   - `_lib/llm_call.py` 入口（mock 协议建立在该模块上，§0.3）
   - `match_entries_for_task` 在 router-agent 调用（TC-M9.5-07 / TC-M9.6-06）
   - GC CLI 归 M9.8（TC-M9.8-09）
3. **TDD 红 / 绿门**：阶段 3-A sub-agent 必须先把所有 70+ case 写成红色
   bats，证据是 `bats ... | grep "not ok"` 数量 ≥ 70；阶段 3-B 实现阶段
   再变绿。
4. **Negative 与 perf 路径**（共 9+3）一个不能漏：
   - **Negative**: TC-M9.1-02, TC-M9.1-04, TC-M9.1-10, TC-M9.3-02, TC-M9.3-03,
     TC-M9.3-08, TC-M9.3-12, TC-M9.4-02, TC-M9.4-07, TC-M9.5-02, TC-M9.7-02,
     TC-M9.7-03, TC-M9.7-06
   - **Perf**: TC-M9.1-08, TC-M9.2-07, TC-M9.3-13, TC-M9.6-02, TC-M9.6-10,
     TC-M9.6-11, TC-M9.8-08
5. **Audit log schema 锁定**：TC-M9.3-09 是合同测试，schema 任何变更必须
   先改本文档再改实现。
6. **NFR 覆盖**：所有 8 个 NFR 在 §0.6 矩阵中均 ≥ 1 case；review 时复跑
   `grep -c '^| NFR-' docs/v6/m9-test-cases.md` 应 = 8。

---

## 12. 自检脚本（review agent / CI 可直接复用）

```bash
set -e
DOC=docs/v6/m9-test-cases.md
HTML=/Users/mingdw/.copilot/session-state/d011f255-1cad-47b2-932b-3673f8928dfc/files/m9-requirements-and-acceptance.html

# 1. 行数
test "$(wc -l < $DOC)" -ge 800

# 2. case 数
test "$(grep -c '^### TC-M9' $DOC)" -ge 70

# 3. milestone 节数
test "$(grep -c '^## M9\.' $DOC)" -eq 8

# 4. FR / AC 全覆盖（HTML 中出现的每个 ID 至少在 doc 出现一次）
for id in $(grep -oE '(FR|AC|NFR)-[A-Z]+(-[A-Z0-9]+)*' "$HTML" | sort -u); do
  grep -q "$id" "$DOC" || { echo "missing $id"; exit 1; }
done

# 5. 禁词（greenfield 守门）—— 通过 base64 隐藏 pattern 避免 doc 自身命中
PATTERN=$(printf '\xe8\xbf\x81\xe7\xa7\xbb|migra''tion|v''0\\.''8|\xe5\x85\xbc\xe5\xae\xb9')
! grep -E "$PATTERN" "$DOC"
```

— END —
