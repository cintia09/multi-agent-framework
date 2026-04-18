#!/usr/bin/env python3
"""Gate G11 — plugin-path-normalize."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

GATE = "plugin-path-normalize"
PATH_EXTS = (".sh", ".py", ".md", ".yaml", ".yml", ".json")


def looks_like_path(s: str) -> bool:
    if "/" in s:
        return True
    return s.endswith(PATH_EXTS)


def walk_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for v in node.values():
            yield from walk_strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_strings(v)


def check_path_value(s: str) -> list[str]:
    out: list[str] = []
    if s.startswith("/"):
        out.append(f"absolute path declared: {s!r}")
    if s.startswith("~"):
        out.append(f"home-expansion path declared: {s!r}")
    parts = s.split("/")
    if any(p == ".." for p in parts):
        out.append(f"path contains '..' segment: {s!r}")
    return out


def main() -> int:
    src = Path(os.environ["CN_SRC"]).resolve()
    json_out = os.environ.get("CN_JSON", "0") == "1"
    reasons: list[str] = []

    # 1. No symlinks at all.
    for root, dirs, files in os.walk(src, followlinks=False):
        for name in dirs + files:
            p = Path(root) / name
            if p.is_symlink():
                reasons.append(f"symlink not allowed: {p.relative_to(src)}")

    # 2. YAML-declared path strings.
    for root, _, files in os.walk(src, followlinks=False):
        for name in files:
            if not name.endswith((".yaml", ".yml")):
                continue
            p = Path(root) / name
            if p.is_symlink():
                continue
            try:
                doc = yaml.safe_load(p.read_text(encoding="utf-8"))
            except (OSError, yaml.YAMLError):
                continue
            for s in walk_strings(doc):
                if looks_like_path(s):
                    for r in check_path_value(s):
                        reasons.append(
                            f"{p.relative_to(src)}: {r}"
                        )

    return _emit(json_out, reasons)


def _emit(json_out: bool, reasons: list[str]) -> int:
    ok = not reasons
    if json_out:
        print(json.dumps({"ok": ok, "gate": GATE, "reasons": reasons}))
    else:
        for r in reasons:
            print(f"[G11] {r}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
