#!/usr/bin/env bats
# M6 U5 — manifest-templates/phase-{1..8}-<role>.md

load helpers/load
load helpers/assertions

MT_DIR="$CORE_ROOT/../../plugins/development/manifest-templates"
EXPECTED="phase-1-clarifier.md phase-2-designer.md phase-3-planner.md phase-4-implementer.md phase-5-builder.md phase-6-reviewer.md phase-7-submitter.md phase-8-test-planner.md phase-9-tester.md phase-10-acceptor.md phase-11-reviewer.md"

@test "exactly 11 manifest templates exist with expected names" {
  for f in $EXPECTED; do
    [ -f "$MT_DIR/$f" ] || { echo "missing $f" >&2; return 1; }
  done
  count=$(ls "$MT_DIR"/phase-*.md | wc -l | tr -d ' ')
  [ "$count" -eq 11 ]
}

@test "every template references {task_id} and {target_dir} placeholders" {
  for f in $EXPECTED; do
    grep -q '{task_id}' "$MT_DIR/$f"     || { echo "$f missing {task_id}" >&2; return 1; }
    grep -q '{target_dir}' "$MT_DIR/$f"  || { echo "$f missing {target_dir}" >&2; return 1; }
  done
}

@test "every template references {iteration}, {prior_summary_path}, {criteria_path}" {
  for f in $EXPECTED; do
    for ph in '{iteration}' '{prior_summary_path}' '{criteria_path}'; do
      grep -qF "$ph" "$MT_DIR/$f" || { echo "$f missing $ph" >&2; return 1; }
    done
  done
}

@test "every template is under 500 lines (sanity)" {
  for f in $EXPECTED; do
    n=$(wc -l <"$MT_DIR/$f" | tr -d ' ')
    [ "$n" -lt 500 ] || { echo "$f is $n lines (cap 500)" >&2; return 1; }
  done
}
