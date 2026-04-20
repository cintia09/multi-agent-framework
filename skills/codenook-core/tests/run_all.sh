#!/usr/bin/env bash
# CodeNook test runner — runs the complete bats + pytest suite.
#
# Usage:  bash skills/codenook-core/tests/run_all.sh
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"

echo "== bats =="
bats "$HERE"/*.bats "$HERE"/e2e/*.bats

echo ""
echo "== pytest =="
python3 -m pytest "$HERE/python/" -q
