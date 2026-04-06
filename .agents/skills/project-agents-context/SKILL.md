---
name: project-agents-context
description: "Multi-Agent Framework 项目上下文。所有 agent 工作时自动加载。"
---

# 项目上下文: Multi-Agent Framework

## 基本信息
- **项目**: multi-agent-framework — AI 辅助软件开发的多 Agent 协作框架
- **仓库**: cintia09/multi-agent-framework (branch: main)
- **性质**: 框架/工具库 (不是应用)

## 技术栈
- **语言**: Bash (hooks), Markdown (skills, docs), JSON (state)
- **依赖**: 零依赖 — 仅需 bash, jq, sqlite3
- **结构**: skills/ (SKILL.md), agents/ (.agent.md), hooks/ (shell), docs/

## 目录结构
```
agents/          # 5 个 .agent.md (Agent profile)
skills/          # 10 个 skill 目录 (每个含 SKILL.md)
hooks/           # 4 个 shell 脚本 (session-start, pre/post-tool-use, staleness)
docs/            # agent-rules.md (协作规则)
AGENTS.md        # 安装指引
README.md        # 项目文档
```

## 构建与测试
- 无构建步骤 (纯文本文件)
- 测试: `bash -n hooks/*.sh` (语法检查)
- 验证: 确保所有 SKILL.md 有正确的 YAML front matter

## 发布
- Push to main 即发布
- 用户通过 AGENTS.md 安装指引自动安装
