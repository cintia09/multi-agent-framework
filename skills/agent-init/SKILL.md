---
name: agent-init
description: "初始化项目的 Agent 协作系统。说 '初始化 Agent 系统' 触发。检测项目技术栈, 创建运行时目录和项目级 skill。"
---

# 项目 Agent 初始化

## 前置条件
- 当前目录是一个项目根目录 (有 git 仓库或 package.json 等)
- 全局 skills 已安装 (`~/.copilot/skills/agent-*/SKILL.md`)
- 全局 agents 已安装 (`~/.copilot/agents/*.agent.md`)

## 执行步骤

### 0. 检查是否已初始化
```bash
ls .copilot/task-board.json 2>/dev/null
```
- **如果已存在**: 输出 "⚠️ Agent 系统已初始化, 跳过。" + 当前状态摘要。**不覆盖任何文件**。
- **如果不存在**: 执行全新初始化 (Step 1-8)。

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

### 2. 创建运行时目录结构
```bash
mkdir -p .copilot/tasks
mkdir -p .copilot/agents/acceptor/workspace/{requirements,acceptance-docs,acceptance-reports}
mkdir -p .copilot/agents/designer/workspace/{research,design-docs,test-specs}
mkdir -p .copilot/agents/implementer/workspace
mkdir -p .copilot/agents/reviewer/workspace/review-reports
mkdir -p .copilot/agents/tester/workspace/{test-cases,test-screenshots}
```

### 3. 初始化状态文件
为每个 Agent (acceptor, designer, implementer, reviewer, tester) 创建:

**state.json**:
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

**inbox.json**:
```json
{"messages": []}
```

### 4. 创建空任务表
**task-board.json**:
```json
{"version": 0, "tasks": []}
```

**task-board.md**:
```markdown
# 📋 项目任务表

> 自动生成, 请勿手动编辑。

| ID | 标题 | 状态 | 负责 | 优先级 | 更新时间 |
|----|------|------|------|--------|---------|

_暂无任务_
```

### 5. 创建项目级 Skills (`.github/skills/`)

基于 Step 1 检测到的项目信息, 在 `.github/skills/` 下创建 **6 个项目级 skill**:

#### 5a. `project-agents-context/SKILL.md` — 项目上下文
```yaml
---
name: project-agents-context
description: "项目上下文信息, 所有 agent 工作时自动获取。包含技术栈、构建命令、部署方式等。"
---
```
内容包含:
- 项目名称、仓库地址
- 技术栈 (语言、框架、数据库)
- 构建命令 (如 `npm run build`)
- 测试命令 (如 `npx playwright test`)
- 部署方式 (如 Docker, SSH)
- 分支策略 (如 main/dev)
- 目录结构概览

#### 5b. `project-acceptor/SKILL.md` — 项目级验收者
```yaml
---
name: project-acceptor
description: "本项目的验收标准和业务背景。验收者 agent 工作时加载。"
---
```
内容包含:
- 项目业务背景和目标用户
- 验收标准和质量基线
- 关键业务流程描述

#### 5c. `project-designer/SKILL.md` — 项目级设计者
```yaml
---
name: project-designer
description: "本项目的架构约束和技术选型。设计者 agent 工作时加载。"
---
```
内容包含:
- 现有架构描述
- 技术选型和约束
- 已有的设计文档和 API 规范

#### 5d. `project-implementer/SKILL.md` — 项目级实现者
```yaml
---
name: project-implementer
description: "本项目的编码规范和开发命令。实现者 agent 工作时加载。"
---
```
内容包含:
- 编码规范 (lint 配置、格式化工具)
- 开发常用命令 (build, test, lint, start)
- 提交规范 (分支、commit message)
- 依赖管理方式

#### 5e. `project-reviewer/SKILL.md` — 项目级审查者
```yaml
---
name: project-reviewer
description: "本项目的审查标准和代码质量要求。审查者 agent 工作时加载。"
---
```
内容包含:
- 代码质量标准 (覆盖率、圈复杂度)
- 安全审查清单
- 项目特定的 lint 规则

#### 5f. `project-tester/SKILL.md` — 项目级测试者
```yaml
---
name: project-tester
description: "本项目的测试框架和测试策略。测试者 agent 工作时加载。"
---
```
内容包含:
- 测试框架和配置 (如 Playwright config)
- 测试运行命令
- 覆盖率要求
- E2E 测试环境配置

### 6. 创建 .copilot/.gitignore
```
# Agent runtime state (不提交到 git)
agents/*/state.json
agents/*/inbox.json

# 保留目录结构
!agents/*/workspace/.gitkeep
```

### 7. 创建 .github/skills/.gitignore (可选)
如果 `.github/skills/` 是新创建的, 确保不会与已有的 .gitignore 冲突。

### 8. 输出摘要
```
✅ Agent 系统已初始化
━━━━━━━━━━━━━━━━━━━━━━━
项目: <name>
路径: <project>/
技术栈: <detected>
━━━━━━━━━━━━━━━━━━━━━━━
运行时: .copilot/ (5 agents, all idle)
Skills: .github/skills/ (6 project skills created)
任务表: .copilot/task-board.json (空)
━━━━━━━━━━━━━━━━━━━━━━━
下一步: /agent acceptor → 开始创建需求
```
