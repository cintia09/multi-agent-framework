#!/usr/bin/env python3
"""validators/post-test.py — mechanical post-condition check.

Verifies the expected output file exists and has YAML frontmatter
with a verdict field and the core test report sections.

Usage: post-test.py <task_id>
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
        print("usage: post-test.py <task_id>", file=sys.stderr)
        return 2
    tid = args[0]
    out = Path(f".codenook/tasks/$TID/outputs/phase-9-tester.md".replace("$TID", tid))
    if not out.is_file():
        print(f"post-test: missing {out}", file=sys.stderr)
        return 1
    text = out.read_text(encoding="utf-8", errors="replace")
    fm = parse_frontmatter(text)
    verdict = fm.get("verdict")
    if not verdict:
        print(f"post-test: {out} lacks verdict frontmatter", file=sys.stderr)
        return 1

    required_sections = [
        "## Submitted Ref",
        "## Test Inventory",
        "## Execution",
        "## Failures",
        "## Coverage Gaps",
        "## Environment Notes",
    ]
    missing = [section for section in required_sections if section not in text]
    if missing:
        print(
            f"post-test: {out} missing required sections: {', '.join(missing)}",
            file=sys.stderr,
        )
        return 1

    if verdict == "ok" and is_missing(fm.get("submitted_ref")):
        print(f"post-test: {out} missing submitted_ref for verdict=ok", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
