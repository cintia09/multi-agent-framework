---
name: agent-init
description: "初始化项目的 Agent 协作系统。说 '初始化 Agent 系统' 触发。检测项目技术栈, 在 .agents/ 下创建运行时目录和项目级 skill。"
---

# 项目 Agent 初始化

## 前置条件
- 当前目录是项目根目录 (有 git 仓库或 package.json 等)
- 全局 skills 已安装 (`~/.claude/skills/agent-*/SKILL.md`)
- 全局 agents 已安装 (`~/.claude/agents/*.agent.md`)

## 执行步骤

### 0. 检查是否已初始化
```bash
ls .agents/task-board.json 2>/dev/null
```
- **已存在**: 输出 "⚠️ Agent 系统已初始化, 跳过。" **不覆盖任何文件**。
- **不存在**: 执行全新初始化 (Step 1-7)。

### 1. 收集上下文信息

#### 1a. 检测项目技术栈
```bash
ls package.json Cargo.toml requirements.txt go.mod pom.xml Gemfile composer.json *.csproj *.sln Package.swift pubspec.yaml build.gradle setup.py pyproject.toml CMakeLists.txt Makefile 2>/dev/null
ls next.config* nuxt.config* angular.json vue.config* Caddyfile nginx.conf webpack.config* vite.config* tsconfig.json .babelrc tailwind.config* 2>/dev/null
ls jest.config* playwright.config* pytest.ini vitest.config* .rspec karma.conf* cypress.config* phpunit.xml 2>/dev/null
ls .github/workflows/*.yml .gitlab-ci.yml .circleci/config.yml Jenkinsfile .travis.yml bitbucket-pipelines.yml 2>/dev/null
ls Dockerfile docker-compose* k8s/ fly.toml render.yaml vercel.json netlify.toml serverless.yml samconfig.toml app.yaml Procfile 2>/dev/null
ls lerna.json pnpm-workspace.yaml nx.json turbo.json rush.json 2>/dev/null
head -5 README.md 2>/dev/null
```

#### 1b. 读取项目级 instructions
```bash
cat CLAUDE.md 2>/dev/null
cat .github/copilot-instructions.md 2>/dev/null
```

#### 1c. 分类项目类型

根据 Step 1a 检测结果, 将项目归类:

| 检测特征 | 项目类型 | 标识 |
|---------|---------|------|
| Package.swift / .xcodeproj / SwiftUI | iOS/macOS 原生 | `ios` |
| next.config / nuxt.config / vue.config / angular.json | 前端 Web | `frontend` |
| package.json + 无前端框架 / go.mod / pom.xml | 后端服务 | `backend` |
| Cargo.toml / CMakeLists.txt / Makefile (C/C++) | 系统级 | `systems` |
| requirements.txt + torch/tensorflow/transformers | AI/ML | `ai-ml` |
| Dockerfile + k8s/ / serverless.yml | DevOps/基础设施 | `devops` |
| 其他 / 混合 | 通用 | `general` |

在 Step 5a 的 project-agents-context 中记录: `project_type: "<类型>"`

#### 1d. 选择工作流模式
询问用户: Simple (线性 SDLC) 或 3-Phase (三阶段工程闭环)
- 选择 1 → `workflow_mode: "simple"` (默认)
- 选择 2 → `workflow_mode: "3phase"` (执行 Step 5h)

#### 1e. 读取全局 agent profiles, skills & rules

扫描全部全局资源, 构建完整上下文:

```bash
# Agent Profiles (5 个, 含 skills: 隔离清单)
for f in acceptor designer implementer reviewer tester; do
  cat ~/.claude/agents/${f}.agent.md 2>/dev/null || cat ~/.copilot/agents/${f}.agent.md 2>/dev/null
done

# 全部 18 个 Skills (只读 frontmatter + 前 20 行摘要, 避免上下文溢出)
for d in ~/.claude/skills/agent-*/SKILL.md; do
  head -20 "$d" 2>/dev/null
done

# 全局 Rules
for r in ~/.claude/rules/*.md; do
  cat "$r" 2>/dev/null
done
```

> 关注: 每个 agent profile 的 `skills:` frontmatter 定义了该角色允许调用的 skills 列表 (Per-Agent 隔离)。

#### 1f. 检测平台

```bash
# 检测当前运行的平台
if [ -d ~/.claude ]; then PLATFORM="claude-code"; fi
if [ -d ~/.copilot ]; then PLATFORM="${PLATFORM:+$PLATFORM+}copilot-cli"; fi
```

### 2. 创建目录结构
```bash
mkdir -p .agents/skills/project-{agents-context,acceptor,designer,implementer,reviewer,tester}
mkdir -p .agents/tasks .agents/memory .agents/docs
mkdir -p .agents/runtime/{acceptor,designer,implementer,reviewer,tester}/workspace
mkdir -p .agents/runtime/designer/workspace/{research,design-docs,test-specs}
mkdir -p .agents/runtime/acceptor/workspace/{requirements,acceptance-docs,acceptance-reports}
mkdir -p .agents/runtime/reviewer/workspace/review-reports
mkdir -p .agents/runtime/tester/workspace/{test-cases,test-screenshots}
mkdir -p docs
for doc in requirement design test-spec implementation review acceptance; do
  [ -f "docs/${doc}.md" ] || cp ~/.claude/skills/agent-init/templates/docs/${doc}.md docs/ 2>/dev/null || true
done
```

### 3. 初始化状态文件

为每个 Agent 创建 `inbox.json`:
```json
// .agents/runtime/<agent>/inbox.json
{"messages":[]}
```

#### 3b. 初始化 events.db
```bash
sqlite3 .agents/events.db <<'SQL'
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp INTEGER NOT NULL,
  event_type TEXT NOT NULL, agent TEXT, task_id TEXT, tool_name TEXT,
  detail TEXT, created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_task ON events(task_id);
SQL
```
事件类型: `session_start` | `tool_use` | `task_board_write` | `state_change` | `agent_switch` | `message_sent`

### 4. 创建空任务表
- **`.agents/task-board.json`**: `{"version": 0, "tasks": []}`
- **`.agents/task-board.md`**: Markdown 表格 (`| ID | 标题 | 状态 | 负责 | 优先级 | 更新时间 |`), 自动生成勿手动编辑

### 5. 生成项目级 Skills (AI 定制化)

> ⚠️ 由 AI 基于 Step 1 上下文**生成**, 不是从模板拷贝。
> 全局 skill 定义"怎么做", 项目 skill 补充"用什么做"。

**通用要求**: YAML frontmatter 开头, Markdown 格式, 项目相对路径, 实际命令。

#### 5a. `project-agents-context/SKILL.md` — 共享上下文
必须包含: 项目信息 (名称/描述/仓库) | 技术栈 | `project_type` | 常用命令表 | 目录结构 | 分支策略

#### 5b. `project-acceptor/SKILL.md` — 项目级验收
必须包含: 业务背景 | 验收标准基线 (测试/构建/lint/覆盖率) | 验收流程 | 质量红线

#### 5c. `project-designer/SKILL.md` — 项目级设计
必须包含: 现有架构 | 技术约束 (语言版本/框架/兼容性) | 设计文档模板 | API/数据约定

#### 5d. `project-implementer/SKILL.md` — 项目级开发
必须包含: 开发命令表 | 编码规范 (缩进/引号/命名/提交) | 依赖管理 | TDD 工作流

#### 5e. `project-reviewer/SKILL.md` — 项目级审查
必须包含: 审查清单 (构建/测试/lint/安全/风格/测试覆盖) | 项目特有规则 | 审查报告模板

#### 5f. `project-tester/SKILL.md` — 项目级测试
必须包含: 测试框架 | 测试命令表 | 测试文件组织 | 测试策略 | 测试环境

> **项目类型适配**: 根据 Step 1c 检测的 `project_type` 定制每个 skill 的内容:
>
> | 项目类型 | Tester 侧重 | Implementer 侧重 | Designer 侧重 |
> |---------|------------|-----------------|--------------|
> | `ios` | XCTest, UI Testing, SwiftUI Previews | Xcode, Swift Package Manager, SwiftUI/UIKit | MVC/MVVM, Core Data, App Lifecycle |
> | `frontend` | Playwright/Cypress, Jest/Vitest, RTL | npm/pnpm, ESLint, TypeScript strict | 组件架构, 状态管理, API 层设计 |
> | `backend` | API 集成测试, 数据库迁移测试, 负载测试 | ORM, 中间件, 容器化 | 微服务/单体, 数据模型, 认证授权 |
> | `systems` | 单元测试 + 集成测试, Valgrind/Sanitizers | CMake/Cargo, 内存安全, 性能 profile | 模块接口, 内存模型, 线程安全 |
> | `ai-ml` | 模型精度/召回率验证, 数据集分割测试 | Jupyter→.py, 训练管线, GPU 资源 | 模型架构, 数据管线, 实验追踪 |
> | `devops` | Terraform plan 验证, 容器健康检查 | IaC, CI/CD pipeline, 监控告警 | 基础设施拓扑, 安全组, 灾备 |

### 5g. 项目级 Hooks (可选)
如需项目级 hook 覆盖:
```bash
mkdir -p .agents/hooks
for hook in agent-session-start.sh agent-pre-tool-use.sh agent-post-tool-use.sh agent-staleness-check.sh; do
  [ -f ~/.claude/hooks/"$hook" ] && cp ~/.claude/hooks/"$hook" .agents/hooks/ && chmod +x .agents/hooks/"$hook"
done
```

### 5h. 3-Phase 初始化 (仅 workflow_mode = "3phase")

#### 检测 AI CLI 命令
```bash
CLI_COMMAND=""
command -v claude >/dev/null 2>&1 && CLI_COMMAND="claude"
[ -z "$CLI_COMMAND" ] && command -v copilot >/dev/null 2>&1 && CLI_COMMAND="copilot"
[ -z "$CLI_COMMAND" ] && CLI_COMMAND="claude"
```

#### 创建 3-Phase 目录 + 16 Prompt 模板
```bash
mkdir -p .agents/orchestrator/logs .agents/prompts
```
生成 16 prompt 模板 (参考 agent-orchestrator SKILL.md):
- Phase 1: requirements, architecture, tdd-design, dfmea, design-review
- Phase 2: implementing, test-scripting, code-reviewing, ci-monitoring, ci-fixing, device-baseline
- Phase 3: deploying, regression-testing, feature-testing, log-analysis, documentation

占位符: `{PROJECT_DIR}`, `{TASK_ID}`, `{CLI_COMMAND}`, `{BUILD_CMD}`, `{TEST_CMD}`, `{LINT_CMD}`, `{CI_SYSTEM}`, `{CI_URL}`, `{REVIEW_SYSTEM}`, `{REVIEW_CMD}`, `{DEVICE_TYPE}`, `{DEPLOY_CMD}`, `{LOG_CMD}`, `{BASELINE_CMD}`

#### 生成 Orchestrator Daemon
从 `agent-orchestrator/SKILL.md` daemon 模板生成, 替换占位符 → `.agents/orchestrator/run.sh`

#### 3-Phase task-board.json
```json
{"version": 0, "tasks": [], "default_workflow_mode": "3phase"}
```
扩展字段: `workflow_mode`, `phase`, `step`, `parallel_tracks`, `feedback_loops`, `feedback_history`

### 6. 创建 .agents/.gitignore
```
runtime/*/inbox.json
orchestrator/logs/
orchestrator/daemon.pid
!runtime/*/workspace/.gitkeep
```

### 7. 生成/更新项目级 Instructions

> 结合 Step 1 收集的上下文 + 全局框架信息, 生成项目级配置文件。
> 如果文件已存在, **追加**框架相关内容 (不覆盖已有内容)。

#### 7a. CLAUDE.md (Claude Code 项目配置)

生成或追加到项目根目录 `CLAUDE.md`:

```markdown
# Agent Framework Configuration

## 框架信息
- Multi-Agent Framework v3.2.x
- 5 Agent 角色 | 18 Skills | 13 Hooks | 双模式 FSM

## 全局资源
- Agent Profiles: ~/.claude/agents/*.agent.md (含 skills: Per-Agent 隔离)
- Skills: ~/.claude/skills/agent-*/ (18 个, 两级加载: 摘要列表 + 按需全文)
- Hooks: ~/.claude/hooks/ (13 个 Shell 脚本)
- Rules: ~/.claude/rules/ (agent-workflow, commit-standards, security)

## 项目技术栈
<基于 Step 1a 检测结果填写>

## 常用命令
| 命令 | 说明 |
|------|------|
| /agent acceptor | 切换到验收者角色 |
| /agent-init | 初始化 Agent 系统 |
| /agent-task-board | 查看任务看板 |
| /agent-fsm | 查看 FSM 状态机 |

## 项目规范
<基于 Step 1b 已有 CLAUDE.md 内容保留>
```

#### 7b. .github/copilot-instructions.md (Copilot CLI 项目配置)

```bash
mkdir -p .github
```

生成或追加到 `.github/copilot-instructions.md`, 内容与 7a 对应, 但路径替换为 Copilot:
- `~/.claude/` → `~/.copilot/`
- `hooks.json` → `hooks-copilot.json`

#### 7c. 更新 .gitignore

确保框架运行时文件被忽略:
```bash
# 检查项目 .gitignore 是否已包含 .agents 排除
grep -q '.agents/runtime' .gitignore 2>/dev/null || cat >> .gitignore << 'GITIGNORE'

# Multi-Agent Framework runtime (not tracked)
.agents/runtime/*/inbox.json
.agents/events.db
.agents/runtime/.lock
.agents/runtime/.task-board-snapshot.json
GITIGNORE
```

### 8. 输出摘要
```
✅ Agent 系统已初始化
━━━━━━━━━━━━━━━━━━━━━━━
项目: <name> | 技术栈: <detected> | 工作流: <Simple/3-Phase>
Skills: 6 project + 18 global | Runtime: 5 agents | 平台: <Claude Code/Copilot/Both>
CLAUDE.md: ✅ 已生成 | copilot-instructions.md: ✅ 已生成
下一步: Simple → /agent acceptor | 3-Phase → bash .agents/orchestrator/run.sh T-001
```
