---
name: agent-init
description: "初始化项目的 Agent 配置。在项目目录下调用 '/init agents' 或说 '初始化 Agent 系统' 使用。"
---

# 项目 Agent 初始化

## 前置条件
- 当前目录是一个项目根目录 (有 git 仓库或 package.json 等)
- 全局 skills 已安装 (agent-*.md 在 ~/.copilot/skills/)

## 执行步骤

### 0. 检查是否已初始化
```bash
ls .copilot/task-board.json 2>/dev/null
```
- **如果已存在**: 说明 Agent 系统已初始化。输出 "⚠️ Agent 系统已初始化, 跳过。" + 当前状态摘要 (调用 agent-switch 的状态面板)。**不覆盖任何文件** (保护已有的 state/inbox/task-board 数据)。
- **如果不存在**: 执行全新初始化 (Step 1-7)。

### 1. 检测项目信息
```bash
# 检测语言和框架
ls package.json Cargo.toml requirements.txt go.mod pom.xml 2>/dev/null
# 检测测试框架
ls jest.config* playwright.config* pytest.ini vitest.config* 2>/dev/null
# 检测 CI
ls .github/workflows/*.yml .gitlab-ci.yml 2>/dev/null
# 检测部署
ls Dockerfile docker-compose* k8s/ 2>/dev/null
```

### 2. 创建目录结构
```bash
mkdir -p .copilot/tasks
mkdir -p .copilot/agents/acceptor/workspace/{requirements,acceptance-docs,acceptance-reports}
mkdir -p .copilot/agents/designer/workspace/{research,design-docs,test-specs}
mkdir -p .copilot/agents/implementer/workspace
mkdir -p .copilot/agents/reviewer/workspace/review-reports
mkdir -p .copilot/agents/tester/workspace/{test-cases,test-screenshots}
```

### 3. 初始化状态文件
为每个 Agent 创建 state.json, inbox.json:

**state.json** (每个 agent 相同模板):
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

**inbox.json** (每个 agent 相同):
```json
{
  "messages": []
}
```

### 4. 创建空任务表
**task-board.json**:
```json
{
  "version": 0,
  "tasks": []
}
```

**task-board.md**:
```markdown
# 📋 项目任务表

> 自动生成, 请勿手动编辑。

| ID | 标题 | 状态 | 负责 | 优先级 | 更新时间 |
|----|------|------|------|--------|---------|

_暂无任务_
```

### 5. 生成项目定制化 instructions
基于检测到的项目信息, 为每个 Agent 生成 `agents/<name>/instructions.md`:
- 包含项目名称和技术栈信息
- 引用项目特定的路径、命令和约定
- 引用已有的测试/CI 配置

### 6. 创建 .gitignore (在 .copilot/ 目录)
```
# Agent runtime state (不提交到 git)
agents/*/state.json
agents/*/inbox.json

# 保留目录结构
!agents/*/workspace/.gitkeep
```

### 7. 输出摘要
```
✅ Agent 系统已初始化
━━━━━━━━━━━━━━━━━━━━━━━
项目: <name>
路径: <project>/.copilot/
技术栈: <detected>
Agent: 5 个角色已就绪 (all idle)
任务表: .copilot/task-board.json (空)
━━━━━━━━━━━━━━━━━━━━━━━
下一步: 使用 '/agent acceptor' 开始创建需求
```
