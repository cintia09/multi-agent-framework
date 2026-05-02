#!/usr/bin/env python3
"""validators/post-test-plan.py - mechanical post-condition check.

Verifies the test plan binds cases to a concrete submitted ref (or n/a
for profiles without a submit phase) before the tester runs.

Usage: post-test-plan.py <task_id>
CWD == workspace root.
"""
from __future__ import annotations

import sys
from pathlib import Path


def parse_frontmatter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    data: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return data
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def is_missing(value: str | None) -> bool:
    return not value or value.strip().lower() in {"", "missing", "none", "null", "todo", "tbd"}


def main(argv=None) -> int:
    args = (argv if argv is not None else sys.argv)[1:]
    if not args:
        print("usage: post-test-plan.py <task_id>", file=sys.stderr)
        return 2
    tid = args[0]
    out = Path(f".codenook/tasks/$TID/outputs/phase-8-test-planner.md".replace("$TID", tid))
    if not out.is_file():
        print(f"post-test-plan: missing {out}", file=sys.stderr)
        return 1

    text = out.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    verdict = fm.get("verdict")
    if not verdict:
        print(f"post-test-plan: {out} lacks verdict frontmatter", file=sys.stderr)
        return 1

    required_frontmatter = ["case_count", "runner", "environment", "environment_source", "submitted_ref"]
    missing_frontmatter = [key for key in required_frontmatter if is_missing(fm.get(key))]
    if verdict == "ok" and missing_frontmatter:
        print(
            f"post-test-plan: {out} missing frontmatter for verdict=ok: {', '.join(missing_frontmatter)}",
            file=sys.stderr,
        )
        return 1

    if verdict == "ok":
        try:
            case_count = int(fm.get("case_count", "0"))
        except ValueError:
            case_count = 0
        if case_count <= 0:
            print(f"post-test-plan: {out} case_count must be > 0 for verdict=ok", file=sys.stderr)
            return 1

    required_sections = ["## Submitted Ref", "## Test Cases"]
    missing_sections = [section for section in required_sections if section not in text]
    if verdict == "ok" and missing_sections:
        print(
            f"post-test-plan: {out} missing required sections: {', '.join(missing_sections)}",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
