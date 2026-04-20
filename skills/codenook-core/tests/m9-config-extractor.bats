#!/usr/bin/env bats
# M9.5 — config-extractor (TC-M9.5-01..07).
# Spec: docs/memory-and-extraction.md §4 + FR-EXT-C / FR-LAY-6
# Cases: docs/m9-test-cases.md §M9.5

load helpers/load
load helpers/assertions
load helpers/m9_memory

EXTRACT_SH="$CORE_ROOT/skills/builtin/config-extractor/extract.sh"
FX="$CORE_ROOT/tests/fixtures/m9-config-extractor"

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

# ------------------------------------------------------------------ TC-M9.5-01

@test "[m9.5] TC-M9.5-01 single cli appends entry" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[{"key":"log.level","value":"debug","applies_when":"when running dev tasks with verbose logging","summary":"verbose logs for dev"}]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-task-config-set.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  cfg="$ws/.codenook/memory/config.yaml"
  [ -f "$cfg" ] || { echo "no config.yaml"; return 1; }

  # Exactly one entry with key=log.level value=debug, applies_when ≤ 200 chars.
  PYTHONPATH="$M9_LIB_DIR" CFG="$cfg" python3 - <<'PY' || { cat "$cfg"; exit 1; }
import os, sys, yaml
data = yaml.safe_load(open(os.environ["CFG"], encoding="utf-8").read()) or {}
entries = data.get("entries") or []
assert len(entries) == 1, f"expected 1 entry, got {len(entries)}: {entries}"
e = entries[0]
assert e.get("key") == "log.level", e
assert e.get("value") == "debug", e
aw = e.get("applies_when") or ""
assert isinstance(aw, str) and 0 < len(aw) <= 200, f"bad applies_when: {aw!r}"
PY
}

# ------------------------------------------------------------------ TC-M9.5-02

@test "[m9.5] TC-M9.5-02 duplicate key in existing rejected" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  # Hand-place a malformed config.yaml with duplicate keys.
  cat > "$ws/.codenook/memory/config.yaml" <<'YML'
version: 1
entries:
  - key: log.level
    value: info
    applies_when: always
  - key: log.level
    value: debug
    applies_when: always
YML

  extract='{"candidates":[{"key":"new.key","value":"x","applies_when":"always","summary":"s"}]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-task-config-set.txt"
  # Best-effort: extractor exits 0 but must NOT mutate the bad file and
  # must record a failed audit entry referencing the duplicate-key error.
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  # config.yaml unchanged (still 2 duplicate entries; new.key NOT added).
  PYTHONPATH="$M9_LIB_DIR" CFG="$ws/.codenook/memory/config.yaml" python3 - <<'PY'
import os, yaml
data = yaml.safe_load(open(os.environ["CFG"], encoding="utf-8").read()) or {}
entries = data.get("entries") or []
keys = [e.get("key") for e in entries]
assert "new.key" not in keys, f"extractor wrote despite duplicate: {keys}"
assert keys.count("log.level") == 2, f"expected duplicate preserved: {keys}"
PY

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q 'duplicate' "$log" \
    || { echo "missing duplicate-key error in audit log"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.5-03

@test "[m9.5] TC-M9.5-03 same key latest wins" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  # Seed an existing log.level=info entry.
  PYTHONPATH="$M9_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, memory_layer as ml
ml.upsert_config_entry(os.environ["WS"],
  entry={"key":"log.level","value":"info","applies_when":"always","summary":"old","status":"candidate","created_from_task":"t0"},
  rationale="seed")
PY

  extract='{"candidates":[{"key":"log.level","value":"debug","applies_when":"when verbose dev logging is wanted","summary":"new"}]}'
  decide='{"action":"merge","rationale":"same key bias toward merge"}'
  mock=$(mock_dir_with "$ws" "$extract" "$decide")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-merge.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  cfg="$ws/.codenook/memory/config.yaml"
  PYTHONPATH="$M9_LIB_DIR" CFG="$cfg" python3 - <<'PY' || { cat "$cfg"; exit 1; }
import os, yaml
data = yaml.safe_load(open(os.environ["CFG"], encoding="utf-8").read()) or {}
entries = data.get("entries") or []
assert len(entries) == 1, f"expected 1 entry after merge, got {len(entries)}: {entries}"
assert entries[0].get("key") == "log.level"
assert entries[0].get("value") == "debug", entries[0]
PY

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  # Last extractor record should report a merge outcome.
  grep -E '"verdict"[[:space:]]*:[[:space:]]*"merge"' "$log" >/dev/null \
    || { echo "missing verdict=merge"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.5-04

@test "[m9.5] TC-M9.5-04 reuse decision flow" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  PYTHONPATH="$M9_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, memory_layer as ml
ml.upsert_config_entry(os.environ["WS"],
  entry={"key":"log.level","value":"info","applies_when":"always","summary":"old","status":"candidate","created_from_task":"t0"},
  rationale="seed")
PY

  extract='{"candidates":[{"key":"log.level","value":"debug","applies_when":"verbose dev logging","summary":"new"}]}'
  # Distinct marker so we can prove the decide endpoint was actually hit.
  decide='{"action":"merge","rationale":"DECIDE_MARKER_M95_04"}'
  mock=$(mock_dir_with "$ws" "$extract" "$decide")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-merge.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  # Count canonical 8-key extractor records whose `reason` carries the
  # decide marker — proves the decide endpoint produced the rationale.
  cnt=$(jq -c 'select(has("asset_type") and has("verdict") and has("outcome") and .reason=="DECIDE_MARKER_M95_04")' "$log" | wc -l | tr -d ' ')
  [ "$cnt" -eq 1 ] || { echo "expected decide marker in exactly 1 canonical audit, got $cnt"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.5-05

@test "[m9.5] TC-M9.5-05 audit asset type" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[{"key":"log.level","value":"debug","applies_when":"always","summary":"s"}]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-task-config-set.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  tail -1 "$log" | jq -e '.asset_type=="config"' >/dev/null \
    || { echo "last audit asset_type != config: $(tail -1 "$log")"; return 1; }

  # Canonical 8-key schema (locked by TC-M9.3-09 / TC-M9.4-04).
  expected='["asset_type","candidate_hash","existing_path","outcome","reason","source_task","timestamp","verdict"]'
  got=$(tail -1 "$log" | jq -c '. as $o | ([$o | keys[]] | sort)')
  [ "$got" = "$expected" ] \
    || { echo "audit keys mismatch"; echo "want: $expected"; echo "got:  $got"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.5-06

@test "[m9.5] TC-M9.5-06 per-task cap 5" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[
    {"key":"k1","value":"v1","applies_when":"a","summary":"s"},
    {"key":"k2","value":"v2","applies_when":"a","summary":"s"},
    {"key":"k3","value":"v3","applies_when":"a","summary":"s"},
    {"key":"k4","value":"v4","applies_when":"a","summary":"s"},
    {"key":"k5","value":"v5","applies_when":"a","summary":"s"},
    {"key":"k6","value":"v6","applies_when":"a","summary":"s"},
    {"key":"k7","value":"v7","applies_when":"a","summary":"s"}
  ]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-multi.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  cfg="$ws/.codenook/memory/config.yaml"
  PYTHONPATH="$M9_LIB_DIR" CFG="$cfg" python3 - <<'PY' || { cat "$cfg"; exit 1; }
import os, yaml
data = yaml.safe_load(open(os.environ["CFG"], encoding="utf-8").read()) or {}
entries = data.get("entries") or []
assert len(entries) == 5, f"expected 5 entries (cap), got {len(entries)}: {entries}"
PY

  log="$ws/.codenook/memory/history/extraction-log.jsonl"
  grep -q '"dropped_by_cap":[[:space:]]*2' "$log" \
    || { echo "missing dropped_by_cap=2"; cat "$log"; return 1; }
}

# ------------------------------------------------------------------ TC-M9.5-07

@test "[m9.5] TC-M9.5-07 applies_when match" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  extract='{"candidates":[{"key":"plugins.dev.hook","value":"on","applies_when":"when task touches plugins/development","summary":"dev hook"}]}'
  mock=$(mock_dir_with "$ws" "$extract")

  run env CN_LLM_MOCK_DIR="$mock" bash "$EXTRACT_SH" \
        --task-id t1 --workspace "$ws" --phase complete --reason after_phase \
        --input "$FX/phase-log-task-config-set.txt"
  [ "$status" -eq 0 ] || { echo "out=$output"; return 1; }

  PYTHONPATH="$M9_LIB_DIR" WS="$ws" python3 - <<'PY'
import os, memory_layer as ml
out = ml.match_entries_for_task(os.environ["WS"], "refactor plugins/development hook")
assert len(out) == 1, f"expected 1 match, got {len(out)}: {out}"
assert out[0].get("key") == "plugins.dev.hook", out
PY
}
