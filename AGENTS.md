# Multi-Agent Software Development Framework

## 安装指引

当用户说 "根据 multi-agent-framework 里的指引, 安装到本地" 或类似意图时, **自动执行以下步骤**:

> ⚠️ **重要**: 必须先 clone 仓库再用 `cp` 命令复制文件。**禁止**用 `cat > file << EOF` 或其他方式重新创建文件内容 — 必须从仓库原文件复制, 确保内容一致。

### Step 1: Clone 到临时目录
```bash
git clone --depth 1 git@github.com:cintia09/multi-agent-framework.git /tmp/multi-agent-framework
```

### Step 2: 复制 Skills (必须用 cp, 禁止 heredoc)
```bash
mkdir -p ~/.copilot/skills
cp -r /tmp/multi-agent-framework/skills/agent-* ~/.copilot/skills/
```

### Step 3: 复制 Agent Profiles (必须用 cp, 禁止 heredoc)
```bash
mkdir -p ~/.copilot/agents
cp /tmp/multi-agent-framework/agents/*.agent.md ~/.copilot/agents/
```

### Step 4: 追加协作规则 (幂等)
```bash
if ! grep -q "## Agent Collaboration Rules" ~/.copilot/copilot-instructions.md 2>/dev/null; then
  echo "" >> ~/.copilot/copilot-instructions.md
  cat /tmp/multi-agent-framework/docs/agent-rules.md >> ~/.copilot/copilot-instructions.md
fi
```

### Step 5: 清理
```bash
rm -rf /tmp/multi-agent-framework
```

### Step 6: 验证安装结果
```bash
echo "Skills:" && ls -d ~/.copilot/skills/agent-* | wc -l
echo "Agents:" && ls ~/.copilot/agents/*.agent.md | wc -l
```
预期: Skills 10 个目录 (每个含 SKILL.md), Agents 5 个 .agent.md 文件。

### Step 7: 输出结果
```
✅ Multi-Agent Framework 安装完成
━━━━━━━━━━━━━━━━━━━━━━━
Skills:  10 个已安装到 ~/.copilot/skills/
Agents:  5 个已安装到 ~/.copilot/agents/ (原生 .agent.md 格式)
Rules:   已追加到 ~/.copilot/copilot-instructions.md
━━━━━━━━━━━━━━━━━━━━━━━
使用方式:
  /agent           → 选择角色
  /agent acceptor  → 直接切换到验收者
  "初始化 Agent 系统" → 在项目中初始化 .copilot/ 目录
```
