#!/usr/bin/env bats
# M9.6 — router-agent memory integration via match_entries_for_task.
# Spec: docs/memory-and-extraction.md §4.3, §10
# Cases: docs/m9-test-cases.md TC-M9.6-03, TC-M9.6-06, TC-M9.6-13
# Locked decision (plan.md #4): router calls Python helper that does
# deterministic matching on `applies_when` (no LLM inline).

load helpers/load
load helpers/assertions
load helpers/m9_memory

SPAWN="$CORE_ROOT/skills/builtin/router-agent/spawn.sh"
LIB_DIR="$CORE_ROOT/skills/builtin/_lib"

# ---- workspace helpers -----------------------------------------------------

# Build a workspace with memory skeleton + a generic plugin (so router
# render_prompt has plugins to enumerate, mirroring m8-router-agent-spawn).
mk_router_ws() {
  local ws
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook/tasks" "$ws/.codenook/plugins"
  cp -R "$FIXTURES_ROOT/m4/plugins/generic" "$ws/.codenook/plugins/generic"
  m9_init_memory "$ws" >/dev/null
  echo "$ws"
}

# Seed knowledge with an applies_when frontmatter field.
seed_knowledge_aw() {
  local ws="$1" topic="$2" summary="$3" applies_when="$4" body="$5"
  PYTHONPATH="$LIB_DIR" WS="$ws" TOPIC="$topic" SUMMARY="$summary" \
    AW="$applies_when" BODY="$body" python3 - <<'PY'
import os
import memory_layer as ml
ws = os.environ["WS"]
ml.write_knowledge(
    ws,
    topic=os.environ["TOPIC"],
    frontmatter={
        "summary": os.environ["SUMMARY"],
        "tags": [],
        "applies_when": os.environ["AW"],
    },
    body=os.environ["BODY"],
)
PY
}

seed_skill_aw() {
  local ws="$1" name="$2" summary="$3" applies_when="$4" body="$5"
  PYTHONPATH="$LIB_DIR" WS="$ws" NAME="$name" SUMMARY="$summary" \
    AW="$applies_when" BODY="$body" python3 - <<'PY'
import os
import memory_layer as ml
ws = os.environ["WS"]
ml.write_skill(
    ws,
    name=os.environ["NAME"],
    frontmatter={
        "summary": os.environ["SUMMARY"],
        "applies_when": os.environ["AW"],
    },
    body=os.environ["BODY"],
)
PY
}

seed_config_entry() {
  local ws="$1" key="$2" value="$3" applies_when="$4" summary="$5"
  PYTHONPATH="$LIB_DIR" WS="$ws" KEY="$key" VAL="$value" AW="$applies_when" \
    SUM="$summary" python3 - <<'PY'
import os
import memory_layer as ml
ml.upsert_config_entry(
    os.environ["WS"],
    entry={
        "key": os.environ["KEY"],
        "value": os.environ["VAL"],
        "applies_when": os.environ["AW"],
        "summary": os.environ["SUM"],
    },
)
PY
}

# ---- match_entries_for_task unit tests ------------------------------------

@test "[m9.6] match_entries_for_task on empty workspace returns []" {
  ws=$(mk_router_ws)
  run m9_py "
import json, memory_layer as ml
print(json.dumps(ml.match_entries_for_task('$ws', 'anything')))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = "[]" ] || { echo "got: $output"; return 1; }
}

@test "[m9.6] match_entries_for_task ranks by applies_when token overlap" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "use-bats" "bats helps testing" "testing,bats" "body"
  seed_knowledge_aw "$ws" "ci-tips" "ci notes" "ci,deploy" "body"
  seed_skill_aw "$ws" "run-tests" "runs the tests" "testing" "body"
  seed_config_entry "$ws" "llm.model" "gpt-4o" "orchestrator" "default model"

  run m9_py "
import json, memory_layer as ml
res = ml.match_entries_for_task('$ws', 'please add bats testing for new feature')
keys = [(r['asset_type'], r.get('key') or r.get('path').split('/')[-1]) for r in res]
print(json.dumps(res, indent=2))
print('KEYS=' + json.dumps(keys))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  # Must include use-bats.md (matches 'bats' and 'testing'), run-tests (matches 'testing')
  assert_contains "$output" "use-bats.md"
  assert_contains "$output" "run-tests"
  # ci-tips and llm.model do NOT match the brief tokens
  case "$output" in
    *ci-tips*) echo "ci-tips should be filtered (no token match)"; return 1 ;;
  esac
  case "$output" in
    *llm.model*) echo "llm.model should be filtered (orchestrator not in brief)"; return 1 ;;
  esac
}

@test "[m9.6] match_entries_for_task returns metadata schema" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "alpha" "summary alpha" "testing" "body"

  run m9_py "
import json, memory_layer as ml
res = ml.match_entries_for_task('$ws', 'testing thing')
assert len(res) == 1, res
e = res[0]
for k in ('asset_type','path','title','summary','applies_when','score'):
    assert k in e, ('missing key', k, e)
assert e['asset_type'] == 'knowledge'
assert e['score'] >= 1
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.6] match_entries_for_task: missing applies_when treated as score=1" {
  ws=$(mk_router_ws)
  # write_knowledge with no applies_when in frontmatter
  m9_write_knowledge "$ws" "loose-knowledge" "no applies" "" "body" >/dev/null

  run m9_py "
import json, memory_layer as ml
res = ml.match_entries_for_task('$ws', 'arbitrary brief')
assert len(res) == 1, res
assert res[0]['score'] == 1, res[0]
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.6] match_entries_for_task: empty brief returns []" {
  ws=$(mk_router_ws)
  m9_write_knowledge "$ws" "loose" "no applies" "" "body" >/dev/null

  run m9_py "
import json, memory_layer as ml
print(json.dumps(ml.match_entries_for_task('$ws', '')))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = "[]" ] || { echo "got: $output"; return 1; }
}

@test "[m9.6] match_entries_for_task: asset_types filter" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "a-know" "k" "testing" "b"
  seed_skill_aw "$ws" "a-skill" "s" "testing" "b"
  seed_config_entry "$ws" "x.y" "1" "testing" "c"

  run m9_py "
import json, memory_layer as ml
res = ml.match_entries_for_task('$ws', 'testing', asset_types=['knowledge'])
ats = sorted(set(r['asset_type'] for r in res))
print('ATS=' + json.dumps(ats))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" 'ATS=["knowledge"]'
}

@test "[m9.6] match_entries_for_task: results sorted by score desc" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "two-hits" "double" "alpha,beta" "b"
  seed_knowledge_aw "$ws" "one-hit" "single" "alpha,gamma" "b"

  run m9_py "
import json, memory_layer as ml
res = ml.match_entries_for_task('$ws', 'alpha beta')
scores = [r['score'] for r in res]
assert scores == sorted(scores, reverse=True), scores
assert res[0]['score'] >= res[-1]['score']
assert 'two-hits' in res[0]['path']
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.6] match_entries_for_task: caps at 20 entries" {
  ws=$(mk_router_ws)
  PYTHONPATH="$LIB_DIR" WS="$ws" python3 - <<'PY'
import os
import memory_layer as ml
ws = os.environ["WS"]
for i in range(30):
    ml.write_knowledge(
        ws,
        topic=f"k-{i:03d}",
        frontmatter={"summary": f"k {i}", "tags": [], "applies_when": "match"},
        body="b",
    )
PY

  run m9_py "
import memory_layer as ml
res = ml.match_entries_for_task('$ws', 'match')
print(len(res))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = "20" ] || { echo "got: $output"; return 1; }
}

@test "[m9.6] match_entries_for_task: tokenizes brief lowercased" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "topic" "s" "testing" "b"

  run m9_py "
import memory_layer as ml
res = ml.match_entries_for_task('$ws', 'TESTING-FRAMEWORK')
assert len(res) == 1 and res[0]['score'] >= 1, res
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.6] match_entries_for_task: applies_when split on , | / whitespace" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "k1" "s" "alpha|beta" "b"
  seed_knowledge_aw "$ws" "k2" "s" "alpha/beta" "b"
  seed_knowledge_aw "$ws" "k3" "s" "alpha beta" "b"

  run m9_py "
import memory_layer as ml
res = ml.match_entries_for_task('$ws', 'beta')
paths = sorted(r['path'].split('/')[-1] for r in res)
assert paths == ['k1.md','k2.md','k3.md'], paths
print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  assert_contains "$output" "OK"
}

@test "[m9.6] match_entries_for_task: paths are workspace-relative (memory/...)" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "use-bats" "bats helps testing" "testing" "body"
  seed_skill_aw "$ws" "run-tests" "runs tests" "testing" "body"
  seed_config_entry "$ws" "llm.model" "gpt-4o" "testing" "default model"

  run m9_py "
import json, memory_layer as ml
res = ml.match_entries_for_task('$ws', 'testing thing')
print(json.dumps(res))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  # Every returned path must start with 'memory/' (workspace-relative).
  python3 - "$output" "$HOME" <<'PY'
import json, sys
payload, home = sys.argv[1], sys.argv[2]
# bats joins stdout into one blob; the JSON is the last printable line.
line = [ln for ln in payload.splitlines() if ln.strip().startswith("[")][-1]
data = json.loads(line)
assert data, "expected at least one match"
for r in data:
    p = r.get("path", "")
    assert p.startswith("memory/"), f"path not workspace-relative: {p!r}"
    assert "/var/" not in p, f"absolute /var/ leaked: {p!r}"
    assert "/private/" not in p, f"absolute /private/ leaked: {p!r}"
    assert home not in p, f"$HOME leaked into path: {p!r}"
# Cover all three asset types we seeded.
ats = sorted({r["asset_type"] for r in data})
assert ats == ["config", "knowledge", "skill"], ats
# Spot-check expected shapes.
shapes = sorted(r["path"] for r in data)
assert "memory/config.yaml" in shapes, shapes
assert "memory/knowledge/use-bats.md" in shapes, shapes
assert "memory/skills/run-tests/SKILL.md" in shapes, shapes
print("OK")
PY
  [ "$?" -eq 0 ] || { echo "post-check failed"; return 1; }
}

# ---- audit emission --------------------------------------------------------

@test "[m9.6] TC-M9.6-13 router match emits audit record" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "use-bats" "bats" "testing" "b"

  run m9_py "
import memory_layer as ml
ml.match_entries_for_task('$ws', 'testing now', source_task='T-099')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  [ -f "$log" ] || { echo "no audit log written"; return 1; }
  last=$(tail -n1 "$log")
  assert_contains "$last" '"asset_type": "router"'
  assert_contains "$last" '"outcome": "matched"'
  assert_contains "$last" '"source_task": "T-099"'
}

# ---- router-agent integration ---------------------------------------------

@test "[m9.6] TC-M9.6-03 spawn renders MEMORY_INDEX block with matched entries" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "use-bats" "bats helps testing" "testing,bats" "body"
  seed_config_entry "$ws" "llm.model" "gpt-4o" "testing" "default model"

  run bash "$SPAWN" --task-id T-100 --workspace "$ws" \
                    --user-turn "please add bats testing for the login flow"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  prompt="$ws/.codenook/tasks/T-100/.router-prompt.md"
  [ -f "$prompt" ] || { echo "no prompt rendered"; return 1; }
  grep -q "MEMORY_INDEX (M9.6)" "$prompt" || \
    { echo "missing MEMORY_INDEX header"; cat "$prompt"; return 1; }
  grep -q "use-bats" "$prompt" || \
    { echo "missing matched knowledge entry"; cat "$prompt"; return 1; }
  grep -q "llm.model" "$prompt" || \
    { echo "missing matched config entry"; cat "$prompt"; return 1; }
}

@test "[m9.6] TC-M9.6-06 applies_when miss → entry omitted from MEMORY_INDEX" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "matches" "m" "deploy" "b"
  seed_knowledge_aw "$ws" "misses"  "n" "totally,unrelated" "b"

  run bash "$SPAWN" --task-id T-101 --workspace "$ws" \
                    --user-turn "help me with deploy please"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  prompt="$ws/.codenook/tasks/T-101/.router-prompt.md"
  grep -q "matches" "$prompt" || { echo "expected matches"; cat "$prompt"; return 1; }
  if grep -q "misses" "$prompt"; then
    echo "should not include unmatched entry"; cat "$prompt"; return 1
  fi
}

@test "[m9.6] empty MEMORY_INDEX still rendered as explicit empty marker" {
  ws=$(mk_router_ws)
  # No memory entries seeded.
  run bash "$SPAWN" --task-id T-102 --workspace "$ws" \
                    --user-turn "do a thing"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  prompt="$ws/.codenook/tasks/T-102/.router-prompt.md"
  grep -q "MEMORY_INDEX (M9.6): empty" "$prompt" || \
    { echo "missing empty marker"; cat "$prompt"; return 1; }
}

@test "[m9.6] spawn integration emits a router audit record" {
  ws=$(mk_router_ws)
  seed_knowledge_aw "$ws" "use-bats" "bats" "testing" "b"

  run bash "$SPAWN" --task-id T-103 --workspace "$ws" \
                    --user-turn "let's add testing"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  [ -f "$log" ] || { echo "no audit log"; return 1; }
  grep -q '"asset_type": "router"' "$log" || \
    { echo "no router audit"; cat "$log"; return 1; }
  grep -q '"source_task": "T-103"' "$log" || \
    { echo "router audit missing task id"; cat "$log"; return 1; }
}
