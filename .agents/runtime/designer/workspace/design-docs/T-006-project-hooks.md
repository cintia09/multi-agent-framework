# Design: T-006 — Generate Project-Level Hooks During Init

## G1: Create .agents/hooks/hooks.json

During init (new Step 5b), generate project-specific hooks config:
```json
{
  "hooks": {
    "SessionStart": [{ "command": ".agents/hooks/project-session-start.sh" }],
    "PreToolUse":  [{ "command": ".agents/hooks/project-pre-tool-use.sh" }],
    "PostToolUse": [{ "command": ".agents/hooks/project-post-tool-use.sh" }]
  }
}
```

## G2: Copy and customize hook scripts

Copy from global hooks as templates, adjust paths:
- Replace `~/.claude/hooks/` references with `.agents/hooks/`
- Set AGENTS_DIR relative to project root
- Make scripts executable

## G3: Update agent-init SKILL.md

Add new step between Step 5 and Step 6:
```markdown
### 5b. 生成项目级 Hooks (可选)
如果全局 hooks 已安装, 复制并调整为项目级:
\```bash
mkdir -p .agents/hooks
cp ~/.claude/hooks/agent-*.sh .agents/hooks/
cp ~/.claude/hooks/hooks.json .agents/hooks/
\```
```

## Files
| File | Action |
|------|--------|
| `skills/agent-init/SKILL.md` | Add Step 5b |
