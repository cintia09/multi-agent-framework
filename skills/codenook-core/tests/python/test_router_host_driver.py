"""E2E-002 — router-agent host_driver writes router-reply.md."""
from __future__ import annotations

from pathlib import Path

import host_driver


def test_drive_writes_reply(workspace: Path, monkeypatch):
    tdir = workspace / ".codenook" / "tasks" / "T-001"
    tdir.mkdir(parents=True)
    (tdir / ".router-prompt.md").write_text("PROMPT: hello\n")
    monkeypatch.setenv("CN_LLM_MODE", "mock")
    monkeypatch.setenv("CN_LLM_MOCK_ROUTER", "MOCKED REPLY\n")

    rc = host_driver.drive(workspace, "T-001")
    assert rc == 0
    reply = (tdir / "router-reply.md").read_text()
    assert "MOCKED REPLY" in reply


def test_drive_missing_prompt(workspace: Path):
    rc = host_driver.drive(workspace, "T-404")
    assert rc == 1


def test_drive_llm_failure(workspace: Path, monkeypatch):
    tdir = workspace / ".codenook" / "tasks" / "T-002"
    tdir.mkdir(parents=True)
    (tdir / ".router-prompt.md").write_text("anything\n")
    monkeypatch.setenv("CN_LLM_MODE", "mock")
    monkeypatch.setenv("CN_LLM_MOCK_ERROR_ROUTER", "boom")
    rc = host_driver.drive(workspace, "T-002")
    assert rc == 1
    assert not (tdir / "router-reply.md").exists()
