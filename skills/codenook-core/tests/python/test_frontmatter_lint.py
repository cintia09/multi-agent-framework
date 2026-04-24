"""frontmatter-lint sub-skill (T-006 §2.4)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

LINT_PY = (
    Path(__file__).resolve().parents[2]
    / "skills/builtin/frontmatter-lint/lint.py"
)
spec = importlib.util.spec_from_file_location("frontmatter_lint", LINT_PY)
assert spec and spec.loader
fl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fl)


def _mk_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    (ws / ".codenook" / "memory" / "knowledge").mkdir(parents=True)
    (ws / ".codenook" / "memory" / "skills").mkdir(parents=True)
    return ws


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def test_clean_workspace_passes(tmp_path: Path) -> None:
    ws = _mk_workspace(tmp_path)
    _write(
        ws / ".codenook/memory/knowledge/foo/index.md",
        "---\nid: foo\ntitle: Foo\ntype: knowledge\ntags: [a]\nsummary: ok\n---\nbody\n",
    )
    _write(
        ws / ".codenook/memory/skills/bar/SKILL.md",
        "---\nid: bar\ntitle: Bar\ntags: [a]\nsummary: ok\n---\nbody\n",
    )
    findings, scanned = fl.lint(ws)
    fails = [f for f in findings if f["level"] == "fail"]
    assert fails == [], findings
    assert scanned == 2


def test_missing_required_field_fails(tmp_path: Path) -> None:
    ws = _mk_workspace(tmp_path)
    _write(
        ws / ".codenook/memory/knowledge/foo/index.md",
        "---\nid: foo\ntitle: Foo\ntags: [a]\nsummary: ok\n---\n",  # no type
    )
    findings, _ = fl.lint(ws)
    fails = [f for f in findings if f["level"] == "fail"]
    assert any(f["code"] == "missing-field" and "type" in f["message"] for f in fails)


def test_forbidden_keywords_fails(tmp_path: Path) -> None:
    ws = _mk_workspace(tmp_path)
    _write(
        ws / ".codenook/memory/knowledge/foo/index.md",
        "---\nid: foo\ntitle: Foo\ntype: knowledge\ntags: [a]\nsummary: ok\nkeywords: [old]\n---\n",
    )
    findings, _ = fl.lint(ws)
    assert any(f["code"] == "forbidden-field" for f in findings)


def test_skill_with_type_warns(tmp_path: Path) -> None:
    ws = _mk_workspace(tmp_path)
    _write(
        ws / ".codenook/memory/skills/bar/SKILL.md",
        "---\nid: bar\ntitle: Bar\ntype: playbook\ntags: [a]\nsummary: ok\n---\n",
    )
    findings, _ = fl.lint(ws)
    assert any(f["level"] == "warn" and f["code"] == "skill-has-type" for f in findings)


def test_duplicate_id_fails(tmp_path: Path) -> None:
    ws = _mk_workspace(tmp_path)
    _write(
        ws / ".codenook/memory/knowledge/foo/index.md",
        "---\nid: same\ntitle: Foo\ntype: knowledge\ntags: [a]\nsummary: ok\n---\n",
    )
    _write(
        ws / ".codenook/memory/knowledge/foo2/index.md",
        "---\nid: same\ntitle: Foo2\ntype: knowledge\ntags: [a]\nsummary: ok\n---\n",
    )
    findings, _ = fl.lint(ws)
    dups = [f for f in findings if f["code"] == "duplicate-id"]
    assert len(dups) == 2


def test_long_summary_warns(tmp_path: Path) -> None:
    ws = _mk_workspace(tmp_path)
    _write(
        ws / ".codenook/memory/knowledge/foo/index.md",
        f"---\nid: foo\ntitle: Foo\ntype: knowledge\ntags: [a]\nsummary: {'x' * 500}\n---\n",
    )
    findings, _ = fl.lint(ws)
    assert any(f["code"] == "summary-too-long" for f in findings)


def test_bad_type_fails(tmp_path: Path) -> None:
    ws = _mk_workspace(tmp_path)
    _write(
        ws / ".codenook/memory/knowledge/foo/index.md",
        "---\nid: foo\ntitle: Foo\ntype: bogus\ntags: [a]\nsummary: ok\n---\n",
    )
    findings, _ = fl.lint(ws)
    assert any(f["code"] == "bad-type" for f in findings)


def test_main_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    ws = _mk_workspace(tmp_path)
    _write(
        ws / ".codenook/memory/knowledge/foo/index.md",
        "---\nid: foo\ntitle: Foo\ntype: knowledge\ntags: [a]\nsummary: ok\n---\n",
    )
    rc = fl.main(["--workspace", str(ws), "--json"])
    assert rc == 0
    captured = capsys.readouterr()
    assert '"ok": true' in captured.out
