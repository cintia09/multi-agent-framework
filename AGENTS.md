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
mkdir -p ~/.claude/skills
cp -r /tmp/multi-agent-framework/skills/agent-* ~/.claude/skills/
```

### Step 3: 复制 Agent Profiles (必须用 cp, 禁止 heredoc)
```bash
mkdir -p ~/.claude/agents
cp /tmp/multi-agent-framework/agents/*.agent.md ~/.claude/agents/
```

### Step 4: 安装 Hooks (必须用 cp, 禁止 heredoc)
```bash
mkdir -p ~/.claude/hooks
cp /tmp/multi-agent-framework/hooks/*.sh ~/.claude/hooks/
chmod +x ~/.claude/hooks/agent-*.sh
```

如果 `~/.claude/hooks/hooks.json` 已存在, 需要**合并** hook 配置而非覆盖:
```bash
if [ -f ~/.claude/hooks/hooks.json ]; then
  echo "⚠️ hooks.json already exists — merge hooks/hooks.json manually"
else
  cp /tmp/multi-agent-framework/hooks/hooks.json ~/.claude/hooks/
fi
```

### Step 5: 追加协作规则 (幂等)
```bash
if ! grep -q "## Agent Collaboration Rules" ~/.claude/CLAUDE.md 2>/dev/null; then
  echo "" >> ~/.claude/CLAUDE.md
  cat /tmp/multi-agent-framework/docs/agent-rules.md >> ~/.claude/CLAUDE.md
fi
```

### Step 6: 验证安装结果
```bash
echo "Skills:" && ls -d ~/.claude/skills/agent-* | wc -l
echo "Agents:" && ls ~/.claude/agents/*.agent.md | wc -l
echo "Hooks:" && ls ~/.claude/hooks/agent-*.sh | wc -l
echo "hooks.json:" && [ -f ~/.claude/hooks/hooks.json ] && echo "✅" || echo "❌"
```
预期: Skills 15 个目录, Agents 5 个文件, Hooks 13 个脚本, hooks.json 存在。

### Step 7: 深度验证 (可选)
如果需要更完整的验证（检查 Skill 格式、YAML frontmatter、文件权限等），可以运行验证脚本：
```bash
# 验证安装完整性
bash /tmp/multi-agent-framework/scripts/verify-install.sh

# 在项目中执行 /init 初始化后，验证 .agents/ 目录结构
bash /tmp/multi-agent-framework/scripts/verify-init.sh
```
> ⚠️ 需要在 Step 8 清理之前运行。

### Step 8: 清理
```bash
rm -rf /tmp/multi-agent-framework
```

### Step 9: 输出结果
```
✅ Multi-Agent Framework 安装完成
━━━━━━━━━━━━━━━━━━━━━━━
Skills:  15 个已安装到 ~/.claude/skills/
Agents:  5 个已安装到 ~/.claude/agents/
Hooks:   13 个已安装到 ~/.claude/hooks/ (boundary + audit + lifecycle + memory + scheduling)
Rules:   已追加到 ~/.claude/CLAUDE.md
━━━━━━━━━━━━━━━━━━━━━━━
使用方式:
  /agent           → 选择角色
  /agent acceptor  → 直接切换到验收者
  "初始化 Agent 系统" → 在项目中初始化 .agents/ 目录
```
