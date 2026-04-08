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
```

#### 1c. 选择工作流模式
询问用户: Simple (线性 SDLC) 或 3-Phase (三阶段工程闭环)
- 选择 1 → `workflow_mode: "simple"` (默认)
- 选择 2 → `workflow_mode: "3phase"` (执行 Step 5h)

#### 1d. 读取全局 agent profiles & skills
```bash
for f in acceptor designer implementer reviewer tester; do cat ~/.claude/agents/${f}.agent.md; done
for f in agent-acceptor agent-designer agent-implementer agent-reviewer agent-tester agent-fsm agent-task-board; do cat ~/.claude/skills/${f}/SKILL.md; done
```

### 2. 创建目录结构
```bash
mkdir -p .agents/skills/project-{agents-context,acceptor,designer,implementer,reviewer,tester}
mkdir -p .agents/tasks .agents/memory
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

为每个 Agent 创建 `state.json` 和 `inbox.json`:
```json
// .agents/runtime/<agent>/state.json
{"agent":"<name>","status":"idle","current_task":null,"sub_state":null,"queue":[],"last_activity":"<ISO>","version":0,"error":null}
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

### 4. 创建空任务表
```json
// .agents/task-board.json
{"version": 0, "tasks": []}
```

### 5. 生成项目级 Skills (AI 定制化)

> ⚠️ 由 AI 基于 Step 1 上下文**生成**, 不是从模板拷贝。
> 全局 skill 定义"怎么做", 项目 skill 补充"用什么做"。

**通用要求**: YAML frontmatter 开头, Markdown 格式, 项目相对路径, 实际命令。

#### 5a. `project-agents-context/SKILL.md` — 共享上下文
必须包含: 项目信息 (名称/描述/仓库) | 技术栈 | 常用命令表 | 目录结构 | 分支策略

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
runtime/*/state.json
runtime/*/inbox.json
orchestrator/logs/
orchestrator/daemon.pid
!runtime/*/workspace/.gitkeep
```

### 7. 输出摘要
```
✅ Agent 系统已初始化
━━━━━━━━━━━━━━━━━━━━━━━
项目: <name> | 技术栈: <detected> | 工作流: <Simple/3-Phase>
Skills: 6 project skills | Runtime: 5 agents (idle) | Memory: 空
下一步: Simple → /agent acceptor | 3-Phase → bash .agents/orchestrator/run.sh T-001
```
