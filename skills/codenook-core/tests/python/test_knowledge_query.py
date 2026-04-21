"""Tests for v0.22.0 ``find_relevant`` API + ``{{KNOWLEDGE_HITS}}``
template substitution (kernel-side knowledge auto-injection).
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

import knowledge_query as kq


# ---------------------------------------------------------------- helpers
def _write_index(ws: Path, knowledge: list[dict]) -> Path:
    p = ws / ".codenook" / "memory" / "index.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        yaml.safe_dump({"version": 1, "knowledge": knowledge, "skills": []}),
        encoding="utf-8",
    )
    return p


def _make_ws(tmp_path: Path) -> Path:
    (tmp_path / ".codenook" / "memory").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------- 1. missing
def test_find_relevant_returns_empty_when_index_missing(tmp_path: Path):
    ws = _make_ws(tmp_path)
    # No index.yaml, no plugins/ — must return [].
    hits = kq.find_relevant(ws, "anything")
    assert hits == []


# ---------------------------------------------------------------- 2. tag>summary
def test_tag_match_outranks_summary_only_match(tmp_path: Path):
    ws = _make_ws(tmp_path)
    _write_index(ws, [
        {
            "plugin": "p1",
            "title": "Tag-matched entry",
            "path": "p1/knowledge/tagged.md",
            "summary": "irrelevant body text.",
            "tags": ["alpha", "bravo"],
        },
        {
            "plugin": "p1",
            "title": "Summary-matched entry",
            "path": "p1/knowledge/summary.md",
            "summary": "Discusses alpha-related concerns at length.",
            "tags": ["unrelated"],
        },
    ])
    hits = kq.find_relevant(ws, "alpha")
    assert len(hits) == 2
    assert hits[0]["path"].endswith("tagged.md"), hits
    assert hits[0]["score"] > hits[1]["score"]


# ---------------------------------------------------------------- 3. top_n
def test_top_n_cap_respected(tmp_path: Path):
    ws = _make_ws(tmp_path)
    knowledge = [
        {
            "plugin": "p1",
            "title": f"Entry {i}",
            "path": f"p1/knowledge/e{i}.md",
            "summary": f"keyword-x present in entry {i}.",
            "tags": ["keyword-x"],
        }
        for i in range(20)
    ]
    _write_index(ws, knowledge)
    hits = kq.find_relevant(ws, "keyword-x", top_n=3)
    assert len(hits) == 3
    hits_all = kq.find_relevant(ws, "keyword-x", top_n=8)
    assert len(hits_all) == 8


# ---------------------------------------------------------------- 4. plugin bias
def test_plugin_pin_bias_breaks_tie(tmp_path: Path):
    ws = _make_ws(tmp_path)
    _write_index(ws, [
        {
            "plugin": "other",
            "title": "Other plugin entry",
            "path": "other/knowledge/x.md",
            "summary": "match-token here.",
            "tags": ["match-token"],
        },
        {
            "plugin": "prnook",
            "title": "Prnook entry",
            "path": "prnook/knowledge/x.md",
            "summary": "match-token here.",
            "tags": ["match-token"],
        },
    ])
    # Without plugin pin: ties resolved by (plugin, path) → "other" first.
    no_pin = kq.find_relevant(ws, "match-token")
    assert no_pin[0]["plugin"] == "other"
    # With plugin pin: prnook wins via +1 bias.
    pinned = kq.find_relevant(ws, "match-token", plugin="prnook")
    assert pinned[0]["plugin"] == "prnook"
    assert pinned[0]["score"] > pinned[1]["score"]


# ---------------------------------------------------------------- 5. fallback scan
def test_fallback_in_memory_scan_when_index_missing(tmp_path: Path):
    """Workspace with installed plugins but no index.yaml still works."""
    ws = _make_ws(tmp_path)
    # Don't write index.yaml; create a plugin with one knowledge file.
    pdir = ws / ".codenook" / "plugins" / "myplug"
    (pdir / "knowledge").mkdir(parents=True)
    (pdir / "knowledge" / "alarm-3001.md").write_text(
        textwrap.dedent("""\
            ---
            title: Alarm 3001 handling
            summary: Reset RU when alarm 3001 fires twice in 5min.
            tags: [alarm, ru, reset]
            ---
            body
        """),
        encoding="utf-8",
    )
    hits = kq.find_relevant(ws, "alarm")
    assert hits, "fallback scan should find the plugin's knowledge"
    assert hits[0]["plugin"] == "myplug"


# ---------------------------------------------------------------- 6. role/phase
def test_role_and_phase_id_fold_into_query(tmp_path: Path):
    ws = _make_ws(tmp_path)
    _write_index(ws, [
        {
            "plugin": "p1",
            "title": "Implementer hint",
            "path": "p1/knowledge/imp.md",
            "summary": "tip for the implementer phase.",
            "tags": ["implementer"],
        },
    ])
    # Empty query, but role="implementer" should still produce a hit.
    hits = kq.find_relevant(ws, "", role="implementer")
    assert len(hits) == 1
    assert "implementer" in hits[0]["reason"]


# ---------------------------------------------------------------- 7. render
def test_render_hits_block_formats_bullets():
    block = kq.render_hits_block([
        {
            "path": "a/b.md",
            "plugin": "p1",
            "score": 4.5,
            "summary": "Hello",
            "tags": ["x", "y"],
            "reason": "tag match: x",
        }
    ])
    assert "Auto-retrieved knowledge hits" in block
    assert "`a/b.md`" in block
    assert "plugin: p1" in block
    assert "score: 4.5" in block
    assert "summary: Hello" in block
    assert "tags: x, y" in block
    assert "why selected: tag match: x" in block


def test_render_hits_block_empty_renders_no_match_message():
    block = kq.render_hits_block([])
    assert "No matches found in index.yaml" in block
    assert "codenook knowledge reindex" in block


# ---------------------------------------------------------------- 8. substitute
def test_substitute_placeholder_replaces_when_present(tmp_path: Path):
    ws = _make_ws(tmp_path)
    _write_index(ws, [
        {
            "plugin": "p1",
            "title": "Match",
            "path": "p1/knowledge/m.md",
            "summary": "alpha keyword here.",
            "tags": ["alpha"],
        },
    ])
    body = "Header\n\n{{KNOWLEDGE_HITS}}\n\nFooter\n"
    out = kq.substitute_placeholder(body, ws, query="alpha")
    assert "{{KNOWLEDGE_HITS}}" not in out
    assert "Auto-retrieved knowledge hits" in out
    assert "Header" in out and "Footer" in out


def test_substitute_placeholder_no_op_when_absent(tmp_path: Path):
    ws = _make_ws(tmp_path)
    body = "no placeholder here"
    assert kq.substitute_placeholder(body, ws, query="alpha") == body


def test_substitute_placeholder_renders_empty_message_on_zero_hits(tmp_path: Path):
    ws = _make_ws(tmp_path)
    _write_index(ws, [])
    body = "{{KNOWLEDGE_HITS}}"
    out = kq.substitute_placeholder(body, ws, query="zzz")
    assert "No matches found in index.yaml" in out


# ---------------------------------------------------------------- 9. config top_n
def test_resolve_top_n_reads_config_yaml(tmp_path: Path):
    ws = _make_ws(tmp_path)
    cfg = ws / ".codenook" / "config.yaml"
    cfg.write_text("knowledge_hits:\n  top_n: 3\n", encoding="utf-8")
    assert kq.resolve_top_n(ws) == 3


def test_resolve_top_n_default_when_missing(tmp_path: Path):
    ws = _make_ws(tmp_path)
    assert kq.resolve_top_n(ws, default=8) == 8


def test_resolve_top_n_default_on_invalid(tmp_path: Path):
    ws = _make_ws(tmp_path)
    cfg = ws / ".codenook" / "config.yaml"
    cfg.write_text("knowledge_hits:\n  top_n: bogus\n", encoding="utf-8")
    assert kq.resolve_top_n(ws, default=8) == 8


# ---------------------------------------------------------------- 10. integ orch render
def test_orchestrator_render_phase_prompt_substitutes_knowledge_hits(
    tmp_path: Path,
):
    """End-to-end check at the orchestrator-tick layer: a manifest
    template containing ``{{KNOWLEDGE_HITS}}`` is substituted; one
    without it is left unchanged.
    """
    import _tick as tick  # type: ignore

    ws = _make_ws(tmp_path)
    plugin_id = "tplug"

    # 1. Workspace with one manifest template carrying both placeholders.
    mt_dir = ws / ".codenook" / "plugins" / plugin_id / "manifest-templates"
    mt_dir.mkdir(parents=True)
    template_with = mt_dir / "phase-1-implementer.md"
    template_with.write_text(
        "Role: implementer\n"
        "TASK: {{TASK_CONTEXT}}\n"
        "{{KNOWLEDGE_HITS}}\n",
        encoding="utf-8",
    )
    template_without = mt_dir / "phase-2-tester.md"
    template_without.write_text("Role: tester\n(no placeholder here)\n", encoding="utf-8")

    # 2. index.yaml with one matching entry.
    _write_index(ws, [
        {
            "plugin": plugin_id,
            "title": "Implementer cheatsheet",
            "path": f"{plugin_id}/knowledge/cheat.md",
            "summary": "cold-start cheatsheet for implementer phase.",
            "tags": ["implementer", "cheatsheet"],
        }
    ])

    state = {
        "task_id": "T-001",
        "plugin": plugin_id,
        "task_input": "implementer cheatsheet please",
        "keywords": ["implementer"],
    }
    phase_with = {"id": 1, "role": "implementer", "produces": "outputs/phase-1-implementer.md"}
    phase_without = {"id": 2, "role": "tester", "produces": "outputs/phase-2-tester.md"}

    out_with = tick._render_phase_prompt(ws, state, phase_with)
    assert out_with is not None
    assert "{{KNOWLEDGE_HITS}}" not in out_with
    assert "Auto-retrieved knowledge hits" in out_with
    assert "cheat.md" in out_with

    out_without = tick._render_phase_prompt(ws, state, phase_without)
    assert out_without is not None
    assert "Auto-retrieved knowledge hits" not in out_without
    assert out_without.strip().endswith("(no placeholder here)")
