#!/usr/bin/env bats
# M9.8 — End-to-end acceptance for the memory layer + extractor stack.
# Spec: docs/v6/memory-and-extraction-v6.md §6 (caps/dedup), §11 (router),
#       docs/v6/m9-test-cases.md §M9.8 (this file is the canonical bats
#       binding for TC-M9.8-01..04 plus the GC and pre-commit regressions
#       carried as TC-M9.8-10..12).
#
# Tests in this file follow the spec numbering:
#   TC-M9.8-01  full e2e two tasks: extractor-batch on task α produces a
#               knowledge entry; spawning task β surfaces α's summary in
#               the rendered router prompt via {{MEMORY_INDEX}}. (AC-E2E-1)
#   TC-M9.8-02  watermark async: extractor-batch --reason context-pressure
#               returns immediately and within 5s a knowledge candidate
#               appears under memory/knowledge/. (AC-E2E-2)
#   TC-M9.8-03  parallel 3 tasks no conflict: 3 concurrent extractor-batch
#               processes against the same workspace; no `.tmp.*` residue
#               under .codenook/memory/, audit log captures each run, and
#               the on-disk knowledge files are duplicate-free. (AC-E2E-3 /
#               NFR-CONC-1)
#   TC-M9.8-04  spawn end-to-end: render_prompt --confirm materialises
#               state.json AND the rendered prompt for the spawned child
#               includes seeded memory (knowledge + applies_when config).
#               (FR-SEL-4 / FR-SEL-5)
#   TC-M9.8-10  GC CLI: dry-run reports planned removals and real run
#               prunes per-task over-cap groups + audits. (locked
#               decision plan.md #5)
#   TC-M9.8-11  pre-commit hook blocks commits writing to top-level
#               plugins/ AND tolerates tests/fixtures/plugins/ paths
#               (regression — fix-r1 anchors the fast-gate to repo root).
#   TC-M9.8-12  router→extractor→memory-index loop is idempotent across
#               two ticks: snapshot stable, no `.tmp.*` leaks.

load ../helpers/load
load ../helpers/assertions
load ../helpers/m9_memory

GC_PY="$CORE_ROOT/skills/builtin/_lib/memory_gc.py"
HOOK_TEMPLATE="$CORE_ROOT/templates/pre-commit-hook.sh"
BATCH_SH="$CORE_ROOT/skills/builtin/extractor-batch/extractor-batch.sh"
SPAWN_SH="$CORE_ROOT/skills/builtin/router-agent/spawn.sh"
KNOWLEDGE_EXTRACTOR_DIR="$CORE_ROOT/skills/builtin/knowledge-extractor"

# --------------------------------------------------------------- helpers

# Build a CN_EXTRACTOR_LOOKUP_ROOT containing ONLY the real
# knowledge-extractor (skill/config extractors deliberately omitted so
# the dispatcher records them as "not_present" and the LLM mock only
# needs to satisfy the knowledge schema).
e2e_lookup_with_knowledge_only() {
  local ws="$1"
  local lookup="$ws/_extractors-knowledge-only"
  mkdir -p "$lookup"
  ln -snf "$KNOWLEDGE_EXTRACTOR_DIR" "$lookup/knowledge-extractor"
  echo "$lookup"
}

# Materialise an extract.json mock under "$ws/_mock/extract.json".
# Mirrors mock_extract_json() from m9-knowledge-extractor.bats.
e2e_mock_extract() {
  local ws="$1" json="$2"
  mkdir -p "$ws/_mock"
  printf '%s' "$json" > "$ws/_mock/extract.json"
  echo "$ws/_mock"
}

# Direct memory_layer writes used only by the GC test (TC-M9.8-10).
write_n_knowledge() {
  local ws="$1" n="$2" task="${3:-T-CAP}"
  PYTHONPATH="$M9_LIB_DIR" WS="$ws" N="$n" T="$task" python3 - <<'PY'
import os, time
import memory_layer as ml
ws, n, task = os.environ["WS"], int(os.environ["N"]), os.environ["T"]
for i in range(n):
    ml.write_knowledge(
        ws,
        topic=f"k-{task.lower()}-{i:03d}",
        summary=f"summary {i}",
        tags=[f"t{i%4}"],
        body=("x" * 64) + str(i),
        created_from_task=task,
    )
    ml.append_audit(ws, {"ts": "2026-04-19T00:00:00Z", "asset_type": "knowledge",
                          "verdict": "create", "source_task": task,
                          "topic": f"k-{task.lower()}-{i:03d}"})
    time.sleep(0.01)
PY
}

write_n_skills() {
  local ws="$1" n="$2" task="${3:-T-CAP}"
  PYTHONPATH="$M9_LIB_DIR" WS="$ws" N="$n" T="$task" python3 - <<'PY'
import os, time
import memory_layer as ml
ws, n, task = os.environ["WS"], int(os.environ["N"]), os.environ["T"]
for i in range(n):
    name = f"s-{task.lower()}-{i:03d}"
    ml.write_skill(
        ws,
        name=name,
        frontmatter={"name": name, "summary": f"s {i}", "tags": ["a"]},
        body=("y" * 64) + str(i),
        created_from_task=task,
    )
    ml.append_audit(ws, {"ts": "2026-04-19T00:00:00Z", "asset_type": "skill",
                          "verdict": "create", "source_task": task, "name": name})
    time.sleep(0.01)
PY
}

write_n_config() {
  local ws="$1" n="$2" task="${3:-T-CAP}"
  PYTHONPATH="$M9_LIB_DIR" WS="$ws" N="$n" T="$task" python3 - <<'PY'
import os, time
import memory_layer as ml
ws, n, task = os.environ["WS"], int(os.environ["N"]), os.environ["T"]
for i in range(n):
    ml.upsert_config_entry(
        ws,
        entry={
            "key": f"c-{task.lower()}-{i:03d}",
            "value": f"v{i}",
            "applies_when": "always",
            "created_from_task": task,
        },
        rationale="seed",
    )
    time.sleep(0.01)
PY
}

# Initialize a git repo with the pre-commit hook installed.
init_git_with_hook() {
  local ws="$1"
  ( cd "$ws" && git init -q && git config user.email t@t && git config user.name t \
    && cp "$HOOK_TEMPLATE" .git/hooks/pre-commit && chmod +x .git/hooks/pre-commit )
}

# Mirrors mk_router_ws() from m9-router-memory.bats so the spawn path has
# at least one plugin to enumerate (router prompt section requires it).
mk_router_workspace() {
  local ws
  ws="$(make_scratch)"
  mkdir -p "$ws/.codenook/tasks" "$ws/.codenook/plugins"
  cp -R "$FIXTURES_ROOT/m4/plugins/generic" "$ws/.codenook/plugins/generic"
  m9_init_memory "$ws" >/dev/null
  echo "$ws"
}

# Wait until $1 (a glob) matches at least one file, with a 5s budget.
wait_for_path() {
  local glob="$1" timeout_ms="${2:-5000}" elapsed=0 step=100
  while [ "$elapsed" -lt "$timeout_ms" ]; do
    # shellcheck disable=SC2086
    set -- $glob
    [ -e "$1" ] && return 0
    sleep 0.1
    elapsed=$((elapsed + step))
  done
  return 1
}

# --------------------------------------------------------------- TC-M9.8-01

@test "[m9.8] TC-M9.8-01 full e2e two tasks" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(e2e_lookup_with_knowledge_only "$ws")

  # ---- Task α: real extractor-batch dispatch with mocked LLM produces
  # a knowledge entry that summarises α's work.
  mock_dir=$(e2e_mock_extract "$ws" '{"candidates":[{"title":"Alpha deployment quirk","summary":"alpha task discovered Lambda needs --region us-east-1 for deploy.","tags":["alpha","deploy"],"body":"# Alpha\n\nAlpha discovered Lambda needs --region us-east-1.\n"}]}')

  # Seed a minimal task dir so the extractor has *some* notes input.
  mkdir -p "$ws/.codenook/tasks/T-ALPHA/notes"
  echo "alpha task notes about deploy" > "$ws/.codenook/tasks/T-ALPHA/notes/n.md"

  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" CN_LLM_MOCK_DIR="$mock_dir" \
        bash "$BATCH_SH" --task-id T-ALPHA --reason after_phase \
                         --workspace "$ws" --phase complete
  [ "$status" -eq 0 ] || { echo "alpha batch out=$output"; return 1; }

  # The dispatcher is fire-and-forget — wait for the candidate file.
  wait_for_path "$ws/.codenook/memory/knowledge/*.md" 5000 \
    || { echo "no knowledge file produced for alpha"; ls -la "$ws/.codenook/memory/knowledge"; return 1; }

  # Verify the on-disk knowledge file contains alpha's summary.
  alpha_file="$(ls "$ws/.codenook/memory/knowledge"/*.md | head -1)"
  grep -q "alpha task discovered" "$alpha_file" \
    || { echo "alpha summary not present in: $alpha_file"; cat "$alpha_file"; return 1; }

  # ---- Task β: spawn the router. The user-turn includes "alpha" so the
  # applies_when matcher (or score=1 default for entries without
  # applies_when) surfaces α's summary in the rendered prompt.
  # Add a plugin so render_prompt has a plugins section (parity with
  # m9-router-memory.bats helpers).
  mkdir -p "$ws/.codenook/plugins"
  cp -R "$FIXTURES_ROOT/m4/plugins/generic" "$ws/.codenook/plugins/generic"

  run bash "$SPAWN_SH" --task-id T-BETA --workspace "$ws" \
        --user-turn "follow-up to alpha — also need to deploy to us-east-1"
  [ "$status" -eq 0 ] || { echo "beta spawn out=$output"; return 1; }

  prompt="$ws/.codenook/tasks/T-BETA/.router-prompt.md"
  [ -f "$prompt" ] || { echo "no beta prompt rendered"; return 1; }

  # Verify MEMORY_INDEX cites α's knowledge entry by its summary.
  grep -q "MEMORY_INDEX" "$prompt" \
    || { echo "missing MEMORY_INDEX header in beta prompt"; return 1; }
  grep -q "alpha task discovered" "$prompt" \
    || { echo "beta prompt missing alpha's summary"; sed -n '/MEMORY_INDEX/,/^## /p' "$prompt"; return 1; }
}

# --------------------------------------------------------------- TC-M9.8-02

@test "[m9.8] TC-M9.8-02 watermark async produces candidate" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(e2e_lookup_with_knowledge_only "$ws")
  mock_dir=$(e2e_mock_extract "$ws" '{"candidates":[{"title":"Watermark relief","summary":"context pressure forced an extraction.","tags":["watermark"],"body":"# Watermark\n\ncontent\n"}]}')

  mkdir -p "$ws/.codenook/tasks/T-WM/notes"
  echo "long task notes that triggered context pressure" \
    > "$ws/.codenook/tasks/T-WM/notes/n.md"

  start=$(python3 -c 'import time;print(int(time.time()*1000))')
  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" CN_LLM_MOCK_DIR="$mock_dir" \
        bash "$BATCH_SH" --task-id T-WM --reason context-pressure \
                         --workspace "$ws" --phase active
  end=$(python3 -c 'import time;print(int(time.time()*1000))')
  [ "$status" -eq 0 ] || { echo "batch out=$output"; return 1; }

  # AC-TRG-4: dispatcher returns immediately. Be generous (CI jitter).
  elapsed=$((end - start))
  echo "wall=${elapsed}ms"
  [ "$elapsed" -le 1500 ] || { echo "watermark dispatch wall ${elapsed}ms > 1500ms"; return 1; }

  # JSON envelope sanity.
  echo "$output" | jq -e '.enqueued_jobs | index("knowledge-extractor")' >/dev/null \
    || { echo "knowledge-extractor not enqueued: $output"; return 1; }

  # Within 5s a candidate appears under memory/knowledge/.
  wait_for_path "$ws/.codenook/memory/knowledge/*.md" 5000 \
    || { echo "no candidate appeared within 5s"; ls -la "$ws/.codenook/memory/knowledge"; return 1; }

  # Audit log records the trigger and the extractor outcome.
  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"reason": "context-pressure"' "$log" \
    || { echo "trigger not audited: $(cat "$log")"; return 1; }
}

# --------------------------------------------------------------- TC-M9.8-03

@test "[m9.8] TC-M9.8-03 parallel 3 tasks no conflict" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(e2e_lookup_with_knowledge_only "$ws")

  # Each parallel task gets a distinct mock-dir so the candidates differ.
  for i in 1 2 3; do
    md="$ws/_mock-$i"; mkdir -p "$md"
    printf '%s' "{\"candidates\":[{\"title\":\"Para $i\",\"summary\":\"parallel task $i learned X.\",\"tags\":[\"para$i\"],\"body\":\"# Para $i\\n\\nbody $i.\\n\"}]}" \
      > "$md/extract.json"
    mkdir -p "$ws/.codenook/tasks/T-P$i/notes"
    echo "task $i notes" > "$ws/.codenook/tasks/T-P$i/notes/n.md"
  done

  # Fire 3 dispatches in parallel.
  pids=()
  for i in 1 2 3; do
    ( CN_EXTRACTOR_LOOKUP_ROOT="$lookup" CN_LLM_MOCK_DIR="$ws/_mock-$i" \
        bash "$BATCH_SH" --task-id "T-P$i" --reason after_phase \
                         --workspace "$ws" --phase complete >/dev/null ) &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done

  # Wait for all 3 candidate files.
  for i in 1 2 3; do
    wait_for_path "$ws/.codenook/memory/knowledge/*para${i}*.md" 5000 \
      || wait_for_path "$ws/.codenook/memory/knowledge/*para-$i*.md" 5000 \
      || true
  done
  # Backstop wait: make sure at least 3 .md files landed.
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    n=$(find "$ws/.codenook/memory/knowledge" -maxdepth 1 -name '*.md' | wc -l | tr -d ' ')
    [ "$n" -ge 3 ] && break
    sleep 0.2
  done
  [ "$n" -ge 3 ] || { echo "expected ≥3 candidate files, got $n"; ls -la "$ws/.codenook/memory/knowledge"; return 1; }

  # AC-E2E-3 / NFR-CONC-1: no half-written `.tmp.*` residue anywhere
  # under memory/.
  leak=$(find "$ws/.codenook/memory" \( -name '.tmp.*' -o -name '.tmp-*' \) \
           | wc -l | tr -d ' ')
  [ "$leak" -eq 0 ] || { echo "leaked tmp files: $leak"; \
    find "$ws/.codenook/memory" \( -name '.tmp.*' -o -name '.tmp-*' \); return 1; }

  # Hash-uniqueness sanity: no two knowledge files share the same hash
  # field (would indicate a duplicated write that the dedup step
  # missed). Each parallel task feeds a different body so collisions
  # would be a real bug.
  dups=$(grep -h '^hash:' "$ws/.codenook/memory/knowledge"/*.md | sort \
           | uniq -c | awk '$1 > 1' | wc -l | tr -d ' ')
  [ "$dups" -eq 0 ] || { echo "duplicate hashes detected"; \
    grep -H '^hash:' "$ws/.codenook/memory/knowledge"/*.md; return 1; }

  # Audit log captures all three dispatches.
  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  for i in 1 2 3; do
    grep -q "\"task_id\": \"T-P$i\"" "$log" \
      || { echo "no audit record for T-P$i"; return 1; }
  done
}

# --------------------------------------------------------------- TC-M9.8-04

@test "[m9.8] TC-M9.8-04 spawn end-to-end" {
  ws=$(mk_router_workspace)

  # Seed memory: one knowledge with applies_when matching the brief, and
  # one config entry that also matches.
  PYTHONPATH="$M9_LIB_DIR" WS="$ws" python3 - <<'PY'
import os
import memory_layer as ml
ws = os.environ["WS"]
ml.write_knowledge(
    ws,
    topic="deploy-region",
    frontmatter={
        "summary": "Always pin --region us-east-1 when deploying.",
        "tags": ["deploy"],
        "applies_when": "deploy,region",
    },
    body="# Deploy region\n\nAlways pin us-east-1.\n",
)
ml.upsert_config_entry(
    ws,
    entry={
        "key": "deploy.region",
        "value": "us-east-1",
        "applies_when": "deploy",
        "summary": "preferred deploy region",
    },
)
PY

  # Round 1 — initial spawn (preparation only).
  run bash "$SPAWN_SH" --task-id T-CHILD --workspace "$ws" \
        --user-turn "please help me deploy the new release"
  [ "$status" -eq 0 ] || { echo "spawn out=$output"; return 1; }

  prompt="$ws/.codenook/tasks/T-CHILD/.router-prompt.md"
  [ -f "$prompt" ] || { echo "no prompt rendered"; return 1; }

  # FR-SEL-4: rendered prompt materialises both selected knowledge and
  # the applies_when-matched config entry into the spawned child.
  grep -q "MEMORY_INDEX" "$prompt" \
    || { echo "missing MEMORY_INDEX block"; return 1; }
  grep -q "deploy-region" "$prompt" \
    || { echo "knowledge entry not in prompt"; sed -n '/MEMORY_INDEX/,/^## /p' "$prompt"; return 1; }
  grep -q "deploy.region" "$prompt" \
    || { echo "config entry not in prompt"; sed -n '/MEMORY_INDEX/,/^## /p' "$prompt"; return 1; }

  # FR-SEL-5: --confirm materialises state.json + runs first tick.
  cat > "$ws/.codenook/tasks/T-CHILD/draft-config.yaml" <<'YAML'
_draft: true
_draft_revision: 1
_draft_updated_at: "2026-05-12T10:00:00Z"
plugin: generic
selected_plugins: [generic]
input: |
  Deploy the release to us-east-1.
max_iterations: 4
YAML
  printf 'go\n' > "$ws/.codenook/tasks/T-CHILD/router-reply.md"

  run bash "$SPAWN_SH" --task-id T-CHILD --workspace "$ws" --confirm
  [ "$status" -eq 0 ] || { echo "confirm out=$output"; return 1; }
  assert_contains "$output" '"action": "handoff"'
  [ -f "$ws/.codenook/tasks/T-CHILD/state.json" ] \
    || { echo "no state.json materialised"; return 1; }

  # The post-confirm prompt must still cite the seeded memory entries
  # (re-rendered on every spawn — this is the "audit + selection log
  # all written" leg of the spec).
  grep -q "deploy-region" "$prompt" \
    || { echo "post-confirm prompt lost knowledge entry"; return 1; }

  # Selection / match audit was recorded by match_entries_for_task.
  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"asset_type": "router"' "$log" \
    || { echo "no router audit record"; tail "$log"; return 1; }
}

# --------------------------------------------------------------- TC-M9.8-10

@test "[m9.8] TC-M9.8-10 gc dry-run reports over-cap; real run prunes + audits" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"

  # Per-task caps from spec §6 / §7: knowledge=3, skill=1, config=5.
  write_n_knowledge "$ws" 5 T-OVER
  write_n_skills    "$ws" 3 T-OVER
  write_n_config    "$ws" 7 T-OVER

  k_before=$(ls "$ws/.codenook/memory/knowledge" | wc -l | tr -d ' ')
  s_before=$(ls "$ws/.codenook/memory/skills"    | wc -l | tr -d ' ')
  c_before=$(PYTHONPATH="$M9_LIB_DIR" python3 -c "import memory_layer as m; print(len(m.read_config_entries('$ws')))")

  run env PYTHONPATH="$M9_LIB_DIR" python3 "$GC_PY" --workspace "$ws" --dry-run --json
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  echo "$output" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
assert d['dry_run'] is True, d
assert d['planned']['knowledge'] == 2, d
assert d['planned']['skill']     == 2, d
assert d['planned']['config']    == 2, d
"

  k_after_dry=$(ls "$ws/.codenook/memory/knowledge" | wc -l | tr -d ' ')
  s_after_dry=$(ls "$ws/.codenook/memory/skills"    | wc -l | tr -d ' ')
  c_after_dry=$(PYTHONPATH="$M9_LIB_DIR" python3 -c "import memory_layer as m; print(len(m.read_config_entries('$ws')))")
  [ "$k_after_dry" = "$k_before" ] || { echo "dry run mutated knowledge"; return 1; }
  [ "$s_after_dry" = "$s_before" ] || { echo "dry run mutated skills"; return 1; }
  [ "$c_after_dry" = "$c_before" ] || { echo "dry run mutated config"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  audit_before=$(wc -l <"$log" | tr -d ' ')

  run env PYTHONPATH="$M9_LIB_DIR" python3 "$GC_PY" --workspace "$ws" --json
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  echo "$output" | python3 -c "
import sys, json
d = json.loads(sys.stdin.read())
assert d['dry_run'] is False, d
assert d['pruned']['knowledge'] == 2, d
assert d['pruned']['skill']     == 2, d
assert d['pruned']['config']    == 2, d
"

  k_post=$(ls "$ws/.codenook/memory/knowledge" | wc -l | tr -d ' ')
  s_post=$(ls "$ws/.codenook/memory/skills"    | wc -l | tr -d ' ')
  c_post=$(PYTHONPATH="$M9_LIB_DIR" python3 -c "import memory_layer as m; print(len(m.read_config_entries('$ws')))")
  [ "$k_post" -eq 3 ] || { echo "knowledge post=$k_post"; return 1; }
  [ "$s_post" -eq 1 ] || { echo "skills post=$s_post";    return 1; }
  [ "$c_post" -eq 5 ] || { echo "config post=$c_post";    return 1; }

  ls "$ws/.codenook/memory/knowledge" | grep -q 'k-t-over-004' \
    || { echo "newest knowledge dropped"; ls "$ws/.codenook/memory/knowledge"; return 1; }
  ls "$ws/.codenook/memory/knowledge" | grep -q 'k-t-over-000' \
    && { echo "oldest knowledge survived"; return 1; } || true

  audit_after=$(wc -l <"$log" | tr -d ' ')
  [ "$audit_after" -gt "$audit_before" ] || { echo "no gc audit appended"; return 1; }
  grep -q '"outcome": "gc_pruned"' "$log" || { echo "gc_pruned outcome missing"; tail "$log"; return 1; }
}

# --------------------------------------------------------------- TC-M9.8-11

@test "[m9.8] TC-M9.8-11 pre-commit hook rejects top-level plugins/ but allows tests/fixtures/plugins/" {
  command -v git >/dev/null || skip "git not available"
  [ -x "$HOOK_TEMPLATE" ] || skip "hook template not yet installed (RED)"

  ws=$(make_scratch)
  init_git_with_hook "$ws"

  # Seed initial commit so HEAD exists.
  ( cd "$ws" && echo hello > README.md && git add README.md \
    && git commit -q -m "init" )

  # ---- (a) Negative leg: top-level plugins/ must be rejected.
  ( cd "$ws" && mkdir -p plugins/some-plugin \
    && cat > plugins/some-plugin/extractor.py <<'PY'
def write():
    open("plugins/some-plugin/out.txt", "w").write("hi")
PY
    git add plugins/some-plugin/extractor.py )

  run bash -c "cd '$ws' && git commit -m 'should be blocked'"
  [ "$status" -ne 0 ] || { echo "top-level commit was allowed; output=$output"; return 1; }
  echo "$output" | grep -qiE 'plugin|read.?only|reject' \
    || { echo "hook output missing rejection cue: $output"; return 1; }

  # Reset the staged plugins/ change so the next leg starts clean.
  ( cd "$ws" && git reset -q HEAD plugins/some-plugin/extractor.py \
    && rm -rf plugins )

  # ---- (b) Positive leg: nested fixture path must NOT be rejected by
  # the fast-gate. fix-r1 anchors the regex to '^plugins/' so paths
  # like tests/fixtures/plugins/... pass the gate.
  ( cd "$ws" && mkdir -p tests/fixtures/plugins/foo \
    && echo 'just a fixture' > tests/fixtures/plugins/foo/bar.md \
    && git add tests/fixtures/plugins/foo/bar.md )

  run bash -c "cd '$ws' && git commit -m 'fixture-add allowed'"
  [ "$status" -eq 0 ] || { echo "fixture commit blocked unexpectedly; output=$output"; return 1; }
}

# --------------------------------------------------------------- TC-M9.8-12

@test "[m9.8] TC-M9.8-12 router→extractor→memory-index loop stable across two ticks" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(e2e_lookup_with_knowledge_only "$ws")
  mock_dir=$(e2e_mock_extract "$ws" '{"candidates":[{"title":"Loop","summary":"loop entry","tags":["loop"],"body":"# Loop\n\nbody.\n"}]}')

  mkdir -p "$ws/.codenook/tasks/T-LOOP/notes"
  echo "loop notes" > "$ws/.codenook/tasks/T-LOOP/notes/n.md"

  # Tick 1.
  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" CN_LLM_MOCK_DIR="$mock_dir" \
        bash "$BATCH_SH" --task-id T-LOOP --reason after_phase \
                         --workspace "$ws" --phase complete
  [ "$status" -eq 0 ] || { echo "tick1 out=$output"; return 1; }
  wait_for_path "$ws/.codenook/memory/knowledge/*.md" 5000 \
    || { echo "tick1 produced no candidate"; return 1; }

  snap1=$(PYTHONPATH="$M9_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, json, memory_layer as ml
idx = ml.scan_memory(os.environ["WS"])
out = {
    "k": sorted(m.get("topic") or m.get("path") for m in idx["knowledge"]),
    "s": sorted(m.get("name")  or m.get("path") for m in idx["skills"]),
    "c": sorted(e.get("key") for e in idx["config"]),
}
print(json.dumps(out, sort_keys=True))
PY
)

  # Tick 2 (same task, same mock content): hash dedup must hold; the
  # extractor-batch trigger-key dedup also short-circuits identical
  # (task,phase,reason) tuples — vary the reason here so the second
  # tick actually runs the extractor.
  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" CN_LLM_MOCK_DIR="$mock_dir" \
        bash "$BATCH_SH" --task-id T-LOOP --reason context-pressure \
                         --workspace "$ws" --phase active
  [ "$status" -eq 0 ] || { echo "tick2 out=$output"; return 1; }
  sleep 0.5  # give the second extractor a moment to finish.

  snap2=$(PYTHONPATH="$M9_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, json, memory_layer as ml
idx = ml.scan_memory(os.environ["WS"])
out = {
    "k": sorted(m.get("topic") or m.get("path") for m in idx["knowledge"]),
    "s": sorted(m.get("name")  or m.get("path") for m in idx["skills"]),
    "c": sorted(e.get("key") for e in idx["config"]),
}
print(json.dumps(out, sort_keys=True))
PY
)

  [ "$snap1" = "$snap2" ] || {
    echo "snapshot drifted across ticks"
    echo "snap1=$snap1"
    echo "snap2=$snap2"
    return 1
  }

  leak=$(find "$ws/.codenook/memory" \( -name '.tmp.*' -o -name '.tmp-*' \) \
           | wc -l | tr -d ' ')
  [ "$leak" -eq 0 ] || { echo "leaked tmp files: $leak"; \
    find "$ws/.codenook/memory" \( -name '.tmp.*' -o -name '.tmp-*' \); return 1; }
}
