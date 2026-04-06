---
name: project-implementer
description: "Multi-Agent Framework 编码规范。实现者 agent 工作时加载。"
---

# 项目实现上下文

## 文件类型规范

### SKILL.md
- 必须以 YAML front matter 开头 (`---name:...---`)
- 使用 Markdown 格式
- 描述 skill 的触发条件、执行步骤、输出格式

### .agent.md
- Agent profile 格式
- 定义角色名、描述、行为指令

### Shell hooks
- 必须以 `#!/bin/bash` 开头
- 使用 `set -e` 严格模式
- 从 stdin 读取 JSON (`INPUT=$(cat)`)
- 通过 jq 解析输入参数
- 语法检查: `bash -n <script.sh>`

## 提交规范
- 英文 commit messages
- 格式: `type(scope): description`
- Co-authored-by trailer required
