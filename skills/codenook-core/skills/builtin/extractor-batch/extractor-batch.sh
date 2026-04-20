#!/usr/bin/env bash
# extractor-batch.sh — M9.2 dispatcher.
#
# Fan out knowledge / skill / config extractors for a finished task phase or
# context-pressure event.  Best-effort + idempotent on (task_id, phase, reason).
#
# Args:
#   --task-id   ID            (required)
#   --reason    REASON        (required) e.g. after_phase | context-pressure
#   --workspace WS            (optional, defaults to $CN_WORKSPACE / $CODENOOK_WORKSPACE / pwd)
#   --phase     PHASE         (optional, defaults to "")
#
# Env:
#   CN_EXTRACTOR_LOOKUP_ROOT  override extractor lookup root (default: skills/builtin)
#
# Output: one JSON object on stdout, e.g.
#   {"enqueued_jobs":["knowledge-extractor"],"skipped":[{"name":"skill-extractor","reason":"not_present"}]}
#
# Exit code is always 0 unless argument parsing fails (FR-EXT-5 / AC-TRG-4).

set -euo pipefail

TASK_ID=""
REASON=""
WORKSPACE="${CN_WORKSPACE:-${CODENOOK_WORKSPACE:-}}"
PHASE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --task-id)   TASK_ID="$2"; shift 2 ;;
    --reason)    REASON="$2"; shift 2 ;;
    --workspace) WORKSPACE="$2"; shift 2 ;;
    --phase)     PHASE="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "extractor-batch.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

[ -n "$TASK_ID" ] || { echo "extractor-batch.sh: --task-id is required" >&2; exit 2; }
[ -n "$REASON" ]  || { echo "extractor-batch.sh: --reason is required" >&2; exit 2; }

if [ -z "$WORKSPACE" ]; then
  cur="$(pwd)"
  while [ "$cur" != "/" ]; do
    if [ -d "$cur/.codenook" ]; then WORKSPACE="$cur"; break; fi
    cur="$(dirname "$cur")"
  done
fi
[ -n "$WORKSPACE" ] || { echo "extractor-batch.sh: workspace not found" >&2; exit 2; }

HISTORY_DIR="$WORKSPACE/.codenook/memory/history"
mkdir -p "$HISTORY_DIR"
TRIGGER_KEYS="$HISTORY_DIR/.trigger-keys"
LOG="$HISTORY_DIR/extraction-log.jsonl"

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
sha() {
  if command -v sha256sum >/dev/null 2>&1; then
    printf '%s' "$1" | sha256sum | awk '{print $1}'
  else
    printf '%s' "$1" | shasum -a 256 | awk '{print $1}'
  fi
}

KEY="$(sha "${TASK_ID}|${PHASE}|${REASON}")"

log_event() {
  local event="$1" name="${2:-}"
  if [ "$event" = "phase_complete" ] && [ -n "${_ROUTE_LOG_EXTRA:-}" ] && [ -f "$_ROUTE_LOG_EXTRA" ]; then
    local _route_json
    _route_json=$(cat "$_ROUTE_LOG_EXTRA" 2>/dev/null || echo '{}')
    jq -cn \
      --arg ts "$(ts)" --arg task "$TASK_ID" --arg phase "$PHASE" \
      --arg reason "$REASON" --arg event "$event" --arg name "$name" \
      --arg key "$KEY" \
      --argjson route "$_route_json" \
      '{ts:$ts, task_id:$task, phase:$phase, reason:$reason, event:$event,
        name:($name | select(. != "")), key:$key, route:$route}
       | with_entries(select(.value != null))' >> "$LOG"
    return 0
  fi
  jq -cn \
    --arg ts "$(ts)" --arg task "$TASK_ID" --arg phase "$PHASE" \
    --arg reason "$REASON" --arg event "$event" --arg name "$name" \
    --arg key "$KEY" \
    '{ts:$ts, task_id:$task, phase:$phase, reason:$reason, event:$event,
      name:($name | select(. != "")), key:$key}
     | with_entries(select(.value != null))' >> "$LOG"
}

# Idempotency: if key already recorded, short-circuit.
if [ -f "$TRIGGER_KEYS" ] && grep -qxF "$KEY" "$TRIGGER_KEYS"; then
  log_event "deduped"
  jq -cn --arg key "$KEY" '{enqueued_jobs:[], skipped:[{reason:"deduped", key:$key}], reason:"deduped"}'
  exit 0
fi
printf '%s\n' "$KEY" >> "$TRIGGER_KEYS"

# ── Route classification (legacy: single-valued cross_task) ──────────────
# Historically the router returned per-artefact ``task_specific`` vs
# ``cross_task``; the per-task destination has been removed and every
# artefact now lands in memory/.  The LLM call is retained for audit
# parity (mocks, .route-*.json) and is slated for removal in a follow-up.
ROUTE_KNOWLEDGE="cross_task"
ROUTE_SKILL="cross_task"
ROUTE_CONFIG="cross_task"
ROUTE_FALLBACK="true"

_ROUTER_PY="$(cd "$(dirname "$0")/../_lib" && pwd)/extraction_router.py"
if [ -f "$_ROUTER_PY" ]; then
  _ROUTE_JSON=$(PYTHONPATH="$(dirname "$_ROUTER_PY")" python3 "$_ROUTER_PY" \
    --task-id "$TASK_ID" --workspace "$WORKSPACE" \
    --phase "$PHASE" --reason "$REASON" 2>/dev/null || echo '{}')
  _PARSED=$(echo "$_ROUTE_JSON" | jq -e \
    '{knowledge:.knowledge,skill:.skill,config:.config,route_fallback:.route_fallback}' \
    2>/dev/null || echo '{}')
  if [ "$(echo "$_PARSED" | jq -r '.knowledge // "cross_task"')" != "null" ]; then
    ROUTE_KNOWLEDGE=$(echo "$_PARSED" | jq -r '.knowledge // "cross_task"')
    ROUTE_SKILL=$(echo "$_PARSED" | jq -r '.skill // "cross_task"')
    ROUTE_CONFIG=$(echo "$_PARSED" | jq -r '.config // "cross_task"')
    ROUTE_FALLBACK=$(echo "$_PARSED" | jq -r 'if .route_fallback == null then true else .route_fallback end')
  fi
fi

# Log routing decision alongside the phase_complete event (written later).
_ROUTE_LOG_EXTRA="$HISTORY_DIR/.route-${KEY}.json"
jq -cn \
  --arg knowledge "$ROUTE_KNOWLEDGE" \
  --arg skill "$ROUTE_SKILL" \
  --arg config "$ROUTE_CONFIG" \
  --argjson fallback "$ROUTE_FALLBACK" \
  '{knowledge:$knowledge,skill:$skill,config:$config,route_fallback:$fallback}' \
  > "$_ROUTE_LOG_EXTRA" 2>/dev/null || true

LOOKUP_ROOT="${CN_EXTRACTOR_LOOKUP_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"

# M9.5 fix: init the memory skeleton ONCE before fan-out so every extractor
# sees a complete layout (dirs + config.yaml). Without this, the first
# extractor (knowledge-extractor) creates the dirs while the later
# config-extractor finds memory/ exists but config.yaml missing →
# MemoryLayoutError. Best-effort; failures don't block dispatch.
LIB_DIR="$(cd "$(dirname "$0")/../_lib" && pwd)"
PYTHONPATH="$LIB_DIR" WORKSPACE="$WORKSPACE" python3 - <<'PY' || true
import os, pathlib
import memory_layer as ml
ws = pathlib.Path(os.environ["WORKSPACE"])
if not ml.has_memory(ws):
    try:
        ml.init_memory_skeleton(ws)
    except Exception as e:
        print(f"[extractor-batch] init_memory_skeleton best-effort failed: {e}", flush=True)
PY

ENQUEUED=()
SKIPPED_JSON='[]'

push_skipped() {
  local name="$1" reason="$2"
  SKIPPED_JSON=$(echo "$SKIPPED_JSON" | jq -c --arg n "$name" --arg r "$reason" '. + [{name:$n, reason:$r}]')
}

dispatch_one() {
  local name="$1"
  local script="$LOOKUP_ROOT/$name/extract.sh"
  if [ ! -x "$script" ]; then
    if [ -f "$script" ]; then
      log_event "extractor_not_executable" "$name"
      push_skipped "$name" "not_executable"
    else
      log_event "extractor_missing" "$name"
      push_skipped "$name" "not_present"
    fi
    return 0
  fi
  # Spawn detached; failures captured to per-extractor log, not propagated.
  # E2E-015: dedup err lines so repeated runs don't unbounded-grow the file.
  local err_log="$HISTORY_DIR/.extractor-${name}.err"
  local err_tmp="$HISTORY_DIR/.extractor-${name}.err.tmp.$$"
  nohup env CN_EXTRACTION_ROUTE_KNOWLEDGE="$ROUTE_KNOWLEDGE" \
            CN_EXTRACTION_ROUTE_SKILL="$ROUTE_SKILL" \
            CN_EXTRACTION_ROUTE_CONFIG="$ROUTE_CONFIG" \
      "$script" --task-id "$TASK_ID" --workspace "$WORKSPACE" \
        --phase "$PHASE" --reason "$REASON" \
        </dev/null >>"$err_tmp" 2>&1 &
  disown $! 2>/dev/null || true
  # Best-effort dedup-merge: when the spawned process completes (usually
  # near-instantly for mock LLM), splice unique lines from tmp into the
  # canonical err log. Idempotency keeps the err file bounded by unique
  # error count, matching E2E-015 / E2E-009 follow-up.
  (
    wait $! 2>/dev/null || true
    if [ -f "$err_tmp" ]; then
      if [ -f "$err_log" ]; then
        cat "$err_log" "$err_tmp" 2>/dev/null | awk '!seen[$0]++' \
          > "$err_log.new" && mv -f "$err_log.new" "$err_log"
      else
        awk '!seen[$0]++' "$err_tmp" > "$err_log" 2>/dev/null || true
      fi
      rm -f "$err_tmp"
    fi
  ) &
  disown $! 2>/dev/null || true
  log_event "extractor_dispatched" "$name"
  ENQUEUED+=("$name")
}

for name in knowledge-extractor skill-extractor config-extractor; do
  dispatch_one "$name"
done

log_event "phase_complete"

ENQ_JSON=$(printf '%s\n' "${ENQUEUED[@]:-}" | jq -R . | jq -s -c 'map(select(. != ""))')
jq -cn --argjson e "$ENQ_JSON" --argjson s "$SKIPPED_JSON" \
  '{enqueued_jobs:$e, skipped:$s}'

exit 0
