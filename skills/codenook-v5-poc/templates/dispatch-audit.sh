#!/usr/bin/env bash
# CodeNook v5.0 — Dispatch Audit
# Reads .codenook/history/dispatch-log.jsonl and verifies the orchestrator
# actually delegated work via Mode B sub-agent dispatches (vs. doing it
# itself in the main session). See core.md §20.
#
# Usage:
#   bash dispatch-audit.sh              # whole workspace
#   bash dispatch-audit.sh T-003        # one task
#
# Exit codes:
#   0 = no violations
#   1 = violations found
#   2 = bad usage / missing files

set -u

WS=".codenook"
LOG="$WS/history/dispatch-log.jsonl"
TASKS_DIR="$WS/tasks"
FILTER="${1:-}"

if [[ ! -d "$WS" ]]; then
  echo "error: not in a CodeNook workspace (no .codenook/)" >&2
  exit 2
fi

if [[ ! -f "$LOG" ]]; then
  echo "warn: no dispatch log yet at $LOG"
  echo "  → if you have outputs but no log, audit will report all of them as ghosts."
  touch "$LOG"
fi

# -----------------------------------------------------------------------
# Parse log into TSV: ts \t task_id \t phase \t role \t manifest \t output_expected \t invocation_id
# Tolerant of pretty-printed JSON? No — JSONL means one object per line.
# -----------------------------------------------------------------------
LOG_TSV=$(mktemp)
trap 'rm -f "$LOG_TSV"' EXIT

python3 - "$LOG" > "$LOG_TSV" <<'PY'
import json, sys
path = sys.argv[1]
with open(path) as f:
    for ln, raw in enumerate(f, 1):
        raw = raw.strip()
        if not raw:
            continue
        try:
            o = json.loads(raw)
        except Exception as e:
            print(f"__PARSE_ERROR__\t{ln}\t{e}\t\t\t\t", file=sys.stderr)
            continue
        fields = ["ts","task_id","phase","role","manifest","output_expected","invocation_id"]
        vals = [str(o.get(k,"")) for k in fields]
        print("\t".join(vals))
PY

violations=0
warnings=0
ok=0

note_v() { echo "  ❌ $1"; violations=$((violations+1)); }
note_w() { echo "  ⚠️  $1"; warnings=$((warnings+1)); }
note_o() { ok=$((ok+1)); }

# -----------------------------------------------------------------------
# Check 1: unique invocation_ids
# -----------------------------------------------------------------------
echo "[1] Unique invocation IDs:"
dups=$(awk -F'\t' 'NF>=7 && $7!=""{print $7}' "$LOG_TSV" | sort | uniq -d)
if [[ -z "$dups" ]]; then
  note_o; echo "  ✅ no duplicate invocation_ids"
else
  while IFS= read -r d; do note_v "duplicate invocation_id: $d"; done <<<"$dups"
fi

# -----------------------------------------------------------------------
# Check 2: every manifest referenced by log exists on disk
# -----------------------------------------------------------------------
echo ""
echo "[2] Manifest existence:"
miss=0
while IFS=$'\t' read -r ts task phase role manifest out invid; do
  [[ -z "${manifest:-}" ]] && continue
  if [[ -n "$FILTER" && "$task" != "$FILTER" ]]; then continue; fi
  if [[ ! -f "$manifest" ]]; then
    note_v "dangling manifest: $manifest (invid=$invid)"
    miss=$((miss+1))
  fi
done < "$LOG_TSV"
[[ $miss -eq 0 ]] && { note_o; echo "  ✅ all logged manifests exist"; }

# -----------------------------------------------------------------------
# Check 3: output coverage — every outputs/*.md must have a dispatch entry
# -----------------------------------------------------------------------
echo ""
echo "[3] Output coverage (ghost-work detection):"

if [[ -n "$FILTER" ]]; then
  out_dirs=("$TASKS_DIR/$FILTER/outputs")
else
  out_dirs=()
  if [[ -d "$TASKS_DIR" ]]; then
    while IFS= read -r d; do out_dirs+=("$d"); done < <(find "$TASKS_DIR" -type d -name outputs 2>/dev/null)
  fi
fi

# Build set of output_expected values from log
LOG_OUTS=$(mktemp); trap 'rm -f "$LOG_TSV" "$LOG_OUTS"' EXIT
awk -F'\t' '$6!=""{print $6}' "$LOG_TSV" | sort -u > "$LOG_OUTS"

ghosts=0
checked=0
for od in ${out_dirs[@]+"${out_dirs[@]}"}; do
  [[ -d "$od" ]] || continue
  while IFS= read -r f; do
    # Skip summary files (orchestrator may write summaries directly only if
    # the worker did; we audit primary outputs only)
    [[ "$f" == *-summary.md ]] && continue
    checked=$((checked+1))
    if ! grep -Fxq "$f" "$LOG_OUTS"; then
      note_v "ghost output (no dispatch entry): $f"
      ghosts=$((ghosts+1))
    fi
  done < <(find "$od" -maxdepth 1 -type f -name '*.md' 2>/dev/null)
done
echo "  audited $checked primary outputs"
[[ $ghosts -eq 0 && $checked -gt 0 ]] && { note_o; echo "  ✅ all outputs trace back to a dispatch"; }
[[ $checked -eq 0 ]] && { note_w "no outputs found yet (workspace still cold)"; }

# -----------------------------------------------------------------------
# Check 4: phase coverage — for each task, every (task,phase) appearing in
# outputs must appear in the log too.
# -----------------------------------------------------------------------
echo ""
echo "[4] Phase coverage:"

# Build (task, phase) set from log
LOG_TP=$(mktemp); trap 'rm -f "$LOG_TSV" "$LOG_OUTS" "$LOG_TP"' EXIT
awk -F'\t' '$2!="" && $3!=""{print $2"\t"$3}' "$LOG_TSV" | sort -u > "$LOG_TP"

mismatches=0
for od in ${out_dirs[@]+"${out_dirs[@]}"}; do
  [[ -d "$od" ]] || continue
  task_id=$(basename "$(dirname "$od")")
  while IFS= read -r f; do
    [[ "$f" == *-summary.md ]] && continue
    base=$(basename "$f" .md)
    # Output filenames look like 'phase-3-implementer'; the phase id in
    # state.json / log uses the action stem ('phase-3-implement'). Match
    # on the leading 'phase-N-' segment, then prefix-compare the stem.
    file_phase_num=$(echo "$base" | grep -oE '^phase-[0-9]+' || true)
    [[ -z "$file_phase_num" ]] && continue
    found=0
    while IFS=$'\t' read -r lt lp; do
      [[ "$lt" == "$task_id" ]] || continue
      log_phase_num=$(echo "$lp" | grep -oE '^phase-[0-9]+' || true)
      if [[ "$log_phase_num" == "$file_phase_num" ]]; then found=1; break; fi
    done < "$LOG_TP"
    if [[ $found -eq 0 ]]; then
      note_v "phase not in log: $task_id / $file_phase_num (file: $f)"
      mismatches=$((mismatches+1))
    fi
  done < <(find "$od" -maxdepth 1 -type f -name '*.md' 2>/dev/null)
done
[[ $mismatches -eq 0 ]] && { note_o; echo "  ✅ all observed phases were dispatched"; }

# -----------------------------------------------------------------------
# Check 5: workspace containment — manifest / output_expected paths must
# not escape the workspace or point at absolute roots. A traversal path in
# the log suggests an orchestrator attempted to have a sub-agent read or
# write outside .codenook/ — flag aggressively.
# -----------------------------------------------------------------------
echo ""
echo "[5] Workspace containment:"
escapes=0
while IFS=$'\t' read -r ts task phase role manifest out invid; do
  if [[ -n "$FILTER" && "$task" != "$FILTER" ]]; then continue; fi
  for p in "$manifest" "$out"; do
    [[ -z "$p" ]] && continue
    if [[ "$p" == /* ]]; then
      note_v "absolute path in log: $p (invid=$invid)"
      escapes=$((escapes+1))
    elif [[ "$p" == *..* ]]; then
      note_v "traversal segment '..' in log path: $p (invid=$invid)"
      escapes=$((escapes+1))
    elif [[ "$p" != .codenook/* && "$p" != "$WS"/* ]]; then
      note_w "path outside $WS/: $p (invid=$invid)"
    fi
  done
done < "$LOG_TSV"
[[ $escapes -eq 0 ]] && { note_o; echo "  ✅ no workspace-escape attempts in log"; }

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------
echo ""
echo "================ Dispatch Audit Summary ================"
echo "  log entries: $(wc -l < "$LOG_TSV" | tr -d ' ')"
echo "  checks ok:   $ok"
echo "  warnings:    $warnings"
echo "  violations:  $violations"
echo "========================================================"

if [[ $violations -gt 0 ]]; then
  exit 1
fi
exit 0
