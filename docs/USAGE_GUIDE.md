# 🤖 Multi-Agent Framework 使用指南

> AI 时代的软件工程流水线框架 — 用 5 个 AI Agent 协作完成完整 SDLC

---

## 目录

1. [快速开始](#1-快速开始)
2. [核心概念](#2-核心概念)
3. [工作流详解](#3-工作流详解)
4. [高级功能](#4-高级功能)
5. [命令参考](#5-命令参考)
6. [最佳实践](#6-最佳实践)
7. [配置参考](#7-配置参考)
8. [3-Phase 工程闭环使用指南](#8-3-phase-工程闭环使用指南)

---

## 1. 快速开始

### 1.1 安装

**一键安装（推荐）：**
```bash
curl -sL https://raw.githubusercontent.com/cintia09/multi-agent-framework/main/install.sh | bash
```

**手动安装：**
```bash
git clone https://github.com/cintia09/multi-agent-framework.git /tmp/maf
cp -r /tmp/maf/skills/agent-* ~/.claude/skills/
cp /tmp/maf/agents/*.agent.md ~/.claude/agents/
cp /tmp/maf/hooks/*.sh ~/.claude/hooks/
cp /tmp/maf/hooks/hooks.json ~/.claude/hooks/
chmod +x ~/.claude/hooks/*.sh
```

**验证安装：**
```bash
bash install.sh --check
# 输出:
#   Skills: 18/18
#   Agents: 5/5
#   Hooks:  13
#   hooks.json: ✅
```

### 1.2 初始化项目

在任何项目根目录中，对 Claude Code 说：

```
初始化 Agent 系统
```

Agent 会自动：
1. 检测项目技术栈（语言、框架、测试工具、CI/CD）
2. 创建 `.agents/` 运行时目录
3. 生成 6 个项目级 Skills（基于检测到的技术栈定制）
4. 初始化空任务表、事件数据库、Agent 状态文件
5. 创建 `docs/` 活文档模板

**初始化后的目录结构：**
```
.agents/
├── skills/                    # 项目级 Skills（AI 定制化）
│   ├── project-agents-context/  # 共享项目上下文
│   ├── project-acceptor/        # 验收者项目指南
│   ├── project-designer/        # 设计者项目指南
│   ├── project-implementer/     # 实现者项目指南
│   ├── project-reviewer/        # 审查者项目指南
│   └── project-tester/          # 测试者项目指南
├── runtime/                   # Agent 运行时状态
│   ├── active-agent             # 当前激活的角色
│   ├── acceptor/                # 验收者工作区
│   ├── designer/                # 设计者工作区
│   ├── implementer/             # 实现者工作区
│   ├── reviewer/                # 审查者工作区
│   └── tester/                  # 测试者工作区
├── memory/                    # 记忆系统
│   ├── PROJECT_MEMORY.md        # 项目级记忆
│   ├── index.sqlite             # FTS5 搜索索引
│   └── {role}/                  # 角色记忆
│       ├── MEMORY.md              # 长期记忆
│       └── diary/                 # 日记记忆
├── tasks/                     # 任务数据
├── task-board.json            # 任务看板
├── task-board.md              # 看板可读版
├── events.db                  # 审计日志
├── jobs.json                  # Cron 调度配置
└── tool-profiles.json         # 工具控制配置
```

### 1.3 第一个任务（5 分钟上手）

**Step 1: 切换到验收者，创建需求**
```
/agent acceptor

我需要一个用户登录功能，包括邮箱密码登录和 OAuth 第三方登录。
```

验收者会：
- 创建任务 T-001（标题、描述、目标列表）
- 目标示例：G1 "邮箱密码登录表单"、G2 "OAuth 集成"、G3 "JWT 令牌管理"

**Step 2: 切换到设计者**
```
/agent designer
```

设计者会：
- 读取 T-001 的目标
- 输出设计文档到 `.agents/runtime/designer/workspace/design-docs/T-001.md`
- 包含：技术方案、文件变更列表、测试规格

**Step 3: 切换到实现者**
```
/agent implementer
```

实现者会：
- 读取设计文档
- 按 TDD 流程编码（写测试 → 红灯 → 实现 → 绿灯 → 重构）
- 完成后提交代码

**Step 4: 切换到审查者**
```
/agent reviewer
```

审查者会：
- 审查设计文档 + 代码变更
- 输出审查报告（CRITICAL/HIGH/MEDIUM/LOW）
- PASS 或 FAIL

**Step 5: 切换到测试者**
```
/agent tester
```

测试者会：
- 逐条验证每个 goal
- 运行测试套件
- 标记 goals 为 met/not-met

**Step 6: 切换到验收者**
```
/agent acceptor
```

验收者会：
- 检查所有 goals 是否 MET
- 接受任务（status → accepted）

---

## 2. 核心概念

### 2.1 五个 Agent 角色

| 角色 | 职责 | 输入 | 输出 |
|------|------|------|------|
| 🎯 **Acceptor** | 需求定义 + 最终验收 | 用户需求 | 任务 + 目标列表 |
| 📐 **Designer** | 技术方案设计 | 任务目标 | 设计文档 + 测试规格 |
| 💻 **Implementer** | 编码实现 | 设计文档 | 代码 + 测试 |
| 🔍 **Reviewer** | 设计 + 代码审查 | 设计文档 + 代码 | 审查报告 |
| 🧪 **Tester** | 目标验证 + 质量检查 | 代码 + 目标 | 验证报告 |

**切换角色：**
```
/agent acceptor    # 切换到验收者
/agent designer    # 切换到设计者
/agent implementer # 切换到实现者
/agent reviewer    # 切换到审查者
/agent tester      # 切换到测试者
```

### 2.2 FSM 状态机

任务通过状态机（Finite State Machine）管理生命周期：

```
              ┌──────────────────────────────────────────────┐
              │                                              │
created ──→ designing ──→ implementing ──→ reviewing ──→ testing ──→ accepting ──→ accepted
              │                ↑              │        │
              │                │              │        │
              │                └── rejected ──┘        └── test_failed ──→ implementing
              │                    (审查不通过)              (测试不通过)
              └──────────────────────────────────────────────┘
                              (设计需要返工)
```

**状态说明：**
| 状态 | 含义 | 负责 Agent |
|------|------|-----------|
| `created` | 任务已创建，等待设计 | Acceptor |
| `designing` | 正在设计方案 | Designer |
| `implementing` | 正在编码实现 | Implementer |
| `reviewing` | 正在审查 | Reviewer |
| `testing` | 正在验证 | Tester |
| `accepting` | 等待最终验收 | Acceptor |
| `accepted` | 任务完成 ✅ | — |

**不允许的转换（Guard Rules）：**
- ❌ 不能跳过审查直接测试
- ❌ 不能从测试跳到验收（必须通过）
- ❌ 只有对应角色才能推进对应状态

### 2.3 任务与目标

**任务结构：**
```json
{
  "id": "T-001",
  "title": "用户登录功能",
  "status": "implementing",
  "goals": [
    {"id": "G1", "description": "邮箱密码登录表单", "met": false},
    {"id": "G2", "description": "OAuth 第三方登录集成", "met": false},
    {"id": "G3", "description": "JWT 令牌管理", "met": true}
  ]
}
```

**目标编写原则：**
- 每个目标必须可验证（有明确的通过/不通过标准）
- 粒度适中（不要太大也不要太细）
- 用户故事格式："作为 XX，我希望 YY，以便 ZZ"

**好的目标：** "登录 API 返回 JWT token，包含 userId 和 exp 字段"
**坏的目标：** "实现登录功能"（太模糊，无法验证）

### 2.4 记忆系统

**三层架构：**

| 层级 | 文件 | 生命周期 | 内容 |
|------|------|----------|------|
| L1 长期 | `{role}/MEMORY.md` | 永久 | 核心决策、架构约定 |
| L2 日记 | `{role}/diary/YYYY-MM-DD.md` | 30-90天 | 每日观察、临时决策 |
| L3 项目 | `PROJECT_MEMORY.md` | 永久 | 技术栈、ADR、热点文件 |

**搜索记忆：**
```bash
bash scripts/memory-search.sh "登录认证"
bash scripts/memory-search.sh "架构决策" --role designer --limit 10
bash scripts/memory-search.sh "测试策略" --layer long-term
```

**输出示例：**
```
[.agents/memory/implementer/MEMORY.md:15] 项目使用 **JWT** 做认证，token 有效期 24h
[.agents/memory/designer/diary/2026-04-07.md:8] 设计决策：**OAuth** 采用 PKCE 流程
```

**自动晋升（Dreaming）：**
- 如果某条日记被搜索 3+ 次、跨 3+ 不同查询 → 自动晋升到 MEMORY.md
- 6 信号打分：频率(24%) + 相关性(30%) + 多样性(15%) + 时效(15%) + 稳定性(10%) + 丰富度(6%)

---

## 3. 工作流详解

### 3.1 标准 SDLC 流水线

```
1. Acceptor: 定义需求
   输出: task-board.json (新任务 + goals)

2. Designer: 设计方案
   输入: 任务 goals
   输出: design-docs/T-xxx.md, test-specs/T-xxx.md

3. Implementer: 编码实现
   输入: 设计文档
   输出: 代码变更 + 测试代码
   流程: TDD (红灯 → 绿灯 → 重构)

4. Reviewer: 审查
   输入: 设计文档 + 代码变更
   输出: review-reports/review-T-xxx.md
   判定: PASS → 进入测试 / FAIL → 返回实现

5. Tester: 验证
   输入: 代码 + goals
   输出: goals met/not-met
   判定: 全部 MET → 进入验收 / 有 NOT MET → 返回实现

6. Acceptor: 验收
   输入: 验证结果
   输出: status → accepted
```

### 3.2 自动流转

**启用自动流转后：**
- Designer 完成设计 → 系统自动切换到 Implementer
- Implementer 完成编码 → 系统自动切换到 Reviewer
- 无需手动 `/agent switch`

**超时检测：**
| 阶段 | 超时阈值 | 超时动作 |
|------|----------|----------|
| designing | 2 小时 | 通知，建议简化 |
| implementing | 4 小时 | 通知，建议拆分 |
| reviewing | 1 小时 | 通知 |
| testing | 2 小时 | 通知 |
| accepting | 1 小时 | 通知 |

### 3.3 并行执行

**多 Implementer 并行：**
```
协调者 (Implementer)
├── Sub-Agent 1: T-024 (memory-index.sh)
├── Sub-Agent 2: T-025 (memory-search.sh)
└── Sub-Agent 3: T-026 (lifecycle management)
```

**使用场景：**
- 多个独立任务同时处于 implementing 状态
- 大任务可拆分为不修改相同文件的子任务
- 审查多个不相关的文件变更

**约束：**
- 每个 sub-agent 操作不同文件（避免冲突）
- task-board.json 只由协调者修改
- sub-agent 完成后，协调者汇总验证

---

## 4. 高级功能

### 4.1 Hook 系统

**15+ 个 Hook 点：**

| Hook | 触发时机 | 用途 |
|------|----------|------|
| `session-start` | 会话开始 | 加载状态 |
| `pre-tool-use` | 工具调用前 | 边界检查 |
| `post-tool-use` | 工具调用后 | 审计日志 |
| `staleness-check` | 定期 | 超时检测 |
| `before-switch` | Agent 切换前 | 验证合法性 |
| `after-switch` | Agent 切换后 | 注入上下文 |
| `before-task-create` | 创建任务前 | 格式/重复验证 |
| `after-task-status` | 状态变更后 | 通知/记忆沉淀 |
| `before-memory-write` | 写记忆前 | 去重/路径验证 |
| `after-memory-write` | 写记忆后 | 索引更新 |
| `before-compaction` | 上下文压缩前 | 自动 flush |
| `on-goal-verified` | 目标验证时 | 进度更新 |
| `security-scan` | 安全扫描 | OWASP 检查 |

**Hook 控制语义：**
```json
{"block": true, "reason": "Reviewer 不能修改源代码"}
{"requireApproval": true, "message": "任务还有未完成目标，确认验收？"}
{"allow": true}
```

**自定义 Hook：**
```bash
#!/usr/bin/env bash
# hooks/my-custom-hook.sh
set -euo pipefail
INPUT=$(cat)  # 读取 stdin JSON
# 你的逻辑...
echo '{"allow": true}'
```

### 4.2 工具控制

**角色工具白名单（`.agents/tool-profiles.json`）：**

| 角色 | 可写 | 只读 |
|------|------|------|
| Acceptor | 无（只读） | 所有文件 |
| Designer | docs/, .agents/runtime/designer/ | skills/, hooks/, src/ |
| Implementer | 所有源码 | task-board.json |
| Reviewer | .agents/runtime/reviewer/, docs/review.md | skills/, hooks/, src/ |
| Tester | tests/, .agents/runtime/tester/ | skills/, hooks/ |

### 4.3 Cron 调度

**配置 `.agents/jobs.json`：**
```json
{
  "jobs": [
    {
      "id": "staleness-check",
      "schedule": "*/30 * * * *",
      "action": "check-staleness",
      "enabled": true,
      "description": "每 30 分钟检查 stale 任务"
    },
    {
      "id": "daily-summary",
      "schedule": "0 9 * * *",
      "action": "generate-report",
      "enabled": true,
      "description": "每天 9 点生成进度摘要"
    }
  ]
}
```

**外部 cron 集成：**
```bash
# 添加到系统 crontab
crontab -e
*/5 * * * * cd /path/to/project && bash scripts/cron-scheduler.sh --run
```

**Webhook 触发：**
```bash
bash scripts/webhook-handler.sh github-push '{"branch":"main"}'
bash scripts/webhook-handler.sh ci-failure '{"build":123}'
```

### 4.4 活文档系统

6 个项目级文档，由各角色累积维护：

| 文档 | 维护者 | 内容 |
|------|--------|------|
| `docs/requirement.md` | Acceptor | 需求累积记录 |
| `docs/design.md` | Designer | 设计决策累积 |
| `docs/implementation.md` | Implementer | 实现笔记 |
| `docs/review.md` | Reviewer | 审查发现 |
| `docs/test-spec.md` | Tester | 测试规格 |
| `docs/acceptance.md` | Acceptor | 验收记录 |

### 4.5 Context Engine

**上下文预算分配：**

| 信息源 | Reviewer | Implementer | Designer |
|--------|----------|-------------|----------|
| 系统提示 | 5k | 5k | 5k |
| 项目上下文 | 10k | 10k | 15k |
| 任务上下文 | 20k | 15k | 20k |
| 代码上下文 | 50k | 40k | 10k |
| 记忆 Top-6 | 10k | 5k | 10k |
| 对话历史 | 85k | 105k | 120k |

**角色 Bootstrap 注入顺序：**
1. 全局 SKILL.md（角色工作流）
2. 项目级 SKILL.md（项目特定命令）
3. 当前任务 goals + 设计文档
4. 记忆搜索 Top-6
5. 上游 Agent 交接消息
6. 项目上下文

---

## 5. 命令参考

### 快速速查表

| 操作 | 命令 |
|------|------|
| 切换角色 | `/agent <role>` |
| 初始化项目 | "初始化 Agent 系统" |
| 查看任务表 | 查看 `.agents/task-board.json` |
| 搜索记忆 | `bash scripts/memory-search.sh "关键词"` |
| 重建索引 | `bash scripts/memory-index.sh --force` |
| 运行测试 | `bash tests/run-all.sh` |
| 检查安装 | `bash install.sh --check` |
| 查看调度 | `bash scripts/cron-scheduler.sh --check` |
| 执行调度 | `bash scripts/cron-scheduler.sh --run` |
| Webhook | `bash scripts/webhook-handler.sh <event> [json]` |

---

## 6. 最佳实践

### 6.1 任务拆分

- **粒度**: 每个任务 2-6 个目标，预计 1-4 小时完成
- **独立性**: 每个任务应该独立可验收
- **目标可验**: 每个 goal 必须有明确的 pass/fail 标准

### 6.2 记忆管理

- 重要决策 → 写入 MEMORY.md（长期）
- 日常观察 → 自动写入 diary（短期）
- 项目级约定 → 写入 PROJECT_MEMORY.md
- 定期运行 `bash scripts/memory-index.sh` 更新索引

### 6.3 常见问题

**Q: Agent 切换后丢失上下文？**
A: 记忆系统会自动加载相关记忆。确保在切换前让当前 Agent 写入关键决策。

**Q: 审查总是不通过？**
A: 检查 Reviewer 的严重级别。CRITICAL/HIGH 必须修复，MEDIUM/LOW 可选。

**Q: 如何跳过某个阶段？**
A: FSM 不允许跳过。如果确实需要，手动修改 task status（不推荐）。

---

## 7. 配置参考

### hooks.json
```json
{
  "hooks": {
    "SessionStart": [{"matcher": "*", "hooks": [{"type": "command", "command": "hooks/xxx.sh"}]}],
    "PreToolUse": [...],
    "PostToolUse": [...],
    "AgentSwitch": [...],
    "TaskCreate": [...],
    "TaskStatusChange": [...],
    "MemoryWrite": [...],
    "Compaction": [...],
    "GoalVerified": [...]
  }
}
```

### task-board.json
```json
{
  "version": 27,
  "tasks": [
    {
      "id": "T-001",
      "title": "任务标题",
      "status": "accepted",
      "goals": [{"id": "G1", "description": "目标描述", "met": true}],
      "created": "2026-04-07T12:00:00"
    }
  ]
}
```

### jobs.json
```json
{
  "jobs": [
    {
      "id": "job-id",
      "schedule": "cron 表达式",
      "action": "动作名",
      "enabled": true,
      "description": "描述"
    }
  ]
}
```

---

## 版本信息

- **框架版本**: v3.2.3
- **Skills**: 18 个（全局安装, 含共享 + 角色专属, Per-Agent 隔离）
- **Hooks**: 13 个 shell 脚本 / 9 种事件
- **Scripts**: 8 个工具脚本
- **工作流模式**: 2 种（Simple + 3-Phase）
- **Phase 1-13**: 全部完成 ✅

---

## 8. 3-Phase 工程闭环使用指南

> v3.0 新增功能 — 适用于复杂功能、硬件/固件、安全关键、多团队协作项目

### 8.1 初始化 3-Phase 项目

在项目根目录中，对 AI 助手说：

```
初始化 Agent 系统
```

当提示选择工作流模式时，选择 **2 (3-Phase)**：

```
🔄 请选择工作流模式:
  1. Simple (简单线性)
  2. 3-Phase (三阶段工程闭环)
请选择 [1/2]: 2
```

初始化后，额外生成：
- `.agents/orchestrator/run.sh` — 编排器守护进程
- `.agents/prompts/` — 16 个步骤 prompt 模板
- `task-board.json` 中 `default_workflow_mode: "3phase"`

### 8.2 启动编排器

创建任务后，使用编排器自动驱动整个 3-Phase 流程：

```bash
# 启动编排器守护进程（后台运行）
nohup bash .agents/orchestrator/run.sh T-001 &

# 查看运行状态
bash .agents/orchestrator/run.sh T-001 --status

# 查看实时日志
tail -f .agents/orchestrator/logs/T-001-*.log

# 停止编排器
bash .agents/orchestrator/run.sh T-001 --stop
```

编排器会自动：
1. Phase 1: 依次调用 acceptor → designer → tester → designer → reviewer
2. Phase 2: 并行启动 implementer + tester + reviewer，汇聚后检查 CI
3. Phase 3: 部署 → 回归测试 → 功能测试 → 日志分析 → 文档

### 8.3 配置外部系统

在初始化时或通过编辑 `.agents/orchestrator/run.sh`，配置可插拔的外部系统：

**CI 系统配置：**
```bash
# GitHub Actions
CI_SYSTEM="github-actions"
CI_URL="https://github.com/org/repo/actions"
CI_STATUS_CMD="gh run list --limit 1 --json status"
CI_TRIGGER_CMD="gh workflow run ci.yml"

# Jenkins
CI_SYSTEM="jenkins"
CI_URL="https://jenkins.example.com/job/my-project"
CI_STATUS_CMD="curl -s ${CI_URL}/lastBuild/api/json | jq .result"
CI_TRIGGER_CMD="curl -X POST ${CI_URL}/build"

# GitLab CI
CI_SYSTEM="gitlab-ci"
CI_URL="https://gitlab.com/org/repo/-/pipelines"
CI_STATUS_CMD="glab ci status"
CI_TRIGGER_CMD="glab ci run"
```

**代码审查系统配置：**
```bash
# GitHub PR
REVIEW_SYSTEM="github-pr"
REVIEW_CMD="gh pr create --fill"
REVIEW_STATUS_CMD="gh pr checks"

# Gerrit
REVIEW_SYSTEM="gerrit"
REVIEW_CMD="git review"
REVIEW_STATUS_CMD="ssh gerrit gerrit query --current-patch-set status:open"

# GitLab MR
REVIEW_SYSTEM="gitlab-mr"
REVIEW_CMD="glab mr create --fill"
REVIEW_STATUS_CMD="glab mr view"
```

**设备/环境配置：**
```bash
# 本地 Docker
DEVICE_TYPE="localhost"
DEPLOY_CMD="docker compose up -d"
LOG_CMD="docker compose logs --tail=200"
BASELINE_CMD="curl -sf http://localhost:8080/health"

# 远程 staging
DEVICE_TYPE="staging"
DEPLOY_CMD="ssh staging 'cd /app && git pull && systemctl restart app'"
LOG_CMD="ssh staging 'journalctl -u app --no-pager -n 200'"
BASELINE_CMD="curl -sf https://staging.example.com/health"

# 真实硬件
DEVICE_TYPE="hardware"
DEPLOY_CMD="scp build/firmware.bin device:/tmp/ && ssh device 'flash /tmp/firmware.bin'"
LOG_CMD="ssh device 'dmesg --follow'"
BASELINE_CMD="ssh device 'run-selftest'"
```

### 8.4 完整示例：3-Phase 任务端到端

```bash
# 1. 初始化项目（选择 3-Phase 模式）
# 对 AI 助手说 "初始化 Agent 系统"，选择模式 2

# 2. 切换到验收者，创建任务
# /agent acceptor
# "创建一个新的 SFP 模块驱动重构任务，需要支持 C++20 协程"

# 3. 启动编排器
bash .agents/orchestrator/run.sh T-001

# 4. 监控进度
watch -n 10 'jq ".tasks[0] | {status, phase, step, feedback_loops, parallel_tracks}" .agents/task-board.json'

# 5. 查看反馈环历史
jq '.tasks[0].feedback_history' .agents/task-board.json

# 6. 如果任务被阻塞（反馈环超限）
# /agent acceptor
# "unblock T-001，重置反馈计数器"
# 然后重新启动编排器

# 7. 任务完成后，查看完整日志
ls -la .agents/orchestrator/logs/T-001-*
```

### 8.5 3-Phase 与 Simple 混用

同一项目可以同时有 Simple 和 3-Phase 任务：
- `T-001` (`workflow_mode: "3phase"`) — 由编排器驱动
- `T-002` (`workflow_mode: "simple"`) — 手动 /agent 切换驱动

FSM 会根据每个任务的 `workflow_mode` 字段自动选择合法转移规则。

---

> 📖 更多信息: [GitHub](https://github.com/cintia09/multi-agent-framework) | [CONTRIBUTING.md](../CONTRIBUTING.md) | [CHANGELOG.md](../CHANGELOG.md)
