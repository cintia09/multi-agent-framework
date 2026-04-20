#!/usr/bin/env python3
"""CLAUDE.md domain-agnostic linter (M8.6 + M9.7 memory-protocol rules).

Scans the root ``CLAUDE.md`` (or any "main session protocol" doc) for
domain-aware tokens that would violate the v6 layering principle
(see ``docs/router-agent.md`` §2). The main session is the
**Conductor** — pure protocol + UX, with zero domain awareness.

M9.7 extension (`docs/memory-and-extraction.md` §2.1, §5.4):

* **Forbidden write-to-plugins prose** — narrative such as
  ``let me write plugins/foo.yaml`` or ``main session may modify
  plugins/bar`` is rejected (FR-RO-3 / AC-RO-3).
* **Forbidden memory-scan prose** — shell-style mentions of the main
  session reading ``.codenook/memory/`` directly (e.g.
  ``grep -r .codenook/memory``, ``cat .codenook/memory/...``) are
  rejected (NFR-LAYER / TC-M9.7-06).
* **Required memory-protocol section** — when the linted file is named
  ``CLAUDE.md`` it must contain the ``## 上下文水位监控`` heading (the
  M9.2 contract; AC-DOC-3 / TC-M9.7-05).

Allowed-context exceptions:

* Fenced code blocks opened with ``forbidden`` or ``forbidden-example``
  as the info-string (e.g. ``\\`\\`\\`forbidden``).
* The single line immediately following an HTML comment of the exact
  form ``<!-- linter:allow -->``.
* Anywhere inside the section whose heading text contains
  ``Hard rules (forbidden)`` — the section ends at the next ``## ``
  level-2 heading.

Tokens found inside an allowed context are still surfaced as
``warning`` findings so you can audit them; tokens elsewhere are
``error`` findings and cause non-zero CLI exit.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

# Pure substring tokens (path-style identifiers; case-sensitive).
_LITERAL_TOKENS: tuple[str, ...] = (
    "plugins/development",
    "plugins/writing",
    "plugins/generic",
    "applies_to",
    "domain_description",
)

# Word-boundary tokens: role names + plugin ids that are also common English
# words. Case-sensitive; matched only as standalone words.
_WORD_TOKENS: tuple[str, ...] = (
    "clarifier",
    "designer",
    "implementer",
    "tester",
    "validator",
    "acceptor",
    "reviewer",
    "development",
    "writing",
    "generic",
)

# Public surface mirrors the spec.
FORBIDDEN_TOKENS: list[str] = [
    *_LITERAL_TOKENS,
    *_WORD_TOKENS[:7],  # roles
    r"\bdevelopment\b",
    r"\bwriting\b",
    r"\bgeneric\b",
]

ALLOWED_CONTEXT_PATTERNS: list[str] = [
    "```forbidden / ```forbidden-example fenced block",
    "<!-- linter:allow --> on the immediately preceding line",
    "section whose ## heading contains 'Hard rules (forbidden)'",
]

_FENCE_RE = re.compile(r"^\s*```([A-Za-z0-9_-]*)\s*$")
_HEADING2_RE = re.compile(r"^##\s+(.*?)\s*$")
_ALLOW_COMMENT_RE = re.compile(r"^\s*<!--\s*linter:allow\s*-->\s*$")
_HARD_RULES_RE = re.compile(r"hard\s+rules\s*\(\s*forbidden\s*\)", re.IGNORECASE)

# ---------------------------------------------------------------- M9.7 rules
#
# Each rule = (rule_id, label, compiled regex). Rules fire in normal
# (i.e. non-forbidden-fence, non-hard-rules, non-allow-comment) context
# and surface as ``severity=error``.

_M97_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "write-to-plugins",
        "narrative writing to plugins/",
        re.compile(
            r"\b(?:let\s+me|I\s+(?:will|can|should|may)|main\s+session\s+(?:can|may|will|should))"
            r"\s+(?:write|edit|modify|update|create|change|patch|append)\s+[^.\n]*\bplugins/",
            re.IGNORECASE,
        ),
    ),
    (
        "scan-memory",
        "main session scanning .codenook/memory/",
        re.compile(
            r"\b(?:grep|cat|ls|find|rg|head|tail|awk|sed)\b[^|\n]*\.codenook/memory\b",
        ),
    ),
)

# Required heading (substring match on level-2 headings) when the file
# basename is CLAUDE.md (TC-M9.7-05).
_REQUIRED_HEADINGS_FOR_CLAUDE_MD: tuple[str, ...] = ("上下文水位监控",)


def _word_iter(line: str, token: str):
    pattern = r"\b" + re.escape(token) + r"\b"
    for m in re.finditer(pattern, line):
        yield m.start(), m.group(0)


def _literal_iter(line: str, token: str):
    start = 0
    while True:
        idx = line.find(token, start)
        if idx < 0:
            return
        yield idx, token
        start = idx + len(token)


def scan_file(path: Path, *, check_required_sections: bool = False) -> list[dict[str, Any]]:
    """Scan one file. Returns a list of finding dicts.

    Each finding has keys: ``file``, ``line``, ``column``, ``token``,
    ``snippet``, ``severity`` (``error`` or ``warning``).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [
            {
                "file": str(path),
                "line": 0,
                "column": 0,
                "token": "",
                "snippet": f"<read error: {exc}>",
                "severity": "error",
            }
        ]

    findings: list[dict[str, Any]] = []
    in_forbidden_fence = False
    in_any_fence = False
    in_hard_rules = False
    prev_was_allow = False

    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.rstrip("\n")
        fence_match = _FENCE_RE.match(line)
        if fence_match:
            tag = fence_match.group(1).lower()
            if in_any_fence:
                # closing fence
                in_any_fence = False
                in_forbidden_fence = False
            else:
                in_any_fence = True
                in_forbidden_fence = tag in ("forbidden", "forbidden-example")
            prev_was_allow = False
            continue

        # Heading tracking happens only outside fences.
        if not in_any_fence:
            heading = _HEADING2_RE.match(line)
            if heading:
                in_hard_rules = bool(_HARD_RULES_RE.search(heading.group(1)))

        if _ALLOW_COMMENT_RE.match(line):
            prev_was_allow = True
            continue

        allowed = in_forbidden_fence or in_hard_rules or prev_was_allow
        severity = "warning" if allowed else "error"

        line_findings: list[tuple[int, str]] = []
        for tok in _LITERAL_TOKENS:
            line_findings.extend(_literal_iter(line, tok))
        for tok in _WORD_TOKENS:
            line_findings.extend(_word_iter(line, tok))

        # De-dup overlapping word/literal hits at the same column+token.
        seen: set[tuple[int, str]] = set()
        for col, tok in sorted(line_findings):
            key = (col, tok)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                {
                    "file": str(path),
                    "line": i,
                    "column": col + 1,
                    "token": tok,
                    "snippet": line.strip()[:200],
                    "severity": severity,
                }
            )

        # M9.7 rule patterns (also subject to the same allowed-context).
        for rule_id, _label, regex in _M97_RULES:
            for m in regex.finditer(line):
                findings.append(
                    {
                        "file": str(path),
                        "line": i,
                        "column": m.start() + 1,
                        "token": rule_id,
                        "snippet": line.strip()[:200],
                        "severity": severity,
                    }
                )

        prev_was_allow = False

    # Required-heading check (TC-M9.7-05): CLAUDE.md must contain the
    # M9.2 watermark protocol section. Gated by ``check_required_sections``
    # so M8.6 unit-test fixtures that build throwaway CLAUDE.md files
    # don't trip the rule. The CLI auto-enables the check when the file
    # path resolves to the repo-root CLAUDE.md (see :func:`cli_main`).
    if check_required_sections and path.name == "CLAUDE.md":
        headings = [
            m.group(1)
            for m in (_HEADING2_RE.match(l) for l in text.splitlines())
            if m is not None
        ]
        joined = "\n".join(headings)
        for required in _REQUIRED_HEADINGS_FOR_CLAUDE_MD:
            if required not in joined:
                findings.append(
                    {
                        "file": str(path),
                        "line": 0,
                        "column": 0,
                        "token": f"missing-heading:{required}",
                        "snippet": (
                            f"CLAUDE.md is missing required section "
                            f"'## {required}' (M9.7 / AC-DOC-3)"
                        ),
                        "severity": "error",
                    }
                )

    return findings


def scan_files(paths: list[Path], *, check_required_sections: bool = False) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    n = 0
    for p in paths:
        n += 1
        for f in scan_file(p, check_required_sections=check_required_sections):
            (errors if f["severity"] == "error" else warnings).append(f)
    return {"errors": errors, "warnings": warnings, "files_scanned": n}


def _format_finding(f: dict[str, Any]) -> str:
    tok = f["token"]
    if tok.startswith("missing-heading:"):
        return (
            f"{f['file']}:{f['line']}:{f['column']}: {f['severity'].upper()}: "
            f"{f['snippet']}"
        )
    if tok in {"write-to-plugins", "scan-memory"}:
        return (
            f"{f['file']}:{f['line']}:{f['column']}: {f['severity'].upper()}: "
            f"forbidden M9.7 pattern '{tok}' -> {f['snippet']}"
        )
    return (
        f"{f['file']}:{f['line']}:{f['column']}: {f['severity'].upper()}: "
        f"forbidden domain token '{tok}' -> {f['snippet']}"
    )


def _looks_like_repo_claude_md(path: Path) -> bool:
    """Heuristic: the file resolves to ``CLAUDE.md`` directly inside a
    repository root (sibling to a ``.git`` dir or to the standard
    ``skills/codenook-core`` tree). Used by the CLI to auto-enable the
    M9.7 required-section check while leaving M8.6 unit fixtures
    (built in throwaway tmpdirs) alone.
    """
    if path.name != "CLAUDE.md":
        return False
    parent = path.resolve().parent
    if (parent / ".git").exists():
        return True
    if (parent / "skills" / "codenook-core").exists():
        return True
    return False


_BEGIN_MARKER = "<!-- codenook:begin -->"
_END_MARKER = "<!-- codenook:end -->"


def _marker_lineranges(text: str) -> tuple[tuple[int, int] | None, list[tuple[int, int]]]:
    """Return (inside_range, outside_ranges).

    Lines are 1-indexed inclusive. ``inside_range`` covers
    BEGIN..END markers (inclusive). ``outside_ranges`` covers everything else.
    If markers are absent, inside_range is None and outside_ranges spans the
    whole file.
    """
    lines = text.splitlines()
    n = len(lines)
    bi = ei = -1
    for i, ln in enumerate(lines, start=1):
        if _BEGIN_MARKER in ln and bi == -1:
            bi = i
        elif _END_MARKER in ln and bi != -1 and ei == -1:
            ei = i
            break
    if bi == -1 or ei == -1 or ei <= bi:
        return None, [(1, n)] if n else []
    inside = (bi, ei)
    outside = []
    if bi > 1:
        outside.append((1, bi - 1))
    if ei < n:
        outside.append((ei + 1, n))
    return inside, outside


def _filter_findings(findings: list[dict], ranges: list[tuple[int, int]]) -> list[dict]:
    if not ranges:
        return []
    out = []
    for f in findings:
        ln = f.get("line", 0) or 0
        if ln <= 0:
            # Required-section findings are file-level — keep them.
            out.append(f)
            continue
        for a, b in ranges:
            if a <= ln <= b:
                out.append(f); break
    return out


def cli_main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(
            "usage: claude_md_linter.py [--marker-only|--strict|--outside-marker-only]\n"
            "                            [--check-claude-md] [--json] <FILE> [<FILE> ...]\n"
            "\n"
            "Modes (default: --marker-only):\n"
            "  --marker-only         scan only INSIDE the codenook:begin..end block\n"
            "  --strict              scan the entire file (legacy v0.11.2 behavior)\n"
            "  --outside-marker-only scan only OUTSIDE the codenook block (installer warning)\n"
            "\n"
            "Other flags:\n"
            "  --check-claude-md     additionally require the M9.2 watermark heading\n"
            "  --json                emit machine-readable {errors,warnings,...} on stdout\n"
            "\n"
            "Exit 0 if no errors, 1 otherwise. Findings printed to stderr unless --json.",
            file=sys.stderr,
        )
        return 0
    if not argv:
        print(
            "usage: claude_md_linter.py [--marker-only|--strict|--outside-marker-only] "
            "[--check-claude-md] [--json] <FILE> [<FILE> ...]",
            file=sys.stderr,
        )
        return 2

    args = list(argv)
    explicit_check = "--check-claude-md" in args
    json_out = "--json" in args
    strict = "--strict" in args
    outside_only = "--outside-marker-only" in args
    marker_only = "--marker-only" in args
    if not (strict or outside_only or marker_only):
        marker_only = True  # E2E-017 default
    args = [a for a in args if a not in (
        "--check-claude-md", "--json", "--strict",
        "--marker-only", "--outside-marker-only")]

    paths = [Path(a) for a in args]
    missing = [p for p in paths if not p.exists()]
    if missing:
        for p in missing:
            print(f"ERROR: file not found: {p}", file=sys.stderr)
        return 2

    auto_check = any(_looks_like_repo_claude_md(p) for p in paths)
    check_required = explicit_check or auto_check

    aggregated: list[dict] = []
    files_scanned = 0
    for p in paths:
        files_scanned += 1
        text = p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""
        raw = scan_file(p, check_required_sections=check_required)
        if strict:
            kept = raw
        else:
            inside, outside = _marker_lineranges(text)
            ranges = [inside] if (marker_only and inside is not None) else (
                outside if outside_only else (
                    [inside] if inside is not None else []
                )
            )
            # When marker-only and there are no markers, scan everything to
            # avoid silently skipping un-augmented files.
            if marker_only and inside is None:
                ranges = [(1, len(text.splitlines()))] if text else []
            kept = _filter_findings(raw, ranges)
        aggregated.extend(kept)

    errors = [f for f in aggregated if f["severity"] == "error"]
    warnings = [f for f in aggregated if f["severity"] == "warning"]

    if json_out:
        import json as _json
        print(_json.dumps({
            "errors": errors,
            "warnings": warnings,
            "files_scanned": files_scanned,
        }))
    else:
        for f in errors:
            print(_format_finding(f), file=sys.stderr)
        for f in warnings:
            print(_format_finding(f), file=sys.stderr)
        print(
            f"scanned {files_scanned} file(s): "
            f"{len(errors)} error(s), {len(warnings)} warning(s)",
            file=sys.stderr,
        )
    return 0 if not errors else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(cli_main(sys.argv[1:]))
