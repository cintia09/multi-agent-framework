#!/usr/bin/env bats
# M9.3 — knowledge-extractor patch-or-create decision flow
# (TC-M9.3-04, 05, 06, 10).
# Spec: docs/memory-and-extraction.md §6
# Cases: docs/m9-test-cases.md §M9.3

load helpers/load
load helpers/assertions
load helpers/m9_memory

EXTRACT_SH="$CORE_ROOT/skills/builtin/knowledge-extractor/extract.sh"
FX="$CORE_ROOT/tests/fixtures/m9-knowledge-extractor"

# Seed: pre-existing alpha.md with tags=[a,b,c,d].
seed_alpha() {
  local ws="$1"
  m9_write_knowledge "$ws" "alpha" "alpha summary" "a,b,c,d" \
    "# Alpha original body content for similarity tests"
}

mock_dir_with() {
  # mock_dir_with <ws> <extract-json> [decide-json]
  local ws="$1" extract="$2" decide="${3:-}"
  mkdir -p "$ws/_mock"
  printf '%s' "$extract" > "$ws/_mock/extract.json"
  if [ -n "$decide" ]; then
    printf '%s' "$decide" > "$ws/_mock/decide.json"
  fi
  echo "$ws/_mock"
}

# ------------------------------------------------------------------ TC-M9.3-04

@test "[m9.3] TC-M9.3-04 tag overlap triggers judge" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  seed_alpha "$ws"

  extract='{"candidates":[{"title":"alpha v2","topic":"alpha-v2","summary":"new summary","tags":["a","b","e","f"],"body":"# Alpha v2\nDifferent body."}]}'
  decide='{"action":"merge","rationale":"overlap"}'
  mock=$(mock_dir_with "$ws" "$extract" "$decide")

  # We track whether the decide endpoint was hit by writing a marker side-effect.
  # llm_call mock simply reads the file when call_name=decide is requested,
  # which is enough — we assert via audit log verdict==merge.
  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  # No new file (merge into alpha.md).
  cnt=$(ls "$ws/.codenook/memory/knowledge" | wc -l | tr -d ' ')
  [ "$cnt" -eq 1 ] || { echo "expected 1 file (merged), got $cnt"; ls "$ws/.codenook/memory/knowledge"; return 1; }
  [ -f "$ws/.codenook/memory/knowledge/alpha.md" ] \
    || { echo "alpha.md missing"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  tail -1 "$log" | jq -e '.verdict=="merge"' >/dev/null \
    || { echo "verdict != merge in last audit:"; tail -1 "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-05

@test "[m9.3] TC-M9.3-05 verdict and reason logged" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  seed_alpha "$ws"

  extract='{"candidates":[{"title":"alpha-v3","topic":"alpha-v3","summary":"replacement","tags":["a","b","e","f"],"body":"# alpha v3 body"}]}'
  decide='{"action":"replace","rationale":"outdated content"}'
  mock=$(mock_dir_with "$ws" "$extract" "$decide")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  rec=$(tail -1 "$log")
  echo "$rec" | jq -e '.verdict=="replace"' >/dev/null \
    || { echo "verdict != replace: $rec"; return 1; }
  echo "$rec" | jq -e '.reason=="outdated content"' >/dev/null \
    || { echo "reason != outdated content: $rec"; return 1; }
  echo "$rec" | jq -e '.existing_path | test("alpha\\.md$")' >/dev/null \
    || { echo "existing_path missing/wrong: $rec"; return 1; }
  echo "$rec" | jq -e '.candidate_hash | test("^[0-9a-f]{64}$")' >/dev/null \
    || { echo "candidate_hash missing/non-sha256: $rec"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-06

@test "[m9.3] TC-M9.3-06 distinct candidate creates timestamped" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  seed_alpha "$ws"
  alpha_orig=$(cat "$ws/.codenook/memory/knowledge/alpha.md")

  # Topic resolves to "alpha" (LLM-derived slug); high tag overlap → judge → create.
  extract='{"candidates":[{"title":"Alpha new","topic":"alpha","summary":"distinct","tags":["a","b","c","d"],"body":"# Distinct alpha doc"}]}'
  decide='{"action":"create","rationale":"distinct topic"}'
  mock=$(mock_dir_with "$ws" "$extract" "$decide")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  # Original alpha.md must be unchanged.
  alpha_now=$(cat "$ws/.codenook/memory/knowledge/alpha.md")
  [ "$alpha_orig" = "$alpha_now" ] || { echo "alpha.md was mutated"; return 1; }

  # New file alpha-<digits>.md must exist.
  shopt -s nullglob
  new_files=("$ws"/.codenook/memory/knowledge/alpha-[0-9]*.md)
  shopt -u nullglob
  [ "${#new_files[@]}" -ge 1 ] \
    || { echo "no alpha-<ts>.md created"; ls "$ws/.codenook/memory/knowledge"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-10

@test "[m9.3] TC-M9.3-10 hash hit skips llm" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  body='# Same body content used to compute the dedup hash key for alpha.'
  m9_write_knowledge "$ws" "alpha" "summary" "a,b" "$body"

  extract=$(jq -cn --arg b "$body" '{candidates:[{title:"alpha",topic:"alpha-2",summary:"s","tags":["x","y"],body:$b}]}')
  # Decide endpoint must NEVER be called; if it is, llm_call will raise.
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" CN_LLM_MOCK_ERROR_DECIDE='SHOULD_NOT_CALL' \
        bash "$EXTRACT_SH" --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  tail -1 "$log" | jq -e '.outcome=="dedup"' >/dev/null \
    || { echo "outcome != dedup: $(tail -1 "$log")"; return 1; }

  # Knowledge dir still has only alpha.md.
  cnt=$(ls "$ws/.codenook/memory/knowledge" | wc -l | tr -d ' ')
  [ "$cnt" -eq 1 ] || { echo "extra files written: $(ls "$ws/.codenook/memory/knowledge")"; return 1; }
}
