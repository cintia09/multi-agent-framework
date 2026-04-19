#!/usr/bin/env bash
# CodeNook v6 — pre-commit hook template (M9.8).
#
# Install per checkout::
#
#   cp skills/codenook-core/templates/pre-commit-hook.sh \
#      .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# The hook fails closed when:
#   1. plugins/ is being modified outside of an explicit upgrade
#      (delegated to _lib/plugin_readonly.py — see M9.7).
#   2. CLAUDE.md is malformed or violates the M9.7 memory protocol.
#   3. Any staged blob contains a known secret (AWS keys, OpenAI / GH
#      PATs, RSA private keys, internal IPs, DB connection strings —
#      see _lib/secret_scan.py).
#
# Exit 0 → commit proceeds. Exit non-zero → commit is rejected.
set -eu

# Locate the repo root and the _lib dir relative to it.
repo_root="$(git rev-parse --show-toplevel)"
# Allow CN_LIB_DIR override so the hook works in checkouts that
# vendor or symlink CodeNook from outside the worktree.
lib_dir="${CN_LIB_DIR:-${repo_root}/skills/codenook-core/skills/builtin/_lib}"

fail() {
  echo "[pre-commit] REJECTED: $*" >&2
  exit 1
}

# ---------------------------------------------------------------- 0. fast staged-plugins gate
# This gate runs *before* the python helpers so even a checkout that
# does not vendor codenook-core still rejects writes under the repo's
# top-level ``plugins/`` tree (the read-only invariant).
#
# fix-r1 (M9.8): anchor to the repo root so nested fixture paths such
# as ``tests/fixtures/plugins/...`` are NOT swept up — git's
# ``--name-only`` already emits paths relative to the repo root, so a
# ``^plugins/`` anchor is sufficient.
staged_plugins="$(git diff --cached --name-only --diff-filter=AM | grep -E '^plugins/' || true)"
if [ -n "$staged_plugins" ]; then
  fail "staged write under plugins/ — read-only invariant violated:
$staged_plugins"
fi

if [ ! -d "$lib_dir" ]; then
  # CodeNook core not present in this checkout — skip the python
  # helpers but the staged-plugins gate above has already run.
  exit 0
fi

# ---------------------------------------------------------------- 1. plugin readonly (static checker)
if ! PYTHONPATH="$lib_dir" python3 "$lib_dir/plugin_readonly.py" \
       --target "$repo_root" --json >/dev/null 2>&1; then
  echo "[pre-commit] plugin_readonly check failed:" >&2
  PYTHONPATH="$lib_dir" python3 "$lib_dir/plugin_readonly.py" \
    --target "$repo_root" --json >&2 || true
  fail "plugin tree may not be modified by extractors / agents"
fi

# ---------------------------------------------------------------- 2. CLAUDE.md lint
if [ -f "$repo_root/CLAUDE.md" ]; then
  if ! PYTHONPATH="$lib_dir" python3 "$lib_dir/claude_md_linter.py" \
         --check-claude-md "$repo_root/CLAUDE.md" >/dev/null 2>&1; then
    echo "[pre-commit] CLAUDE.md linter found errors:" >&2
    PYTHONPATH="$lib_dir" python3 "$lib_dir/claude_md_linter.py" \
      --check-claude-md "$repo_root/CLAUDE.md" >&2 || true
    fail "CLAUDE.md linter errors must be fixed before commit"
  fi
fi

# ---------------------------------------------------------------- 3. secret scan
# Run the shared SECRET_PATTERNS regex set against every staged blob.
staged_files="$(git diff --cached --name-only --diff-filter=AM)"
if [ -n "$staged_files" ]; then
  scan_result="$(
    PYTHONPATH="$lib_dir" FILES="$staged_files" REPO="$repo_root" python3 - <<'PY'
import os, sys
from pathlib import Path

sys.path.insert(0, os.environ["PYTHONPATH"])
from secret_scan import scan_secrets

repo = Path(os.environ["REPO"])
hits = []
for rel in os.environ["FILES"].splitlines():
    rel = rel.strip()
    if not rel:
        continue
    p = repo / rel
    if not p.is_file():
        continue
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    hit, rule = scan_secrets(text)
    if hit:
        hits.append(f"{rel}: {rule}")
if hits:
    print("\n".join(hits))
    sys.exit(1)
PY
  )" || {
    echo "[pre-commit] secret scanner hits:" >&2
    echo "$scan_result" >&2
    fail "remove the secret(s) above before committing"
  }
fi

exit 0
