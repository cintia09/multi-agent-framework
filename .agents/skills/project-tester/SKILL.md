---
name: project-tester
description: "本项目的测试框架和测试策略。测试者 agent 工作时加载。"
---

# 项目级测试指南

## 测试框架
- **单元测试**: Bash 测试脚本 (`tests/test-*.sh`)
- **集成测试**: `tests/run-all.sh` 运行全部
- **E2E 测试**: N/A (CLI 框架, 无 UI)

## 测试命令
| 操作 | 命令 |
|------|------|
| 全部测试 | `bash tests/run-all.sh` |
| Skills 格式 | `bash tests/test-skills.sh` |
| Agents 格式 | `bash tests/test-agents.sh` |
| Hooks 格式 | `bash tests/test-hooks.sh` |
| 安装验证 | `bash install.sh --check` |

## 测试文件组织
- **位置**: `tests/`
- **命名**: `test-*.sh`
- **Runner**: `run-all.sh` (汇总所有 test-*.sh)
- **输出**: `✅` 通过 / `❌` 失败, 非零退出码表示失败

## 测试策略
- **新 Skill**: 验证 SKILL.md 有 frontmatter, 内容非空
- **新 Hook**: 验证有 `+x` 权限, 可执行
- **新 Agent Profile**: 验证 `.agent.md` 后缀, 内容非空
- **Goal 验证**: 读取 task-board.json goals, 逐条对照实际文件
- **回归**: 修改现有 skill 后重新运行全部测试

## 验证规则
| 目标 | 验证方法 |
|------|----------|
| SKILL.md 格式 | 检查 `---` frontmatter 存在 |
| JSON 合法 | `python3 -m json.tool < file.json` |
| Hook 权限 | `test -x hooks/*.sh` |
| Agent profile | 检查 `.agent.md` 文件存在且非空 |
| Task board | JSON 有 `version` 和 `tasks` 字段 |
