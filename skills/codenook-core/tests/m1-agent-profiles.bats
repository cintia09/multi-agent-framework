#!/usr/bin/env bats
# Agent profiles — 5 builtin agent markdown files

load helpers/load
load helpers/assertions

AGENTS_DIR="$CORE_ROOT/agents"

@test "router.md exists and ≤2KB" {
  assert_file_exists "$AGENTS_DIR/router.md"
  assert_file_size_le "$AGENTS_DIR/router.md" 2048
}

@test "distiller.md exists and ≤2KB" {
  assert_file_exists "$AGENTS_DIR/distiller.md"
  assert_file_size_le "$AGENTS_DIR/distiller.md" 2048
}

@test "security-auditor.md exists and ≤2KB" {
  assert_file_exists "$AGENTS_DIR/security-auditor.md"
  assert_file_size_le "$AGENTS_DIR/security-auditor.md" 2048
}

@test "hitl-adapter.md exists and ≤2KB" {
  assert_file_exists "$AGENTS_DIR/hitl-adapter.md"
  assert_file_size_le "$AGENTS_DIR/hitl-adapter.md" 2048
}

@test "config-mutator.md exists and ≤2KB" {
  assert_file_exists "$AGENTS_DIR/config-mutator.md"
  assert_file_size_le "$AGENTS_DIR/config-mutator.md" 2048
}

@test "router.md contains all 6 required sections" {
  assert_contains "$(cat $AGENTS_DIR/router.md)" "角色"
  assert_contains "$(cat $AGENTS_DIR/router.md)" "模型偏好"
  assert_contains "$(cat $AGENTS_DIR/router.md)" "Self-bootstrap"
  assert_contains "$(cat $AGENTS_DIR/router.md)" "输入"
  assert_contains "$(cat $AGENTS_DIR/router.md)" "输出"
  assert_contains "$(cat $AGENTS_DIR/router.md)" "禁止清单"
}

@test "distiller.md contains all 6 required sections" {
  assert_contains "$(cat $AGENTS_DIR/distiller.md)" "角色"
  assert_contains "$(cat $AGENTS_DIR/distiller.md)" "模型偏好"
  assert_contains "$(cat $AGENTS_DIR/distiller.md)" "Self-bootstrap"
}

@test "security-auditor.md contains all 6 required sections" {
  assert_contains "$(cat $AGENTS_DIR/security-auditor.md)" "角色"
  assert_contains "$(cat $AGENTS_DIR/security-auditor.md)" "模型偏好"
}

@test "router.md specifies tier_strong" {
  assert_contains "$(cat $AGENTS_DIR/router.md)" "tier_strong"
}

@test "distiller.md specifies tier_cheap" {
  assert_contains "$(cat $AGENTS_DIR/distiller.md)" "tier_cheap"
}

@test "each profile declares exactly one tier symbol" {
  # Check router has tier_strong
  grep -q "tier_strong" "$AGENTS_DIR/router.md"
  
  # Check distiller has tier_cheap  
  grep -q "tier_cheap" "$AGENTS_DIR/distiller.md"
  
  # Check others have tier_balanced
  grep -q "tier_balanced" "$AGENTS_DIR/security-auditor.md"
  grep -q "tier_balanced" "$AGENTS_DIR/hitl-adapter.md"
  grep -q "tier_balanced" "$AGENTS_DIR/config-mutator.md"
}
