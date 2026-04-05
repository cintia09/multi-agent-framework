# Test Report: T-001 + T-002

## T-001: Update README with Phase 2 Features

### G1: Hooks Section — ✅ PASS
- [x] Section exists (line 112: "## Hooks (Agent Boundary Enforcement)")
- [x] Contains 3-hook table (session-start, pre-tool-use, post-tool-use)
- [x] Contains boundary rules table (line 124-134, 5 roles)
- [x] Mentions `active-agent` file mechanism (line 134)

### G2: events.db Section — ✅ PASS
- [x] Section exists after Hooks
- [x] Contains schema table
- [x] Contains 3 sqlite3 query examples

### G3: Architecture Update — ✅ PASS
- [x] "Hook enforcement" in Key Features
- [x] "SQLite audit log" in Key Features
- [x] Roadmap shows Phase 2 as ✅ (line 220)

### G4: File Structure Update — ✅ PASS
- [x] hooks/ directory shown in global layer tree
- [x] events.db shown in project layer tree
- [x] Installation steps include hook copying

**T-001 Result: ✅ ALL 4 GOALS PASS**

---

## T-002: Phase 3 Auto-dispatch + Staleness

### G1: Auto-dispatch Design — ✅ PASS
- [x] Design doc exists with FSM status→agent mapping table
- [x] Covers all 10 transitions

### G2: Auto-dispatch Implementation — ✅ PASS
- [x] post-tool-use hook has AUTO-DISPATCH section (line 37-87)
- [x] status=reviewing → reviewer inbox message ✅ (tested)
- [x] Duplicate prevention via existing message check
- [x] auto_dispatch event logged to events.db ✅ (tested)
- [x] Hook completes within 5 seconds

**ISSUE FOUND**: Installed hooks were out of sync with repo (46 vs 87 lines).
Fixed by re-copying. Recommend adding sync verification to install flow.

### G3: Staleness Detection — ✅ PASS
- [x] Script exists at hooks/agent-staleness-check.sh
- [x] Script is executable
- [x] Configurable threshold (default 24h)

### G4: Session-start Integration — ✅ PASS
- [x] Session-start hook calls staleness check

### G5: Agent-switch Queue Processing — ✅ PASS
- [x] agent-switch SKILL.md includes inbox processing steps
- [x] Includes staleness warning in activation flow

**T-002 Result: ✅ ALL 5 GOALS PASS**

---

## Issues Found (Non-blocking)

1. **Sync gap**: After modifying hook scripts in repo, must manually
   `cp hooks/*.sh ~/.copilot/hooks/`. Easy to forget.
   **Recommendation**: Add a `make sync` or verification step.

## Summary

| Task | Goals | Result |
|------|-------|--------|
| T-001 | 4/4 pass | ✅ PASS |
| T-002 | 5/5 pass | ✅ PASS |

Both tasks ready for acceptance.
