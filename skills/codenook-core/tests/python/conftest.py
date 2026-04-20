"""Pytest fixtures for CodeNook v0.11.3 fix-pack tests."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[4]
LIB = REPO / "skills" / "codenook-core" / "skills" / "builtin" / "_lib"
ROUTER = REPO / "skills" / "codenook-core" / "skills" / "builtin" / "router-agent"
ORCH = REPO / "skills" / "codenook-core" / "skills" / "builtin" / "orchestrator-tick"
EXTR = REPO / "skills" / "codenook-core" / "skills" / "builtin" / "knowledge-extractor"
INST = REPO / "skills" / "codenook-core" / "skills" / "builtin" / "install-orchestrator"

for p in (LIB, ROUTER, ORCH, EXTR, INST):
    sys.path.insert(0, str(p))


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / ".codenook" / "tasks").mkdir(parents=True)
    (tmp_path / ".codenook" / "plugins" / "development").mkdir(parents=True)
    (tmp_path / ".codenook" / "memory" / "knowledge").mkdir(parents=True)
    (tmp_path / ".codenook" / "memory" / "skills").mkdir(parents=True)
    (tmp_path / ".codenook" / "memory" / "history").mkdir(parents=True)
    (tmp_path / ".codenook" / "memory" / "_pending").mkdir(parents=True)
    (tmp_path / ".codenook" / "memory" / "config.yaml").write_text("entries: []\n")
    return tmp_path
