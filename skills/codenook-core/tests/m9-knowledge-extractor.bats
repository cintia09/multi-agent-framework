#!/usr/bin/env bats
# M9.3 — knowledge-extractor (TC-M9.3-01..03, 07..13).
# Spec: docs/v6/memory-and-extraction-v6.md §3.1 §6 §7 §9
# Cases: docs/v6/m9-test-cases.md §M9.3

load helpers/load
load helpers/assertions
load helpers/m9_memory

EXTRACT_SH="$CORE_ROOT/skills/builtin/knowledge-extractor/extract.sh"
FX="$CORE_ROOT/tests/fixtures/m9-knowledge-extractor"

# Helper: build a CN_LLM_MOCK_DIR with extract.json.
mock_extract_json() {
  local ws="$1" json="$2"
  mkdir -p "$ws/_mock"
  printf '%s' "$json" > "$ws/_mock/extract.json"
  echo "$ws/_mock"
}

# ------------------------------------------------------------------ TC-M9.3-01

@test "[m9.3] TC-M9.3-01 single cli produces valid file" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  mock_dir=$(mock_extract_json "$ws" '{"candidates":[{"title":"Deploy region quirk","summary":"Lambda needs --region us-east-1.","tags":["deploy","aws"],"body":"# Deploy\n\nUse --region us-east-1 always.\n"}]}')

  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  files=("$ws/.codenook/memory/knowledge"/*.md)
  [ "${#files[@]}" -eq 1 ] || { echo "expected 1 .md, got: ${files[*]}"; return 1; }

  # frontmatter must contain the required fields.
  for fld in summary tags status hash source_task; do
    grep -qE "^${fld}:" "${files[0]}" \
      || { echo "missing field $fld in frontmatter"; cat "${files[0]}"; return 1; }
  done
  grep -qE '^status: candidate$' "${files[0]}" \
    || { echo "status must be candidate"; cat "${files[0]}"; return 1; }
  grep -qE '^source_task: t1$' "${files[0]}" \
    || { echo "source_task must equal t1"; cat "${files[0]}"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-02

@test "[m9.3] TC-M9.3-02 summary cap 200" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  long=$(python3 -c "print('S'*250)")
  mock_dir=$(mock_extract_json "$ws" "$(jq -cn --arg s "$long" '{candidates:[{title:"Long",summary:$s,tags:["x"],body:"body content"}]}')")

  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  files=("$ws/.codenook/memory/knowledge"/*.md)
  [ -f "${files[0]}" ] || { echo "no md written"; return 1; }
  py_summary_len=$(python3 -c "
import sys, yaml
text = open('${files[0]}').read()
fm_end = text.find('\n---\n', 4)
fm = yaml.safe_load(text[4:fm_end])
print(len(fm['summary']))
")
  [ "$py_summary_len" -le 200 ] || { echo "summary length=$py_summary_len > 200"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"truncated":[[:space:]]*true' "$log" \
    || { echo "no truncated:true in audit log"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-03

@test "[m9.3] TC-M9.3-03 tags cap 8" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  tags_json=$(python3 -c "import json;print(json.dumps([f't{i}' for i in range(12)]))")
  mock_dir=$(mock_extract_json "$ws" "$(jq -cn --argjson t "$tags_json" '{candidates:[{title:"TT",summary:"s",tags:$t,body:"body"}]}')")

  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  files=("$ws/.codenook/memory/knowledge"/*.md)
  n=$(python3 -c "
import yaml
text = open('${files[0]}').read()
fm_end = text.find('\n---\n', 4)
fm = yaml.safe_load(text[4:fm_end])
print(len(fm['tags']))
")
  [ "$n" -eq 8 ] || { echo "tags length=$n != 8"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"truncated":[[:space:]]*true' "$log" \
    || { echo "no truncated:true"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-07

@test "[m9.3] TC-M9.3-07 per-task cap 3" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  body_json='{"candidates":['
  for i in 1 2 3 4 5; do
    [ "$i" -gt 1 ] && body_json+=','
    body_json+="{\"title\":\"Topic $i\",\"summary\":\"Summary $i\",\"tags\":[\"a$i\",\"b$i\"],\"body\":\"Body $i unique content $i\"}"
  done
  body_json+=']}'
  mock_dir=$(mock_extract_json "$ws" "$body_json")

  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  cnt=$(ls "$ws/.codenook/memory/knowledge" | wc -l | tr -d ' ')
  [ "$cnt" -eq 3 ] || { echo "expected 3 files, got $cnt"; ls "$ws/.codenook/memory/knowledge"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"dropped_by_cap":[[:space:]]*2' "$log" \
    || { echo "missing dropped_by_cap=2"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-08

@test "[m9.3] TC-M9.3-08 llm error best-effort" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"

  run_with_stderr env CN_LLM_MOCK_ERROR_EXTRACT='timeout' bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "expected exit 0, got $status; stderr=$STDERR"; return 1; }

  case "$STDERR" in
    *"[best-effort] llm call failed"*) :;;
    *) echo "stderr missing best-effort marker: $STDERR"; return 1;;
  esac

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  [ -f "$log" ] || { echo "no audit log"; return 1; }
  grep -q '"status":[[:space:]]*"failed"' "$log" \
    || { echo "missing status=failed in audit log"; cat "$log"; return 1; }

  # No knowledge file written.
  [ -z "$(ls -A "$ws/.codenook/memory/knowledge")" ] \
    || { echo "expected no knowledge file"; ls "$ws/.codenook/memory/knowledge"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-09

@test "[m9.3] TC-M9.3-09 audit log schema locked" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  mock_dir=$(mock_extract_json "$ws" '{"candidates":[{"title":"A","summary":"s","tags":["x"],"body":"hello body content"}]}')

  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  expected='["asset_type","candidate_hash","existing_path","outcome","reason","source_task","timestamp","verdict"]'
  got=$(tail -1 "$log" | jq -c '. as $o | ([$o | keys[]] | sort)')
  [ "$got" = "$expected" ] \
    || { echo "audit keys mismatch"; echo "want: $expected"; echo "got:  $got"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.3-11

@test "[m9.3] TC-M9.3-11 default candidate" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  mock_dir=$(mock_extract_json "$ws" '{"candidates":[{"title":"X","summary":"s","tags":["x"],"body":"any body"}]}')

  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }

  for f in "$ws/.codenook/memory/knowledge"/*.md; do
    grep -qE '^status: candidate$' "$f" \
      || { echo "$f not status:candidate"; cat "$f"; return 1; }
  done
}

# ------------------------------------------------------------------ TC-M9.3-12

@test "[m9.3] TC-M9.3-12 secret blocks write" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  # M9.8 fix-r2: split AKIA token so this fixture file does not itself
  # trip the pre-commit secret scanner. Concatenated at runtime so the
  # rendered body still matches the AWS access-key regex.
  aws_key="AKIA""ABCDEFGHIJKLMNOP"
  body="Here is the leaked AWS key ${aws_key} and stuff."
  mock_dir=$(mock_extract_json "$ws" "$(jq -cn --arg b "$body" '{candidates:[{title:"S",summary:"s",tags:["x"],body:$b}]}')")

  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -ne 0 ] || { echo "expected non-zero exit, got 0; out=$output"; return 1; }

  [ -z "$(ls -A "$ws/.codenook/memory/knowledge")" ] \
    || { echo "knowledge file should not exist"; ls "$ws/.codenook/memory/knowledge"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"outcome":[[:space:]]*"blocked_secret"' "$log" \
    || { echo "missing outcome=blocked_secret"; cat "$log"; return 1; }

  # The audit log MUST NOT contain the raw key.
  if grep -q "$aws_key" "$log"; then
    echo "raw key leaked into audit log!"; cat "$log"; return 1
  fi
}

# ------------------------------------------------------------------ TC-M9.3-12b

@test "[m9.3] TC-M9.3-12b ipv6 ula blocks write" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  # M9.8 fix-r2: split fd00 ULA token to avoid pre-commit secret-scan.
  ipv6_ula="fd""00::1234"
  body="Hosted at ${ipv6_ula}."
  mock_dir=$(mock_extract_json "$ws" "$(jq -cn --arg b "$body" '{candidates:[{title:"U","summary":"s","tags":["x"],body:$b}]}')")

  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  [ "$status" -eq 1 ] || { echo "expected exit 1, got $status; out=$output"; return 1; }

  [ -z "$(ls -A "$ws/.codenook/memory/knowledge")" ] \
    || { echo "knowledge file should not exist"; ls "$ws/.codenook/memory/knowledge"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"outcome":[[:space:]]*"blocked_secret"' "$log" \
    || { echo "missing outcome=blocked_secret"; cat "$log"; return 1; }

  if grep -q "$ipv6_ula" "$log"; then
    echo "raw ipv6 ula leaked into audit log!"; cat "$log"; return 1
  fi
}

# ------------------------------------------------------------------ TC-M9.3-13

@test "[m9.3] TC-M9.3-13 wall budget 30s" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  m9_seed_n_knowledge "$ws" 200
  mock_dir=$(mock_extract_json "$ws" '{"candidates":[{"title":"P","summary":"s","tags":["perfx"],"body":"perf body"}]}')

  start=$(python3 -c "import time;print(int(time.time()*1000))")
  run env CN_LLM_MOCK_DIR="$mock_dir" bash "$EXTRACT_SH" \
        --task-id tperf --workspace "$ws" --phase p --reason after_phase \
        --input "$FX/k1.md"
  end=$(python3 -c "import time;print(int(time.time()*1000))")
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  elapsed=$(( end - start ))
  [ "$elapsed" -le 30000 ] \
    || { echo "wall ${elapsed}ms > 30000ms"; return 1; }
}
