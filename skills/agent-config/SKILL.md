---
name: agent-config
description: "Agent 配置管理 — 查看/设置 agent 模型、工具权限、平台状态。当用户说「配置 agent」「设置模型」「配置工具」「agent config」「/agent-config」时激活。"
---

# Agent 配置管理

管理 Multi-Agent Framework 的 agent 配置。支持 model 和 tools 两个维度，同时应用到所有平台。

## 配置脚本

脚本路径: `~/.claude/skills/agent-config/config.sh`（Claude Code）或 `~/.copilot/skills/agent-config/config.sh`（Copilot）

### 查看配置

```bash
# 查看全部 agent 配置（model + tools）
bash ~/.claude/skills/agent-config/config.sh list

# 查看单个 agent 详细配置
bash ~/.claude/skills/agent-config/config.sh get implementer

# 查看检测到的平台
bash ~/.claude/skills/agent-config/config.sh platforms
```

### 模型配置

```bash
# 设置单个 agent 的模型
bash ~/.claude/skills/agent-config/config.sh model set implementer claude-sonnet-4

# 设置所有 agent 使用同一模型
bash ~/.claude/skills/agent-config/config.sh model set-all claude-sonnet-4

# 重置单个 agent 为系统默认
bash ~/.claude/skills/agent-config/config.sh model reset implementer

# 重置所有 agent 模型
bash ~/.claude/skills/agent-config/config.sh model reset-all
```

### 工具配置

控制每个 agent 可使用的工具。在 Copilot CLI 中，`tools` 字段由平台原生执行；在 Claude Code 中作为指导性约束。

```bash
# 查看 agent 的工具列表
bash ~/.claude/skills/agent-config/config.sh tools get reviewer

# 设置工具（逗号分隔）— 限制 reviewer 只能读和搜索
bash ~/.claude/skills/agent-config/config.sh tools set reviewer read,search,grep,glob

# 添加单个工具
bash ~/.claude/skills/agent-config/config.sh tools add reviewer view

# 移除单个工具
bash ~/.claude/skills/agent-config/config.sh tools rm reviewer edit

# 重置（移除限制，允许所有工具）
bash ~/.claude/skills/agent-config/config.sh tools reset reviewer
```

### 推荐工具配置（内置 agent 参考）

| Agent | 推荐 tools 设置 | 说明 |
|-------|-----------------|------|
| acceptor | (all) | 需要完整访问来验收功能 |
| designer | read,search,grep,glob,view | 只读 — 设计阶段不修改代码 |
| implementer | (all) | 需要完整读写+执行能力 |
| reviewer | read,search,grep,glob,view | 只读 — 审查不修改 |
| tester | read,search,grep,glob,view,bash | 可读可执行测试，不直接编辑 src |

> 自定义 agent 的工具配置由用户自行决定。使用 `config.sh tools set <agent> <tools>` 配置。

## 模型解析优先级

当 agent 执行任务时，模型按以下优先级解析（高→低）：

1. **任务级** — `task-board.json` 中的 `model_override` 字段
2. **Agent 级** — `.agent.md` frontmatter 的 `model` 字段（本 Skill 管理的）
3. **项目级** — `.agents/project-agents-context/SKILL.md` 中的 `default_model`
4. **系统级** — 平台默认模型（Claude Code 或 Copilot CLI 的全局设置）

## 交互式配置

当用户要求配置 agent 时:

1. **先运行发现命令**获取实际 agent 列表:
   ```bash
   bash ~/.claude/skills/agent-config/config.sh list
   ```
   > ⚠️ 不要假设只有 5 个 agent。用户可能添加了自定义 agent（如 `security-auditor.agent.md`）。始终从 `config.sh list` 的输出中动态获取 agent 列表。

2. 向用户展示 `config.sh list` 的**完整输出**（包括所有检测到的 agent）
3. 询问用户要配置什么（模型/工具/两者都配）
4. 询问目标 agent — **列出所有从 step 1 发现的 agent**，加上"全部"选项
5. 执行对应命令
6. 再次运行 `config.sh list` 确认更改

## 注意事项

- Agent 列表是**动态发现**的 — config.sh 扫描所有平台目录中的 `*.agent.md` 文件
- 所有更改同时应用到 `~/.claude/agents/` 和 `~/.copilot/agents/`
- `model: ""` = 使用系统默认模型
- `tools` 字段省略 = 不限制工具（agent 可使用所有工具）
- Copilot CLI 原生执行 `tools` 限制；Claude Code 通过 hooks 辅助执行
- 使用 `/model` 命令（两个平台都支持）查看当前可用模型列表
