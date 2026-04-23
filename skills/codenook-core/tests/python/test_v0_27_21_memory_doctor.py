"""Tests for ``memory_doctor.diagnose()`` and ``codenook memory doctor``
(``_lib/cli/cmd_memory.py``). New in v0.27.21.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import memory_doctor  # provided via conftest sys.path insertion

_REPO = Path(__file__).resolve().parents[4]
_CORE = _REPO / "skills" / "codenook-core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


class _Ctx:
    def __init__(self, ws: Path) -> None:
        self.workspace = ws


# ───────────────────────────────────────────── diagnose()

def test_diagnose_missing_summary(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    (kdir / "foo.md").write_text(
        "---\ntitle: Foo\ntags: [a]\n---\nFoo body paragraph.\n",
        encoding="utf-8",
    )
    report = memory_doctor.diagnose(workspace)
    assert len(report["workspace_issues"]) == 1
    diag = report["workspace_issues"][0]
    assert any("summary" in i for i in diag["issues"])
    assert diag["fixes"].get("summary")  # has a proposed fix


def test_diagnose_non_list_tags(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    (kdir / "bar.md").write_text(
        "---\ntitle: Bar\nsummary: s\ntags: cli,auth\n---\nBody.\n",
        encoding="utf-8",
    )
    report = memory_doctor.diagnose(workspace)
    assert len(report["workspace_issues"]) == 1
    diag = report["workspace_issues"][0]
    assert any("tags not a list" in i for i in diag["issues"])
    assert diag["fixes"]["tags"] == ["cli", "auth"]


def test_diagnose_non_string_tag(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    (kdir / "hex.md").write_text(
        "---\ntitle: T\nsummary: s\ntags: [0x2c2000, memory]\n---\nBody.\n",
        encoding="utf-8",
    )
    report = memory_doctor.diagnose(workspace)
    diag = report["workspace_issues"][0]
    assert any("non-string" in i for i in diag["issues"])


def test_diagnose_datetime_fm_value(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    (kdir / "dated.md").write_text(
        "---\ntitle: Dated\nsummary: s\ntags: [a]\ncreated: 2026-04-22\n---\nBody.\n",
        encoding="utf-8",
    )
    report = memory_doctor.diagnose(workspace)
    diag = report["workspace_issues"][0]
    assert any("created is date" in i for i in diag["issues"])
    assert diag["fixes"]["frontmatter_stringify"]["created"] == "2026-04-22"


def test_diagnose_no_frontmatter(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    (kdir / "raw.md").write_text("just body text\n", encoding="utf-8")
    report = memory_doctor.diagnose(workspace)
    diag = report["workspace_issues"][0]
    assert any("no frontmatter" in i for i in diag["issues"])
    # No auto-repair for missing frontmatter.
    assert not diag["fixes"]


def test_diagnose_clean_file(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    (kdir / "ok.md").write_text(
        "---\ntitle: OK\nsummary: clean summary\ntags: [a, b]\n---\nBody.\n",
        encoding="utf-8",
    )
    report = memory_doctor.diagnose(workspace)
    assert report["workspace_issues"] == []
    assert report["workspace_clean"] == 1


# ───────────────────────────────────────────── repair

def test_repair_fixes_and_writes_backup(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    path = kdir / "fixable.md"
    path.write_text(
        "---\ntitle: T\ntags: cli,auth\n---\nBody paragraph here.\n",
        encoding="utf-8",
    )

    report = memory_doctor.diagnose(workspace, repair=True)
    assert len(report["repaired"]) == 1
    assert report["repaired"][0]["path"].endswith("fixable.md")

    # Backup exists.
    backup_root = workspace / ".codenook" / "memory" / ".repair-backup" / report["timestamp"]
    assert backup_root.is_dir()
    # Backed-up file contains the ORIGINAL content.
    backed = list(backup_root.rglob("fixable.md"))
    assert backed, "expected a backup of fixable.md"
    assert "tags: cli,auth" in backed[0].read_text(encoding="utf-8")

    # Re-read repaired file — tags should now be a proper list, and a
    # summary should have been added.
    fixed = path.read_text(encoding="utf-8")
    assert "tags:" in fixed
    # Tags list form: yaml-safe_dump emits `- cli\n- auth`
    assert "- cli" in fixed and "- auth" in fixed
    assert "summary:" in fixed


def test_repair_leaves_plugin_files_untouched(workspace: Path):
    # Plugin file with issues
    plug_kdir = workspace / ".codenook" / "plugins" / "development" / "knowledge"
    plug_kdir.mkdir(parents=True, exist_ok=True)
    plugin_path = plug_kdir / "bad.md"
    before = "---\ntitle: Bad\ntags: cli,auth\n---\nBody.\n"
    plugin_path.write_text(before, encoding="utf-8")

    report = memory_doctor.diagnose(workspace, repair=True)

    assert any(
        d["path"] == str(plugin_path) for d in report["plugin_issues"]
    )
    # Plugin file unchanged.
    assert plugin_path.read_text(encoding="utf-8") == before


def test_repair_no_frontmatter_is_not_modified(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    p = kdir / "raw.md"
    p.write_text("just body\n", encoding="utf-8")
    before = p.read_text(encoding="utf-8")
    report = memory_doctor.diagnose(workspace, repair=True)
    assert report["repaired"] == []
    assert p.read_text(encoding="utf-8") == before


# ───────────────────────────────────────────── CLI

def test_cli_json_output_is_parseable(workspace: Path, capsys):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    (kdir / "foo.md").write_text(
        "---\ntitle: Foo\ntags: [a]\n---\nBody.\n", encoding="utf-8",
    )
    from _lib.cli import cmd_memory  # type: ignore

    rc = cmd_memory.run(_Ctx(workspace), ["doctor", "--json"])
    out = capsys.readouterr().out
    data = json.loads(out)
    assert "workspace_issues" in data
    assert "plugin_issues" in data
    assert rc == 1  # issues present


def test_cli_exit_zero_when_clean(workspace: Path, capsys):
    from _lib.cli import cmd_memory  # type: ignore
    # Empty memory — no issues.
    rc = cmd_memory.run(_Ctx(workspace), ["doctor"])
    capsys.readouterr()  # discard
    assert rc == 0


def test_cli_repair_reports_fixed(workspace: Path, capsys):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    (kdir / "x.md").write_text(
        "---\ntitle: X\ntags: cli,auth\n---\nBody.\n", encoding="utf-8",
    )
    from _lib.cli import cmd_memory  # type: ignore
    rc = cmd_memory.run(_Ctx(workspace), ["doctor", "--repair"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Repaired" in out
