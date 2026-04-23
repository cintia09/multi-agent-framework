"""``knowledge search`` covers skills too, not just knowledge entries.
New in v0.27.21 — the aggregator now merges ``payload['skills']`` into
the search pool and tags each hit as ``[K]`` or ``[S]``.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_CORE = _REPO / "skills" / "codenook-core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


class _Ctx:
    def __init__(self, ws: Path) -> None:
        self.workspace = ws


def _seed_skill(workspace: Path, plugin: str, name: str,
                summary: str, tags: list[str]) -> None:
    sdir = workspace / ".codenook" / "plugins" / plugin / "skills" / name
    sdir.mkdir(parents=True, exist_ok=True)
    fm_tags = "[" + ", ".join(tags) + "]"
    (sdir / "SKILL.md").write_text(
        f"---\nname: {name}\nsummary: {summary}\ntags: {fm_tags}\n---\nBody.\n",
        encoding="utf-8",
    )


def _seed_knowledge(workspace: Path, plugin: str, filename: str,
                    title: str, summary: str, tags: list[str]) -> None:
    kdir = workspace / ".codenook" / "plugins" / plugin / "knowledge"
    kdir.mkdir(parents=True, exist_ok=True)
    fm_tags = "[" + ", ".join(tags) + "]"
    (kdir / filename).write_text(
        f"---\ntitle: {title}\nsummary: {summary}\ntags: {fm_tags}\n---\nBody.\n",
        encoding="utf-8",
    )


def test_search_finds_skill_by_name(workspace: Path, capsys):
    _seed_skill(workspace, "development", "run-pytest",
                "Run the Python test suite", ["dev", "testing"])
    from _lib.cli import cmd_knowledge  # type: ignore
    rc = cmd_knowledge.run(_Ctx(workspace), ["search", "pytest"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "run-pytest" in out
    assert "[S]" in out


def test_search_finds_skill_by_tag(workspace: Path, capsys):
    _seed_skill(workspace, "development", "lint-yaml",
                "Lint YAML files", ["lint", "yaml"])
    from _lib.cli import cmd_knowledge  # type: ignore
    rc = cmd_knowledge.run(_Ctx(workspace), ["search", "yaml"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "lint-yaml" in out
    assert "[S]" in out


def test_search_marks_knowledge_vs_skill(workspace: Path, capsys):
    _seed_skill(workspace, "development", "foo-skill",
                "Foo helper skill", ["foo"])
    _seed_knowledge(workspace, "development", "foo.md",
                    "Foo knowledge", "Foo docs.", ["foo"])
    from _lib.cli import cmd_knowledge  # type: ignore
    rc = cmd_knowledge.run(_Ctx(workspace), ["search", "foo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "[K]" in out
    assert "[S]" in out
