---
name: project-agents-context
description: "项目上下文信息, 所有 agent 工作时自动获取。包含技术栈、构建命令、部署方式等。"
---

# 项目上下文

## 项目信息
- **名称**: multi-agent-framework
- **描述**: AI 时代的软件工程流水线框架 — 用 5 个 AI Agent 协作完成完整 SDLC
- **仓库**: git@github.com:cintia09/multi-agent-framework.git
- **分支策略**: `main` (直接推送, 无 PR 流程)

## 技术栈
- **语言**: Bash (shell scripts), Markdown (skills/docs), JSON (state/config)
- **框架**: 自研 Agent 协作框架 (FSM + Task Board + Memory + Messaging)
- **样式/UI**: N/A (CLI 框架, 无前端)
- **数据库**: SQLite (events.db 审计日志)
- **测试**: 自研 bash 测试套件 (`tests/run-all.sh`)
- **CI**: N/A (本地开发为主)
- **部署**: `install.sh` 一键安装到 `~/.claude/`

## 常用命令
| 操作 | 命令 |
|------|------|
| 运行测试 | `bash tests/run-all.sh` |
| 检查安装 | `bash install.sh --check` |
| 安装框架 | `bash install.sh --full` |
| 卸载框架 | `bash install.sh --uninstall` |
| 验证脚本 | `bash scripts/verify-install.sh` |

## 目录结构
| 目录 | 用途 |
|------|------|
| `skills/` | 12 个全局 Agent Skills (SKILL.md 定义行为) |
| `agents/` | 5 个 Agent Profile (角色定义) |
| `hooks/` | Shell hooks (边界执行、审计、安全扫描) |
| `scripts/` | 工具脚本 (验证安装等) |
| `tests/` | 测试套件 (skills/agents/hooks 格式验证) |
| `docs/` | 项目级活文档 (需求、设计、测试、实现、审查、验收) |
| `.agents/` | 运行时目录 (任务表、状态、记忆、项目级 skills) |
| `blog/` | 架构图等资源 |

## 项目约定
- 所有 commit message 必须英文
- commit 必须包含 `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`
- Skills 以 YAML frontmatter 开头
- Agent profiles 以 `.agent.md` 为后缀
- Hook 脚本必须有 `+x` 权限
