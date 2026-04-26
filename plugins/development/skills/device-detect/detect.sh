#!/usr/bin/env bash
# device-detect/detect.sh — enumerate generic execution-environment
# markers under <target-dir> so the test-planner can do a memory
# lookup (and, on miss, ask the user) about the right environment.
#
# This skill never hard-codes ADB / QEMU / device-type-specific names;
# it only reports generic buckets (local-*, recorded-env, custom-runner,
# unknown-config, unknown). Mapping bucket → concrete environment is
# memory + user's job.
#
# Spec: see SKILL.md in this directory.
set -euo pipefail

TARGET=""
JSON="0"
while [ $# -gt 0 ]; do
  case "$1" in
    --target-dir)
      [ $# -ge 2 ] || { echo "detect.sh: --target-dir requires a value" >&2; exit 2; }
      TARGET="$2"; shift 2 ;;
    --json)       JSON="1"; shift ;;
    -h|--help)    sed -n '1,80p' "$(dirname "$0")/SKILL.md"; exit 0 ;;
    *) echo "detect.sh: unknown arg: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$TARGET" ]; then
  echo "detect.sh: --target-dir required" >&2
  exit 2
fi
if [ ! -d "$TARGET" ]; then
  echo "detect.sh: target dir not found: $TARGET" >&2
  exit 2
fi

# Bash 3.2-compatible parallel arrays (macOS default).
BUCKETS=()
HITS=()

add_hit() {
  # add_hit <bucket> <marker>
  local b="$1" m="$2" i found=-1
  for ((i=0; i<${#BUCKETS[@]}; i++)); do
    if [ "${BUCKETS[$i]}" = "$b" ]; then found="$i"; break; fi
  done
  if [ "$found" -eq -1 ]; then
    BUCKETS+=("$b"); HITS+=("$m")
  else
    HITS[$found]="${HITS[$found]},$m"
  fi
}

# ── tier 1: known software runners (pure local) ──────────────────────
[ -e "$TARGET/pyproject.toml" ] && add_hit "local-python" "pyproject.toml"
[ -e "$TARGET/setup.py"        ] && add_hit "local-python" "setup.py"
[ -e "$TARGET/pytest.ini"      ] && add_hit "local-python" "pytest.ini"
[ -e "$TARGET/tox.ini"         ] && add_hit "local-python" "tox.ini"
[ -e "$TARGET/package.json"    ] && add_hit "local-node"   "package.json"
[ -e "$TARGET/go.mod"          ] && add_hit "local-go"     "go.mod"

# ── tier 2: prior recorded environment for this target ───────────────
for f in "$TARGET"/.codenook-test-env* "$TARGET"/.test-env*; do
  [ -e "$f" ] && add_hit "recorded-env" "$(basename "$f")"
done

# ── tier 3: workspace-supplied custom runners ────────────────────────
if [ -d "$TARGET/scripts" ]; then
  for f in "$TARGET"/scripts/run-*-tests.sh; do
    [ -e "$f" ] && add_hit "custom-runner" "scripts/$(basename "$f")"
  done
fi

# ── tier 4: any *.cfg / *.toml not already classified — generic hint ─
for ext in cfg toml yaml; do
  for f in "$TARGET"/*."$ext"; do
    [ -e "$f" ] || continue
    name="$(basename "$f")"
    case "$name" in
      pyproject.toml|setup.py|pytest.ini|tox.ini|package.json|go.mod) ;;
      *) add_hit "unknown-config" "$name" ;;
    esac
  done
done

if [ "${#BUCKETS[@]}" -eq 0 ]; then
  BUCKETS=("unknown"); HITS=("(no markers found)")
fi

# Pick primary: first non-unknown if any, else "unknown".
PRIMARY="${BUCKETS[0]}"
for b in "${BUCKETS[@]}"; do
  if [ "$b" != "unknown" ]; then PRIMARY="$b"; break; fi
done

HINT_BASE="$(basename "$(cd "$TARGET" && pwd)")"
HINT="test-environment target=$HINT_BASE"

if [ "$JSON" = "1" ]; then
  buckets_json=""
  markers_json=""
  for ((i=0; i<${#BUCKETS[@]}; i++)); do
    b="${BUCKETS[$i]}"
    h="${HITS[$i]}"
    [ -n "$buckets_json" ] && buckets_json="$buckets_json,"
    buckets_json="$buckets_json\"$b\""
    marr=""
    IFS=',' read -ra parts <<< "$h"
    for p in "${parts[@]}"; do
      [ -n "$marr" ] && marr="$marr,"
      marr="$marr\"$p\""
    done
    [ -n "$markers_json" ] && markers_json="$markers_json,"
    markers_json="$markers_json\"$b\":[$marr]"
  done
  printf '{"target":"%s","buckets":[%s],"primary":"%s","markers":{%s},"memory_search_hint":"%s"}\n' \
    "$TARGET" "$buckets_json" "$PRIMARY" "$markers_json" "$HINT"
else
  echo "target: $TARGET"
  echo "primary: $PRIMARY"
  echo "memory_search_hint: $HINT"
  echo "buckets:"
  for ((i=0; i<${#BUCKETS[@]}; i++)); do
    echo "  - ${BUCKETS[$i]}: ${HITS[$i]}"
  done
fi
exit 0

