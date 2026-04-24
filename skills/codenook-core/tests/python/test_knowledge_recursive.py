"""Tests for v0.21.0 recursive knowledge discovery + INDEX overrides
+ ``codenook knowledge reindex/list/search`` CLI.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

import knowledge_index as ki
import full_index as fi


# ---------------------------------------------------------------- helpers
def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")


def _make_plugin(root: Path, plugin: str) -> Path:
    pdir = root / "plugins" / plugin
    (pdir / "knowledge").mkdir(parents=True)
    return pdir


# ---------------------------------------------------------------- 1. recursion
def test_recursive_scan_finds_nested_files(tmp_path: Path):
    """Canonical descriptors only: root-level flat short form +
    nested ``<slug>/index.md``. Sibling ``case.md`` / ``entry.md``
    files are intentionally ignored (T-006 §2.4)."""
    pdir = _make_plugin(tmp_path, "p1")
    _write(pdir / "knowledge" / "top.md", "# Top\n\nbody.\n")
    _write(pdir / "knowledge" / "baselines" / "APHA" / "index.md",
           "# APHA Startup\n\nReference cold-start sequence.\n")
    _write(pdir / "knowledge" / "cases" / "issue-01" / "index.md",
           "# Case 1\n\nA case.\n")
    # A legacy sibling that MUST be ignored — proves the duplicate-hit
    # bug fix-pass 1 closed (reviewer MF-1 / MF-2).
    _write(pdir / "knowledge" / "cases" / "issue-01" / "case.md",
           "# Stale sibling\n\nshould not appear\n")
    recs = ki.discover_knowledge(pdir)
    paths = [Path(r["path"]).relative_to(pdir / "knowledge").as_posix()
             for r in recs]
    assert "top.md" in paths
    assert "baselines/APHA/index.md" in paths
    assert "cases/issue-01/index.md" in paths
    assert "cases/issue-01/case.md" not in paths
    assert len(recs) == 3


# ---------------------------------------------------------------- 2. tags from path
def test_implicit_tags_from_directory_path(tmp_path: Path):
    pdir = _make_plugin(tmp_path, "p1")
    _write(pdir / "knowledge" / "baselines" / "APHA" / "index.md",
           "# APHA Startup\n\nbody.\n")
    recs = ki.discover_knowledge(pdir)
    assert len(recs) == 1
    assert recs[0]["tags"] == ["baselines", "APHA"]


# ---------------------------------------------------------------- 3. body summary
def test_summary_extraction_from_h1_and_paragraph(tmp_path: Path):
    pdir = _make_plugin(tmp_path, "p1")
    _write(pdir / "knowledge" / "h1.md",
           "# The Heading Wins\n\nlater paragraph.\n")
    _write(pdir / "knowledge" / "para.md",
           "Just an opening paragraph with [a link](http://x) here.\n\nmore.\n")
    by_name = {Path(r["path"]).name: r for r in ki.discover_knowledge(pdir)}
    assert by_name["h1.md"]["summary"] == "The Heading Wins"
    # Markdown link syntax should be stripped, leaving the visible label.
    assert "a link" in by_name["para.md"]["summary"]
    assert "http://x" not in by_name["para.md"]["summary"]


# ---------------------------------------------------------------- 4. INDEX.yaml
def test_index_yaml_overrides_implicit(tmp_path: Path):
    pdir = _make_plugin(tmp_path, "p1")
    _write(pdir / "knowledge" / "baselines" / "APHA" / "index.md",
           "# Generic body heading\n\nbody.\n")
    _write(pdir / "knowledge" / "INDEX.yaml", """\
        entries:
          - path: baselines/APHA/index.md
            title: APHA Startup Baseline
            summary: Reference cold-start sequence for APHA board family.
            tags: [baselines, APHA, startup]
        """)
    recs = ki.discover_knowledge(pdir)
    rec = next(r for r in recs if r["path"].endswith("index.md"))
    assert rec["title"] == "APHA Startup Baseline"
    assert "cold-start" in rec["summary"]
    assert rec["tags"] == ["baselines", "APHA", "startup"]


def test_index_yaml_directory_path_picks_primary_md(tmp_path: Path):
    pdir = _make_plugin(tmp_path, "p1")
    _write(pdir / "knowledge" / "cases" / "issue-01" / "index.md",
           "# raw\nbody\n")
    _write(pdir / "knowledge" / "INDEX.yaml", """\
        entries:
          - path: cases/issue-01/
            title: Issue 1 Title
            summary: Index summary.
            tags: [case, foo]
        """)
    recs = ki.discover_knowledge(pdir)
    rec = next(r for r in recs if r["path"].endswith("index.md"))
    assert rec["title"] == "Issue 1 Title"
    assert rec["tags"] == ["case", "foo"]


# ---------------------------------------------------------------- 5. INDEX.md
def test_index_md_overrides_implicit(tmp_path: Path):
    pdir = _make_plugin(tmp_path, "p1")
    _write(pdir / "knowledge" / "guide.md", "Implicit body line.\n")
    _write(pdir / "knowledge" / "INDEX.md",
           "# Catalog\n\n- [Friendly Title](guide.md) — friendly summary text\n")
    recs = ki.discover_knowledge(pdir)
    rec = next(r for r in recs if r["path"].endswith("guide.md"))
    assert rec["title"] == "Friendly Title"
    assert "friendly summary" in rec["summary"]


# ---------------------------------------------------------------- 6. fm wins
def test_frontmatter_beats_index_files(tmp_path: Path):
    pdir = _make_plugin(tmp_path, "p1")
    _write(pdir / "knowledge" / "thing.md", """\
        ---
        title: Frontmatter Title
        summary: fm-summary
        tags: [from-fm]
        ---
        body.
        """)
    _write(pdir / "knowledge" / "INDEX.yaml", """\
        entries:
          - path: thing.md
            title: INDEX Title
            summary: index summary
            tags: [from-index]
        """)
    _write(pdir / "knowledge" / "INDEX.md",
           "- [MD Title](thing.md) — md summary\n")
    recs = ki.discover_knowledge(pdir)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["title"] == "Frontmatter Title"
    assert rec["summary"] == "fm-summary"
    assert rec["tags"] == ["from-fm"]


# ---------------------------------------------------------------- 7. skip noise
def test_skip_dot_dirs_and_pycache(tmp_path: Path):
    pdir = _make_plugin(tmp_path, "p1")
    _write(pdir / "knowledge" / "good.md", "# good\n\nbody\n")
    _write(pdir / "knowledge" / ".hidden" / "secret.md", "# nope\n")
    _write(pdir / "knowledge" / "__pycache__" / "junk.md", "# nope\n")
    _write(pdir / "knowledge" / "node_modules" / "pkg" / "x.md", "# nope\n")
    _write(pdir / "knowledge" / ".git" / "x.md", "# nope\n")
    recs = ki.discover_knowledge(pdir)
    names = [Path(r["path"]).name for r in recs]
    assert names == ["good.md"]


# ---------------------------------------------------------------- 8. reindex against repo prnook
@pytest.fixture()
def real_workspace_with_prnook() -> Path | None:
    """Locate the dev workspace at ``…/Documents/workspace`` and only
    yield it when prnook is installed there. Otherwise skip."""
    candidate = Path(
        r"C:\N-5CG1411304-Data\mingdw\Documents\workspace"
    )
    if not (candidate / ".codenook" / "plugins" / "prnook" / "knowledge").is_dir():
        pytest.skip("prnook not installed in the dev workspace")
    return candidate


def test_full_index_picks_up_prnook_knowledge(real_workspace_with_prnook: Path):
    payload = fi.build_full_index(real_workspace_with_prnook)
    prnook_entries = [
        e for e in payload["knowledge"] if e.get("plugin") == "prnook"
    ]
    # Pre-v0.21.0 only the 5 top-level files showed up; recursive scan
    # must surface significantly more (baselines / cases / etc.).
    assert len(prnook_entries) >= 10, (
        f"expected ≥10 prnook knowledge entries after recursive scan, "
        f"got {len(prnook_entries)}"
    )
    # Spot-check: at least one nested baseline / case file is present.
    nested = [
        e for e in prnook_entries
        if "/baselines/" in e["path"].replace(os.sep, "/")
        or "/cases/" in e["path"].replace(os.sep, "/")
    ]
    assert nested, "expected nested baseline/case files in the index"


def test_reindex_is_idempotent(tmp_path: Path):
    """Running build_full_index twice yields identical payloads modulo
    ``generated_at``."""
    (tmp_path / ".codenook" / "plugins" / "p1" / "knowledge").mkdir(parents=True)
    _write(
        tmp_path / ".codenook" / "plugins" / "p1" / "knowledge" / "a.md",
        "# A\nbody\n",
    )
    a = fi.build_full_index(tmp_path)
    b = fi.build_full_index(tmp_path)
    a.pop("generated_at")
    b.pop("generated_at")
    assert a == b


# ---------------------------------------------------------------- 9. CLI search
def test_cli_knowledge_search_against_prnook(real_workspace_with_prnook: Path):
    cli = real_workspace_with_prnook / ".codenook" / "bin"
    cli = cli / ("codenook.cmd" if sys.platform == "win32" else "codenook")
    if not cli.is_file():
        pytest.skip("codenook bin shim not installed in the dev workspace")
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    # Skip if the installed CLI predates v0.21.0 (no `knowledge` subcommand).
    probe = subprocess.run(
        [str(cli), "knowledge", "--help"],
        capture_output=True, env=env,
    )
    if probe.returncode != 0:
        pytest.skip("installed CLI predates v0.21.0 knowledge subcommand")
    cp = subprocess.run(
        [str(cli), "knowledge", "search", "APHA"],
        capture_output=True, env=env,
    )
    assert cp.returncode == 0, cp.stderr.decode("utf-8", errors="replace")
    out = cp.stdout.decode("utf-8", errors="replace")
    assert "prnook" in out or "no hits" in out
