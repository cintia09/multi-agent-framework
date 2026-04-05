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

### Step 4: 安装 Hooks (必须用 cp, 禁止 heredoc)
```bash
mkdir -p ~/.copilot/hooks
cp /tmp/multi-agent-framework/hooks/*.sh ~/.copilot/hooks/
chmod +x ~/.copilot/hooks/agent-*.sh
```

如果 `~/.copilot/hooks/hooks.json` 已存在, 需要**合并** hook 配置而非覆盖:
```bash
if [ -f ~/.copilot/hooks/hooks.json ]; then
  echo "⚠️ hooks.json already exists — merge hooks/hooks.json manually"
else
  cp /tmp/multi-agent-framework/hooks/hooks.json ~/.copilot/hooks/
fi
```

### Step 5: 追加协作规则 (幂等)
```bash
if ! grep -q "## Agent Collaboration Rules" ~/.copilot/copilot-instructions.md 2>/dev/null; then
  echo "" >> ~/.copilot/copilot-instructions.md
  cat /tmp/multi-agent-framework/docs/agent-rules.md >> ~/.copilot/copilot-instructions.md
fi
```

### Step 6: 清理
```bash
rm -rf /tmp/multi-agent-framework
```

### Step 7: 验证安装结果
```bash
echo "Skills:" && ls -d ~/.copilot/skills/agent-* | wc -l
echo "Agents:" && ls ~/.copilot/agents/*.agent.md | wc -l
echo "Hooks:" && ls ~/.copilot/hooks/agent-*.sh | wc -l
echo "hooks.json:" && [ -f ~/.copilot/hooks/hooks.json ] && echo "✅" || echo "❌"
```
预期: Skills 12 个目录, Agents 5 个文件, Hooks 4 个脚本, hooks.json 存在。

### Step 8: 输出结果
```
✅ Multi-Agent Framework 安装完成
━━━━━━━━━━━━━━━━━━━━━━━
Skills:  12 个已安装到 ~/.copilot/skills/
Agents:  5 个已安装到 ~/.copilot/agents/
Hooks:   4 个已安装到 ~/.copilot/hooks/ (boundary enforcement + audit log + staleness)
Rules:   已追加到 ~/.copilot/copilot-instructions.md
━━━━━━━━━━━━━━━━━━━━━━━
使用方式:
  /agent           → 选择角色
  /agent acceptor  → 直接切换到验收者
  "初始化 Agent 系统" → 在项目中初始化 .agents/ 目录
```
