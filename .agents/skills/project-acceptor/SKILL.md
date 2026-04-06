---
name: project-acceptor
description: "本项目的验收标准和业务背景。验收者 agent 工作时加载。"
---

# 项目级验收指南

## 业务背景
Multi-Agent Framework 是一个 AI 软件工程流水线框架。目标用户是使用 Claude Code 的开发者，通过 5 个专业化 Agent 角色协作完成 SDLC（需求→设计→实现→审查→测试→验收）。核心价值是解决 AI context window 有限的问题，通过跨 Agent 记忆和 FSM 状态机保障工程质量。

## 验收标准基线
- **功能测试**: `bash tests/run-all.sh` — 全部通过
- **构建检查**: N/A (无编译步骤, 全 shell/markdown)
- **Lint 检查**: 无自动 linter, 手动检查 SKILL.md frontmatter 格式
- **覆盖率要求**: 测试套件覆盖 skills/agents/hooks 格式验证

## 验收流程
1. 读取任务的 goals 列表
2. 逐条验证每个 goal 的 `description` 是否在代码中体现
3. 运行 `bash tests/run-all.sh` 确认全部通过
4. 检查 SKILL.md 文件有 YAML frontmatter
5. 检查 hooks 有 `+x` 权限
6. 标记 goals `met: true`, task status → `accepted`

## 质量红线
- 不允许删除现有 skill 内容 (只能追加/增强)
- 不允许破坏 FSM 状态转换逻辑
- Commit message 必须英文
- 不允许在 .agents/ 中硬编码绝对路径
