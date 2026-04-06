# Design: T-004 — Install Verification Scripts

## G1: scripts/verify-install.sh

New file that checks global installation:
```bash
#!/bin/bash
# Verify multi-agent-framework global installation
PASS=0; FAIL=0

# Check skills (expect 10 directories)
SKILL_COUNT=$(ls -d ~/.claude/skills/agent-* 2>/dev/null | wc -l | tr -d ' ')
[ "$SKILL_COUNT" -ge 10 ] && echo "✅ Skills: $SKILL_COUNT" && PASS=$((PASS+1)) || echo "❌ Skills: $SKILL_COUNT (expected ≥10)" && FAIL=$((FAIL+1))

# Check each SKILL.md has YAML frontmatter
for dir in ~/.claude/skills/agent-*/; do
  [ -f "$dir/SKILL.md" ] || { echo "❌ Missing: $dir/SKILL.md"; FAIL=$((FAIL+1)); continue; }
  head -1 "$dir/SKILL.md" | grep -q "^---" || { echo "❌ No frontmatter: $dir/SKILL.md"; FAIL=$((FAIL+1)); continue; }
  PASS=$((PASS+1))
done

# Check agents (expect 5)
AGENT_COUNT=$(ls ~/.claude/agents/*.agent.md 2>/dev/null | wc -l | tr -d ' ')
[ "$AGENT_COUNT" -eq 5 ] && echo "✅ Agents: $AGENT_COUNT" && PASS=$((PASS+1)) || echo "❌ Agents: $AGENT_COUNT (expected 5)" && FAIL=$((FAIL+1))

# Check hooks (expect 3-4 scripts)
HOOK_COUNT=$(ls ~/.claude/hooks/*.sh 2>/dev/null | wc -l | tr -d ' ')
[ "$HOOK_COUNT" -ge 3 ] && echo "✅ Hooks: $HOOK_COUNT" && PASS=$((PASS+1)) || echo "❌ Hooks: $HOOK_COUNT (expected ≥3)" && FAIL=$((FAIL+1))

# Check executable permissions on hooks
for hook in ~/.claude/hooks/*.sh; do
  [ -x "$hook" ] || { echo "❌ Not executable: $hook"; FAIL=$((FAIL+1)); }
done

# Check hooks.json
[ -f ~/.claude/hooks/hooks.json ] && echo "✅ hooks.json exists" && PASS=$((PASS+1)) || echo "❌ Missing hooks.json" && FAIL=$((FAIL+1))

echo "━━━ Result: $PASS passed, $FAIL failed ━━━"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
```

## G2: scripts/verify-init.sh

Checks project-level initialization:
```bash
#!/bin/bash
# Verify .agents/ project initialization
AGENTS_DIR="${1:-.agents}"
# Check: directory exists, 6 project skills, 5 runtime dirs, task-board.json schema, state.json format
```

## G3: AGENTS.md update

Add after Step 7:
```markdown
### Step 8: 验证安装 (可选)
\```bash
bash /tmp/multi-agent-framework/scripts/verify-install.sh
\```
```

## Files to create/modify
| File | Action |
|------|--------|
| `scripts/verify-install.sh` | CREATE |
| `scripts/verify-init.sh` | CREATE |
| `AGENTS.md` | MODIFY (add step 8) |
