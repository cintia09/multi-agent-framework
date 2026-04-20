"""E2E-017 — claude_md_linter marker-only mode skips user content outside markers."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

LINTER = (
    Path(__file__).resolve().parents[4]
    / "skills" / "codenook-core" / "skills" / "builtin" / "_lib" / "claude_md_linter.py"
)


def _run(*args, file: Path) -> dict:
    res = subprocess.run(
        ["python3", str(LINTER), *args, "--json", str(file)],
        capture_output=True, text=True, check=False,
    )
    return json.loads(res.stdout)


OUTSIDE = "User-written prose mentioning the writing plugin's clarifier role.\n"
INSIDE = (
    "<!-- codenook:begin -->\n"
    "Pure CodeNook block; no domain tokens.\n"
    "<!-- codenook:end -->\n"
)


def test_marker_only_default_skips_outside(tmp_path: Path):
    f = tmp_path / "CLAUDE.md"
    f.write_text(OUTSIDE + INSIDE)
    out = _run(file=f)
    assert out["errors"] == [] and out["warnings"] == []


def test_strict_flags_outside(tmp_path: Path):
    f = tmp_path / "CLAUDE.md"
    f.write_text(OUTSIDE + INSIDE)
    out = _run("--strict", file=f)
    findings = out["errors"] + out["warnings"]
    assert any("clarifier" == fnd.get("token") for fnd in findings), findings


def test_outside_marker_only_isolates(tmp_path: Path):
    f = tmp_path / "CLAUDE.md"
    f.write_text(OUTSIDE + INSIDE)
    out = _run("--outside-marker-only", file=f)
    findings = out["errors"] + out["warnings"]
    assert findings
    assert all(fnd.get("line", 1) <= len(OUTSIDE.splitlines()) for fnd in findings)


def test_marker_only_falls_back_when_no_markers(tmp_path: Path):
    f = tmp_path / "CLAUDE.md"
    f.write_text(OUTSIDE)
    out = _run(file=f)
    findings = out["errors"] + out["warnings"]
    assert findings, "fallback whole-file scan expected when markers missing"
