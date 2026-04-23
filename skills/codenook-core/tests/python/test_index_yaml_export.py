"""Tests for memory_index.export_index_yaml() and the auto-refresh
hook in memory_layer write paths.
"""
from __future__ import annotations

from pathlib import Path

import yaml

import memory_index
import memory_layer as ml


def _load(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def test_empty_memory_exports_empty_lists(workspace: Path):
    target = memory_index.export_index_yaml(workspace)
    assert target.is_file()
    assert target.name == "index.yaml"
    data = _load(target)
    assert data["version"] == 1
    assert "generated_at" in data
    assert isinstance(data["generated_at"], str) and data["generated_at"].endswith("Z")
    assert data["skills"] == []
    assert data["knowledge"] == []


def test_write_skill_triggers_index_yaml_refresh(workspace: Path):
    # Pre-condition: no index.yaml yet.
    idx = workspace / ".codenook" / "memory" / "index.yaml"
    assert not idx.exists()

    ml.write_skill(
        workspace,
        name="run-tests",
        frontmatter={"name": "run-tests", "summary": "Run pytest", "tags": ["dev"]},
        body="Body",
        created_from_task="T-001",
    )

    assert idx.is_file(), "write_skill should refresh index.yaml"
    data = _load(idx)
    names = [s["name"] for s in data["skills"]]
    assert "run-tests" in names
    skill = next(s for s in data["skills"] if s["name"] == "run-tests")
    assert skill["summary"] == "Run pytest"
    assert skill["tags"] == ["dev"]
    assert skill["path"].replace("\\", "/").endswith(".codenook/memory/skills/run-tests/SKILL.md")


def test_write_knowledge_triggers_index_yaml_refresh(workspace: Path):
    ml.write_knowledge(
        workspace,
        topic="cache-strategy",
        summary="Use Redis for L2 cache",
        tags=["cache"],
        body="Body",
        created_from_task="T-002",
    )

    idx = workspace / ".codenook" / "memory" / "index.yaml"
    assert idx.is_file()
    data = _load(idx)
    topics = [k["topic"] for k in data["knowledge"]]
    assert "cache-strategy" in topics
    entry = next(k for k in data["knowledge"] if k["topic"] == "cache-strategy")
    assert entry["summary"] == "Use Redis for L2 cache"
    assert entry["tags"] == ["cache"]
    assert entry["path"].replace("\\", "/").endswith(".codenook/memory/knowledge/cache-strategy.md")


def test_index_yaml_has_expected_top_level_keys(workspace: Path):
    target = memory_index.export_index_yaml(workspace)
    data = _load(target)
    assert set(data.keys()) >= {"version", "generated_at", "skills", "knowledge"}
    assert isinstance(data["skills"], list)
    assert isinstance(data["knowledge"], list)
