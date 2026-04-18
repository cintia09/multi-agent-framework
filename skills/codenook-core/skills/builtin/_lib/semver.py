"""Tiny SemVer 2.0 parser + comparator (no third-party deps).

Used by gates G04 (plugin-version-check) and G06 (plugin-deps-check).
Extracted during the M2 refactor pass after both gates landed
GREEN with copies of the same logic.

Reference: https://semver.org §11 (precedence rules).
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

# Official SemVer 2.0.0 regex (semver.org §9, simplified to drop named
# groups so it stays under a single line per part).
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

Parsed = Tuple[int, int, int, Optional[str]]


def parse(v: str) -> Optional[Parsed]:
    if not isinstance(v, str):
        return None
    m = SEMVER_RE.match(v)
    if not m:
        return None
    return (int(m[1]), int(m[2]), int(m[3]), m[4])


def _pre_key(pre: Optional[str]):
    # Per semver §11: a version with pre-release < the same without.
    if pre is None:
        return (1,)
    parts = []
    for p in pre.split("."):
        parts.append((0, int(p)) if p.isdigit() else (1, p))
    return (0, tuple(parts))


def cmp_key(parsed: Parsed):
    major, minor, patch, pre = parsed
    return (major, minor, patch, _pre_key(pre))


# Comparator parsing (used by G06).
OPS = ("==", "!=", ">=", "<=", ">", "<", "=")


def split_constraint(c: str):
    c = c.strip()
    for op in OPS:
        if c.startswith(op):
            return op, c[len(op):].strip()
    return None, None


def satisfies(core: Parsed, op: str, target: Parsed) -> bool:
    a, b = cmp_key(core), cmp_key(target)
    if op in ("==", "="):
        return a == b
    if op == "!=":
        return a != b
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    return False
