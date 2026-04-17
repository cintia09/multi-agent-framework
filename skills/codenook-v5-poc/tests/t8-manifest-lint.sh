#!/usr/bin/env bash
# T8: Prompt manifest format lint
# Validates that any manifest files under tasks/*/prompts/ follow the required format.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${1:-$SCRIPT_DIR/fixtures}"

FAIL=0

validate_manifest() {
  local file="$1"
  local errs=0

  grep -q '^Template:' "$file" || { echo "    ❌ missing 'Template:' field"; errs=$((errs+1)); }
  grep -q '^Variables:' "$file" || { echo "    ❌ missing 'Variables:' block"; errs=$((errs+1)); }
  grep -q '^Output_to:' "$file" || { echo "    ❌ missing 'Output_to:' field"; errs=$((errs+1)); }
  grep -q '^Summary_to:' "$file" || { echo "    ❌ missing 'Summary_to:' field"; errs=$((errs+1)); }

  local size=$(wc -c < "$file")
  if (( size > 2000 )); then
    echo "    ❌ manifest too large: ${size} bytes (>2000, likely >500 tokens)"
    errs=$((errs+1))
  fi

  local bad_refs=$(grep -oE '@[^ ]+' "$file" | grep -vE '^@[./_a-zA-Z0-9-]+$' || true)
  if [[ -n "$bad_refs" ]]; then
    echo "    ❌ suspicious @ references: $bad_refs"
    errs=$((errs+1))
  fi

  if ! grep -q '@' "$file"; then
    echo "    ⚠️  no @ references found — likely inline content (discouraged)"
  fi

  return $errs
}

mkdir -p "$SCRIPT_DIR/fixtures"
VALID_FIXTURE="$SCRIPT_DIR/fixtures/valid-manifest.md"
INVALID_FIXTURE="$SCRIPT_DIR/fixtures/invalid-manifest.md"

cat > "$VALID_FIXTURE" <<'EOF'
Template: @prompts-templates/implementer.md
Variables:
  task_id: T-001
  phase: implement
  iteration: 1
  task_description: @../task.md
  clarify_output: @../outputs/phase-1-clarify-summary.md
  project_env: @../../../project/ENVIRONMENT.md
  project_conv: @../../../project/CONVENTIONS.md
Output_to: @../outputs/phase-2-implementer.md
Summary_to: @../outputs/phase-2-implementer-summary.md
EOF

cat > "$INVALID_FIXTURE" <<'EOF'
Some random text without any required fields.

This manifest is missing everything important.
EOF

echo "=== T8: Manifest Format Lint ==="
echo ""

echo "[1] Validating fixture VALID manifest (should pass):"
valid_output=$(validate_manifest "$VALID_FIXTURE" 2>&1 && echo "__OK__" || echo "__FAIL__")
if echo "$valid_output" | grep -q '__OK__'; then
  echo "    ✅ valid manifest passes lint"
else
  echo "    ❌ valid manifest FAILED lint (linter bug)"
  echo "$valid_output"
  FAIL=$((FAIL+1))
fi

echo ""
echo "[2] Validating fixture INVALID manifest (should fail):"
invalid_output=$(validate_manifest "$INVALID_FIXTURE" 2>&1 || true)
if echo "$invalid_output" | grep -q '❌'; then
  echo "    ✅ invalid manifest correctly rejected"
else
  echo "    ❌ linter failed to detect invalid manifest"
  FAIL=$((FAIL+1))
fi

echo ""
echo "[3] Scanning real manifests (if any) under: $TARGET_DIR"
if [[ -d "$TARGET_DIR" ]]; then
  MANIFESTS=$(find "$TARGET_DIR" -path '*/tasks/*/prompts/*.md' -type f 2>/dev/null || true)
  if [[ -z "$MANIFESTS" ]]; then
    echo "    (no runtime manifests found — expected for fresh workspace)"
  else
    while IFS= read -r m; do
      echo "  checking: $m"
      if ! validate_manifest "$m"; then
        FAIL=$((FAIL+1))
      fi
    done <<< "$MANIFESTS"
  fi
fi

echo ""
if [[ $FAIL -eq 0 ]]; then
  echo "=== T8 PASSED ==="
  exit 0
else
  echo "=== T8 FAILED ($FAIL issues) ==="
  exit 1
fi
