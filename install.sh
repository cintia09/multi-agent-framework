#!/usr/bin/env bash
# CodeNook v0.13.2 — top-level installer.
#
# Usage:
#   bash install.sh                       # install into $PWD
#   bash install.sh <workspace_path>      # install into a specific workspace
#   bash install.sh --dry-run [<path>]    # run install gates, do not commit
#   bash install.sh --upgrade [<path>]    # allow re-install of existing plugin
#   bash install.sh --plugin <id> [<path>]  # plugin id under plugins/ (default: development)
#   bash install.sh --no-claude-md [<path>] # skip CLAUDE.md augmentation
#   bash install.sh --yes [<path>]          # auto-confirm CLAUDE.md write (CI)
#   bash install.sh --check [<path>]      # report install state of a workspace
#   bash install.sh --help                # show this help
#
# Behaviour:
#   1. Runs the kernel installer (skills/codenook-core/install.sh) which
#      stages the requested plugin into <workspace>/.codenook/plugins/<id>/
#      and updates <workspace>/.codenook/state.json. Idempotent (G03/G04).
#   2. Augments the workspace CLAUDE.md with a clearly delimited
#      <!-- codenook:begin --> ... <!-- codenook:end --> bootloader block
#      (DR-006). The block is replaced verbatim on re-install; user content
#      outside the markers is never touched. If CLAUDE.md does not exist
#      a stub is created containing only the block.
#
# Exit codes:
#   0  installed (or dry-run pass)
#   1  any gate failed
#   2  usage / IO error
#   3  already installed (without --upgrade)

set -euo pipefail

VERSION="0.13.10"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PLUGIN="development"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✗${NC} $*" >&2; }

usage() {
  cat <<EOF
CodeNook installer v${VERSION}

Usage:
  bash install.sh [<workspace_path>]                  install plugin into workspace
  bash install.sh --dry-run [<workspace_path>]        gates only, no commit
  bash install.sh --upgrade [<workspace_path>]        allow re-install
  bash install.sh --plugin <id> [<workspace_path>]    plugin id (default: ${DEFAULT_PLUGIN})
  bash install.sh --no-claude-md [<workspace_path>]   skip CLAUDE.md augmentation
  bash install.sh --yes [<workspace_path>]            auto-confirm CLAUDE.md write (CI/non-interactive)
  bash install.sh --check [<workspace_path>]          report install state
  bash install.sh --help                              show this help

When <workspace_path> is omitted, the current directory is used.
EOF
}

# ── arg parsing ──────────────────────────────────────────────────────────
WORKSPACE=""
PLUGIN_ID="$DEFAULT_PLUGIN"
DRY_RUN=""
UPGRADE=""
CHECK_ONLY=0
AUGMENT_CLAUDE=1
AUTO_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --help|-h) usage; exit 0 ;;
    --dry-run) DRY_RUN="--dry-run"; shift ;;
    --upgrade) UPGRADE="--upgrade"; shift ;;
    --plugin)  PLUGIN_ID="${2:-}"; shift 2 ;;
    --no-claude-md) AUGMENT_CLAUDE=0; shift ;;
    --yes|-y) AUTO_YES=1; shift ;;
    --check)   CHECK_ONLY=1; shift ;;
    --) shift; if [ $# -gt 0 ]; then WORKSPACE="$1"; shift; fi ;;
    -*) err "unknown option: $1"; usage >&2; exit 2 ;;
    *)
      if [ -z "$WORKSPACE" ]; then
        WORKSPACE="$1"; shift
      else
        err "unexpected positional arg: $1"; usage >&2; exit 2
      fi
      ;;
  esac
done

if [ -z "$WORKSPACE" ]; then
  WORKSPACE="$PWD"
fi
if [ ! -d "$WORKSPACE" ]; then
  err "workspace path does not exist: $WORKSPACE"; exit 2
fi
WORKSPACE="$(cd "$WORKSPACE" && pwd)"

SOURCE_CORE="$SELF_DIR/skills/codenook-core"
WS_CORE="$WORKSPACE/.codenook/codenook-core"
KERNEL_INSTALL="$WS_CORE/install.sh"   # resolved post-bootstrap (see below)
PLUGIN_SRC="$SELF_DIR/plugins/$PLUGIN_ID"

# ── check-only mode ──────────────────────────────────────────────────────
check_workspace() {
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "🔍 CodeNook v${VERSION} — workspace status"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  Workspace : $WORKSPACE"
  local state_file="$WORKSPACE/.codenook/state.json"
  if [ -f "$state_file" ]; then
    info ".codenook/state.json present"
    cat "$state_file" | sed 's/^/    /'
  else
    warn "no .codenook/state.json — workspace not initialised"
  fi
  if [ -f "$WORKSPACE/CLAUDE.md" ] && grep -q "codenook:begin" "$WORKSPACE/CLAUDE.md" 2>/dev/null; then
    info "CLAUDE.md has codenook bootloader block"
  else
    warn "CLAUDE.md has no codenook bootloader block"
  fi
}
if [ "$CHECK_ONLY" -eq 1 ]; then
  check_workspace
  exit 0
fi

# ── pre-flight ───────────────────────────────────────────────────────────
if [ ! -d "$SOURCE_CORE" ]; then
  err "source codenook-core/ not found: $SOURCE_CORE"; exit 2
fi
if [ ! -d "$PLUGIN_SRC" ]; then
  err "plugin source not found: $PLUGIN_SRC"; exit 2
fi

# ── self-contained kernel bootstrap ──────────────────────────────────────
# Copy <SOURCE_CORE>/* into <workspace>/.codenook/codenook-core/ so the
# workspace owns its own kernel and is independent of this source repo.
# The builtin/init/init.sh implements VERSION-compare + atomic swap and
# is itself part of the kernel we are about to copy, so we shell out to
# the *source* copy here (a single rsync-equivalent step).
SOURCE_INIT="$SOURCE_CORE/skills/builtin/init/init.sh"
if [ ! -x "$SOURCE_INIT" ]; then
  err "source init.sh not executable: $SOURCE_INIT"; exit 2
fi
if ! "$SOURCE_INIT" "$WORKSPACE"; then
  err "kernel bootstrap failed (init.sh exited non-zero); workspace may be in a half-written state"
  err "inspect: $WORKSPACE/.codenook/codenook-core (and any .codenook-core.* staging dirs alongside it)"
  exit 2
fi
info "Kernel staged at $WS_CORE (self-contained)"

if [ ! -x "$KERNEL_INSTALL" ]; then
  err "kernel installer missing after bootstrap: $KERNEL_INSTALL"; exit 2
fi

# Read incoming plugin version from plugin.yaml (best-effort).
read_plugin_version() {
  python3 -c "
import sys, yaml
try:
    d = yaml.safe_load(open('$PLUGIN_SRC/plugin.yaml')) or {}
    print(d.get('version') or '')
except Exception:
    print('')
" 2>/dev/null
}
NEW_VERSION="$(read_plugin_version)"

# E2E-016: idempotent re-install. If state.json shows the same plugin id at
# the same version, auto-promote to --upgrade so G03/G07 don't trip. If the
# version differs, --upgrade must be explicit (preserves accidental-bump
# protection).
STATE_FILE="$WORKSPACE/.codenook/state.json"
EXISTING_VERSION=""
EXISTING_HASH=""
if [ -f "$STATE_FILE" ]; then
  EXISTING_VERSION="$(python3 -c "
import json,sys
try:
    d=json.load(open('$STATE_FILE'))
    for r in (d.get('installed_plugins') or []):
        if r.get('id')=='$PLUGIN_ID':
            print(r.get('version') or ''); break
    else:
        print('')
except Exception:
    print('')
" 2>/dev/null)"
  EXISTING_HASH="$(python3 -c "
import json
try:
    d=json.load(open('$STATE_FILE'))
    for r in (d.get('installed_plugins') or []):
        if r.get('id')=='$PLUGIN_ID':
            print(r.get('files_sha256') or ''); break
    else:
        print('')
except Exception:
    print('')
" 2>/dev/null)"
fi

IDEMPOTENT_RUN=0
if [ -n "$EXISTING_VERSION" ] && [ "$EXISTING_VERSION" = "$NEW_VERSION" ] && [ -z "$UPGRADE" ]; then
  # Same version on disk → automatic upgrade (idempotent path).
  UPGRADE="--upgrade"
  IDEMPOTENT_RUN=1
elif [ -n "$EXISTING_VERSION" ] && [ "$EXISTING_VERSION" != "$NEW_VERSION" ] && [ -z "$UPGRADE" ]; then
  err "plugin '$PLUGIN_ID' is installed at v${EXISTING_VERSION}; this source is v${NEW_VERSION}"
  err "re-run with --upgrade to perform the version bump"
  exit 3
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🤖 CodeNook v${VERSION}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Workspace : $WORKSPACE"
echo "  Plugin    : ${PLUGIN_ID} (from ${PLUGIN_SRC})"
[ -n "$NEW_VERSION" ] && echo "  Version   : ${NEW_VERSION}${EXISTING_VERSION:+ (was ${EXISTING_VERSION})}"
[ -n "$DRY_RUN" ] && echo "  Mode      : DRY-RUN"
[ -n "$UPGRADE" ] && [ "$IDEMPOTENT_RUN" -eq 0 ] && echo "  Mode      : UPGRADE"
[ "$IDEMPOTENT_RUN" -eq 1 ] && echo "  Mode      : IDEMPOTENT (re-install)"
echo ""

if [ "$IDEMPOTENT_RUN" -eq 1 ] && [ -z "$DRY_RUN" ]; then
  # E2E-016: skip the kernel install entirely — same version already on disk.
  # G04 (--upgrade rejects no-op) would otherwise fire. We still re-seed the
  # bin/memory/schemas below to heal any user-deleted files.
  info "↻ already installed (idempotent): plugin ${PLUGIN_ID} v${NEW_VERSION}"
  # E2E-019: still upgrade state.json to the v0.11.3 schema (kernel_version,
  # kernel_dir, files_sha256, schema_version, bin) so the wrapper resolves.
  CN_WS="$WORKSPACE" CN_PLUGIN="$PLUGIN_ID" CN_VER="$NEW_VERSION" \
  CN_KV="$VERSION" CN_KDIR="$WS_CORE/skills/builtin" \
  CN_PSRC="$PLUGIN_SRC" \
  python3 - <<'PY'
import os, sys
sys.path.insert(0, os.path.join(os.environ["CN_KDIR"], "install-orchestrator"))
sys.path.insert(0, os.path.join(os.environ["CN_KDIR"], "_lib"))
from pathlib import Path
import _orchestrator as orch
ws = Path(os.environ["CN_WS"])
sha = orch._aggregate_files_sha256(ws / ".codenook" / "plugins" / os.environ["CN_PLUGIN"])
orch.update_state_json(
    ws, os.environ["CN_PLUGIN"], os.environ["CN_VER"],
    kernel_version=os.environ["CN_KV"],
    kernel_dir=os.environ["CN_KDIR"],
    files_sha256=sha,
)
PY
else
  set +e
  CN_CORE_VERSION="$VERSION" \
  "$KERNEL_INSTALL" --src "$PLUGIN_SRC" --workspace "$WORKSPACE" $DRY_RUN $UPGRADE
  rc=$?
  set -e
  if [ "$rc" -ne 0 ]; then
    err "kernel install exited with rc=$rc"
    exit "$rc"
  fi
  info "Plugin '$PLUGIN_ID' installed into $WORKSPACE/.codenook/"
fi

# ── CLAUDE.md augmentation (DR-006) ──────────────────────────────────────
if [ -n "$DRY_RUN" ]; then
  echo "  [DRY-RUN] Would write CLAUDE.md bootloader block + bin wrapper + memory skeleton"
  exit 0
fi

if [ "$AUGMENT_CLAUDE" -eq 1 ]; then
  # Determine the action that will be taken so the prompt is informative.
  CLAUDE_FILE="$WORKSPACE/CLAUDE.md"
  if [ ! -f "$CLAUDE_FILE" ]; then
    CLAUDE_ACTION="create new CLAUDE.md with codenook bootloader stub"
  elif grep -q "codenook:begin" "$CLAUDE_FILE" 2>/dev/null; then
    CLAUDE_ACTION="replace existing codenook block in CLAUDE.md (idempotent; user content outside markers untouched)"
  else
    CLAUDE_ACTION="append codenook block to your existing CLAUDE.md (your content is preserved above the markers)"
  fi

  PROCEED=1
  if [ "$AUTO_YES" -ne 1 ]; then
    if [ -t 0 ] && [ -t 1 ]; then
      echo ""
      echo "  About to: ${CLAUDE_ACTION}"
      echo "  Target  : ${CLAUDE_FILE}"
      printf "  Proceed? [y/N] "
      read -r reply || reply=""
      case "$reply" in
        y|Y|yes|YES) PROCEED=1 ;;
        *) PROCEED=0 ;;
      esac
    fi
    # Non-interactive (no TTY): proceed silently. CI / piped installs keep
    # their pre-v0.13.2 behaviour. Pass --yes explicitly to suppress the
    # prompt in an interactive shell.
  fi

  if [ "$PROCEED" -ne 1 ]; then
    warn "skipped CLAUDE.md augmentation (user declined)"
    warn "  re-run with --yes to confirm, or --no-claude-md to suppress this prompt"
  else
    python3 "$WS_CORE/skills/builtin/_lib/claude_md_sync.py" \
      --workspace "$WORKSPACE" \
      --version "$VERSION" \
      --plugin "$PLUGIN_ID"
    info "CLAUDE.md bootloader block synced (idempotent)"

    # Warn (don't fail) if the user's own CLAUDE.md content outside
    # the codenook marker block contains legacy v4.x role tokens.
    python3 "$WS_CORE/skills/builtin/_lib/claude_md_linter.py" \
      --marker-only --json "$WORKSPACE/CLAUDE.md" >/dev/null 2>&1 || true
    outside_hits="$(
      {
        python3 "$WS_CORE/skills/builtin/_lib/claude_md_linter.py" \
          --outside-marker-only --json "$WORKSPACE/CLAUDE.md" 2>/dev/null || true
      } | python3 -c "import json,sys
try:
  d=json.load(sys.stdin)
  toks=sorted({f.get('token','') for f in (d.get('errors',[])+d.get('warnings',[])) if f.get('token')})
  print(','.join(t for t in toks if t))
except Exception:
  pass
" || true
    )"
    if [ -n "$outside_hits" ]; then
      warn "legacy v4.x tokens in CLAUDE.md outside codenook block: ${outside_hits}"
      warn "  they're harmless but consider cleanup; rerun with"
      warn "  \`bash install.sh --migrate-claude-md\` (planned v0.12)"
    fi
  fi
fi

# ── seed schemas, memory skeleton, bin wrapper ──────────────────────────
TPL_DIR="$WS_CORE/templates"
SCHEMAS_SRC="$WS_CORE/schemas"

mkdir -p "$WORKSPACE/.codenook/schemas"
for f in task-state.schema.json hitl-entry.schema.json queue-entry.schema.json \
         locks-entry.schema.json installed.schema.json; do
  [ -f "$SCHEMAS_SRC/$f" ] && cp -f "$SCHEMAS_SRC/$f" "$WORKSPACE/.codenook/schemas/$f"
done
[ -f "$TPL_DIR/state.example.md" ] && \
  cp -f "$TPL_DIR/state.example.md" "$WORKSPACE/.codenook/schemas/state.example.md"
# E2E-P-006: legacy location had state.example.md at .codenook/ root.
# Remove the stale copy if it exists from a previous install.
[ -f "$WORKSPACE/.codenook/state.example.md" ] && \
  rm -f "$WORKSPACE/.codenook/state.example.md" || true

# Memory skeleton (idempotent — never overwrite existing files).
MEM_DIR="$WORKSPACE/.codenook/memory"
for sub in knowledge skills history _pending; do
  mkdir -p "$MEM_DIR/$sub"
  [ -f "$MEM_DIR/$sub/.gitkeep" ] || : > "$MEM_DIR/$sub/.gitkeep"
done
if [ ! -f "$MEM_DIR/config.yaml" ]; then
  cp "$TPL_DIR/memory-config.yaml" "$MEM_DIR/config.yaml"
fi

# Bin wrapper (idempotent — overwrite is OK; it's source-controlled).
BIN_DIR="$WORKSPACE/.codenook/bin"
mkdir -p "$BIN_DIR"
cp -f "$TPL_DIR/codenook-wrapper.sh" "$BIN_DIR/codenook"
chmod +x "$BIN_DIR/codenook"
# Windows shim so PowerShell / cmd users can call `.codenook\bin\codenook ...`
# without the OS popping the "Open with…" dialog for the extension-less script.
if [ -f "$TPL_DIR/codenook-wrapper.cmd" ]; then
  cp -f "$TPL_DIR/codenook-wrapper.cmd" "$BIN_DIR/codenook.cmd"
fi

info "Seeded .codenook/{schemas,memory,bin/codenook}"

# E2E-P-001: assert state.json.kernel_version matches the installer VERSION.
# Pass the path via env so msys-style POSIX paths (/c/...) are converted to
# native Windows form before native python sees them on Windows / Git-Bash.
ACTUAL_KV="$(CN_STATE="$WORKSPACE/.codenook/state.json" python3 -c "import json,os; print(json.load(open(os.environ['CN_STATE'])).get('kernel_version',''))" 2>/dev/null || echo '')"
if [ "$ACTUAL_KV" != "$VERSION" ]; then
  err "post-install assertion failed: state.json.kernel_version='$ACTUAL_KV' != VERSION='$VERSION'"
  err "  (this indicates the inner skills/codenook-core/VERSION drifted from the root VERSION)"
  exit 1
fi

echo ""
echo "  Quick start:"
echo "    cd \"$WORKSPACE\""
echo "    .codenook/bin/codenook --help"
echo "    .codenook/bin/codenook task new --title \"Implement X\""
echo "    .codenook/bin/codenook tick --task T-001"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
