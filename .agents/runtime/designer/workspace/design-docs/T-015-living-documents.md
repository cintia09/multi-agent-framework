# T-015: 项目级活文档系统

## Context

当前框架中，各代理（Acceptor、Designer、Tester、Implementer、Reviewer）在任务生命周期中产生大量信息——需求定义、设计决策、测试用例、实现细节、审查结论——但这些信息散落在各自的 workspace 目录中（如 `design-docs/`、`test-results/`），**缺少项目级的持续累积文档**。

痛点：
1. **项目历史不可追溯**：task-board.json 仅记录任务状态，不记录决策过程和技术演变
2. **跨代理信息断层**：Tester 编写测试时无法方便地查阅 requirement 和 design 的全貌
3. **新成员/新代理缺乏上下文**：没有集中的项目知识库，只能逐个翻阅历史任务文件
4. **验收缺少闭环记录**：Acceptor 验收后没有统一的验收记录积累

## Decision

在 `docs/` 目录下建立 **6 个项目级活文档**，分别由对应代理在完成任务阶段后自动追加内容。文档采用累积式结构（每个任务追加 `## T-NNN: 标题` 新章节），形成项目完整历史。

| 文档 | 维护者 | 写入时机 |
|------|--------|----------|
| `docs/requirement.md` | Acceptor | 任务被 accepted 后 |
| `docs/design.md` | Designer | 设计文档完成后 |
| `docs/test-spec.md` | Tester | 测试规格编写完成后 |
| `docs/implementation.md` | Implementer | 实现完成后 |
| `docs/review.md` | Reviewer | 审查完成后 |
| `docs/acceptance.md` | Acceptor | 最终验收完成后 |

## Alternatives Considered

| 方案 | 优点 | 缺点 | 决定 |
|------|------|------|------|
| **A: docs/ 累积文档（选中）** | 集中管理、git 可追踪、跨代理可读 | 文件会随项目增长变大 | ✅ 选中 |
| **B: 每任务独立文档 + 索引** | 文件小、好管理 | 需维护索引，跨任务查询不便 | ❌ 碎片化 |
| **C: 写入 events.db** | 结构化查询 | 不适合长文本，可读性差 | ❌ 不适合文档内容 |
| **D: Wiki/外部系统** | 功能丰富 | 脱离代码仓库，增加依赖 | ❌ 过度工程化 |

## Design

### Architecture

```
docs/                              # 项目级活文档目录
├── requirement.md                 # Acceptor: 需求记录
├── design.md                      # Designer: 设计记录
├── test-spec.md                   # Tester: 测试规格记录
├── implementation.md              # Implementer: 实现记录
├── review.md                      # Reviewer: 审查记录
└── acceptance.md                  # Acceptor: 验收记录

写入流程:
  Acceptor accepts T-NNN
    └─→ append to docs/requirement.md
  Designer designs T-NNN
    └─→ append to docs/design.md
  Tester writes tests for T-NNN
    ├─→ read docs/requirement.md (input)
    ├─→ read docs/design.md (input)
    └─→ append to docs/test-spec.md
  Implementer implements T-NNN
    └─→ append to docs/implementation.md
  Reviewer reviews T-NNN
    └─→ append to docs/review.md
  Acceptor accepts T-NNN final
    └─→ append to docs/acceptance.md
```

### Data Model

#### 文档模板结构

每个文档共享相同的顶层结构：

```markdown
# <文档标题>

> 本文档由 <角色> 代理自动维护，记录项目全生命周期的 <类型> 信息。
> 每个任务追加一个 `## T-NNN: 标题` 章节，请勿手动编辑。

---

## T-001: <任务标题>
**日期**: YYYY-MM-DD
**状态**: <对应阶段状态>

<内容>

---

## T-002: <任务标题>
...
```

#### 各文档专属内容模板

**requirement.md** (Acceptor):
```markdown
## T-NNN: <标题>
**日期**: YYYY-MM-DD
**来源**: <用户请求 / 自动发现 / 代理提议>

### 功能目标
| Goal | 描述 | 验收标准 |
|------|------|----------|
| G1   | ...  | ...      |

### 用户故事（如适用）
作为 <角色>，我希望 <功能>，以便 <价值>。

### 约束与注意事项
- ...
```

**design.md** (Designer):
```markdown
## T-NNN: <标题>
**日期**: YYYY-MM-DD
**设计文档**: `.agents/runtime/designer/workspace/design-docs/T-NNN-*.md`

### 决策摘要
- 选择方案: <方案名称>
- 关键权衡: <简述>

### 架构变更
<简要描述架构影响，引用详细设计文档>

### 实施步骤概要
1. ...
2. ...
```

**test-spec.md** (Tester):
```markdown
## T-NNN: <标题>
**日期**: YYYY-MM-DD
**输入文档**: requirement.md#T-NNN, design.md#T-NNN

### 测试范围
- 覆盖的 Goals: G1, G2, ...
- 测试类型: 单元 / 集成 / E2E

### 测试用例
| ID | 场景 | 预期结果 | 状态 |
|----|------|----------|------|
| TC-1 | ... | ... | ⬜ |

### 覆盖率要求
- 行覆盖率: ≥ X%
- 分支覆盖率: ≥ Y%
```

**implementation.md** (Implementer):
```markdown
## T-NNN: <标题>
**日期**: YYYY-MM-DD
**分支**: <branch-name>

### 变更文件
| 文件 | 变更类型 | 说明 |
|------|----------|------|
| path/to/file | 新增/修改/删除 | ... |

### 关键实现决策
- ...

### TDD 状态（如适用）
- RED: X 个测试编写
- GREEN: X 个测试通过
- REFACTOR: 已完成 / 未完成
```

**review.md** (Reviewer):
```markdown
## T-NNN: <标题>
**日期**: YYYY-MM-DD
**审查者**: Reviewer Agent

### 审查结果
- 总体评价: ✅ 通过 / ⚠️ 有条件通过 / ❌ 需修改

### 发现的问题
| 严重级别 | 文件 | 描述 | 状态 |
|----------|------|------|------|
| P0-blocker | ... | ... | 🔴 |

### 安全检查
- [ ] 无硬编码凭据
- [ ] 输入已验证
- [ ] 无路径遍历风险
```

**acceptance.md** (Acceptor):
```markdown
## T-NNN: <标题>
**日期**: YYYY-MM-DD
**验收结果**: ✅ 通过 / ❌ 拒绝

### Goals 验收
| Goal | 状态 | 备注 |
|------|------|------|
| G1   | ✅   | ...  |

### 验收备注
- ...
```

### API / Interface

#### SKILL.md 变更

需要更新 5 个代理的 SKILL.md，在各自的工作流末尾添加"追加活文档"步骤：

**1. agent-acceptor/SKILL.md** — 两处追加:
```
# Flow A 末尾（accepted 后）:
- 追加 docs/requirement.md: 写入 ## T-NNN 章节（Goals、用户故事、约束）

# Flow C 末尾（验收后）:
- 追加 docs/acceptance.md: 写入 ## T-NNN 章节（验收结果、Goals 状态）
```

**2. agent-designer/SKILL.md** — 一处追加:
```
# Flow A 末尾（设计完成后）:
- 追加 docs/design.md: 写入 ## T-NNN 章节（决策摘要、架构变更、步骤概要）
```

**3. agent-tester/SKILL.md** — 一处追加 + 一处输入:
```
# Flow A 开始（编写测试前）:
- 读取 docs/requirement.md 和 docs/design.md 中 T-NNN 章节作为输入

# Flow A 末尾（测试编写后）:
- 追加 docs/test-spec.md: 写入 ## T-NNN 章节（测试范围、用例、覆盖率）
```

**4. agent-implementer/SKILL.md** — 一处追加:
```
# 实现完成后:
- 追加 docs/implementation.md: 写入 ## T-NNN 章节（变更文件、决策、TDD 状态）
```

**5. agent-reviewer/SKILL.md** — 一处追加:
```
# 审查完成后:
- 追加 docs/review.md: 写入 ## T-NNN 章节（审查结果、问题、安全检查）
```

#### agent-init 变更

在 `skills/agent-init/SKILL.md` 的初始化流程中，创建 `docs/` 目录时同时生成 6 个空模板：

```bash
mkdir -p docs
for doc in requirement design test-spec implementation review acceptance; do
  cat > "docs/${doc}.md" << 'EOF'
# <对应标题>

> 本文档由 <对应角色> 代理自动维护。每个任务追加一个 `## T-NNN: 标题` 章节。

---
EOF
done
```

### Implementation Steps

1. **创建 docs/ 目录和 6 个模板文件**
   - 在项目根目录创建 `docs/` 目录
   - 创建 `requirement.md`、`design.md`、`test-spec.md`、`implementation.md`、`review.md`、`acceptance.md`
   - 每个文件包含标题、维护者说明、分隔符

2. **更新 agent-acceptor SKILL.md**
   - 在 Flow A（收集需求 → accepted）末尾添加步骤："追加 `docs/requirement.md`"
   - 在 Flow C（验收）末尾添加步骤："追加 `docs/acceptance.md`"
   - 提供各模板的具体字段说明

3. **更新 agent-designer SKILL.md**
   - 在 Flow A（设计完成后）末尾添加步骤："追加 `docs/design.md`"
   - 引用上方的 design.md 模板格式

4. **更新 agent-tester SKILL.md**
   - 在 Flow A 开始添加："读取 `docs/requirement.md` 和 `docs/design.md` 中 T-NNN 章节"
   - 在 Flow A 末尾添加："追加 `docs/test-spec.md`"

5. **更新 agent-implementer SKILL.md**
   - 在实现完成后添加步骤："追加 `docs/implementation.md`"

6. **更新 agent-reviewer SKILL.md**
   - 在审查完成后添加步骤："追加 `docs/review.md`"

7. **更新 agent-init SKILL.md**
   - 在初始化流程的目录创建部分，添加 `docs/` 及 6 个模板文件的创建步骤
   - 使用上方的 shell 脚本片段

8. **更新现有 docs/agent-rules.md**
   - 添加说明："docs/ 目录下的活文档由代理自动维护，请勿手动编辑任务章节"

## Test Spec

### 验证项

| ID | 验证内容 | 方法 | 预期结果 |
|----|----------|------|----------|
| V1 | 6 个模板文件存在 | `ls docs/` | 6 个 .md 文件 |
| V2 | 模板文件包含正确标题和维护者说明 | `head -5 docs/*.md` | 各文件标题和说明正确 |
| V3 | agent-acceptor SKILL.md 包含追加步骤 | `grep "docs/requirement" SKILL.md` | 有 requirement 和 acceptance 两处 |
| V4 | agent-designer SKILL.md 包含追加步骤 | `grep "docs/design" SKILL.md` | 有 design.md 追加 |
| V5 | agent-tester SKILL.md 包含读取和追加步骤 | `grep "docs/" SKILL.md` | 有 requirement+design 读取，test-spec 追加 |
| V6 | agent-implementer SKILL.md 包含追加步骤 | `grep "docs/implementation" SKILL.md` | 有追加 |
| V7 | agent-reviewer SKILL.md 包含追加步骤 | `grep "docs/review" SKILL.md` | 有追加 |
| V8 | agent-init SKILL.md 包含 docs/ 创建步骤 | `grep "docs/" SKILL.md` | 有 6 个模板文件创建 |
| V9 | 累积追加测试 | 模拟两次追加 | 两个 ## T-NNN 章节共存 |
| V10 | Tester 交叉引用 | 模拟 Tester 读取 requirement+design | 能正确提取对应 T-NNN 章节 |

## Consequences

### 正面
- **项目历史完整可追溯**：从需求到验收的完整链路记录在 git 中
- **跨代理协作增强**：Tester 可直接读取 requirement.md + design.md，无需在 workspace 中翻找
- **新成员友好**：阅读 docs/ 即可了解项目所有决策和演变
- **验收有据可查**：每次验收都有记录，可回溯

### 负面
- **文件增长**：随任务增多，文档会变大（但 markdown 压缩率高，可接受）
- **写入冲突**：多代理同时写入同一文件可能冲突（实际中各代理顺序执行，风险低）
- **SKILL.md 变更量**：需同时修改 5 + 1 = 6 个文件

### 缓解措施
- 每个 ## T-NNN 章节以 `---` 分隔，便于定位和解析
- 未来可添加 `docs/index.md` 自动生成目录索引
- 文件过大时可按年份归档（如 `docs/archive/2024-design.md`）
