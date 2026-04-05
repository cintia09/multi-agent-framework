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

### 1. 检测项目信息
```bash
# 语言/框架
ls package.json Cargo.toml requirements.txt go.mod pom.xml 2>/dev/null
# 测试框架
ls jest.config* playwright.config* pytest.ini vitest.config* 2>/dev/null
# CI/CD
ls .github/workflows/*.yml .gitlab-ci.yml 2>/dev/null
# 部署
ls Dockerfile docker-compose* k8s/ 2>/dev/null
```
将检测结果记录下来, 用于后续定制化。

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

### 5. 创建项目级 Skills

基于 Step 1 检测到的项目信息, 创建 **6 个项目级 skill**:

#### 5a. `skills/project-agents-context/SKILL.md` — 项目上下文
```yaml
---
name: project-agents-context
description: "项目上下文信息, 所有 agent 工作时自动获取。包含技术栈、构建命令、部署方式等。"
---
```
内容: 项目名称、技术栈、构建命令、测试命令、部署方式、分支策略、目录结构

#### 5b. `skills/project-acceptor/SKILL.md` — 项目级验收者
```yaml
---
name: project-acceptor
description: "本项目的验收标准和业务背景。验收者 agent 工作时加载。"
---
```
内容: 业务背景、目标用户、验收标准、质量基线

#### 5c. `skills/project-designer/SKILL.md` — 项目级设计者
```yaml
---
name: project-designer
description: "本项目的架构约束和技术选型。设计者 agent 工作时加载。"
---
```
内容: 现有架构、技术约束、API 规范

#### 5d. `skills/project-implementer/SKILL.md` — 项目级实现者
```yaml
---
name: project-implementer
description: "本项目的编码规范和开发命令。实现者 agent 工作时加载。"
---
```
内容: 编码规范、开发命令 (build/test/lint)、提交规范、依赖管理

#### 5e. `skills/project-reviewer/SKILL.md` — 项目级审查者
```yaml
---
name: project-reviewer
description: "本项目的审查标准和代码质量要求。审查者 agent 工作时加载。"
---
```
内容: 代码质量标准、安全审查清单、lint 规则

#### 5f. `skills/project-tester/SKILL.md` — 项目级测试者
```yaml
---
name: project-tester
description: "本项目的测试框架和测试策略。测试者 agent 工作时加载。"
---
```
内容: 测试框架、测试命令、覆盖率要求、E2E 环境

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
