---
name: agent-init
description: "初始化项目的 Agent 协作系统。说 '初始化 Agent 系统' 触发。检测项目技术栈, 在 .agents/ 下创建运行时目录和项目级 skill。"
---

# 项目 Agent 初始化

## 前置条件
- 当前目录是一个项目根目录 (有 git 仓库或 package.json 等)
- 全局 skills 已安装 (`~/.copilot/skills/agent-*/SKILL.md`)
- 全局 agents 已安装 (`~/.copilot/agents/*.agent.md`)

## 执行步骤

### 0. 检查是否已初始化
```bash
ls .agents/task-board.json 2>/dev/null
```
- **如果已存在**: 输出 "⚠️ Agent 系统已初始化, 跳过。" + 当前状态摘要。**不覆盖任何文件**。
- **如果不存在**: 执行全新初始化 (Step 1-7)。

### 1. 收集上下文信息

#### 1a. 检测项目技术栈
```bash
# 语言/框架
ls package.json Cargo.toml requirements.txt go.mod pom.xml \
   Gemfile composer.json *.csproj *.sln Package.swift pubspec.yaml \
   build.gradle setup.py pyproject.toml CMakeLists.txt Makefile 2>/dev/null

# 框架特征
ls next.config* nuxt.config* angular.json vue.config* \
   Caddyfile nginx.conf webpack.config* vite.config* \
   tsconfig.json .babelrc tailwind.config* 2>/dev/null

# 测试框架
ls jest.config* playwright.config* pytest.ini vitest.config* \
   .rspec karma.conf* cypress.config* phpunit.xml 2>/dev/null

# CI/CD
ls .github/workflows/*.yml .gitlab-ci.yml .circleci/config.yml \
   Jenkinsfile .travis.yml bitbucket-pipelines.yml 2>/dev/null

# 部署
ls Dockerfile docker-compose* k8s/ fly.toml render.yaml \
   vercel.json netlify.toml serverless.yml samconfig.toml \
   app.yaml Procfile 2>/dev/null

# Monorepo
ls lerna.json pnpm-workspace.yaml nx.json turbo.json rush.json 2>/dev/null

# README (fallback for project description)
head -5 README.md 2>/dev/null
```

#### 1b. 读取项目级 instructions (如果存在)
```bash
cat .github/copilot-instructions.md 2>/dev/null
```
项目级 instructions 包含项目特定的规范、约定和偏好, 这些信息会融入到生成的 skill 中。

#### 1c. 读取全局 agent profiles
```bash
cat ~/.copilot/agents/acceptor.agent.md
cat ~/.copilot/agents/designer.agent.md
cat ~/.copilot/agents/implementer.agent.md
cat ~/.copilot/agents/reviewer.agent.md
cat ~/.copilot/agents/tester.agent.md
```
全局 agent profiles 定义了每个角色的通用行为, 项目级 skill 在此基础上添加项目特定信息。

#### 1d. 读取全局 skills
```bash
cat ~/.copilot/skills/agent-acceptor/SKILL.md
cat ~/.copilot/skills/agent-designer/SKILL.md
cat ~/.copilot/skills/agent-implementer/SKILL.md
cat ~/.copilot/skills/agent-reviewer/SKILL.md
cat ~/.copilot/skills/agent-tester/SKILL.md
cat ~/.copilot/skills/agent-fsm/SKILL.md
cat ~/.copilot/skills/agent-task-board/SKILL.md
```
全局 skills 定义了每个角色的工作流和通用操作。生成项目级 skill 时, 需要参考全局 skill 了解角色"怎么工作", 以便生成有针对性的项目上下文。例如: 全局 skill 说 "运行测试" → 项目 skill 填入具体命令 `npx playwright test`。

### 2. 创建目录结构

所有 Agent 系统文件统一放在 `.agents/` 目录下:

```bash
# 项目级 skill (Copilot 自动发现 .agents/skills/)
mkdir -p .agents/skills/project-agents-context
mkdir -p .agents/skills/project-acceptor
mkdir -p .agents/skills/project-designer
mkdir -p .agents/skills/project-implementer
mkdir -p .agents/skills/project-reviewer
mkdir -p .agents/skills/project-tester

# 任务数据
mkdir -p .agents/tasks

# Agent 运行时
mkdir -p .agents/runtime/acceptor/workspace/{requirements,acceptance-docs,acceptance-reports}
mkdir -p .agents/runtime/designer/workspace/{research,design-docs,test-specs}
mkdir -p .agents/runtime/implementer/workspace
mkdir -p .agents/runtime/reviewer/workspace/review-reports
mkdir -p .agents/runtime/tester/workspace/{test-cases,test-screenshots}
```

### 3. 初始化状态文件
为每个 Agent (acceptor, designer, implementer, reviewer, tester) 创建:

**`.agents/runtime/<agent>/state.json`**:
```json
{
  "agent": "<agent_name>",
  "status": "idle",
  "current_task": null,
  "sub_state": null,
  "queue": [],
  "last_activity": "<current ISO 8601>",
  "version": 0,
  "error": null
}
```

**`.agents/runtime/<agent>/inbox.json`**:
```json
{"messages": []}
```

### 3b. 初始化 events.db (SQLite 审计日志)
```bash
sqlite3 .agents/events.db <<'SQL'
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  timestamp INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  agent TEXT,
  task_id TEXT,
  tool_name TEXT,
  detail TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
SQL
```

事件类型: `session_start`, `tool_use`, `task_board_write`, `state_change`, `agent_switch`, `message_sent`

### 4. 创建空任务表

**`.agents/task-board.json`**:
```json
{"version": 0, "tasks": []}
```

**`.agents/task-board.md`**:
```markdown
# 📋 项目任务表

> 自动生成, 请勿手动编辑。

| ID | 标题 | 状态 | 负责 | 优先级 | 更新时间 |
|----|------|------|------|--------|---------|

_暂无任务_
```

### 5. 生成项目级 Skills (AI 定制化, 非拷贝!)

> ⚠️ 以下 skill 由 AI 基于 **Step 1 收集的全部上下文** 生成, 不是从全局模板拷贝。
> 输入源: 全局 agent profiles + 全局 skills (工作流) + 项目 instructions + 检测到的技术栈信息。
> 生成原则: 全局 skill 定义"怎么做", 项目 skill 补充"用什么做" (具体命令、路径、标准)。

**通用要求**:
- 每个 SKILL.md 必须以 YAML frontmatter 开头 (`---\nname: ...\ndescription: ...\n---`)
- 内容使用 Markdown, 信息密度高, 避免废话
- 所有路径使用项目相对路径 (不硬编码绝对路径)
- 命令必须是检测到的实际可执行命令, 不是假设

#### 5a. `.agents/skills/project-agents-context/SKILL.md` — 项目上下文

所有 Agent 工作时自动获取的共享上下文。
```yaml
---
name: project-agents-context
description: "项目上下文信息, 所有 agent 工作时自动获取。包含技术栈、构建命令、部署方式等。"
---
```

**必须包含以下章节** (根据检测结果填充, 未检测到的标注 "N/A"):

```markdown
# 项目上下文

## 项目信息
- **名称**: <从 package.json name / Cargo.toml [package].name / 目录名>
- **描述**: <从 package.json description / README 首段 / 用户输入>
- **仓库**: <从 git remote -v 获取>

## 技术栈
- **语言**: <从检测结果, 含版本号>
- **框架**: <从检测结果>
- **样式/UI**: <从检测结果>
- **数据库**: <从检测结果, 如无则 N/A>
- **测试**: <从检测结果, 含框架名>
- **CI**: <从检测结果>
- **部署**: <从检测结果>

## 常用命令
| 操作 | 命令 |
|------|------|
| 安装依赖 | `<实际命令>` |
| 开发服务器 | `<实际命令>` |
| 运行测试 | `<实际命令>` |
| 构建 | `<实际命令>` |
| Lint | `<实际命令>` |
| 部署 | `<实际命令>` |

## 目录结构
<列出主要目录及用途, 从 ls / tree 输出推断>

## 分支策略
<从 .github/copilot-instructions.md 或 git branch 推断>
```

#### 5b. `.agents/skills/project-acceptor/SKILL.md` — 项目级验收者

验收者 Agent 的项目特定信息。
```yaml
---
name: project-acceptor
description: "本项目的验收标准和业务背景。验收者 agent 工作时加载。"
---
```

**必须包含**:
```markdown
# 项目级验收指南

## 业务背景
<从 README / 项目 instructions 提取, 描述项目目标和用户群体>

## 验收标准基线
- **功能测试**: <项目的测试命令, 如 `npx playwright test`>
- **构建检查**: <项目的构建命令, 如 `npm run build`>
- **Lint 检查**: <项目的 lint 命令, 如无则 "N/A">
- **覆盖率要求**: <从配置文件检测, 如 "无强制要求" 或 ">80%">

## 验收流程 (项目特定)
1. 检出代码, 运行 `<安装命令>`
2. 运行 `<测试命令>`, 确认全部通过
3. <如有 E2E 测试> 在 `<URL>` 上验证页面功能
4. <如有部署> 验证部署环境可达

## 质量红线
<从项目 instructions 提取, 如: "不允许降低测试覆盖率", "所有 API 必须有错误处理">
```

#### 5c. `.agents/skills/project-designer/SKILL.md` — 项目级设计者

```yaml
---
name: project-designer
description: "本项目的架构约束和技术选型。设计者 agent 工作时加载。"
---
```

**必须包含**:
```markdown
# 项目级设计指南

## 现有架构
<从目录结构和技术栈推断: 单体/微服务/Jamstack/etc., 入口文件, 路由方式>

## 技术约束
- **语言版本**: <检测到的版本约束>
- **框架限制**: <框架特有的约定, 如 Next.js 的 app router>
- **兼容性**: <从配置文件检测的 target, 如 ES2020, browserslist>

## 设计文档模板
设计文档应输出到 `.agents/runtime/designer/workspace/design-docs/` 并包含:
1. 需求摘要 (引用 goal ID)
2. 技术方案 (含备选方案对比)
3. 文件变更列表 (新增/修改/删除)
4. 测试规格 (输出到 `test-specs/`)

## API/数据约定
<从现有代码推断: REST/GraphQL, 数据格式, 命名规范>
```

#### 5d. `.agents/skills/project-implementer/SKILL.md` — 项目级实现者

```yaml
---
name: project-implementer
description: "本项目的编码规范和开发命令。实现者 agent 工作时加载。"
---
```

**必须包含**:
```markdown
# 项目级开发指南

## 开发命令
| 操作 | 命令 | 说明 |
|------|------|------|
| 安装 | `<命令>` | |
| 开发 | `<命令>` | <端口号等> |
| 测试 | `<命令>` | |
| 单个测试 | `<命令> <pattern>` | |
| 调试测试 | `<命令> --headed` 或 `--inspect` | |
| Lint | `<命令>` | |
| 构建 | `<命令>` | |

## 编码规范
- **缩进**: <从 .editorconfig / .prettierrc / eslintrc 检测>
- **引号**: <从配置检测>
- **命名**: <从现有代码推断, 如 camelCase / snake_case>
- **提交**: <从项目 instructions 提取提交规范>

## 依赖管理
- **包管理器**: <npm / yarn / pnpm / pip / cargo>
- **Lock 文件**: <是否提交>
- **添加依赖**: `<命令>`

## TDD 工作流 (项目适配)
1. 测试文件位置: `<tests/ 或 __tests__/ 或 src/**/*.test.ts>`
2. 测试命名: `<从现有测试推断>`
3. Mock/Fixture: `<从现有代码推断>`
4. 写测试 → `<运行测试命令>` 确认红灯 → 写实现 → 确认绿灯 → 重构
```

#### 5e. `.agents/skills/project-reviewer/SKILL.md` — 项目级审查者

```yaml
---
name: project-reviewer
description: "本项目的审查标准和代码质量要求。审查者 agent 工作时加载。"
---
```

**必须包含**:
```markdown
# 项目级审查指南

## 审查清单
- [ ] 代码能编译/构建: `<构建命令>`
- [ ] 测试通过: `<测试命令>`
- [ ] Lint 通过: `<lint 命令>`
- [ ] 无安全漏洞 (硬编码密钥、SQL 注入、XSS 等)
- [ ] 与现有代码风格一致
- [ ] 新增代码有对应测试

## 项目特有规则
<从 .eslintrc / .github/copilot-instructions.md 提取, 如:>
<- "所有 API 端点必须有错误处理">
<- "不允许使用 any 类型">
<- "CSS 类名使用 BEM 命名">

## 审查报告模板
输出到 `.agents/runtime/reviewer/workspace/review-reports/` 格式:
- 文件名: `review-T-NNN-<date>.md`
- 包含: 严重问题 (必须修复) / 建议 (可选修复) / 总评 (pass/fail)
```

#### 5f. `.agents/skills/project-tester/SKILL.md` — 项目级测试者

```yaml
---
name: project-tester
description: "本项目的测试框架和测试策略。测试者 agent 工作时加载。"
---
```

**必须包含**:
```markdown
# 项目级测试指南

## 测试框架
- **单元测试**: <框架名 + 运行命令>
- **E2E 测试**: <框架名 + 运行命令, 如 Playwright>
- **其他**: <性能测试、安全测试等, 如有>

## 测试命令
| 操作 | 命令 |
|------|------|
| 全部测试 | `<命令>` |
| 单个文件 | `<命令> <file>` |
| 匹配名称 | `<命令> -g "<pattern>"` |
| 有头模式 | `<命令> --headed` |
| 调试模式 | `<命令> --debug` |
| 覆盖率 | `<命令> --coverage` |

## 测试文件组织
- 位置: `<tests/ 或 __tests__/ 或 alongside source>`
- 命名: `<*.test.ts / *.spec.js / test_*.py>`
- Fixture: `<位置和用法>`

## 测试策略
- 新功能: 至少覆盖 happy path + 1 个 error case
- Bug 修复: 先写回归测试 (红灯) → 确认修复 (绿灯)
- 测试用例输出到: `.agents/runtime/tester/workspace/test-cases/`
- 问题报告输出到: `.agents/runtime/tester/workspace/issues-report.md`

## 测试环境
<从配置推断: 浏览器配置、环境变量、测试数据库等>
```

### 5g. 生成项目级 Hooks (可选)

如果项目需要项目级 hook 覆盖 (如更严格的边界规则、项目特定的审计需求):

```bash
mkdir -p .agents/hooks
```

从全局 hooks 复制基础版本并注入项目路径:

```bash
# 复制全局 hooks 作为基础
for hook in agent-session-start.sh agent-pre-tool-use.sh agent-post-tool-use.sh agent-staleness-check.sh; do
  if [ -f ~/.copilot/hooks/"$hook" ]; then
    cp ~/.copilot/hooks/"$hook" .agents/hooks/"$hook"
    chmod +x .agents/hooks/"$hook"
  fi
done
```

生成 `.agents/hooks/hooks.json`:

```json
{
  "hooks": {
    "copilot-agent:sessionStart": [
      {
        "command": ".agents/hooks/agent-session-start.sh",
        "description": "Project-level session start (events.db + inbox check)",
        "timeoutSec": 10
      }
    ],
    "copilot-agent:preToolUse": [
      {
        "command": ".agents/hooks/agent-pre-tool-use.sh",
        "description": "Project-level boundary enforcement",
        "timeoutSec": 5
      }
    ],
    "copilot-agent:postToolUse": [
      {
        "command": ".agents/hooks/agent-post-tool-use.sh",
        "description": "Project-level audit + auto-dispatch",
        "timeoutSec": 10
      }
    ]
  }
}
```

> **注意**: 项目级 hooks 会与全局 hooks 同时执行。如果项目不需要额外的 hook 定制，跳过此步骤，全局 hooks 已足够。

### 6. 创建 .agents/.gitignore
```
# Agent runtime state (不提交到 git)
runtime/*/state.json
runtime/*/inbox.json

# 保留目录结构
!runtime/*/workspace/.gitkeep
```

### 7. 输出摘要
```
✅ Agent 系统已初始化
━━━━━━━━━━━━━━━━━━━━━━━
项目: <name>
目录: <project>/.agents/
技术栈: <detected>
━━━━━━━━━━━━━━━━━━━━━━━
Skills: .agents/skills/ (6 project skills)
Runtime: .agents/runtime/ (5 agents, all idle)
任务表: .agents/task-board.json (空)
━━━━━━━━━━━━━━━━━━━━━━━
下一步: /agent acceptor → 开始创建需求
```
