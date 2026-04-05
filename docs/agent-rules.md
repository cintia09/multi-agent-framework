## Multi-Agent 协作规则

### Agent 角色系统
本环境支持 5 个 Agent 角色, 通过 skill 切换:
- `agent-acceptor` — 🎯 验收者 (需求方/甲方)
- `agent-designer` — 🏗️ 设计者 (架构师)
- `agent-implementer` — 💻 实现者 (程序员)
- `agent-reviewer` — 🔍 代码审查者
- `agent-tester` — 🧪 测试者 (QA)

### 角色切换
当用户调用某个 agent-* skill 或说 "/agent <name>" 时:
1. 读取对应的 agent skill (agent-<name>.md)
2. 按照该 skill 定义的启动流程执行
3. 在该角色范围内行动, 不越权

### 状态管理
- 所有状态变更必须通过 `agent-task-board` 和 `agent-fsm` skill
- 不允许直接编辑 task-board.json (必须通过 skill 操作)
- 每次状态变更必须记录 history

### 项目初始化
- 使用 `agent-init` skill 在项目中初始化 Agent 系统
- 初始化后生成 `<project>/.copilot/` 目录结构

### 任务流转规则
任务必须按照状态机定义的路径流转:
```
created → designing → implementing → reviewing → testing → accepting → accepted
```
不允许跳跃 (如 created 直接到 testing)。
唯一的回路: reviewing → implementing (审查退回), testing → fixing → testing (修复循环), accepting → accept_fail → designing (验收失败)。

### 关键约束
1. **角色隔离**: 每个 Agent 只做自己职责范围内的事
2. **状态强制**: 不合法的状态转移必须被拒绝
3. **完整记录**: 每次操作都要更新 state.json、task-board.json、inbox.json
4. **人工介入**: 需求确认、设计审批、验收决定、安全敏感操作需要人确认
5. **🔒 提交前安全检查**: 在 `git add` / `git commit` 之前, 必须扫描待提交文件中是否包含敏感信息:
   - API Key (如 `AIza...`, `sk-...`, `ghp_...`, `AKIA...`)
   - 密码、密钥、token 的明文值
   - 内网 IP 地址 (192.168.x.x, 10.x.x.x)
   - 数据库连接串 (含用户名密码)
   - `.env` 文件或其内容
   - SSH 私钥
   
   如果发现敏感内容, **必须先移除或替换为占位符**, 再提交。绝不将秘密值推送到 GitHub。
