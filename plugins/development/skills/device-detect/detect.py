#!/usr/bin/env python3
"""device-detect/detect.py — enumerate generic execution-environment
markers under <target-dir> so the test-planner can do a memory lookup
(and, on miss, ask the user) about the right environment.

This skill never hard-codes ADB / QEMU / device-type-specific names;
it only reports generic buckets (local-*, recorded-env, custom-runner,
unknown-config, unknown). Mapping bucket → concrete environment is
memory + user's job.

Spec: see SKILL.md in this directory.

Exit codes:
  0  detected (or unknown bucket emitted) — caller reads JSON/plain
  2  usage error (bad arg, target dir missing, etc.)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


# (marker filename, bucket name)
TIER1_MARKERS: list[tuple[str, str]] = [
    ("pyproject.toml", "local-python"),
    ("setup.py",       "local-python"),
    ("pytest.ini",     "local-python"),
    ("tox.ini",        "local-python"),
    ("package.json",   "local-node"),
    ("go.mod",         "local-go"),
]

TIER1_NAMES = {m for m, _ in TIER1_MARKERS}

GENERIC_CONFIG_EXTS = (".cfg", ".toml", ".yaml")


def _print_help_from_skill_md(here: Path) -> None:
    sm = here / "SKILL.md"
    if sm.is_file():
        with sm.open() as fh:
            for i, line in enumerate(fh):
                if i >= 80:
                    break
                sys.stdout.write(line)


def _scan(target: Path) -> tuple[list[str], dict[str, list[str]]]:
    """Return (ordered_buckets, bucket→markers)."""
    buckets: list[str] = []
    hits: dict[str, list[str]] = {}

    def add(bucket: str, marker: str) -> None:
        if bucket not in hits:
            hits[bucket] = []
            buckets.append(bucket)
        hits[bucket].append(marker)

    # tier 1: known software runners
    for fname, bucket in TIER1_MARKERS:
        if (target / fname).exists():
            add(bucket, fname)

    # tier 2: prior recorded environment (.codenook-test-env*, .test-env*)
    try:
        for entry in sorted(target.iterdir()):
            name = entry.name
            if name.startswith(".codenook-test-env") or name.startswith(".test-env"):
                add("recorded-env", name)
    except OSError:
        pass

    # tier 3: workspace-supplied custom runners under scripts/run-*-tests.sh
    scripts_dir = target / "scripts"
    if scripts_dir.is_dir():
        for entry in sorted(scripts_dir.iterdir()):
            n = entry.name
            if n.startswith("run-") and n.endswith("-tests.sh"):
                add("custom-runner", f"scripts/{n}")

    # tier 4: any *.cfg / *.toml / *.yaml not already classified
    try:
        for entry in sorted(target.iterdir()):
            if not entry.is_file():
                continue
            n = entry.name
            if n in TIER1_NAMES:
                continue
            if n.endswith(GENERIC_CONFIG_EXTS):
                add("unknown-config", n)
    except OSError:
        pass

    if not buckets:
        buckets.append("unknown")
        hits["unknown"] = ["(no markers found)"]

    return buckets, hits


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(
        prog="detect.py",
        description="Generic execution-environment marker scan",
        add_help=False,
    )
    p.add_argument("--target-dir", dest="target", default=None)
    p.add_argument("--json", dest="json_out", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return 2

    if args.help:
        _print_help_from_skill_md(here)
        return 0
    if not args.target:
        print("detect.py: --target-dir required", file=sys.stderr)
        return 2

    target = Path(args.target)
    if not target.is_dir():
        print(f"detect.py: target dir not found: {target}", file=sys.stderr)
        return 2

    buckets, hits = _scan(target)

    primary = next((b for b in buckets if b != "unknown"), buckets[0])
    hint_base = os.path.basename(target.resolve())
    hint = f"test-environment target={hint_base}"

    if args.json_out:
        out = {
            "target":              str(target),
            "buckets":             buckets,
            "primary":             primary,
            "markers":             hits,
            "memory_search_hint":  hint,
        }
        print(json.dumps(out))
    else:
        print(f"target: {target}")
        print(f"primary: {primary}")
        print(f"memory_search_hint: {hint}")
        print("buckets:")
        for b in buckets:
            print(f"  - {b}: {','.join(hits[b])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
