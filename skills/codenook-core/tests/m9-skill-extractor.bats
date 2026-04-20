#!/usr/bin/env bats
# M9.4 — skill-extractor (TC-M9.4-01..07).
# Spec: docs/memory-and-extraction.md §6 + FR-EXT-S
# Cases: docs/m9-test-cases.md §M9.4

load helpers/load
load helpers/assertions
load helpers/m9_memory

EXTRACT_SH="$CORE_ROOT/skills/builtin/skill-extractor/extract.sh"
FX="$CORE_ROOT/tests/fixtures/m9-skill-extractor"

# Build a CN_LLM_MOCK_DIR populated with extract.json (and optional decide.json).
mock_dir_with() {
  local ws="$1" extract="$2" decide="${3:-}"
  mkdir -p "$ws/_mock"
  printf '%s' "$extract" > "$ws/_mock/extract.json"
  if [ -n "$decide" ]; then
    printf '%s' "$decide" > "$ws/_mock/decide.json"
  fi
  echo "$ws/_mock"
}

# ------------------------------------------------------------------ TC-M9.4-01

@test "[m9.4] TC-M9.4-01 single cli produces skill" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[{"name":"build-runner","title":"Build Runner","summary":"Run the build script reliably.","tags":["build","ci"],"body":"# Build Runner\n\nRun: bash scripts/build.sh --release\n"}]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-5x.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  shopt -s nullglob
  dirs=("$ws/.codenook/memory/skills"/*/)
  shopt -u nullglob
  [ "${#dirs[@]}" -eq 1 ] || { echo "expected 1 skill dir, got ${#dirs[@]}: ${dirs[*]}"; return 1; }
  [ -f "${dirs[0]}SKILL.md" ] || { echo "no SKILL.md in ${dirs[0]}"; return 1; }

  for fld in name summary tags status; do
    grep -qE "^${fld}:" "${dirs[0]}SKILL.md" \
      || { echo "missing field $fld in skill frontmatter"; cat "${dirs[0]}SKILL.md"; return 1; }
  done
  grep -qE '^status: candidate$' "${dirs[0]}SKILL.md" \
    || { echo "status must be candidate"; cat "${dirs[0]}SKILL.md"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.4-02

@test "[m9.4] TC-M9.4-02 below threshold no propose" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[{"name":"build-runner","title":"Build Runner","summary":"s","tags":["build"],"body":"x"}]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-2x.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  # No skill dir created.
  shopt -s nullglob
  dirs=("$ws/.codenook/memory/skills"/*/)
  shopt -u nullglob
  [ "${#dirs[@]}" -eq 0 ] || { echo "expected 0 skill dirs, got ${#dirs[@]}: ${dirs[*]}"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"outcome":[[:space:]]*"below_threshold"' "$log" \
    || { echo "missing outcome=below_threshold"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.4-03

@test "[m9.4] TC-M9.4-03 patch existing skill" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  m9_write_skill "$ws" "build-runner" "old summary" "build,ci" \
    "# Build runner\n\nOriginal body for build-runner skill.\n"

  extract='{"candidates":[{"name":"build-runner","title":"Build Runner v2","summary":"new summary","tags":["build","ci","release"],"body":"# Build Runner v2\n\nUpdated steps for build-runner.\n"}]}'
  decide='{"action":"merge","rationale":"overlap"}'
  mock=$(mock_dir_with "$ws" "$extract" "$decide")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-5x.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  cnt=$(ls "$ws/.codenook/memory/skills" | wc -l | tr -d ' ')
  [ "$cnt" -eq 1 ] || { echo "expected 1 skill dir (merged), got $cnt"; ls "$ws/.codenook/memory/skills"; return 1; }
  [ -f "$ws/.codenook/memory/skills/build-runner/SKILL.md" ] \
    || { echo "build-runner SKILL.md missing"; return 1; }

  # Merge must have introduced new tag(s) into existing file.
  grep -q "release" "$ws/.codenook/memory/skills/build-runner/SKILL.md" \
    || { echo "merge did not patch tags"; cat "$ws/.codenook/memory/skills/build-runner/SKILL.md"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"verdict":[[:space:]]*"merge"' "$log" \
    || { echo "verdict=merge missing in audit log"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.4-04

@test "[m9.4] TC-M9.4-04 audit asset type" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[{"name":"build-runner","title":"Build Runner","summary":"s","tags":["build"],"body":"# Build runner doc"}]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-5x.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  tail -1 "$log" | jq -e '.asset_type=="skill"' >/dev/null \
    || { echo "last audit asset_type != skill: $(tail -1 "$log")"; return 1; }

  # Canonical 8-key schema (same as M9.3) on the last record.
  expected='["asset_type","candidate_hash","existing_path","outcome","reason","source_task","timestamp","verdict"]'
  got=$(tail -1 "$log" | jq -c '. as $o | ([$o | keys[]] | sort)')
  [ "$got" = "$expected" ] \
    || { echo "audit keys mismatch"; echo "want: $expected"; echo "got:  $got"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.4-05

@test "[m9.4] TC-M9.4-05 per-task cap 1" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[
    {"name":"build-runner","title":"Build Runner","summary":"build","tags":["build"],"body":"# build runner body"},
    {"name":"deploy-runner","title":"Deploy Runner","summary":"deploy","tags":["deploy"],"body":"# deploy runner body"},
    {"name":"lint-runner","title":"Lint Runner","summary":"lint","tags":["lint"],"body":"# lint runner body"}
  ]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-multi.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  cnt=$(ls "$ws/.codenook/memory/skills" | wc -l | tr -d ' ')
  [ "$cnt" -eq 1 ] || { echo "expected 1 skill dir (cap=1), got $cnt"; ls "$ws/.codenook/memory/skills"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"dropped_by_cap":[[:space:]]*2' "$log" \
    || { echo "missing dropped_by_cap=2"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.4-06

@test "[m9.4] TC-M9.4-06 hash dedup" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  body='# Build runner\n\nIdentical body content used for hash dedup test.\n'
  # Seed an existing skill with the same body. write_skill computes
  # dedup_hash from the literal body bytes.
  m9_write_skill "$ws" "build-runner" "old summary" "build,ci" "$body"

  extract=$(jq -cn --arg b "$body" '{candidates:[{name:"build-runner-v2",title:"Build Runner v2",summary:"s",tags:["build","ci"],body:$b}]}')
  # Decide endpoint must NOT be called when hash matches.
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" CN_LLM_MOCK_ERROR_DECIDE='SHOULD_NOT_CALL' \
        bash "$EXTRACT_SH" --task-id t1 --workspace "$ws" --phase complete \
        --reason after_phase --input "$FX/phase-log-5x.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  tail -1 "$log" | jq -e '.outcome=="dedup"' >/dev/null \
    || { echo "outcome != dedup: $(tail -1 "$log")"; return 1; }

  cnt=$(ls "$ws/.codenook/memory/skills" | wc -l | tr -d ' ')
  [ "$cnt" -eq 1 ] || { echo "extra skill dirs written: $(ls "$ws/.codenook/memory/skills")"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.4-07

@test "[m9.4] TC-M9.4-07 best-effort" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"

  run_with_stderr env CN_LLM_MOCK_ERROR_EXTRACT='timeout' bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-5x.txt"
  [ "$status" -eq 0 ] || { echo "expected exit 0, got $status; stderr=$STDERR"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  [ -f "$log" ] || { echo "no audit log"; return 1; }
  grep -q '"status":[[:space:]]*"failed"' "$log" \
    || { echo "missing status=failed in audit log"; cat "$log"; return 1; }

  # No skill written.
  [ -z "$(ls -A "$ws/.codenook/memory/skills" 2>/dev/null)" ] \
    || { echo "expected no skill dir"; ls "$ws/.codenook/memory/skills"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.4-01b

@test "[m9.4] TC-M9.4-01b dotslash invocations meet threshold" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[{"name":"foo-runner","title":"Foo Runner","summary":"Run the foo build script.","tags":["build"],"body":"# Foo Runner\n\nRun: ./scripts/foo.sh build\n"}]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-dotslash.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  shopt -s nullglob
  dirs=("$ws/.codenook/memory/skills"/*/)
  shopt -u nullglob
  [ "${#dirs[@]}" -eq 1 ] || { echo "expected 1 skill dir, got ${#dirs[@]}: ${dirs[*]}"; return 1; }
  [ -f "${dirs[0]}SKILL.md" ] || { echo "no SKILL.md in ${dirs[0]}"; return 1; }
}
