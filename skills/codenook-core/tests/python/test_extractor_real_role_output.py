"""E2E-P-003 belt-and-suspenders — extractor consumes a *real* role
output that lacks the optional ``extract:`` block and still produces
≥1 candidate via the fall-back synthesis path.
"""
from __future__ import annotations

from pathlib import Path

import extract


REAL_ROLE_OUTPUT = """\
---
verdict: ok
summary: Use iterative fib(n) for n<1000 to avoid Python's stack limits.
iteration: 1
---

# Phase-1 clarifier — fib helper

The user wants `fib(n)` in `src/fib.py`. Constraints:
* Pure-python, no third-party deps.
* O(n) time, O(1) space.
* pytest coverage at 100%.
"""


def test_real_role_output_yields_fallback_candidate(workspace: Path):
    tid = "T-real-1"
    out_dir = workspace / ".codenook" / "tasks" / tid / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phase-1-clarifier.md").write_text(REAL_ROLE_OUTPUT)
    cands = extract._candidates_from_role_outputs(workspace, tid)
    assert isinstance(cands, list) and len(cands) >= 1
    c = cands[0]
    assert "Use iterative fib" in c["title"]
    assert "summary" in c and c["summary"]
    assert isinstance(c.get("tags"), list) and c["tags"]


def test_real_role_output_main_creates_knowledge_file(workspace: Path, monkeypatch):
    tid = "T-real-2"
    out_dir = workspace / ".codenook" / "tasks" / tid / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phase-1-clarifier.md").write_text(REAL_ROLE_OUTPUT)
    monkeypatch.setenv("CN_LLM_MODE", "mock")
    rc = extract.main([
        "--task-id", tid,
        "--workspace", str(workspace),
        "--phase", "clarify",
        "--reason", "after_phase",
    ])
    assert rc == 0
    files = list((workspace / ".codenook" / "memory" / "knowledge").glob("*.md"))
    assert files, "expected at least one knowledge entry written"


def test_role_output_with_needs_revision_does_not_emit(workspace: Path):
    tid = "T-real-3"
    out_dir = workspace / ".codenook" / "tasks" / tid / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "phase-1.md").write_text(
        "---\nverdict: needs_revision\nsummary: x\n---\nbody\n"
    )
    cands = extract._candidates_from_role_outputs(workspace, tid)
    # needs_revision must not seed memory.
    assert cands == []
