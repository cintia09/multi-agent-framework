#!/usr/bin/env bash
set -euo pipefail

# CodeNook skill sync — copies repo skills to all installed locations
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_SRC="${REPO_DIR}/skills/codenook-init"

# Security scan before syncing
if [[ -f "${REPO_DIR}/skill-security-scan.sh" ]]; then
  echo "🔐 Running security scan..."
  if ! "${REPO_DIR}/skill-security-scan.sh" "$SKILL_SRC"; then
    scan_exit=$?
    if [[ "$scan_exit" -eq 2 ]]; then
      echo "❌ Security scan BLOCKED sync. Critical issues found."
      exit 2
    else
      echo "⚠️  Security scan found warnings. Review above."
      read -r -p "Continue sync? [y/N] " confirm
      if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo "Sync cancelled."
        exit 1
      fi
    fi
  fi
  echo ""
fi

TARGETS=(
  "$HOME/.copilot/skills/codenook-init"
  "$HOME/.claude/skills/codenook-init"
)

for target in "${TARGETS[@]}"; do
  if [[ -d "$target" ]]; then
    mkdir -p "$target/templates" "$target/hitl-adapters"
    cp "$SKILL_SRC/SKILL.md" "$target/SKILL.md"
    cp "$SKILL_SRC/templates/codenook.instructions.md" "$target/templates/codenook.instructions.md"
    for f in "$SKILL_SRC"/templates/*.agent.md; do
      [[ -f "$f" ]] && cp "$f" "$target/templates/$(basename "$f")"
    done
    for f in "$SKILL_SRC"/hitl-adapters/*; do
      [[ -f "$f" ]] && cp "$f" "$target/hitl-adapters/$(basename "$f")"
    done
    echo "✅ Synced → $target"
  else
    echo "⏭️  Skipped (not found): $target"
  fi
done

echo "Done. Version: $(cat "$REPO_DIR/VERSION")"
