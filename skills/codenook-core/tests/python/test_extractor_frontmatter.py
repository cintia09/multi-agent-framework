"""E2E-009 — knowledge-extractor consumes YAML frontmatter from role outputs."""
from __future__ import annotations

from pathlib import Path

import extract


def _seed(workspace: Path, tid: str, name: str, body: str) -> None:
    out = workspace / ".codenook" / "tasks" / tid / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(body)


def test_frontmatter_extract_block_yields_candidates(workspace: Path):
    tid = "T-100"
    _seed(workspace, tid, "phase-1.md",
          "---\n"
          "verdict: ok\n"
          "extract:\n"
          "  - title: Use iterative fib\n"
          "    summary: Linear-time path avoids stack blowup.\n"
          "    tags: [algorithm, fibonacci]\n"
          "    body: Iterative is O(n) and stack-safe.\n"
          "---\nBody.\n")
    cands = extract._candidates_from_role_outputs(workspace, tid)
    assert isinstance(cands, list) and len(cands) == 1
    assert cands[0]["title"] == "Use iterative fib"
    assert "algorithm" in cands[0]["tags"]


def test_no_extract_block_returns_empty(workspace: Path):
    tid = "T-101"
    _seed(workspace, tid, "phase-1.md", "---\nverdict: ok\n---\nbody\n")
    assert extract._candidates_from_role_outputs(workspace, tid) == []


def test_no_outputs_returns_none(workspace: Path):
    tid = "T-102"
    (workspace / ".codenook" / "tasks" / tid).mkdir(parents=True)
    assert extract._candidates_from_role_outputs(workspace, tid) is None


def test_smoke_creates_knowledge_entry(workspace: Path, monkeypatch):
    tid = "T-200"
    _seed(workspace, tid, "phase-1.md",
          "---\n"
          "verdict: ok\n"
          "extract:\n"
          "  - title: Cache HTTP idempotent GETs\n"
          "    summary: 304 saves bandwidth and CPU.\n"
          "    tags: [http, cache, performance]\n"
          "    body: Use ETag/If-None-Match headers; honor max-age.\n"
          "---\nbody\n")
    monkeypatch.setenv("CN_LLM_MODE", "mock")
    rc = extract.main([
        "--task-id", tid,
        "--workspace", str(workspace),
        "--phase", "clarify",
        "--reason", "after_phase",
    ])
    assert rc == 0
    files = list((workspace / ".codenook" / "memory" / "knowledge").glob("*.md"))
    assert files, "expected ≥1 knowledge entry written"
    body = files[0].read_text()
    assert any(t in body for t in ("Cache", "cache", "ETag"))
