# Multi-Agent 协作框架 — 项目初始化指引

> 本文件由全局安装放置于 `~/.copilot/AGENTS.md`。当用户在任何项目中执行 `/init` 时, Copilot 应读取此文件并自动执行项目级 Agent 初始化。

## /init 自动执行指令

当在任何项目中执行 `/init` 且检测到此文件存在时, **请自动执行以下项目初始化**:

### Step 1: 检查是否已初始化
```bash
ls .copilot/task-board.json 2>/dev/null
```
- 如果已存在 → 输出 "⚠️ Agent 系统已初始化" + 状态摘要, 不覆盖
- 如果不存在 → 继续 Step 2

### Step 2: 检测项目信息
- 语言/框架: package.json, Cargo.toml, requirements.txt, go.mod 等
- 测试框架: jest, playwright, pytest, vitest 等
- CI: .github/workflows/, .gitlab-ci.yml 等
- 部署: Dockerfile, docker-compose, k8s/ 等

### Step 3: 创建项目 Agent 目录
```bash
mkdir -p .copilot/tasks
mkdir -p .copilot/agents/acceptor/workspace/{requirements,acceptance-docs,acceptance-reports}
mkdir -p .copilot/agents/designer/workspace/{research,design-docs,test-specs}
mkdir -p .copilot/agents/implementer/workspace
mkdir -p .copilot/agents/reviewer/workspace/review-reports
mkdir -p .copilot/agents/tester/workspace/{test-cases,test-screenshots}
```

### Step 4: 初始化状态文件
为每个 Agent (acceptor, designer, implementer, reviewer, tester) 创建:

**state.json**:
```json
{
  "agent": "<name>",
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

### Step 5: 创建空任务表
**task-board.json**: `{"version": 0, "tasks": []}`

**task-board.md**:
```markdown
# 📋 项目任务表
> 自动生成, 请勿手动编辑。
| ID | 标题 | 状态 | 负责 | 优先级 | 更新时间 |
|----|------|------|------|--------|---------|
_暂无任务_
```

### Step 6: 生成项目定制化 instructions
读取 `~/.copilot/agents/<role>/instructions.md` (全局模板), 结合 Step 2 检测到的项目信息, 为每个 Agent 生成 `.copilot/agents/<role>/instructions.md`:

定制化内容包括:
- 项目名称和技术栈
- 项目特定的构建/测试命令 (如 `npm run build`, `npx playwright test`)
- 项目特定的部署方式 (如 Docker, SSH 等)
- 已有的测试配置和 CI 集成方式
- 项目的目录结构和代码组织

### Step 7: 创建 .gitignore
```
agents/*/state.json
agents/*/inbox.json
```

### Step 8: 输出摘要
```
✅ Agent 系统已初始化
━━━━━━━━━━━━━━━━━━━━━━━
项目: <name>
技术栈: <detected>
Agent: 5 个角色已就绪 (all idle)
任务表: .copilot/task-board.json (空)
━━━━━━━━━━━━━━━━━━━━━━━
下一步: 说 "切换到验收者" 开始创建需求
```

---

## 框架概述

### 5 个 Agent 角色
| 角色 | 触发方式 | 职责 |
|------|---------|------|
| 🎯 验收者 | "切换到验收者" | 需求、任务发布、验收 |
| 🏗️ 设计者 | "切换到设计者" | 架构设计、测试规格 |
| 💻 实现者 | "切换到实现者" | TDD 开发、Bug 修复 |
| 🔍 审查者 | "切换到审查者" | 代码审查、安全审计 |
| 🧪 测试者 | "切换到测试者" | 测试、问题报告 |

### 任务流转
```
created → designing → implementing → reviewing → testing → accepting → accepted ✅
```

### 目标清单 (goals)
每个任务包含功能目标清单:
- 实现者: 所有 goals `done` → 提交审查
- 验收者: 所有 goals `verified` → 标记验收通过
