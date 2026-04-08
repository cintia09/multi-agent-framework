---
name: agent-config
description: "Agent 配置管理 — 查看/设置 agent 模型偏好、检查平台状态。当用户说「配置 agent」「设置模型」「查看模型配置」「agent config」时激活。"
---

# Agent 配置管理

管理 Multi-Agent Framework 的 agent 配置，包括模型选择、平台检查。

## 配置脚本

使用此 Skill 目录下的 `config.sh` 脚本执行配置操作。

### 查看当前配置

```bash
bash ~/.claude/skills/agent-config/config.sh list
```

输出示例:
```
📋 Agent Model Configuration

  📁 /Users/xxx/.claude/agents:
    acceptor       → (system default)  [需求理解 — sonnet 或 haiku 均可]
    designer       → claude-sonnet-4   [架构设计 — 推荐 sonnet]
    implementer    → (system default)  [编码实现 — sonnet 或 opus]
    reviewer       → (system default)  [代码审查 — 推荐 sonnet]
    tester         → (system default)  [测试 — haiku 即可]

  📁 /Users/xxx/.copilot/agents:
    ...（同上）
```

### 设置模型

```bash
# 设置单个 agent 的模型
bash ~/.claude/skills/agent-config/config.sh set implementer claude-sonnet-4

# 设置所有 agent 使用同一模型
bash ~/.claude/skills/agent-config/config.sh set-all claude-sonnet-4

# 重置单个 agent 为系统默认
bash ~/.claude/skills/agent-config/config.sh reset implementer

# 重置所有 agent
bash ~/.claude/skills/agent-config/config.sh reset-all
```

### 检查平台

```bash
bash ~/.claude/skills/agent-config/config.sh platforms
```

## 支持的模型标识

### Claude Code
- `claude-sonnet-4` — 标准推理，平衡速度和质量
- `claude-haiku-4` — 快速响应，适合简单任务
- `claude-opus-4` — 最强推理，适合复杂设计和审查

### Copilot CLI
- `claude-sonnet-4.5` — 默认模型
- `claude-sonnet-4` — 标准
- `gpt-5` — OpenAI 模型

> 模型标识取决于平台支持。使用 `/model` 命令查看当前平台可用模型列表。

## 模型解析优先级

当 agent 执行任务时，模型按以下优先级解析（高→低）：

1. **任务级** — `task-board.json` 中的 `model_override` 字段
2. **Agent 级** — `.agent.md` frontmatter 的 `model` 字段（本 Skill 管理的）
3. **项目级** — `.agents/project-agents-context/SKILL.md` 中的 `default_model`
4. **系统级** — 平台默认模型

## 交互式配置

当用户要求配置 agent 模型时:

1. 先运行 `config.sh list` 展示当前配置
2. 询问用户要修改哪个 agent（或全部）
3. 询问目标模型
4. 运行 `config.sh set` 命令
5. 再次 `config.sh list` 确认更改

## 注意事项

- 配置同时应用到所有检测到的平台（Claude Code + Copilot CLI）
- `model: ""` 表示使用系统默认模型（推荐，除非有特殊需求）
- `model_hint` 是人类可读提示，不影响模型选择
- 项目级 `.agents/` 中的 agent 文件也会被更新（如果存在）
