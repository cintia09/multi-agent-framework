---
name: agent-hitl-gate
description: "Human-in-the-Loop 审批门禁。每个阶段输出文档后，必须经过人工审批才能进入下一阶段。Use when publishing documents for review, collecting feedback, or checking approval status."
---

# 🚪 Human-in-the-Loop Gate

## 概述

HITL Gate 是 Agent 工作流中的人工审批检查点。每个 Agent 在完成阶段性工作后，必须将输出文档发布到交互式审批页面，等待人工确认后才能进行 FSM 状态转移。

## 配置

项目级配置存储在 `.agents/config.json`:

```json
{
  "hitl": {
    "enabled": true,
    "platform": "local-html",
    "gates": {
      "acceptor":    { "enabled": true, "output": "requirements + acceptance-criteria" },
      "designer":    { "enabled": true, "output": "design-doc + test-spec" },
      "implementer": { "enabled": true, "output": "code-summary + dfmea" },
      "reviewer":    { "enabled": true, "output": "review-report" },
      "tester":      { "enabled": true, "output": "test-report" }
    },
    "auto_approve_timeout_hours": null
  }
}
```

**平台选项**:
- `"local-html"` (默认): 生成本地 HTML 页面，浏览器打开
- `"github-issue"`: 创建 GitHub Issue，通过评论/反应审批
- `"confluence"`: 发布到 Confluence，通过评论审批

如果 `hitl.enabled` 为 `false` 或配置不存在，跳过 HITL 门禁 (向后兼容)。

## 核心流程

### 1. 发布审批文档 (publish)

Agent 完成文档后调用:

```
HITL Gate: publish(task_id, agent_role, output_doc_path)
```

**步骤**:
1. 读取输出文档 (markdown)
2. 调用平台适配器:
   - **local-html**: 启动本地 HTTP 服务器 (hitl-server.py)，打开浏览器
     ```bash
     bash scripts/hitl-adapters/local-html.sh publish T-NNN <role> <doc.md>
     # → 启动 http://127.0.0.1:8900 并自动打开浏览器
     ```
   - **github-issue**: 创建 GitHub Issue
   - **confluence**: 创建 Confluence 页面
3. 在 task-board.json 中记录 HITL 状态:
   ```json
   {
     "hitl_status": {
       "current_gate": "designer",
       "review_url": "http://127.0.0.1:8900",
       "status": "pending_review",
       "feedback_rounds": 0,
       "published_at": "<ISO 8601>",
       "approved_at": null,
       "approved_by": null
     }
   }
   ```
4. 输出: "📄 审批页面已发布: <URL>。请在浏览器中审批..."

### 多轮交互流程

```
Agent 发布文档 → 用户在浏览器看到文档
  ↓
用户在页面 textarea 写反馈 → 点击 "Request Changes"
  ↓
Agent 轮询 feedback JSON → 读取反馈 → 修改文档 → 重新发布
  (Agent 修改原始 markdown 文件, hitl-server 自动刷新显示新版本)
  ↓
用户刷新页面 → 看到修改后的文档 → 写更多反馈或点击 "Approve"
  ↓
Agent 检测到 approved → 停止服务器 → 继续 FSM 转移
```

**Local HTML 服务器特性**:
- 纯 Python (零依赖)，自动选择可用端口 (8900-8999)
- 文档实时刷新 (每次访问读取最新文件内容)
- 反馈历史完整保留 (每轮都追加到 history JSON)
- 服务器 PID 记录在 `.agents/reviews/T-NNN-<role>-server.pid`
- 审批完成后清理: `bash scripts/hitl-adapters/local-html.sh stop T-NNN <role>`

### 2. 检查审批状态 (check)

Agent 定期检查或用户手动触发:

```
HITL Gate: check(task_id)
```

**步骤**:
1. 读取 task-board.json 中的 hitl_status
2. 调用平台适配器获取状态
3. 返回状态:
   - `pending_review`: 等待审批
   - `feedback`: 收到反馈，需要修改
   - `approved`: 已批准

### 3. 收集反馈 (collect_feedback)

当状态为 `feedback` 时:

```
HITL Gate: collect_feedback(task_id)
```

**步骤**:
1. 调用平台适配器获取反馈内容
2. 返回反馈列表: `[{section, comment, author, at}]`
3. Agent 根据反馈修改文档
4. 重新发布 (feedback_rounds + 1)
5. 循环直到 approved

### 4. 确认审批 (confirm)

当状态为 `approved` 时:

```
HITL Gate: confirm(task_id)
```

**步骤**:
1. 记录 approved_at 和 approved_by
2. 更新 hitl_status.status = "approved"
3. 允许 FSM 转移

## 各角色的 HITL 检查点

| 角色 | 触发时机 | 审批内容 | 批准后转移 |
|------|---------|---------|-----------|
| 🎯 acceptor | 需求文档完成后 | 需求说明 + 验收标准 | created → designing |
| 🏗️ designer | 设计文档完成后 | 设计方案 + 测试规格 | designing → implementing |
| 💻 implementer | 代码实现完成后 | 代码摘要 + DFMEA | implementing → reviewing |
| 🔍 reviewer | 审查报告完成后 | 审查结论 + 修改建议 | reviewing → testing |
| 🧪 tester | 测试报告完成后 | 测试结果 + 问题列表 | testing → accepting |

## 平台适配器接口

每个平台适配器必须实现以下接口:

```bash
# 发布文档，返回审批页面 URL
hitl_publish(task_id, role, content_md) → review_url

# 获取审批状态
hitl_poll(task_id, role) → { status: "pending"|"feedback"|"approved", comments: [] }

# 获取反馈内容
hitl_get_feedback(task_id, role) → [{ section, comment, author, at }]
```

适配器脚本位置: `scripts/hitl-adapters/<platform>.sh`

## FSM 集成

在 agent-fsm 的 Guard 规则中新增:

**HITL 审批守卫**:
- 仅在 `hitl.enabled == true` 时生效
- FSM 转移前检查: `hitl_status.status == "approved"`
- 如果不是 approved: 拒绝转移, 提示 "⛔ HITL 审批未通过, 请先完成人工审批"

## 快速审批 (shortcut)

用户可以在 Agent 对话中说:
- "approve" / "批准" / "通过" → 直接标记当前 HITL 门禁为 approved
- "feedback: <内容>" / "反馈: <内容>" → 写入反馈，Agent 修改后重新发布

这提供了一个不需要离开终端的快速审批路径。

## 自动审批 (可选)

如果配置了 `auto_approve_timeout_hours`:
- 发布后经过指定小时数无人反馈 → 自动标记 approved
- 设为 `null` 表示禁用自动审批 (默认)
