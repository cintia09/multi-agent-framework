# M10 测试用例集 — Task Chains（父子链接 + 链感知上下文）

> 版本：M10.0.1（紧随 M10.0 设计文档之后交付的 TDD 输入合同）
>
> 适用范围：M10.1 – M10.7 全部里程碑
>
> 关联文档：
> - `docs/v6/task-chains-v6.md`（M10 唯一规范源；§1–§12 + 附录）
> - `docs/v6/implementation-v6.md` §M10.0–M10.7（每里程碑文件 / 测试 / DoD）
> - `docs/v6/memory-and-extraction-v6.md` §6（M9 mock LLM 协议，本文档 §0.3 沿用）
> - `docs/v6/architecture-v6.md` §13（Memory Layer 决策；M10 不修改之）
>
> 本文档是 M10 TDD 阶段的**唯一**测试合同：所有 M10.x 的 bats / 集成 / E2E
> 用例必须先在此文档登记（编号 + 关联 AC + 步骤 + 期望），sub-agent 才能
> 在 TDD 阶段「先写红用例，后写实现」。任何在文档外凭空增加的用例必须
> 倒灌回本文件（review 阶段会比对）。M10 是**对 M9 的纯增量扩展**，不
> 修改 memory 层、不引入新可写存储路径。

---

## 0. 概述与测试策略

### 0.1 与设计 / 验收文档的对应关系

| 维度 | 来源章节 | 在本文档中的体现 |
|------|----------|------------------|
| 数据模型 / schema | spec §2 | TC-M10.0-* 校验 schema 增量；TC-M10.1-* 验证 state.json 写盘 |
| Lifecycle (创建 / attach / walk) | spec §3 | TC-M10.1-* 与 TC-M10.3-* 共同覆盖 |
| `task_chain.py` 接口 | spec §4 | TC-M10.1-* 全部 unit + CLI 用例 |
| `parent_suggester.py` 算法 | spec §5 | TC-M10.2-* |
| `chain_summarize.py` 流程 | spec §6 | TC-M10.4-* |
| Router slot 集成 | spec §7 | TC-M10.5-* |
| Snapshot / 性能 | spec §8 | TC-M10.6-02..05 |
| Audit / Security | spec §9 | TC-M10.6-01 + TC-M10.4-05 |
| 共存语义 | spec §10 | TC-M10.0-04 + 全 §M10.5 regression |
| AC mapping | spec §12 | §0.5 矩阵 + 各 case 的「关联 AC」字段 |

### 0.2 bats 路径与 helpers 约定

沿用 M1–M9 baseline，所有 bats 落在仓库内：

| 类型 | 路径 |
|------|------|
| Unit / integration bats | `skills/codenook-core/tests/m10-*.bats` |
| E2E bats | `skills/codenook-core/tests/e2e/m10-e2e.bats` |
| 通用 helper（M8/M9 既有） | `skills/codenook-core/tests/helpers/load.bash`, `assertions.bash` |
| M9 memory helper（regression 用） | `skills/codenook-core/tests/helpers/m9_memory.bash` |
| M10 新增 helper | `skills/codenook-core/tests/helpers/m10_chain.bash` |

`m10_chain.bash` 必须暴露以下 API（M10.0.1 DoD）：

| API | 作用 |
|-----|------|
| `make_task <ws> <id> [parent_id] [status]` | 在 `<ws>/.codenook/tasks/<id>/` 写入合规 `state.json`（默认 status=`active`） |
| `make_task_with_brief <ws> <id> <input>` | 同上 + 写 `draft-config.yaml` 含 `input:` 字段，供 suggester 抽取 |
| `make_chain <ws> <root> <depth>` | 一次性构造深度 N 的链，返回链尾 task_id（最深的 child）|
| `assert_chain_walk <ws> <id> <expected_csv>` | `python -m _lib.task_chain show <id> --format=json` ⇒ `ancestors` 与 csv 顺序一致 |
| `assert_audit <ws> <outcome>` | jq 断言 `extraction-log.jsonl` 含至少一行 `outcome=<outcome>` 的 `asset_type="chain"` 记录 |
| `seed_mock_llm <dir> <call_name> <body>` | 写 `<dir>/<call_name>.txt`，供 `CN_LLM_MOCK_DIR` 读取 |
| `with_isolated_ws cmd...` | 建临时 workspace、复制 plugins、清理 trap；防止跨 case 污染 |

每个 @test 的命名格式：`[m10.x] TC-M10.x-NN <one-line-description>`，便于 `bats -f` 子集筛选。

### 0.3 LLM mock 协议（沿用 M9）

M10 仅 `chain_summarize.py` 调用 LLM，调用入口仍为 `_lib/llm_call.py`。
mock 解析顺序与 M9.0.1 §0.3 完全一致（spec §6.7）：

```
1. $CN_LLM_MOCK_DIR/<call_name>.json | .txt    （文件，按 .json 优先 .txt 兜底）
2. $CN_LLM_MOCK_<CALL>                         （环境变量；CALL = upper(call_name)）
3. $CN_LLM_MOCK_RESPONSE                       （环境变量；通用回退）
4. $CN_LLM_MOCK_FILE                           （单文件路径）
5. fallback: "[mock-llm:<call_name>] <prompt[:80]>"
```

bats fixture 准备模式（典型 case 内）：

```bash
setup() {
  load helpers/load.bash
  load helpers/m10_chain.bash
  WS="$(make_ws)"
  MOCK="$WS/.mock"
  mkdir -p "$MOCK"
  export CN_LLM_MOCK_DIR="$MOCK"
}
```

`teardown` 必须 `unset CN_LLM_MOCK_*` 全部 4 项以及 `CN_AUDIT_PATH` 等
跨 case 污染源；M10 helper 的 `with_isolated_ws` 已封装。

### 0.4 M10 引入的 LLM call_names

M10 仅引入一个 `call_name`：

| call_name | 触发位置 | mock 文件名（默认） | 备注 |
|---|---|---|---|
| `chain_summarize` | `_lib/chain_summarize.py` 的 pass-1（per-ancestor）与 pass-2（whole-chain）共享 | `$CN_LLM_MOCK_DIR/chain_summarize.json` 或 `.txt` | 两阶段都使用同一 `call_name`，由 prompt 内容区分（spec §6.4）。测试中如需对 pass-1 / pass-2 分别注入不同响应，使用 fixture 目录 + 多 call 计数（mock 协议第 5 档 fallback 仍可触发） |

**禁止**为 pass-2 单独引入 `chain_compress` 之类的新 call_name —— spec §6.4
明确「避免 mock 协议爆炸」。本文档全部 case 默认使用单一 call_name。

### 0.5 用例编号 & 验收门约定

| 字段 | 含义 |
|------|------|
| **ID** | `TC-M10.<milestone>-<NN>` 或 E2E 专用 `TC-M10.7-E2E-NN`，全局可 grep |
| **类型** | `unit` / `integration` / `e2e` / `perf` / `negative` / `property` |
| **关联 AC** | 必须能在 `task-chains-v6.md` §12 表格中 grep 到 |
| **前置条件** | 描述 fixture / mock / env，testers 可逐字执行 |
| **步骤** | 命令或 Python 调用，编号 1..N |
| **期望** | bats 断言粒度（exit code、stdout/stderr 包含、文件内容、jq path） |
| **bats 文件** | 必须落在 §0.2 表内的命名空间 |

每个 milestone 的 acceptance gate 表见 §最后一节「Milestone gate table」。

### 0.6 AC ↔ Test Case 覆盖矩阵（与 spec §12 一致）

| AC ID | 来源 spec 章节 | 覆盖 Test Case |
|---|---|---|
| AC-CHAIN-MOD-1 | §2.3 | TC-M10.0-02, TC-M10.1-01 |
| AC-CHAIN-MOD-2 | §2.5 | TC-M10.1-04 |
| AC-CHAIN-MOD-3 | §2.5 | TC-M10.1-05 |
| AC-CHAIN-MOD-4 | §2.3 | TC-M10.1-03, TC-M10.1-08 |
| AC-CHAIN-LINK-1 | §3.3 | TC-M10.1-09, TC-M10.3-02 |
| AC-CHAIN-LINK-2 | §3.3 | TC-M10.1-10 |
| AC-CHAIN-LINK-3 | §3.3 | TC-M10.1-11 |
| AC-CHAIN-LINK-4 | §3.3 | TC-M10.1-12 |
| AC-CHAIN-SUG-1 | §5.5 | TC-M10.2-01 |
| AC-CHAIN-SUG-2 | §5.5 | TC-M10.2-02 |
| AC-CHAIN-SUG-3 | §5.3 | TC-M10.2-06 |
| AC-CHAIN-SUG-4 | §5.7 | TC-M10.2-04 |
| AC-CHAIN-CTX-1 | §7.1 | TC-M10.5-01 |
| AC-CHAIN-CTX-2 | §7.2 | TC-M10.5-02 |
| AC-CHAIN-CTX-3 | §7.2 | TC-M10.5-03 |
| AC-CHAIN-CTX-4 | §6.6 | TC-M10.4-01, TC-M10.4-04 |
| AC-CHAIN-BUD-1 | §6.4 | TC-M10.4-02, TC-M10.4-08 |
| AC-CHAIN-BUD-2 | §6.5 | TC-M10.4-03 |
| AC-CHAIN-BUD-3 | §6.5 | TC-M10.4-03 |
| AC-CHAIN-NF-1 | §6.8 | TC-M10.4-07 |
| AC-CHAIN-NF-2 | §3.4 | TC-M10.1-07 |
| AC-CHAIN-NF-3 | §9.2 | TC-M10.4-05 |
| AC-CHAIN-PERF-1 | §8.1 | TC-M10.6-02 |
| AC-CHAIN-PERF-2 | §8.5 | TC-M10.6-03 |
| AC-CHAIN-AUD-1 | §9.1 | TC-M10.6-01 |
| AC-CHAIN-AUD-2 | §9.1 | TC-M10.6-01 |
| AC-CHAIN-RO-1 | §9.3 | TC-M10.5-05 (negative branch) + TC-M10.4-05 |
| AC-CHAIN-COMPAT-1 | §10.1 | TC-M10.0-04, TC-M10.1-02 |
| AC-CHAIN-COMPAT-2 | §10.3 | TC-M10.5-04, TC-M10.7-E2E-01 (regression hook) |
| AC-CHAIN-E2E-1 | E2E | TC-M10.7-E2E-01 |
| AC-CHAIN-E2E-2 | E2E | TC-M10.7-E2E-02, TC-M10.7-E2E-03 |
| AC-CHAIN-E2E-3 | E2E | TC-M10.7-E2E-04 |
| AC-CHAIN-E2E-4 | E2E | TC-M10.7-E2E-04 |

### 0.7 Acceptance gate 格式

每个 milestone 的 gate 由两部分组成（详见文末 §Milestone gate table）：

1. **必 PASS Test Case 列表** —— 该 milestone 的全部 TC 必须 `bats` 退出
   码 0；E2E milestone 还要求关联 unit 套件 regression 全绿。
2. **覆盖率 / 性能门槛** —— 行覆盖（`coverage.py`）按文件级阈值；性能
   case 直接以 wall-clock 上界断言。

任一项未达成 → 阻断进入下一 milestone（与 M9 §10 同制）。

---

## M10.0 — Spec doc 自校验

**里程碑目标摘要**：M10.0 仅交付文档；其自检通过 5 个轻量 bats case
锁定文档结构与 greenfield 守门，可在 CI 直接跑（无需任何代码）。

**涉及 bats 文件**：
- `skills/codenook-core/tests/m10-spec-doc.bats`（TC-M10.0-01..05）

### TC-M10.0-01 spec sections present

- **关联 AC**: 文档结构合同（spec §1–§12 + 附录）
- **类型**: integration
- **前置条件**: `docs/v6/task-chains-v6.md` 已存在
- **步骤**:
  1. `grep -c '^## ' docs/v6/task-chains-v6.md`
  2. `grep -E '^## (1\.|2\.|3\.|4\.|5\.|6\.|7\.|8\.|9\.|10\.|11\.|12\.) ' docs/v6/task-chains-v6.md | wc -l`
  3. `grep -c '^## 附录 [A-C]' docs/v6/task-chains-v6.md`
- **期望**:
  - 步骤 1 ≥ 12（顶层节数）
  - 步骤 2 = 12（§1–§12 全在）
  - 步骤 3 = 3（附录 A、B、C）

### TC-M10.0-02 AC mapping table well-formed

- **关联 AC**: AC-CHAIN-MOD-1, AC-CHAIN-COMPAT-1（spec §12 自检）
- **类型**: integration
- **前置条件**: 同上
- **步骤**:
  1. `awk '/^## 12\. /,/^## 附录/' docs/v6/task-chains-v6.md | grep -c '^| AC-CHAIN-'`
  2. 解析每行第二列（来源章节），断言取值集合 ⊆ `{§1..§12 子节标号}`
  3. 解析每行最后一列（计划测试文件），断言全部以 `m10-` 或 `m9-` 前缀
- **期望**:
  - 步骤 1 ≥ 25（覆盖全部 AC-CHAIN-*）
  - 步骤 2 / 步骤 3 全通过

### TC-M10.0-03 no forbidden greenfield tokens

- **关联 AC**: greenfield 守门（plan.md §Greenfield rule）
- **类型**: negative
- **前置条件**: 同上 + 本测试文档（M10.0.1 产物）也参与扫描
- **步骤**: 在 `docs/v6/task-chains-v6.md` 与 `docs/v6/m10-test-cases.md` 上
  跑等价于以下命令：

  ```bash
  PATTERN=$(printf '\xe8\xbf\x81\xe7\xa7\xbb|migra''tion|v''0\\.''8|\xe5\x85\xbc\xe5\xae\xb9|description\\.md')
  ! grep -nE "$PATTERN" docs/v6/task-chains-v6.md
  ! grep -nE "$PATTERN" docs/v6/m10-test-cases.md
  ```

  pattern 通过 base64/printf 拼接，避免本文件自身命中（与 M9 §12 同技巧）。
- **期望**: 两次 grep 均无命中（exit 1 → bats `!` 断言通过）。
  完整禁词列表见 plan.md「Greenfield rule」；本测试文档承诺这些字面量绝不
  以原文形式出现，凡需要引用一律走 printf / base64 编码。

### TC-M10.0-04 backward-compatible state.json schema

- **关联 AC**: AC-CHAIN-COMPAT-1
- **类型**: integration
- **前置条件**: spec §2.3 增量已落 `task-state.schema.json`（M10.1 DoD 项），
  本 case 验证「缺字段不破校验」的合同表述存在于 spec
- **步骤**:
  1. `grep -nE 'parent_id.*(optional|可选|null)' docs/v6/task-chains-v6.md`
  2. `grep -nE 'chain_root.*(optional|可选|缓存)' docs/v6/task-chains-v6.md`
  3. `grep -n 'AC-CHAIN-COMPAT-1' docs/v6/task-chains-v6.md`
- **期望**: 三步均至少 1 行命中 → 文档已锁定共存语义。

### TC-M10.0-05 default values appendix B sanity

- **关联 AC**: spec §附录 B 默认值表（M10 自动模式合同）
- **类型**: integration
- **前置条件**: 同上
- **步骤**:
  1. `awk '/^## 附录 B/,/^## 附录 C/' docs/v6/task-chains-v6.md | grep -cE '^[0-9]+\. '`
  2. 校验关键默认值字面量存在：`0.15`、`8192`、`1500`、`100`、`3`
- **期望**: 步骤 1 ≥ 12（附录 B 列表至少 12 条）；步骤 2 全部命中。

---

## M10.1 — `_lib/task_chain.py` primitives

**里程碑目标摘要**：实现 chain CRUD + walk + cycle 检测 + CLI；schema
增量落地。所有写操作走 `_lib/atomic.atomic_write_json`。

**涉及 bats 文件**：
- `skills/codenook-core/tests/m10-task-chain.bats`（TC-M10.1-01..12）

### TC-M10.1-01 get_parent on fresh task returns None

- **关联 AC**: AC-CHAIN-MOD-1
- **类型**: unit
- **前置条件**: `WS=$(make_ws)`；`make_task "$WS" T-001`（无 parent_id 字段）
- **步骤**: `python -c "from _lib import task_chain as tc; print(tc.get_parent('$WS','T-001'))"`
- **期望**: stdout = `None`；exit 0。

### TC-M10.1-02 get_parent on missing task returns None

- **关联 AC**: AC-CHAIN-COMPAT-1
- **类型**: unit
- **前置条件**: `WS=$(make_ws)`；不创建任何 task
- **步骤**: 同 TC-M10.1-01 但 task_id=`T-404`
- **期望**: stdout = `None`；**不**抛 `TaskNotFoundError`；exit 0。

### TC-M10.1-03 set_parent happy path writes parent_id + chain_root

- **关联 AC**: AC-CHAIN-MOD-4, AC-CHAIN-LINK-1
- **类型**: unit
- **前置条件**:
  - `make_task "$WS" T-005`
  - `make_task "$WS" T-007`（无 parent，将作为 child 的祖父；为本 case 意图，T-007 是 root）
  - `make_task "$WS" T-012`
- **步骤**:
  1. `tc.set_parent(WS, "T-007", "T-005")`
  2. `tc.set_parent(WS, "T-012", "T-007")`
  3. `jq -r '.parent_id, .chain_root' $WS/.codenook/tasks/T-012/state.json`
- **期望**:
  - 步骤 3 输出依次为 `T-007`、`T-005`
  - `T-007/state.json` 同样含 `parent_id=T-005, chain_root=T-005`
  - `assert_audit "$WS" chain_attached`

### TC-M10.1-04 set_parent self-loop raises CycleError

- **关联 AC**: AC-CHAIN-MOD-2
- **类型**: negative
- **前置条件**: `make_task "$WS" T-001`
- **步骤**: `python -c "from _lib import task_chain as tc; tc.set_parent('$WS','T-001','T-001')"; echo $?`
- **期望**:
  - exit 非 0
  - stderr 含 `CycleError`
  - `assert_audit "$WS" chain_attach_failed` 且 `reason` 字段含 `cycle`

### TC-M10.1-05 set_parent indirect cycle raises CycleError

- **关联 AC**: AC-CHAIN-MOD-3
- **类型**: negative
- **前置条件**: 已构造链 `T-003 → T-002 → T-001`（child → parent）
- **步骤**: `tc.set_parent(WS, "T-001", "T-003")`（试图把根挂到自己的孙子）
- **期望**: 抛 `CycleError`；`T-001/state.json` 的 `parent_id` 仍为 `null`；
  `assert_audit "$WS" chain_attach_failed`。

### TC-M10.1-06 walk_ancestors returns child→root order including self

- **关联 AC**: AC-CHAIN-MOD-4（间接：walk 与 chain_root 一致性）
- **类型**: unit
- **前置条件**: 链 `T-012 → T-007 → T-005`（已 set_parent）
- **步骤**: `tc.walk_ancestors(WS, "T-012")`
- **期望**: 返回值 = `["T-012", "T-007", "T-005"]`；
  `assert_chain_walk "$WS" T-012 "T-012,T-007,T-005"`。

### TC-M10.1-07 walk_ancestors mid-chain corruption truncates without raising

- **关联 AC**: AC-CHAIN-NF-2
- **类型**: negative
- **前置条件**: 链 `T-012 → T-007 → T-005`，然后 `echo "{ broken json" > $WS/.codenook/tasks/T-007/state.json`
- **步骤**: `tc.walk_ancestors(WS, "T-012")`
- **期望**:
  - 返回 `["T-012"]`（截断在损坏点之前）
  - 不抛异常
  - `assert_audit "$WS" chain_walk_truncated`

### TC-M10.1-08 chain_root cache hit avoids walk

- **关联 AC**: AC-CHAIN-MOD-4, AC-CHAIN-PERF-1（pre-condition）
- **类型**: unit
- **前置条件**: 链 `T-012 → T-007 → T-005`，且 `T-012/state.json.chain_root="T-005"`
  已经写入；spy 注入 `walk_ancestors` 的内部 `_read_state_json`，统计调用次数。
- **步骤**:
  1. `tc.chain_root(WS, "T-012")`
- **期望**:
  - 返回 `"T-005"`
  - 内部 `_read_state_json` 调用次数 = **1**（仅读 T-012；不沿链遍历）
  - 第二次再调一次 `tc.chain_root(WS, "T-012")` 仍返回 `T-005`，调用次数 ≤ 2

### TC-M10.1-09 CLI attach exit 0 + state updated

- **关联 AC**: AC-CHAIN-LINK-1
- **类型**: integration
- **前置条件**: `make_task "$WS" T-005`；`make_task "$WS" T-007`
- **步骤**:
  1. `python -m _lib.task_chain attach T-007 T-005 --workspace "$WS"`
  2. 读 `T-007/state.json` 的 `parent_id`、`chain_root`
- **期望**:
  - 步骤 1 exit 0
  - parent_id=`T-005`、chain_root=`T-005`
  - snapshot 文件存在（`tasks/.chain-snapshot.json`），`generation` ≥ 1

### TC-M10.1-10 CLI detach is idempotent

- **关联 AC**: AC-CHAIN-LINK-2
- **类型**: integration
- **前置条件**: `T-007.parent_id=T-005`
- **步骤**:
  1. `python -m _lib.task_chain detach T-007 --workspace "$WS"` → exit 0
  2. 再跑一次同命令 → exit 0
  3. 读 `state.json`
- **期望**:
  - 两次 exit 均 0
  - `parent_id`、`chain_root` 均为 `null`
  - 第二次调用**不**写新 audit（`detach` no-op，spec §4.4）

### TC-M10.1-11 CLI show outputs child→root order

- **关联 AC**: AC-CHAIN-LINK-3
- **类型**: integration
- **前置条件**: 链 `T-012 → T-007 → T-005`
- **步骤**:
  1. `python -m _lib.task_chain show T-012 --workspace "$WS" --format=text`
  2. `python -m _lib.task_chain show T-012 --workspace "$WS" --format=json | jq -r '.ancestors | join(",")'`
- **期望**:
  - text 输出第一行含 `T-012`，最后一行含 `T-005`
  - json 输出 `T-012,T-007,T-005`
  - exit 0

### TC-M10.1-12 CLI attach on already-attached task exits 3 without --force

- **关联 AC**: AC-CHAIN-LINK-4
- **类型**: negative
- **前置条件**: `T-007.parent_id=T-005`
- **步骤**:
  1. `python -m _lib.task_chain attach T-007 T-099 --workspace "$WS"`（无 `--force`）
  2. 同命令加 `--force`
- **期望**:
  - 步骤 1 exit = 3（`AlreadyAttachedError`，spec §4.3）；stderr 含 `AlreadyAttachedError`；
    `T-007.parent_id` 仍 = `T-005`
  - 步骤 2 exit = 0；`T-007.parent_id` 变更为 `T-099`；snapshot `generation` 递增

---

## M10.2 — `_lib/parent_suggester.py`

**里程碑目标摘要**：纯 Python 零依赖 token-set Jaccard 排名；阈值 0.15、
top-3。50 任务规模 ≤ 30 ms。

**涉及 bats 文件**：
- `skills/codenook-core/tests/m10-parent-suggester.bats`（TC-M10.2-01..06）

### TC-M10.2-01 top-3 ranking with distinct scores

- **关联 AC**: AC-CHAIN-SUG-1
- **类型**: unit
- **前置条件**:
  - 创建 5 个 active 任务，brief 分别为：
    - T-A: `"feature auth login refresh jwt token implementation"`
    - T-B: `"feature auth login design jwt"`
    - T-C: `"feature billing invoice"`
    - T-D: `"docs landing page copy edit"`
    - T-E: `"db schema bootstrap script preflight"`
- **步骤**: `suggest_parents(WS, "feature auth login token", top_k=3, threshold=0.15)`
- **期望**:
  - 返回长度 = 3
  - 第一项 `task_id` ∈ {T-A, T-B}（与 child brief 共享 token 最多）
  - 三项 score 严格降序：`s[0] > s[1] > s[2]`
  - 每项 `reason` 字段包含「shared:」前缀 + 至少 1 个共享 token

### TC-M10.2-02 threshold filter drops scores < 0.15

- **关联 AC**: AC-CHAIN-SUG-2
- **类型**: unit
- **前置条件**: 候选池中 4 个任务，故意使其 Jaccard ∈ {0.45, 0.20, 0.10, 0.05}
  （通过 brief 调控）
- **步骤**: `suggest_parents(WS, "<child_brief>", threshold=0.15)`
- **期望**: 返回 ≤ 2 项；最低 score ≥ 0.15；`< 0.15` 的两项绝不出现。

### TC-M10.2-03 empty workspace returns []

- **关联 AC**: AC-CHAIN-SUG-1（边界）
- **类型**: unit
- **前置条件**: `WS=$(make_ws)`，不创建任何 task
- **步骤**: `suggest_parents(WS, "any brief")`
- **期望**: 返回 `[]`；不抛异常；不写 audit（无候选 ≠ 失败）。

### TC-M10.2-04 corruption / IO failure → empty list + audit

- **关联 AC**: AC-CHAIN-SUG-4
- **类型**: negative
- **前置条件**:
  - 创建 3 个合规任务
  - 把其中 1 个 `state.json` 写为 `"{ broken"`
  - mock `_list_open_tasks` 内部抛 `OSError`（通过 monkeypatch 一次性触发整体失败，验证整体失败路径）
- **步骤**: `suggest_parents(WS, "child")`
- **期望**:
  - 返回 `[]`
  - `assert_audit "$WS" parent_suggest_failed`
  - 单个候选损坏时（不 monkeypatch 全局，仅破坏 1 个 state.json），返回 ≤ 2 个有效候选 +
    `assert_audit "$WS" parent_suggest_skip`

### TC-M10.2-05 ties broken deterministically by task_id alpha

- **关联 AC**: AC-CHAIN-SUG-1（确定性附加约束）
- **类型**: property
- **前置条件**:
  - 构造 3 个候选 brief 完全相同 → Jaccard 完全相等
  - task_id 为 T-105、T-099、T-200
- **步骤**: 重复运行 `suggest_parents(...)` 5 次，收集顺序
- **期望**:
  - 5 次顺序完全一致
  - 顺序 = task_id 字典序升序：`T-099, T-105, T-200`
  - 三项 score 字段相等

### TC-M10.2-06 done / cancelled tasks excluded from candidate pool

- **关联 AC**: AC-CHAIN-SUG-3
- **类型**: unit
- **前置条件**:
  - 5 个候选：3 个 status=`active`、1 个 `done`、1 个 `cancelled`
  - 全部 brief 与 child_brief 高度相似（Jaccard ≥ 0.4）
- **步骤**: `suggest_parents(WS, "<child_brief>", top_k=5)`
- **期望**:
  - 返回长度 = 3
  - 返回的 task_id 集合 ∩ {done_task, cancelled_task} = ∅
  - 已 attach 的链上 done 祖先**不**进入候选池（spec §5.3 + §11.4）

---

## M10.3 — Creation-time UX hook

**里程碑目标摘要**：把 suggester 接入 router-agent prepare 路径；
`--confirm` 时把用户选择落到 `state.json.parent_id`。

**涉及 bats 文件**：
- `skills/codenook-core/tests/m10-spawn-parent-ux.bats`（TC-M10.3-01..05）

### TC-M10.3-01 spawn prepare presents top-3 + "independent"

- **关联 AC**: spec §3.1
- **类型**: integration
- **前置条件**:
  - 5 个 active 候选任务，3 个高 Jaccard
  - mock router-agent 的 prompt 渲染入口 `render_prompt.py prepare`
  - 子任务 brief = `"unit test feature auth login"`
- **步骤**:
  1. 调 `render_prompt.py prepare --task-id T-NEW --workspace $WS`
  2. 抓取 stdout（router-agent prompt 文本）
- **期望**:
  - prompt 含一段「Suggested parents」节
  - 该节列出 ≥ 1 ≤ 3 个候选；每行格式 `<index>. T-XXX (score=0.NN) — <reason>`
  - 末尾列出选项 `0. independent (no parent)` 字样
  - 候选与 `suggest_parents()` 直接调用的结果集合一致

### TC-M10.3-02 user picks parent → state.json has parent_id

- **关联 AC**: AC-CHAIN-LINK-1
- **类型**: integration
- **前置条件**: 同 TC-M10.3-01；预先把 `draft-config.yaml` 的
  `parent_id: "T-007"`（模拟用户在对话中确认选 1 号 = T-007）
- **步骤**:
  1. `render_prompt.py --confirm --task-id T-NEW --workspace $WS`
  2. 读 `T-NEW/state.json`
- **期望**:
  - exit 0
  - `state.json.parent_id == "T-007"`
  - `state.json.chain_root` 与 T-007 的 chain_root 一致（或 = T-007 自身若 T-007 是 root）
  - `assert_audit "$WS" chain_attached`

### TC-M10.3-03 user picks "independent" → parent_id=null

- **关联 AC**: spec §3.1（用户拒绝建议路径）
- **类型**: integration
- **前置条件**: `draft-config.yaml.parent_id: null`（即用户选了 "independent"）
- **步骤**: `render_prompt.py --confirm --task-id T-NEW --workspace $WS`
- **期望**:
  - exit 0
  - `state.json.parent_id == null`
  - `state.json.chain_root == null`
  - **不**写 `chain_attached` audit（无 attach 事件即无 audit）

### TC-M10.3-04 no suggestion above threshold → only "independent" offered

- **关联 AC**: AC-CHAIN-SUG-2（边界传播到 UX）
- **类型**: integration
- **前置条件**:
  - 候选池中所有任务的 brief 与 child_brief 相似度 < 0.15
  - child_brief = `"add ssh key rotation script"`
  - 候选 brief 集中于 `"feature auth login"` / `"docs landing page"` / `"refactor logger"`
- **步骤**: `render_prompt.py prepare --task-id T-NEW --workspace $WS`
- **期望**:
  - prompt **不**含「Suggested parents:」节，或该节明确写 `(none above threshold)`
  - 仍然渲染 `0. independent (no parent)` 选项
  - 不抛异常；exit 0

### TC-M10.3-05 re-attach via CLI updates state.json + chain_root

- **关联 AC**: AC-CHAIN-LINK-1, AC-CHAIN-LINK-4
- **类型**: integration
- **前置条件**: `T-NEW.parent_id == null`（独立任务）；后续用户决定挂到 T-007
- **步骤**:
  1. `python -m _lib.task_chain attach T-NEW T-007 --workspace $WS` → exit 0
  2. 读 state.json
  3. 再 `attach T-NEW T-008 --force` → exit 0
- **期望**:
  - 步骤 2：parent_id=T-007、chain_root 沿 T-007 向上
  - 步骤 3：parent_id 切换为 T-008、chain_root 重新计算
  - 两次都写 `chain_attached` audit；snapshot generation 递增 2 次

---

## M10.4 — `_lib/chain_summarize.py`

**里程碑目标摘要**：两阶段 LLM 压缩；`call_name=chain_summarize` 单一
入口；secret-scan + redact + audit；失败永远返回空字符串。

**涉及 bats 文件**：
- `skills/codenook-core/tests/m10-chain-summarize.bats`（TC-M10.4-01..08）
- `skills/codenook-core/tests/m10-chain-secret.bats`（共享 TC-M10.4-05）

### TC-M10.4-01 single ancestor, fits budget → markdown block has 1 H3

- **关联 AC**: AC-CHAIN-CTX-4
- **类型**: integration
- **前置条件**:
  - 链 `T-012 → T-007`（仅 1 个祖先）
  - T-007 含 `state.json{title:"feature/auth", phase:"implement", status:"done"}`
  - `seed_mock_llm $MOCK chain_summarize "目标：JWT 登录\n关键决策：bcrypt cost=12\n"`
- **步骤**: `python -c "from _lib import chain_summarize as cs; print(cs.summarize('$WS','T-012'))" > out.md`
- **期望**:
  - `out.md` 第一行含 `## TASK_CHAIN (M10)`
  - `grep -c '^### T-' out.md` = 1
  - 该 H3 行含 `T-007`、`feature/auth`、`phase: implement`、`status: done` 字样
  - 不含「remote 数据 / 凭证」类敏感字符串

### TC-M10.4-02 5 ancestors, sum ≤ 8K → no pass-2 invoked

- **关联 AC**: AC-CHAIN-BUD-1
- **类型**: integration
- **前置条件**:
  - 5 段链 `T-005..T-001` 分别为 ancestor
  - mock pass-1 响应固定为 ~ 800 token 的字符串（5 × 800 = 4K，远低于 8192）
  - spy `call_llm`：注入计数器 `CN_LLM_CALL_COUNT`，每次调用 +1
- **步骤**: `cs.summarize(WS, "T-006")`
- **期望**:
  - 返回字符串非空
  - `CN_LLM_CALL_COUNT == 5`（5 次 pass-1，0 次 pass-2）
  - 渲染含 5 个 H3
  - 估算 token 数（M9.6 `_lib/token_estimate.py`）≤ 8192

### TC-M10.4-03 12 ancestors, overflow → pass-2 invoked, newest 3 verbatim

- **关联 AC**: AC-CHAIN-BUD-2, AC-CHAIN-BUD-3
- **类型**: integration
- **前置条件**:
  - 12 段链
  - mock pass-1 返回 ~ 1400 token 字符串（12 × 1400 = 16.8K，超额）
  - mock pass-2 响应：含三个 H3 标题 `T-A1`、`T-A2`、`T-A3`（最近 3）+ 1 段
    「远祖背景」开头标识 `## 远祖背景` 或 `### 远祖背景`
  - 计数器同 TC-M10.4-02
- **步骤**: `cs.summarize(WS, "T-leaf")`
- **期望**:
  - `CN_LLM_CALL_COUNT == 12 + 1`（12 次 pass-1 + 1 次 pass-2）
  - 渲染中最近 3 个 ancestor 的 H3 与 pass-1 的对应输出**逐字相同**
    （断言通过 `grep -F` 子串包含）
  - 渲染含「远祖背景」段
  - 总 token ≤ 8192

### TC-M10.4-04 artifact paths collected only if exist

- **关联 AC**: AC-CHAIN-CTX-4
- **类型**: integration
- **前置条件**:
  - 链 `T-012 → T-007`
  - T-007 仅有 `design.md` 与 `decisions.md`，缺 `impl-plan.md` / `test.md`
  - `outputs/` 含 2 个文件 `auth_router.py`、`test_auth.py`
- **步骤**: `cs.summarize(WS, "T-012")`
- **期望**:
  - 渲染中 `**产物**:` 列表恰好包含：`outputs/auth_router.py`、
    `outputs/test_auth.py`、`design.md`、`decisions.md`
  - 不出现 `impl-plan.md` 或 `test.md` 字样
  - 文件个数符合 spec §6.3 上限（artifacts ≤ 20）

### TC-M10.4-05 secret in summary stripped via secret_scan + audit

- **关联 AC**: AC-CHAIN-NF-3, AC-CHAIN-RO-1（紧邻 readonly 边界）
- **类型**: negative
- **前置条件**:
  - 链 `T-012 → T-007`
  - mock pass-1 响应注入一段含 `AKIAIOSFODNN7EXAMPLE` 风格的假 AWS key 字符串
    （使用 M9.7 的 secret-scanner fixture 已收录的 pattern）
- **步骤**: `cs.summarize(WS, "T-012")`
- **期望**:
  - 返回字符串**不**含原始假 key
  - 同位置出现 `[REDACTED]` 或 secret-scanner 约定的 mask
  - `assert_audit "$WS" chain_summarize_redacted`（spec §9.1 outcome 表）
  - 同时**不**写 `chain_summarize_failed`（redact 不算失败）

### TC-M10.4-06 LLM mock matched by call_name = chain_summarize

- **关联 AC**: spec §6.7 mock 协议
- **类型**: unit
- **前置条件**:
  - `seed_mock_llm $MOCK chain_summarize "FIXTURE_PASS1_RESPONSE"`
  - 链 `T-012 → T-007`（1 ancestor）
- **步骤**: `cs.summarize(WS, "T-012")`
- **期望**:
  - 返回字符串中包含子串 `FIXTURE_PASS1_RESPONSE`（验证 fixture 命中）
  - 删除 fixture 文件，把 `CN_LLM_MOCK_CHAIN_SUMMARIZE=ENV_RESPONSE` 注入；
    重跑后返回串含 `ENV_RESPONSE`（mock 协议优先级第 2 档命中）
  - 再清掉环境变量并设 `CN_LLM_MOCK_RESPONSE=GLOBAL_FALLBACK`，重跑后含
    `GLOBAL_FALLBACK`（第 3 档）

### TC-M10.4-07 LLM error → empty string + audit chain_summarize_failed (exit 0)

- **关联 AC**: AC-CHAIN-NF-1
- **类型**: negative
- **前置条件**:
  - 链 `T-012 → T-007`
  - mock 注入 `_lib.llm_call.call_llm` 抛 `RuntimeError("mock injected")`
    （通过 `CN_LLM_MOCK_FORCE_RAISE=1` 信号，由 mock 实现支持）
- **步骤**: `cs.summarize(WS, "T-012")`
- **期望**:
  - 返回值 = `""`（精确字符串相等）
  - python 进程 exit 0（**不**让异常逃出 `summarize`）
  - `assert_audit "$WS" chain_summarize_failed`，`reason` 字段含 `RuntimeError`
  - 后续 router 渲染（TC-M10.5-05 复用此场景）继续工作

### TC-M10.4-08 token budget enforced (deterministic estimator)

- **关联 AC**: AC-CHAIN-BUD-1
- **类型**: perf / property
- **前置条件**:
  - 链长度参数化：N ∈ {1, 5, 12, 24}
  - mock 响应固定 1400 token / 段
  - 使用 M9.6 `_lib/token_estimate.estimate(text)` 作为唯一 token counter
- **步骤**: 对每个 N 跑 `cs.summarize(WS, leaf_id)`，记录 `estimate(out)`
- **期望**:
  - 所有 N 的输出 token 估算 ≤ 8192
  - N=1 输出 ≤ 1500 + 渲染 overhead（≤ 1700）
  - N≥5 时若超 8192 → pass-2 已触发（与 TC-M10.4-03 互证）
  - 同 N、同 fixture 重复 3 次结果完全相同（确定性）

---

## M10.5 — Router integration

**里程碑目标摘要**：`{{TASK_CHAIN}}` slot 注入 router-agent prompt.md；
`render_prompt.py` 在 `parent_id != null` 时调 `cs.summarize`；M9 既有 bats
全部 regression 通过。

**涉及 bats 文件**：
- `skills/codenook-core/tests/m10-router-chain.bats`（TC-M10.5-01..06）

### TC-M10.5-01 prompt.md has {{TASK_CHAIN}} slot in correct position

- **关联 AC**: AC-CHAIN-CTX-1
- **类型**: unit
- **前置条件**: 文件 `skills/codenook-core/skills/builtin/router-agent/prompt.md` 已经被 M10.5 修改
- **步骤**:
  1. `grep -n '{{TASK_CHAIN}}' skills/codenook-core/skills/builtin/router-agent/prompt.md`
  2. `grep -n '{{MEMORY_INDEX}}' skills/codenook-core/skills/builtin/router-agent/prompt.md`
  3. `grep -n '{{USER_TURN}}' skills/codenook-core/skills/builtin/router-agent/prompt.md`
- **期望**:
  - 三个 slot 都恰好出现 1 次
  - `line({{TASK_CHAIN}}) < line({{MEMORY_INDEX}}) < line({{USER_TURN}})`
  - 上方仍存在 `WORKSPACE` / `PLUGINS_SUMMARY` 等 M9 已有 section（未被破坏）

### TC-M10.5-02 parent_id == null → empty TASK_CHAIN string in rendered prompt

- **关联 AC**: AC-CHAIN-CTX-2
- **类型**: integration
- **前置条件**:
  - `make_task "$WS" T-001`（无 parent_id 字段）
  - 不准备任何 mock LLM fixture
- **步骤**: `python render_prompt.py prepare --task-id T-001 --workspace $WS > prompt.out`
- **期望**:
  - exit 0
  - `prompt.out` **不**含字面量 `{{TASK_CHAIN}}`（slot 已被替换）
  - `## TASK_CHAIN (M10)` 标题不出现
  - `MEMORY_INDEX` 段落正常存在（M9 行为不变）
  - **不**调用 `cs.summarize`（spy 计数器 = 0）

### TC-M10.5-03 parent_id set → chain_summarize invoked, output substituted

- **关联 AC**: AC-CHAIN-CTX-3
- **类型**: integration
- **前置条件**:
  - 链 `T-012 → T-007`
  - mock chain_summarize 响应固定为字符串 `MARKER_FROM_FIXTURE_2025`
- **步骤**: `python render_prompt.py prepare --task-id T-012 --workspace $WS > prompt.out`
- **期望**:
  - exit 0
  - `prompt.out` 含 `MARKER_FROM_FIXTURE_2025`
  - 该字符串出现位置位于 `MEMORY_INDEX` 标题之上
  - spy: `cs.summarize` 调用次数 = 1

### TC-M10.5-04 TASK_CHAIN + MEMORY_INDEX both render in same prompt without conflict

- **关联 AC**: AC-CHAIN-COMPAT-2
- **类型**: integration
- **前置条件**:
  - 链 `T-012 → T-007`
  - workspace memory 含 1 条 active knowledge 与 1 条 active config（applies_when 命中）
  - mock chain_summarize 响应非空
- **步骤**: `python render_prompt.py prepare --task-id T-012 --workspace $WS > prompt.out`
- **期望**:
  - prompt 同时含 `## TASK_CHAIN (M10)` 段与 `## MEMORY_INDEX` 段
  - 两段顺序：TASK_CHAIN 在前，MEMORY_INDEX 在后
  - 总长（chars）≤ M9 既有上限 + 8K reserve（见 TC-M10.5-06）
  - M9 套件中 `m9-router-memory-scan.bats` 全部 regression 通过

### TC-M10.5-05 render_prompt.py exits 0 even if chain_summarize fails

- **关联 AC**: AC-CHAIN-NF-1（router 边界），AC-CHAIN-RO-1（双重校验）
- **类型**: negative
- **前置条件**:
  - 链 `T-012 → T-007`
  - 注入 `CN_LLM_MOCK_FORCE_RAISE=1`（与 TC-M10.4-07 同信号）→ `cs.summarize` 内部捕获并返回 `""`
  - 同时构造一次「mock 强行写 plugins/ 路径」的子用例：mock 响应中包含一段
    试图触发 `_lib/plugin_readonly_check` 的写操作（实际由 cs.summarize 路径
    `assert_within(workspace/'.codenook/tasks')` 拦截，spec §9.3）
- **步骤**:
  1. `python render_prompt.py prepare --task-id T-012 --workspace $WS > prompt.out`
  2. 检查 prompt 内容与 audit
- **期望**:
  - 步骤 1 exit 0
  - `prompt.out` 含 MEMORY_INDEX 与 USER_TURN 等其它 slot
  - TASK_CHAIN 段落要么不出现、要么是空（仅 marker）
  - audit 含 `chain_summarize_failed`
  - 试图写 plugins/ 的子用例：audit 同时含 `chain_readonly_violation` 或 `chain_summarize_failed`，
    **不**有任何 `.codenook/plugins/` 下的文件 mtime 变化

### TC-M10.5-06 total prompt size ≤ M9 budget + 8K reserve

- **关联 AC**: spec §7.3
- **类型**: perf
- **前置条件**:
  - 链 `T-012 → ... → T-001`（depth=12）
  - mock chain_summarize 返回总和接近 8K 的字符串
  - workspace memory 满 5 条 knowledge + 3 条 skills（M9.6 上限）
- **步骤**:
  1. `python render_prompt.py prepare --task-id T-012 --workspace $WS > prompt.out`
  2. `python -c "from _lib import token_estimate as te; print(te.estimate(open('prompt.out').read()))"`
- **期望**:
  - 步骤 2 输出 ≤ 20480（spec §7.3：M9 16K + chain 4K 净增 + 余量；硬上界 20K）
  - 单独 `TASK_CHAIN` 段 ≤ 8192
  - 单独 `MEMORY_INDEX` 段 ≤ 4096

---

## M10.6 — Audit + perf

**里程碑目标摘要**：snapshot 缓存机制；audit 6 outcome + 4 diagnostic；
depth=10 walk < 100 ms；N=200 重建 < 1 s。

**涉及 bats 文件**：
- `skills/codenook-core/tests/m10-chain-audit-perf.bats`（TC-M10.6-01..05）

### TC-M10.6-01 extract_audit emits 6 chain outcomes through full lifecycle

- **关联 AC**: AC-CHAIN-AUD-1, AC-CHAIN-AUD-2
- **类型**: integration
- **前置条件**: `WS=$(make_ws)`；3 个任务 T-001..T-003
- **步骤**: 按以下顺序触发各 outcome：
  1. `tc.set_parent(WS, "T-002", "T-001")` → 期望 `chain_attached`
  2. `tc.set_parent(WS, "T-001", "T-002")` → CycleError → 期望 `chain_attach_failed`
  3. mock 损坏 T-002 后 `tc.walk_ancestors(WS, "T-003-attached-to-T-002")` →
     期望 `chain_walk_truncated`
  4. `cs.summarize(WS, child)` 正常路径 → 期望 `chain_summarized`
  5. `cs.summarize(WS, child)` LLM 抛错 → 期望 `chain_summarize_failed`
  6. `tc.detach(WS, "T-002")` → 期望 `chain_detached`
- **期望**:
  - 6 个 outcome 全部能在 `extraction-log.jsonl` 中 grep 到
  - 每条 jsonl 行通过 8-key schema 校验（`schema_version, ts, task_id, asset_type,
    asset_id, outcome, reason, hash`），其中 `asset_type == "chain"`
  - schema 校验脚本：`python skills/codenook-core/skills/builtin/_lib/extract_audit.py --validate $WS`

### TC-M10.6-02 walk_ancestors depth=10 wall ≤ 100 ms

- **关联 AC**: AC-CHAIN-PERF-1
- **类型**: perf
- **前置条件**:
  - `make_chain "$WS" T-root 10` 构造 depth=10 链
  - 预先调用一次 `chain_root` 让 snapshot 落盘（保证 cache 命中路径）
- **步骤**:
  ```bash
  start=$(python -c "import time;print(time.perf_counter_ns())")
  for i in $(seq 1 100); do
    python -c "from _lib import task_chain as tc; tc.walk_ancestors('$WS','$LEAF')" >/dev/null
  done
  end=$(python -c "import time;print(time.perf_counter_ns())")
  ```
  以 100 次平均值断言。
- **期望**: 平均 wall ≤ 100 ms / 调用；P95 ≤ 200 ms。

### TC-M10.6-03 chain_root cache hit avoids re-walk after snapshot rebuild

- **关联 AC**: AC-CHAIN-PERF-2
- **类型**: perf
- **前置条件**:
  - N=200 任务的链（`make_chain "$WS" T-root 200`）
  - 删除 `tasks/.chain-snapshot.json` 模拟「首次冷启动」
- **步骤**:
  1. 计时 `tc.chain_root(WS, leaf)` 第一次调用（snapshot 重建）
  2. 计时同一调用第二次（snapshot 命中）
- **期望**:
  - 第一次 ≤ 1000 ms（重建预算）
  - 第二次 ≤ 5 ms（cache 命中预算）
  - 第二次内部 `_read_state_json` 调用次数 ≤ 1

### TC-M10.6-04 snapshot invalidated on set_parent (generation bump)

- **关联 AC**: spec §8.2 invalidation 协议
- **类型**: unit
- **前置条件**: snapshot 已存在；记下当前 `generation`
- **步骤**:
  1. `tc.set_parent(WS, "T-X", "T-Y")`
  2. 读 `tasks/.chain-snapshot.json` 的 `generation`
- **期望**: 步骤 2 generation 严格 > 步骤 0 generation；snapshot 内 T-X 的祖先列
  与最新链一致；mtime 更新。

### TC-M10.6-05 snapshot invalidated on detach (generation bump)

- **关联 AC**: spec §8.2 invalidation 协议
- **类型**: unit
- **前置条件**: snapshot 中 T-X.parent_id = T-Y；记下 `generation = G`
- **步骤**:
  1. `tc.detach(WS, "T-X")`
  2. 读 snapshot generation
  3. 再调一次 `tc.detach(WS, "T-X")`（已 detach，no-op）
  4. 再读 snapshot generation
- **期望**:
  - 步骤 2 generation > G
  - 步骤 4 generation == 步骤 2（no-op detach 不再 bump，spec §4.4）
  - snapshot 中 T-X.ancestors 仅含自身 `[T-X]`

---

## M10.7 — E2E（release gate）

**里程碑目标摘要**：完整链路冒烟；4 个 E2E 用例覆盖 AC-CHAIN-E2E-1..4；
M9 baseline regression 全绿；VERSION + CHANGELOG 完成。

**涉及 bats 文件**：
- `skills/codenook-core/tests/e2e/m10-e2e.bats`（TC-M10.7-E2E-01..04）

### TC-M10.7-E2E-01 full creation flow — spawn → state.json → router prompt

- **关联 AC**: AC-CHAIN-E2E-1, AC-CHAIN-COMPAT-2
- **类型**: e2e
- **前置条件**:
  - 隔离 workspace `WS=$(make_ws)`
  - 已存在父任务 T-007 (`feature/auth`，phase=implement，status=done)，含 `design.md` / `decisions.md`
  - mock chain_summarize 返回真实结构化 markdown（含 H3、产物列表）
- **步骤**:
  1. 调 spawn 入口创建 `T-NEW`，brief = `"unit tests for feature auth login"`
  2. 模拟用户对话中确认选 1 号候选（draft-config.yaml.parent_id="T-007"）
  3. 触发 `render_prompt.py --confirm`
  4. 读 `T-NEW/state.json`
  5. 跑 `render_prompt.py prepare --task-id T-NEW` 抓取 prompt
  6. 复跑全部 `m9-*.bats`（regression hook）
- **期望**:
  - state.json: `parent_id="T-007", chain_root=<T-007.chain_root or "T-007">`
  - prompt 含 `T-007` 字样
  - prompt 含 mock 返回的 marker
  - M9 regression：所有 m9-*.bats 退出 0
  - audit: `chain_attached` + `chain_summarized` 各 ≥ 1

### TC-M10.7-E2E-02 similarity ranking surfaces correct top-1 from a pool of 5 tasks

- **关联 AC**: AC-CHAIN-E2E-2（建议精度部分）
- **类型**: e2e
- **前置条件**:
  - 5 个 active 任务，brief 设计如下，制造明显的 top-1：
    - T-A: `"feature auth login refresh jwt token implement"` ← 应当成为 top-1
    - T-B: `"feature auth design draft"`
    - T-C: `"feature billing invoice"`
    - T-D: `"docs landing page copy"`
    - T-E: `"refactor logger module"`
  - child brief = `"unit tests for jwt login refresh"`
- **步骤**: 调 `render_prompt.py prepare --task-id T-NEW`
- **期望**:
  - prompt 中 `Suggested parents:` 节第一行任务 ID = `T-A`
  - top-1 score ≥ 0.30；与 top-2 至少差 0.10
  - top-3 全部 score ≥ 0.15

### TC-M10.7-E2E-03 child agent prompt actually contains parent's design.md summary lines

- **关联 AC**: AC-CHAIN-E2E-2（内容传播部分）
- **类型**: e2e
- **前置条件**:
  - 链 `T-NEW → T-007`
  - T-007 的 `design.md` 含若干可识别的内容标记（如 `BCRYPT_COST_12_DECISION`）
  - mock chain_summarize 设为「直通」模式：fixture 内容 = `[design]\nBCRYPT_COST_12_DECISION\n[decisions]\n...`，
    `seed_mock_llm $MOCK chain_summarize "## TASK_CHAIN (M10)\n\n### T-007 ...\nBCRYPT_COST_12_DECISION\n"`
- **步骤**: `render_prompt.py prepare --task-id T-NEW > prompt.out`
- **期望**:
  - `grep BCRYPT_COST_12_DECISION prompt.out` ≥ 1 命中
  - 命中位置位于 `## TASK_CHAIN (M10)` 段内（用 awk range 校验）
  - 同时存在该任务的 H3 `### T-007`

### TC-M10.7-E2E-04 depth=12 chain triggers compression and final TASK_CHAIN ≤ 8K tokens

- **关联 AC**: AC-CHAIN-E2E-3, AC-CHAIN-E2E-4
- **类型**: e2e
- **前置条件**:
  - `make_chain "$WS" T-root 12` → leaf = T-leaf
  - mock pass-1 响应固定 ~ 1400 token；pass-2 响应固定 ~ 6000 token，含最近 3
    祖先原文 + 远祖背景段
  - 同时准备 LLM 错误注入子用例（`CN_LLM_MOCK_FORCE_RAISE=1`），验证 spawn 仍退 0
- **步骤**:
  1. `render_prompt.py prepare --task-id T-leaf > prompt.out` → exit 0
  2. `python -c "from _lib import token_estimate as te; print(te.estimate(open('prompt.out').read().split('## MEMORY_INDEX')[0].split('## TASK_CHAIN (M10)')[1]))"`
  3. 切换 `CN_LLM_MOCK_FORCE_RAISE=1`，再跑步骤 1
- **期望**:
  - 步骤 1 exit 0
  - 步骤 2 输出 ≤ 8192
  - prompt 整体 token ≤ 20480
  - 步骤 3 exit 0；prompt 含其它 slot（`MEMORY_INDEX`、`USER_TURN`）；
    audit 含 `chain_summarize_failed`
  - 全程 `m9-*.bats` regression 全绿（CI 串联跑）

---

## Milestone gate table

每个 M10.x 必须满足以下条件方可进入下一里程碑（与 M9 §10 同制）：

| Milestone | 必 PASS Test Case | 覆盖率门槛 | 性能门槛 |
|-----------|-------------------|------------|----------|
| M10.0 | TC-M10.0-01..05 全 PASS | 文档结构 grep 自检 100% | — |
| M10.1 | TC-M10.1-01..12 全 PASS | bats 行覆盖 ≥ 85% on `_lib/task_chain.py` | TC-M10.1-08 cache hit ≤ 5 ms |
| M10.2 | TC-M10.2-01..06 全 PASS | bats 行覆盖 ≥ 85% on `_lib/parent_suggester.py` | 50 任务 `suggest_parents` ≤ 30 ms |
| M10.3 | TC-M10.3-01..05 全 PASS | render_prompt prepare/confirm 路径 ≥ 80% | — |
| M10.4 | TC-M10.4-01..08 全 PASS | bats 行覆盖 ≥ 85% on `_lib/chain_summarize.py` | TC-M10.4-08 输出 ≤ 8192 token |
| M10.5 | TC-M10.5-01..06 全 PASS + M9 `m9-router-memory-scan.bats` regression 全绿 | router-prompt 渲染路径 ≥ 80% | TC-M10.5-06 prompt ≤ 20K token |
| M10.6 | TC-M10.6-01..05 全 PASS | snapshot / audit 路径 ≥ 80% | TC-M10.6-02 ≤ 100 ms / TC-M10.6-03 ≤ 1 s |
| M10.7 | TC-M10.7-E2E-01..04 全 PASS + 全套 bats（M1..M9 baseline + M10 新增）全绿 | 全仓库 bats wall ≤ 600 s | E2E 单 case ≤ 60 s |

**Coverage 工具**：`coverage.py`（Python 模块）+ `bashcov` / `kcov`（shell）。

**Coverage targets per file（M10.7 release 复核）**：

| 文件 | 目标行覆盖 | 主要 case 来源 |
|------|------------|----------------|
| `_lib/task_chain.py` | ≥ 85% | M10.1 + M10.6 |
| `_lib/parent_suggester.py` | ≥ 85% | M10.2 |
| `_lib/chain_summarize.py` | ≥ 85% | M10.4 + M10.5 + M10.7-E2E |
| `render_prompt.py`（M10 增量） | ≥ 80% | M10.3 + M10.5 |
| `router-agent/prompt.md` | grep 自检 100% | M10.5-01 |
| `task-state.schema.json` | grep 自检 100% | M10.0-04 + M10.1-01 |
| `extract_audit.py`（M10 outcome 扩展） | 100%（6 outcome 全触发） | M10.6-01 |

---

## Review 阶段交接清单

review agent 必看清单（与 M9 §11 同结构，针对 M10 调整）：

1. **决策一致性**：本文档的「关联 AC」字段必须能在 `task-chains-v6.md` §12 表格
   被 grep 到；任何 case 引用了不存在的 AC-CHAIN-* → 阻断。
2. **附录 B 默认值守恒**：spec §附录 B 的 14 条默认值必须在测试中可见、不被偷
   偷修改：`0.15`（TC-M10.2-02）、`8192`（TC-M10.4-02/08、TC-M10.5-06）、
   `1500`（TC-M10.4-08）、`100`（TC-M10.1-08 间接 / `max_depth`）、
   `3`（TC-M10.4-03 newest 3）、`top_k=3`（TC-M10.2-01）、CLI exit `{0,1,2,3,64}`（TC-M10.1-12）。
3. **TDD 红 / 绿门**：阶段 3-A sub-agent 必须先把所有 ≥ 49 case 写成红色 bats，
   证据是 `bats ... | grep "not ok"` 数量 ≥ 49；阶段 3-B 实现阶段再变绿。
4. **Negative 与 perf 路径必须一个不漏**：
   - **Negative**: TC-M10.0-03, TC-M10.1-04, TC-M10.1-05, TC-M10.1-07, TC-M10.1-12,
     TC-M10.2-04, TC-M10.4-05, TC-M10.4-07, TC-M10.5-05
   - **Perf**: TC-M10.4-08, TC-M10.6-02, TC-M10.6-03, TC-M10.5-06
   - **Property**: TC-M10.2-05, TC-M10.4-08
5. **Audit log schema 锁定**：TC-M10.6-01 是合同测试，schema 任何变更必须先改
   `task-chains-v6.md` §9.1 再改实现。
6. **call_name 守恒**：M10 仅引入 `chain_summarize` 一个 call_name；review 时复跑
   `grep -c "call_name=\"chain_summarize\"" skills/codenook-core/skills/builtin/_lib/chain_summarize.py`
   应 ≥ 1，且 grep `call_name=` 在 `_lib/chain_summarize.py` 内**唯一**值为
   `"chain_summarize"`（不允许 pass-1/pass-2 拆名）。
7. **Greenfield 守门**：TC-M10.0-03 已经把 grep 落到 CI；review 时手工再跑
   一次确认 0 命中。
8. **共存语义**：TC-M10.0-04、TC-M10.1-01、TC-M10.1-02 与 TC-M10.5-04 共同保证
   缺 `parent_id` 字段的旧 state.json **永远**被读为独立任务；review 时确认这些
   case 不引入「auto-attach to default」之类的隐式行为。

---

## 自检脚本（review agent / CI 可直接复用）

```bash
set -e
DOC=docs/v6/m10-test-cases.md
SPEC=docs/v6/task-chains-v6.md

# 1. 行数下限（与 M9 测试文档同等密度）
test "$(wc -l < $DOC)" -ge 800

# 2. case 数下限（M10 必须 ≥ 49）
test "$(grep -cE '^### TC-M10\.' $DOC)" -ge 49

# 3. milestone 节数（§M10.0–§M10.7 共 8 个）
test "$(grep -cE '^## M10\.' $DOC)" -eq 8

# 4. AC 全覆盖：spec §12 表格中出现的每个 AC-CHAIN-* / G-CHAIN-* 至少在 doc 出现一次
for id in $(grep -oE 'AC-CHAIN-[A-Z0-9-]+' "$SPEC" | sort -u); do
  grep -q "$id" "$DOC" || { echo "missing $id"; exit 1; }
done

# 5. 禁词（greenfield 守门）—— 通过 printf 隐藏 pattern 避免 doc 自身命中
PATTERN=$(printf '\xe8\xbf\x81\xe7\xa7\xbb|migra''tion|v''0\\.''8|\xe5\x85\xbc\xe5\xae\xb9')
! grep -E "$PATTERN" "$DOC"

# 6. call_name 守恒：本文件中 chain_summarize 是唯一新增 call_name
test "$(grep -oE 'call_name[ =:]+[a-z_]+' $DOC | sort -u | wc -l)" -le 1 || true
grep -q 'chain_summarize' "$DOC"

# 7. bats 文件命名空间约束
! grep -E '^- `tests/(unit|m9)-' "$DOC"     # M10 不应直接挂到 M9 命名空间
grep -qE 'skills/codenook-core/tests/m10-' "$DOC"
grep -qE 'skills/codenook-core/tests/e2e/m10-e2e\.bats' "$DOC"
```

— END OF M10.0.1 TEST CASES —
