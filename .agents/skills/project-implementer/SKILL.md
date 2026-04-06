---
name: project-implementer
description: "本项目的编码规范和开发命令。实现者 agent 工作时加载。"
---

# 项目级开发指南

## 开发命令
| 操作 | 命令 | 说明 |
|------|------|------|
| 运行测试 | `bash tests/run-all.sh` | 3 个测试 (skills/agents/hooks) |
| 单个测试 | `bash tests/test-skills.sh` | 验证 SKILL.md 格式 |
| 检查安装 | `bash install.sh --check` | 验证 ~/.claude/ 中的安装状态 |
| 安装到本地 | `bash install.sh --full` | 从 GitHub 克隆并安装 |

## 编码规范
- **Shell**: `set -euo pipefail` 开头, 使用函数封装逻辑
- **Markdown**: YAML frontmatter 必须有 `name` 和 `description`
- **JSON**: 2 空格缩进, `ensure_ascii=False` (保留中文)
- **命名**: kebab-case (文件/目录), snake_case (JSON 字段)
- **提交**: 英文 commit message + Co-authored-by trailer

## 文件类型指南
| 文件类型 | 位置 | 规范 |
|----------|------|------|
| Skill | `skills/agent-*/SKILL.md` | YAML frontmatter + 步骤化 Markdown |
| Agent Profile | `agents/*.agent.md` | 角色 persona 定义 |
| Hook | `hooks/*.sh` | Bash 脚本, 需 `+x`, 读 stdin JSON |
| Test | `tests/test-*.sh` | Bash, 输出 ✅/❌, 非零退出码表示失败 |
| Doc | `docs/*.md` | 项目级活文档, 追加模式 |

## TDD 工作流 (项目适配)
1. 测试文件: `tests/test-*.sh`
2. 写新 test case → `bash tests/run-all.sh` 确认红灯
3. 实现功能
4. `bash tests/run-all.sh` 确认绿灯
5. 重构 (保持绿灯)

## 依赖管理
- **无包管理器**: 框架零外部依赖
- 所有工具: bash, sqlite3, python3 (系统自带)
- 新 skill/hook 只需创建文件, 无需安装步骤
