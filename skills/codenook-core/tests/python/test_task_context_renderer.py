"""Unit tests for the {{TASK_CONTEXT}} renderer (build_task_context)."""
from __future__ import annotations

from pathlib import Path

import memory_layer as ml


def _make_knowledge(ws: Path, tid: str, topic: str, summary: str, body: str = "") -> None:
    ml.init_task_extracted_skeleton(ws, tid)
    ml.write_knowledge_to_task(
        ws, tid,
        topic=topic,
        summary=summary,
        body=body or f"Body of {topic}.",
    )


def _make_skill(ws: Path, tid: str, name: str, summary: str, body: str = "") -> None:
    ml.init_task_extracted_skeleton(ws, tid)
    ml.write_skill_to_task(
        ws, tid,
        name=name,
        frontmatter={"summary": summary, "name": name},
        body=body or f"Body of skill {name}.",
    )


def _make_config(ws: Path, tid: str, key: str, value: str) -> None:
    ml.init_task_extracted_skeleton(ws, tid)
    ml.upsert_config_to_task(
        ws, tid,
        entry={"key": key, "value": value, "applies_when": "always", "summary": "test"},
    )


def test_empty_extracted_dir_returns_empty(workspace: Path):
    result = ml.build_task_context(workspace, "T-999")
    assert result == ""


def test_missing_extracted_dir_returns_empty(workspace: Path, tmp_path: Path):
    ws = tmp_path / "fresh"
    ws.mkdir()
    (ws / ".codenook" / "tasks").mkdir(parents=True)
    result = ml.build_task_context(ws, "T-MISSING")
    assert result == ""


def test_knowledge_entry_appears_in_context(workspace: Path):
    tid = "T-CTX-01"
    _make_knowledge(workspace, tid, "cache-strategy", "Use Redis for L2 cache")
    result = ml.build_task_context(workspace, tid)
    assert result != ""
    assert "## Task-extracted context" in result
    assert "knowledge/cache-strategy.md" in result
    assert "Use Redis for L2 cache" in result


def test_skill_entry_appears_in_context(workspace: Path):
    tid = "T-CTX-02"
    _make_skill(workspace, tid, "run-tests", "Run the test suite via pytest")
    result = ml.build_task_context(workspace, tid)
    assert result != ""
    assert "skills/run-tests/SKILL.md" in result
    assert "Run the test suite" in result


def test_config_entry_appears_in_context(workspace: Path):
    tid = "T-CTX-03"
    _make_config(workspace, tid, "DB_PORT", "5432")
    result = ml.build_task_context(workspace, tid)
    assert result != ""
    assert "config: DB_PORT=" in result
    assert "5432" in result


def test_empty_extracted_dirs_no_header(workspace: Path):
    tid = "T-CTX-04"
    ml.init_task_extracted_skeleton(workspace, tid)
    result = ml.build_task_context(workspace, tid)
    assert result == ""


def test_multiple_artefacts_all_appear(workspace: Path):
    tid = "T-CTX-05"
    _make_knowledge(workspace, tid, "algo-tip", "Use binary search when sorted")
    _make_skill(workspace, tid, "deploy-script", "Deploy via docker-compose up")
    _make_config(workspace, tid, "TIMEOUT", "30")
    result = ml.build_task_context(workspace, tid)
    assert "knowledge/algo-tip.md" in result
    assert "skills/deploy-script/SKILL.md" in result
    assert "TIMEOUT=" in result
