"""E2E-019 — workspace state.json schema includes kernel metadata."""
from __future__ import annotations

import json
from pathlib import Path

import _orchestrator as orch


def test_update_state_json_writes_v1_schema(workspace: Path):
    orch.update_state_json(
        workspace, "development", "0.1.0",
        kernel_version="0.11.3",
        kernel_dir="/abs/path/to/kernel",
        files_sha256="deadbeef" * 8,
    )
    sj = workspace / ".codenook" / "state.json"
    d = json.loads(sj.read_text())
    assert d["schema_version"] == "v1"
    assert d["kernel_version"] == "0.11.3"
    assert d["installed_at"]
    assert d["kernel_dir"] == "/abs/path/to/kernel"
    assert d["bin"] == ".codenook/bin/codenook"
    assert d["installed_plugins"][0]["id"] == "development"
    assert d["installed_plugins"][0]["version"] == "0.1.0"
    assert d["installed_plugins"][0]["files_sha256"] == "deadbeef" * 8


def test_update_state_json_upgrades_old_format(workspace: Path):
    sj = workspace / ".codenook" / "state.json"
    sj.parent.mkdir(parents=True, exist_ok=True)
    sj.write_text(json.dumps({
        "installed_plugins": [{"id": "development", "version": "0.0.9"}]
    }))
    orch.update_state_json(workspace, "development", "0.1.0",
                           kernel_version="0.11.3",
                           kernel_dir="/k",
                           files_sha256="hash")
    d = json.loads(sj.read_text())
    assert d["schema_version"] == "v1"
    assert d["kernel_version"] == "0.11.3"
    plugins = d["installed_plugins"]
    assert [p["id"] for p in plugins] == ["development"]
    assert plugins[0]["version"] == "0.1.0"
    assert plugins[0]["files_sha256"] == "hash"


def test_aggregate_files_sha256_is_stable(tmp_path: Path):
    d = tmp_path / "plugin"
    d.mkdir()
    (d / "a.txt").write_text("hello")
    (d / "b.txt").write_text("world")
    h1 = orch._aggregate_files_sha256(d)
    h2 = orch._aggregate_files_sha256(d)
    assert h1 == h2 and len(h1) == 64
    (d / "b.txt").write_text("world!")
    assert orch._aggregate_files_sha256(d) != h1
