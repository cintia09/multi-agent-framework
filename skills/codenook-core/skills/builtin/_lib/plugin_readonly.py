#!/usr/bin/env python3
"""Plugin read-only enforcement (M9.7).

Two complementary defences:

1. **Runtime guard** — :func:`assert_writable_path` raises
   :class:`PluginReadOnlyViolation` (a ``PermissionError`` subclass)
   when a write target resolves under a ``plugins/`` directory. The
   memory_layer central choke point (``_atomic_write_text``) calls
   this on every write, so any extractor / router / orchestrator-tick
   path that accidentally targets ``plugins/`` fails closed.

2. **Static checker** — when invoked as a CLI, walks a target tree
   and flags any source line that opens, replaces or copies a path
   under ``plugins/``. CI / pre-commit can run::

       python3 plugin_readonly.py --target <dir> [--json]

   Exit 0 if no violations, 1 otherwise. Emits JSON envelope with
   ``scanned_files`` and ``writes_to_plugins`` (list of
   ``{file, line, snippet, kind}``) when ``--json`` is set.

See ``docs/v6/memory-and-extraction-v6.md`` §2.1 / §9 for the
canonical layering rule (FR-RO-1, FR-RO-2, AC-RO-1, AC-RO-2).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Iterable


class PluginReadOnlyViolation(PermissionError):
    """Raised when a write would land under a ``plugins/`` directory."""


# ---------------------------------------------------------------- runtime


def _has_plugins_segment(parts: tuple[str, ...]) -> bool:
    return any(seg == "plugins" for seg in parts)


def assert_writable_path(
    path: os.PathLike[str] | str,
    workspace_root: os.PathLike[str] | str | None = None,
    *,
    asset_type: str = "unknown",
) -> None:
    """Raise :class:`PluginReadOnlyViolation` if ``path`` is read-only.

    A path is read-only when, in the resolved form, any directory
    component is named ``plugins``. When ``workspace_root`` is given,
    only paths *inside* the workspace are checked (external writes are
    none of our business).

    On violation, an audit record is appended to the workspace's
    ``extraction-log.jsonl`` (best-effort; never re-raises from the
    audit path so the original ``PluginReadOnlyViolation`` reaches the
    caller).
    """
    p = Path(path).resolve()
    if workspace_root is not None:
        ws = Path(workspace_root).resolve()
        try:
            rel_parts = p.relative_to(ws).parts
        except ValueError:
            return
        bad = _has_plugins_segment(rel_parts)
    else:
        bad = _has_plugins_segment(p.parts)

    if not bad:
        return

    if workspace_root is not None:
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            from extract_audit import audit  # noqa: WPS433

            audit(
                workspace_root,
                asset_type=asset_type,
                outcome="plugin_readonly_violation",
                verdict="rejected",
                reason=str(p),
            )
        except Exception:  # pragma: no cover — audit must never mask the real error
            pass

    raise PluginReadOnlyViolation(
        f"refusing to write under plugins/ (read-only): {p}"
    )


# ---------------------------------------------------------------- static scan


# open(<...>plugins/...<...>, "w"|"a"|"x"...)
_OPEN_W_RE = re.compile(
    r"""open\s*\(\s*['\"][^'\"]*\bplugins/[^'\"]*['\"]\s*,\s*['\"][wax]""",
    re.VERBOSE,
)
# Path("...plugins/...").write_text / .write_bytes
_PATH_WRITE_RE = re.compile(
    r"""Path\s*\(\s*['\"][^'\"]*\bplugins/[^'\"]*['\"]\s*\)\s*\.\s*write_(?:text|bytes)""",
    re.VERBOSE,
)
# shutil.copy / move / copyfile / copy2 → plugins/
_SHUTIL_RE = re.compile(
    r"""shutil\.(?:copy|copy2|copyfile|move)\s*\([^)]*['\"][^'\"]*\bplugins/[^'\"]*['\"]""",
    re.VERBOSE,
)

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("open_w", _OPEN_W_RE),
    ("path_write", _PATH_WRITE_RE),
    ("shutil_copy", _SHUTIL_RE),
)


def _iter_python_files(target: Path) -> Iterable[Path]:
    if target.is_file():
        if target.suffix == ".py":
            yield target
        return
    for p in target.rglob("*.py"):
        # Skip caches & vendored deps.
        parts = p.parts
        if "__pycache__" in parts or ".venv" in parts or "site-packages" in parts:
            continue
        yield p


def scan_target(target: Path) -> dict[str, Any]:
    scanned = 0
    hits: list[dict[str, Any]] = []
    for py in _iter_python_files(target):
        scanned += 1
        try:
            text = py.read_text(encoding="utf-8")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = _strip_inline_comment(line)
            for kind, regex in _PATTERNS:
                if regex.search(stripped):
                    hits.append(
                        {
                            "file": str(py),
                            "line": i,
                            "kind": kind,
                            "snippet": line.strip()[:200],
                        }
                    )
                    break
    return {"scanned_files": scanned, "writes_to_plugins": hits}


def _strip_inline_comment(line: str) -> str:
    """Crude Python-comment stripper used by the scanner.

    Walks the line, tracks whether we are inside a single- or
    double-quoted string (no triple-quote handling — line-local), and
    cuts everything from the first ``#`` outside a string. Good enough
    for the scanner's purpose: avoid matching example snippets that
    only appear inside Python comments.
    """
    in_s = in_d = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            i += 2
            continue
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            return line[:i]
        i += 1
    return line


def cli_main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="plugin_readonly.py",
        description="Static checker: forbid writes under plugins/.",
    )
    ap.add_argument(
        "--target",
        default=".",
        help="File or directory to scan (default: cwd).",
    )
    ap.add_argument("--json", action="store_true", help="Emit JSON envelope.")
    args = ap.parse_args(argv)

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"target not found: {target}", file=sys.stderr)
        return 2

    result = scan_target(target)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for h in result["writes_to_plugins"]:
            print(f"{h['file']}:{h['line']}: {h['kind']}: {h['snippet']}")
        print(
            f"scanned {result['scanned_files']} file(s), "
            f"{len(result['writes_to_plugins'])} violation(s)",
            file=sys.stderr,
        )

    return 0 if not result["writes_to_plugins"] else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main(sys.argv[1:]))
