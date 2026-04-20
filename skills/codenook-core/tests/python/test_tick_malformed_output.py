"""E2E-005 — read_verdict_detailed distinguishes missing vs malformed."""
from __future__ import annotations

from pathlib import Path

import _tick


def _seed_task(workspace: Path, contents: str | None) -> str:
    tid = "T-100"
    out = workspace / ".codenook" / "tasks" / tid / "outputs"
    out.mkdir(parents=True)
    if contents is not None:
        (out / "phase-1.md").write_text(contents)
    return tid


def test_missing_output(workspace: Path):
    tid = _seed_task(workspace, None)
    v, status, _ = _tick.read_verdict_detailed(workspace, tid, "outputs/phase-1.md")
    assert v is None and status == _tick._OutputState.MISSING


def test_no_frontmatter(workspace: Path):
    tid = _seed_task(workspace, "Just a body, no frontmatter\n")
    v, status, _ = _tick.read_verdict_detailed(workspace, tid, "outputs/phase-1.md")
    assert v is None and status == _tick._OutputState.NO_FRONTMATTER


def test_yaml_parse_error(workspace: Path):
    tid = _seed_task(workspace, "---\nverdict: ok\n  bad: : indent\n---\nbody\n")
    v, status, detail = _tick.read_verdict_detailed(workspace, tid, "outputs/phase-1.md")
    assert v is None
    assert status == _tick._OutputState.YAML_PARSE_ERROR
    assert "phase-1.md" in detail


def test_bad_verdict(workspace: Path):
    tid = _seed_task(workspace, "---\nverdict: nope\n---\n")
    v, status, _ = _tick.read_verdict_detailed(workspace, tid, "outputs/phase-1.md")
    assert v is None and status == _tick._OutputState.BAD_VERDICT


def test_ok_path(workspace: Path):
    tid = _seed_task(workspace, "---\nverdict: ok\n---\nbody\n")
    v, status, _ = _tick.read_verdict_detailed(workspace, tid, "outputs/phase-1.md")
    assert v == "ok" and status == "ok"
