#!/usr/bin/env bats
# M7 routing -- with all 3 M6/M7 plugins installed:
#   * "implement a Python function" -> development
#   * "write a blog post about AI"  -> writing
#   * "summarise this PDF"          -> generic (fallback)
#
# Uses the M7 router_select shim at
#   skills/codenook-core/skills/builtin/_lib/router_select.py
# which routes on the new packaging-spec fields (keywords, applies_to,
# routing.priority). The shim does NOT replace the M3 router; the
# README in plugins/generic and plugins/writing documents the split.

load helpers/load
load helpers/assertions

LIB_DIR="$CORE_ROOT/skills/builtin/_lib"
PLUGINS_ROOT="$CORE_ROOT/../../plugins"

run_select() {
  # $1 = input text
  python3 - "$1" "$LIB_DIR" "$PLUGINS_ROOT" <<'PY'
import sys, yaml, pathlib
text, lib_dir, plugins_root = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, lib_dir)
from router_select import select, select_with_score

manifests = []
for p in sorted(pathlib.Path(plugins_root).iterdir()):
    yml = p / "plugin.yaml"
    if not yml.is_file(): continue
    d = yaml.safe_load(open(yml)) or {}
    manifests.append(d)

chosen = select(text, manifests)
diag = select_with_score(text, manifests)
print(chosen)
print(diag)
PY
}

@test "router_select shim is importable" {
  run python3 -c "import sys; sys.path.insert(0, '$LIB_DIR'); import router_select; print('ok')"
  [ "$status" -eq 0 ]
  [ "$output" = "ok" ]
}

@test "router_select: 'implement a Python function' -> development" {
  run run_select "implement a Python function"
  [ "$status" -eq 0 ]
  echo "$output" | head -1 | grep -q '^development$'
}

@test "router_select: 'write a blog post about AI' -> writing" {
  run run_select "write a blog post about AI"
  [ "$status" -eq 0 ]
  echo "$output" | head -1 | grep -q '^writing$'
}

@test "router_select: 'summarise this PDF' -> generic (wildcard fallback)" {
  run run_select "summarise this PDF"
  [ "$status" -eq 0 ]
  echo "$output" | head -1 | grep -q '^generic$'
}

@test "router_select: 'tell me a joke' -> generic (no specialised match)" {
  run run_select "tell me a joke"
  [ "$status" -eq 0 ]
  echo "$output" | head -1 | grep -q '^generic$'
}

@test "router_select: priority breaks score ties" {
  run python3 - "$LIB_DIR" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from router_select import select
manifests = [
    {"id": "a", "keywords": ["foo"], "routing": {"priority": 10}},
    {"id": "b", "keywords": ["foo"], "routing": {"priority": 50}},
]
assert select("foo", manifests) == "b", select("foo", manifests)
print("ok")
PY
  [ "$status" -eq 0 ]
  [ "$output" = "ok" ]
}

@test "router_select: alphabetical id breaks priority ties" {
  run python3 - "$LIB_DIR" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from router_select import select
manifests = [
    {"id": "z-plugin", "keywords": ["foo"], "routing": {"priority": 50}},
    {"id": "a-plugin", "keywords": ["foo"], "routing": {"priority": 50}},
]
assert select("foo", manifests) == "a-plugin"
print("ok")
PY
  [ "$status" -eq 0 ]
  [ "$output" = "ok" ]
}

@test "router_select: wildcard '*' is excluded from positive scoring" {
  # If 'foo' matches any keyword/applies_to in 'special', special wins
  # over the wildcard fallback regardless of priority.
  run python3 - "$LIB_DIR" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from router_select import select
manifests = [
    {"id": "fallback", "applies_to": ["*"], "routing": {"priority": 99}},
    {"id": "special",  "keywords": ["foo"], "routing": {"priority": 1}},
]
assert select("foo bar", manifests) == "special"
# When nothing matches, fallback wins.
assert select("zzzz", manifests) == "fallback"
print("ok")
PY
  [ "$status" -eq 0 ]
  [ "$output" = "ok" ]
}

@test "router_select: returns None when no manifests at all" {
  run python3 - "$LIB_DIR" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from router_select import select
assert select("anything", []) is None
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "router_select: returns None when no match and no wildcard" {
  run python3 - "$LIB_DIR" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from router_select import select
manifests = [
    {"id": "alpha", "keywords": ["foo"]},
    {"id": "beta",  "keywords": ["bar"]},
]
assert select("nothing matches here", manifests) is None
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "router_select: case-insensitive keyword matching" {
  run python3 - "$LIB_DIR" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from router_select import select
manifests = [
    {"id": "cap", "keywords": ["BlOg"]},
    {"id": "fb",  "applies_to": ["*"]},
]
assert select("write a Blog now", manifests) == "cap"
print("ok")
PY
  [ "$status" -eq 0 ]
}

@test "router_select: select_with_score returns id, score, priority, reason" {
  run python3 - "$LIB_DIR" <<'PY'
import sys; sys.path.insert(0, sys.argv[1])
from router_select import select_with_score
manifests = [
    {"id": "writing", "keywords": ["blog"], "routing": {"priority": 50}},
    {"id": "generic", "applies_to": ["*"],  "routing": {"priority": 10}},
]
d = select_with_score("write a blog post", manifests)
assert d["id"] == "writing", d
assert d["score"] >= 10, d
assert d["priority"] == 50, d
assert d["reason"] == "keyword_or_applies_to", d
e = select_with_score("hello world", manifests)
assert e["id"] == "generic" and e["reason"] == "wildcard_fallback", e
print("ok")
PY
  [ "$status" -eq 0 ]
}
