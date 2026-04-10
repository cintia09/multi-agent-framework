# Skills 工作机制 — 加载、注入与 Agent 行为

## 1. 两级加载机制

```mermaid
sequenceDiagram
    participant FS as 📂 文件系统
    participant Platform as Claude Code / Copilot CLI
    participant SP as System Prompt
    participant LLM as 🧠 LLM
    participant Msg as Messages 数组

    Note over FS: 18 个 SKILL.md 文件<br/>~/.claude/skills/ 或 ~/.copilot/skills/

    FS->>Platform: 扫描 skills 目录
    Platform->>Platform: 提取 name + description (≤250字符)

    rect rgb(255, 212, 59)
        Note over Platform,SP: 第一级: 摘要列表 (~1% token)
        Platform->>SP: 注入 skill 名称+描述列表
    end

    SP->>LLM: System Prompt (含摘要列表)
    LLM->>LLM: 根据用户意图判断需要哪个 skill

    rect rgb(81, 207, 102)
        Note over LLM,Msg: 第二级: 按需全文 (5-15% token)
        LLM->>Platform: 调用 /skillname 或自动激活
        Platform->>FS: 读取完整 SKILL.md
        FS-->>Platform: 全文内容 + 变量替换
        Platform->>Msg: 全文注入 Messages 数组
    end

    Msg->>LLM: 下一轮对话包含 skill 全文
```

## 2. Skill 发现路径

```mermaid
flowchart TB
    subgraph CC["Claude Code"]
        CC1["~/.claude/skills/ (用户级)"]
        CC2[".claude/skills/ (项目级)"]
        CC3[".agents/skills/ (共享路径)"]
    end

    subgraph CP["GitHub Copilot CLI"]
        CP1["~/.copilot/skills/ (用户级)"]
        CP2[".github/skills/ (项目级)"]
        CP3[".claude/skills/ (兼容路径)"]
        CP4[".agents/skills/ (共享路径)"]
    end

    subgraph Agent["🤖 当前 Agent"]
        A1["Skills 摘要列表<br/>(全部 18 个)"]
    end

    CC1 & CC2 & CC3 --> A1
    CP1 & CP2 & CP3 & CP4 --> A1

    style CC fill:#845ef7,color:#fff
    style CP fill:#4dabf7,color:#fff
    style Agent fill:#51cf66,color:#fff
```

| 维度 | Claude Code | Copilot CLI |
|------|------------|-------------|
| 用户级 | `~/.claude/skills/` | `~/.copilot/skills/` |
| 项目级 | `.claude/skills/` | `.github/skills/` |
| 共享路径 | `.agents/skills/` ✅ | `.agents/skills/` ✅ |
| 热加载 | ⚠️ memoize 缓存, 需新会话 | `/skills reload` |
| 选择性 | frontmatter `paths:` | `/skills` 命令 |

## 3. Per-Agent Skill 隔离

```mermaid
flowchart LR
    subgraph Shared["📚 共享 Skills (7个)"]
        SK1["orchestrator"]
        SK2["fsm"]
        SK3["task-board"]
        SK4["messaging"]
        SK5["memory"]
        SK6["switch"]
        SK7["docs"]
    end

    subgraph RoleSkills["🎯 角色专属 Skills"]
        direction TB
        RS1["acceptor: config, init,<br/>acceptor, teams"]
        RS2["designer: designer,<br/>hypothesis"]
        RS3["implementer: implementer,<br/>events, hooks, hypothesis"]
        RS4["reviewer: reviewer"]
        RS5["tester: tester, events"]
    end

    subgraph Agents["👥 Agent Profiles"]
        A1["🎯 Acceptor<br/>skills: 共享7 + 专属4 = 11"]
        A2["🏗️ Designer<br/>skills: 共享7 + 专属2 = 9"]
        A3["💻 Implementer<br/>skills: 共享7 + 专属4 = 11"]
        A4["🔍 Reviewer<br/>skills: 共享7 + 专属1 = 8"]
        A5["🧪 Tester<br/>skills: 共享7 + 专属2 = 9"]
    end

    Shared --> A1 & A2 & A3 & A4 & A5
    RS1 --> A1
    RS2 --> A2
    RS3 --> A3
    RS4 --> A4
    RS5 --> A5

    style Shared fill:#ffd43b,color:#333
    style RoleSkills fill:#ff922b,color:#fff
    style A1 fill:#ff6b6b,color:#fff
    style A2 fill:#845ef7,color:#fff
    style A3 fill:#51cf66,color:#fff
    style A4 fill:#4dabf7,color:#fff
    style A5 fill:#ff922b,color:#fff
```

> **隔离强度**: Prompt 软约束 (~95% LLM 遵守率)。隔离仅影响项目级 5 个 agent 角色之间，不影响非 agent 模式下的 skill 使用。

## 4. 三层行为控制体系

```mermaid
flowchart TB
    subgraph Layer1["第1层: Agent Profile + Skill 约束 (定义)"]
        direction LR
        P1["acceptor.agent.md<br/>skills: [共享7 + 专属4]<br/>不能写代码"]
        P2["implementer.agent.md<br/>skills: [共享7 + 专属4]<br/>可以写代码"]
    end

    subgraph Layer2["第2层: Pre-Tool-Use Hook (强制)"]
        direction LR
        H1["Reviewer 调用 rm?"]
        H2{agent-pre-tool-use.sh}
        H3["⛔ Deny: Reviewer<br/>cannot run write commands"]
        H4["✅ Allow"]
    end

    subgraph Layer3["第3层: Auto-Dispatch (路由)"]
        direction LR
        D1["状态变为 testing"]
        D2{auto-dispatch.sh}
        D3["📨 消息 → tester inbox<br/>'请测试 T-042'"]
    end

    subgraph Analogy["🏢 类比"]
        direction TB
        AN1["Skills 摘要 = 📖 目录<br/>(全员可见)"]
        AN2["Skill 全文 = 📚 手册<br/>(按需查阅)"]
        AN3["Agent Profile = 📋 岗位职责<br/>(含 skill 权限)"]
        AN4["Hook = 🔒 门禁系统<br/>(运行时强制)"]
    end

    Layer1 -->|"LLM 自觉遵守<br/>(软约束)"| Layer2
    Layer2 -->|"Hook 运行时强制<br/>(硬约束)"| Layer3

    H1 --> H2
    H2 -->|"违规"| H3
    H2 -->|"合规"| H4
    D1 --> D2 --> D3

    style Layer1 fill:#4a90d9,color:#fff
    style Layer2 fill:#ff6b6b,color:#fff
    style Layer3 fill:#51cf66,color:#fff
    style Analogy fill:#ffd43b,color:#333
```

## 5. 完整请求生命周期

```mermaid
sequenceDiagram
    participant U as 👤 用户
    participant CC as Claude Code/Copilot
    participant LLM as 🧠 大模型

    Note over CC: 📂 扫描 18 Skills → 构建摘要列表 (~1% token)<br/>+ Agent Profile (含 skills: 约束)

    U->>CC: "请把 T-042 状态改为 testing"

    CC->>LLM: System Prompt (摘要列表 + Agent Profile)<br/>+ 对话历史<br/>+ 用户消息

    Note over LLM: 🧠 LLM 从摘要中识别需要:<br/>1. agent-fsm → 按需加载全文<br/>2. agent-task-board → 按需加载全文<br/>3. 检查 skills: 约束 → 允许操作

    LLM-->>CC: 调用 Write 工具修改 task-board.json

    Note over CC: 🪝 Pre-Hook: implementer 可以写文件 ✅
    Note over CC: 🔧 执行: 写入 task-board.json
    Note over CC: 🪝 Post-Hook:<br/>1. FSM: implementing→testing ✅ 合法<br/>2. Doc Gate: ⚠️/⛔ 检查文档<br/>3. Dispatch: 📨 消息→tester<br/>4. Memory: 🧠 记录状态变化

    CC-->>LLM: 工具结果 + Hook 输出

    LLM-->>U: "已将 T-042 状态更改为 testing,<br/>已通知 tester 进行测试"
```
