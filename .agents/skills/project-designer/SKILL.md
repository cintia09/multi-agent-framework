---
name: project-designer
description: "本项目的架构约束和技术选型。设计者 agent 工作时加载。"
---

# 项目级设计指南

## 现有架构
- **类型**: 单体 CLI 框架 (非 web 服务)
- **入口**: `install.sh` (安装), Agent skills (运行时行为定义)
- **数据流**: Task Board (JSON) → FSM 状态机 → Agent Skills → Memory → Events.db
- **运行模式**: Claude Code 会话内, Agent 读取 SKILL.md 执行工作流

## 技术约束
- **Shell 兼容**: Bash 4+ (macOS/Linux)
- **JSON 处理**: 通过 Python3 `json` 模块 (不依赖 jq)
- **SQLite**: 系统自带, 用于 events.db
- **无外部依赖**: 不引入 npm/pip/cargo 等包管理器

## 设计文档规范
设计文档输出到 `.agents/runtime/designer/workspace/design-docs/` 并包含:
1. 需求摘要 (引用 goal ID)
2. 技术方案 (含备选方案对比)
3. 文件变更列表 (新增/修改/删除)
4. 测试规格 (输出到 `test-specs/`)
5. ADR 格式: Context → Decision → Consequences

## 架构原则
- Skills 是 "documentation as code" — SKILL.md 即是文档也是行为定义
- Agent profiles 定义角色 persona, skills 定义工作流
- 状态持久化: JSON 文件 (task-board, state, inbox, memory)
- 审计日志: SQLite events.db (不可变追加)
- 一切操作通过 FSM guard 验证合法性
