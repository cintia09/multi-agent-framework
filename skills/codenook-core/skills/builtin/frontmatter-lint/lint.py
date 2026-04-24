#!/usr/bin/env python3
"""frontmatter-lint — validate memory + plugin frontmatter contracts.

See SKILL.md for the contract.  Implements T-006 design §2.4.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

KNOWLEDGE_TYPES = {"case", "playbook", "error", "knowledge"}
KNOWLEDGE_REQUIRED = ("id", "title", "type", "tags", "summary")
SKILL_REQUIRED = ("id", "title", "tags", "summary")
FORBIDDEN_FIELD = "keywords"
MAX_SUMMARY_CHARS = 400


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    if not text.startswith("---"):
        return None
    lines = text.split("\n")
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None
    try:
        fm = yaml.safe_load("\n".join(lines[1:end]))
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def _scan_dir(root: Path, glob: str, kind: str) -> list[tuple[Path, dict[str, Any] | None]]:
    out: list[tuple[Path, dict[str, Any] | None]] = []
    if not root.is_dir():
        return out
    for p in sorted(root.glob(glob)):
        try:
            fm = _parse_frontmatter(p.read_text(encoding="utf-8"))
        except OSError:
            fm = None
        out.append((p, fm))
    return out


def lint(workspace: Path) -> tuple[list[dict[str, Any]], int]:
    """Return (findings, scanned_count)."""
    findings: list[dict[str, Any]] = []
    scanned = 0
    ids_seen: dict[str, list[str]] = defaultdict(list)

    targets: list[tuple[Path, str, str]] = []  # (root, glob, kind)
    mem = workspace / ".codenook" / "memory"
    targets.append((mem / "knowledge", "*/index.md", "knowledge"))
    targets.append((mem / "skills", "*/SKILL.md", "skill"))
    plugins_root = workspace / ".codenook" / "plugins"
    if plugins_root.is_dir():
        for pdir in sorted(plugins_root.iterdir()):
            if not pdir.is_dir() or pdir.name.startswith((".", "_")):
                continue
            targets.append((pdir / "knowledge", "*/index.md", "knowledge"))
            targets.append((pdir / "skills", "*/SKILL.md", "skill"))

    for root, glob, kind in targets:
        for path, fm in _scan_dir(root, glob, kind):
            scanned += 1
            rel = str(path.relative_to(workspace)) if workspace in path.parents else str(path)
            if fm is None:
                findings.append({
                    "path": rel, "level": "fail", "code": "no-frontmatter",
                    "message": "missing or unparseable YAML frontmatter",
                })
                continue
            required = KNOWLEDGE_REQUIRED if kind == "knowledge" else SKILL_REQUIRED
            for field in required:
                if field not in fm:
                    findings.append({
                        "path": rel, "level": "fail", "code": "missing-field",
                        "message": f"required field '{field}' missing",
                    })
            if FORBIDDEN_FIELD in fm:
                findings.append({
                    "path": rel, "level": "fail", "code": "forbidden-field",
                    "message": f"deprecated field '{FORBIDDEN_FIELD}' present "
                               f"(T-004/T-006 dropped it; use 'tags')",
                })
            if kind == "knowledge":
                t = fm.get("type")
                if t and t not in KNOWLEDGE_TYPES:
                    findings.append({
                        "path": rel, "level": "fail", "code": "bad-type",
                        "message": f"type {t!r} not in {sorted(KNOWLEDGE_TYPES)}",
                    })
            else:  # skill
                if "type" in fm:
                    findings.append({
                        "path": rel, "level": "warn", "code": "skill-has-type",
                        "message": "SKILL.md frontmatter should not carry "
                                   "'type:' (filename is the type)",
                    })
            summary = fm.get("summary") or ""
            if isinstance(summary, str) and len(summary) > MAX_SUMMARY_CHARS:
                findings.append({
                    "path": rel, "level": "warn", "code": "summary-too-long",
                    "message": f"summary {len(summary)} chars > {MAX_SUMMARY_CHARS}",
                })
            ent_id = fm.get("id")
            if isinstance(ent_id, str) and ent_id:
                ids_seen[ent_id].append(rel)

    for ent_id, locs in ids_seen.items():
        if len(locs) > 1:
            for loc in locs:
                findings.append({
                    "path": loc, "level": "fail", "code": "duplicate-id",
                    "message": f"id {ent_id!r} also used at: "
                               f"{', '.join(other for other in locs if other != loc)}",
                })

    return findings, scanned


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="frontmatter-lint")
    ap.add_argument("--workspace", required=True, type=Path)
    ap.add_argument("--json", action="store_true", dest="json_out")
    args = ap.parse_args(argv)
    if not args.workspace.is_dir():
        sys.stderr.write(f"frontmatter-lint: workspace not found: {args.workspace}\n")
        return 2

    findings, scanned = lint(args.workspace)
    fails = [f for f in findings if f["level"] == "fail"]
    warns = [f for f in findings if f["level"] == "warn"]
    rc = 1 if fails else 0

    if args.json_out:
        print(json.dumps(
            {"ok": rc == 0, "scanned": scanned, "findings": findings},
            ensure_ascii=False, indent=2,
        ))
    else:
        for f in findings:
            sys.stderr.write(
                f"[{f['level'].upper()}] {f['path']}: {f['code']}: {f['message']}\n"
            )
        sys.stderr.write(
            f"frontmatter-lint: scanned {scanned} files, "
            f"{len(fails)} fail, {len(warns)} warn\n"
        )
    return rc


if __name__ == "__main__":
    sys.exit(main())
