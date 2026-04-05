# Multi-Agent Software Development Framework

## 安装说明

本项目提供 5 角色 Agent 协作框架。安装到本地后, 任何项目都可以通过 `/init` 自动初始化 Agent 系统。

### 安装步骤

当用户说 "帮我将这个 repo 里的 agents 安装到我本地" 或 "安装 agent 框架" 时, 执行以下操作:

1. **复制 skills 文件**:
```bash
cp skills/agent-*.md ~/.copilot/skills/
```

2. **追加全局指令** (如果 `~/.copilot/copilot-instructions.md` 中还没有 "Multi-Agent 协作规则"):
```bash
cat docs/agent-rules.md >> ~/.copilot/copilot-instructions.md
```

3. **验证安装**:
```bash
ls ~/.copilot/skills/agent-*.md | wc -l   # 应该是 10
grep "Multi-Agent" ~/.copilot/copilot-instructions.md  # 应该匹配
```

4. 输出: "✅ Agent 框架已安装。去任何项目目录, 说 '初始化 Agent 系统' 即可。"

### 项目初始化

安装完成后, 在任何项目目录中说 "初始化 Agent 系统", 将自动:
- 创建 `.copilot/agents/` 目录 (5 个角色)
- 创建 `task-board.json` 和 `task-board.md`
- 初始化每个 Agent 的 `state.json` 和 `inbox.json`
- 检测项目技术栈并生成定制化 instructions

详细流程参见 `~/.copilot/skills/agent-init.md`。

## 框架概述

### 5 个 Agent 角色
| 角色 | 命令 | 职责 |
|------|------|------|
| 🎯 验收者 | "切换到验收者" | 需求收集、任务发布、验收测试 |
| 🏗️ 设计者 | "切换到设计者" | 架构设计、技术调研、测试规格 |
| 💻 实现者 | "切换到实现者" | TDD 开发、Bug 修复 |
| 🔍 审查者 | "切换到审查者" | 代码审查、安全审计 |
| 🧪 测试者 | "切换到测试者" | 测试用例、E2E 测试、问题报告 |

### 任务流转
```
created → designing → implementing → reviewing → testing → accepting → accepted ✅
```

### 功能目标清单 (goals)
- 每个任务包含多个功能目标 (goals)
- 实现者: 所有 goals 为 `done` 才能提交审查
- 验收者: 所有 goals 为 `verified` 才能标记验收通过

### 文件结构
项目初始化后生成:
```
<project>/.copilot/
├── task-board.json         # 任务表 (机器读)
├── task-board.md           # 任务表 (人读)
├── tasks/T-NNN.json        # 任务详情 (含 goals)
└── agents/
    └── <role>/
        ├── state.json      # Agent 状态
        ├── inbox.json      # 消息收件箱
        └── workspace/      # 工作产出物
```
