#!/usr/bin/env bash
# remote-watch/watch.sh — generic three-tier remote review/CI poller.
# Knows nothing system-specific; specifics live in memory or come via
# --config. Spec: see SKILL.md.
set -euo pipefail

TARGET=""
REF=""
CONFIG=""
JSON="0"
while [ $# -gt 0 ]; do
  case "$1" in
    --target-dir)
      [ $# -ge 2 ] || { echo "watch.sh: --target-dir requires a value" >&2; exit 2; }
      TARGET="$2"; shift 2 ;;
    --ref)
      [ $# -ge 2 ] || { echo "watch.sh: --ref requires a value" >&2; exit 2; }
      REF="$2";    shift 2 ;;
    --config)
      [ $# -ge 2 ] || { echo "watch.sh: --config requires a value" >&2; exit 2; }
      CONFIG="$2"; shift 2 ;;
    --json)       JSON="1";    shift ;;
    -h|--help)    sed -n '1,80p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "watch.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "watch.sh: --target-dir required" >&2
  exit 2
fi
if [ ! -d "$TARGET" ]; then
  echo "watch.sh: target dir not found: $TARGET" >&2
  exit 2
fi

HINT_BASE="$(basename "$(cd "$TARGET" && pwd)")"
HINT="remote-watch-config target=$HINT_BASE"

emit() {
  local status="$1" source="$2" raw="$3"
  if [ "$JSON" = "1" ]; then
    raw_esc="$(printf '%s' "$raw" | python3 -c 'import json,sys;print(json.dumps(sys.stdin.read()))' 2>/dev/null || echo '""')"
    printf '{"status":"%s","source":"%s","raw":%s,"memory_search_hint":"%s"}\n' \
      "$status" "$source" "$raw_esc" "$HINT"
  else
    echo "status: $status"
    echo "source: $source"
    echo "memory_search_hint: $HINT"
    [ -n "$raw" ] && { echo "raw:"; echo "$raw"; }
  fi
}

classify() {
  # classify <stdout> <merged-re> <rejected-re> <pending-re>
  local out="$1" mre="$2" rre="$3" pre="$4"
  if [ -n "$mre" ] && echo "$out" | grep -Eq "$mre"; then echo "merged"; return; fi
  if [ -n "$rre" ] && echo "$out" | grep -Eq "$rre"; then echo "rejected"; return; fi
  if [ -n "$pre" ] && echo "$out" | grep -Eq "$pre"; then echo "pending"; return; fi
  echo "unknown"
}

# ── tier 2: --config wins (memory-driven custom probe) ───────────────
if [ -n "$CONFIG" ]; then
  if [ ! -r "$CONFIG" ]; then
    echo "watch.sh: --config not readable: $CONFIG" >&2
    exit 2
  fi
  PROBE_CMD=""; STATUS_REGEX_MERGED=""; STATUS_REGEX_REJECTED=""
  STATUS_REGEX_PENDING=".*"
  # shellcheck disable=SC1090
  . "$CONFIG"
  if [ -z "$PROBE_CMD" ]; then
    echo "watch.sh: config did not set PROBE_CMD" >&2
    exit 2
  fi
  out="$(REF="$REF" TARGET="$TARGET" bash -c "$PROBE_CMD" 2>&1)"
  probe_rc=$?
  if [ $probe_rc -ne 0 ]; then
    # Probe itself failed (network down, auth, missing CLI, …). Report
    # status=unknown and bubble up rc=2 — DO NOT classify garbage stderr
    # as "pending" via the catch-all regex.
    emit "unknown" "tier2-config" "$out"
    exit 2
  fi
  status="$(classify "$out" "$STATUS_REGEX_MERGED" "$STATUS_REGEX_REJECTED" "$STATUS_REGEX_PENDING")"
  emit "$status" "tier2-config" "$out"
  exit 0
fi

# ── tier 1a: GitHub PR (gh CLI present + .github/ in target) ─────────
if [ -d "$TARGET/.github" ] && command -v gh >/dev/null 2>&1 && [ -n "$REF" ]; then
  out="$(gh pr view "$REF" --json state,mergedAt 2>&1)"
  probe_rc=$?
  if [ $probe_rc -ne 0 ]; then
    emit "unknown" "tier1-github" "$out"
    exit 2
  fi
  status="$(classify "$out" '"state":"MERGED"' '"state":"CLOSED"' '"state":"OPEN"')"
  emit "$status" "tier1-github" "$out"
  exit 0
fi

# ── tier 1b: Gerrit (.gerrit marker + recorded host) ─────────────────
if [ -e "$TARGET/.gerrit" ] && [ -n "$REF" ]; then
  GERRIT_HOST="$(head -n1 "$TARGET/.gerrit" 2>/dev/null || true)"
  if [ -n "$GERRIT_HOST" ] && command -v ssh >/dev/null 2>&1; then
    out="$(ssh -o BatchMode=yes "$GERRIT_HOST" gerrit query --format=JSON "change:$REF" 2>&1)"
    probe_rc=$?
    if [ $probe_rc -ne 0 ]; then
      emit "unknown" "tier1-gerrit" "$out"
      exit 2
    fi
    status="$(classify "$out" '"status":"MERGED"' '"status":"ABANDONED"' '"status":"NEW"|"status":"DRAFT"')"
    emit "$status" "tier1-gerrit" "$out"
    exit 0
  fi
fi

# ── tier 3: needs_user_config ───────────────────────────────────────
if [ "$JSON" = "1" ]; then
  printf '{"status":"unknown","source":"none","needs_user_config":true,"memory_search_hint":"%s"}\n' "$HINT"
else
  echo "status: unknown"
  echo "source: none"
  echo "needs_user_config: true"
  echo "memory_search_hint: $HINT"
fi
exit 3
