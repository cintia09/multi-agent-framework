#!/usr/bin/env python3
"""Gate G06 — plugin-deps-check.  Uses _lib.semver."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from semver import parse, satisfies, split_constraint  # noqa: E402

GATE = "plugin-deps-check"


def main() -> int:
    src = Path(os.environ["CN_SRC"])
    core_v = os.environ.get("CN_CORE_VERSION", "")
    json_out = os.environ.get("CN_JSON", "0") == "1"
    reasons: list[str] = []

    core_parsed = parse(core_v) if core_v else None
    if core_parsed is None:
        reasons.append(f"current core VERSION {core_v!r} is not valid semver")
        return _emit(json_out, reasons)

    try:
        plugin = yaml.safe_load((src / "plugin.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        reasons.append(f"cannot read plugin.yaml: {e}")
        return _emit(json_out, reasons)

    requires = plugin.get("requires") or {}
    constraint = requires.get("core_version")
    if constraint is None:
        return _emit(json_out, reasons)
    if not isinstance(constraint, str):
        reasons.append("requires.core_version must be a string")
        return _emit(json_out, reasons)

    parts = [p.strip() for p in constraint.split(",") if p.strip()]
    if not parts:
        reasons.append("requires.core_version is empty")
        return _emit(json_out, reasons)

    for part in parts:
        op, rhs = split_constraint(part)
        if op is None:
            reasons.append(f"unparseable comparator: {part!r}")
            continue
        target = parse(rhs)
        if target is None:
            reasons.append(f"comparator operand not semver: {rhs!r}")
            continue
        if not satisfies(core_parsed, op, target):
            reasons.append(
                f"core_version {core_v} fails constraint {part}"
            )

    return _emit(json_out, reasons)


def _emit(json_out: bool, reasons: list[str]) -> int:
    ok = not reasons
    if json_out:
        print(json.dumps({"ok": ok, "gate": GATE, "reasons": reasons}))
    else:
        for r in reasons:
            print(f"[G06] {r}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
