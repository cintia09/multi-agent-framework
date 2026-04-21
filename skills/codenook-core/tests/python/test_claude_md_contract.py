"""Functional contract for the rendered CLAUDE.md bootloader.

These tests pin the *invariants* the bootloader must convey to the
conductor LLM, regardless of wording, length or section ordering.
A refactor of ``claude_md_sync.render_block`` is allowed (and
encouraged) to change phrasing or structure — but every assertion
below must still hold afterwards.

Each test maps to ONE behavioural contract, written as ``CONTRACT-XX``
in the docstring so reviewers can trace coverage.
"""
from __future__ import annotations

import re
from pathlib import Path
import sys

LIB = Path(__file__).resolve().parents[2] / "skills" / "builtin" / "_lib"
sys.path.insert(0, str(LIB))

from claude_md_sync import render_block, BEGIN, END  # noqa: E402

VERSION = "0.27.2"


def render(plugins=("development", "writing", "research")):
    return render_block(VERSION, list(plugins))


def has_any(text: str, *patterns: str) -> list[str]:
    """Return the patterns that match (case-insensitive substring or regex)."""
    found = []
    for p in patterns:
        if re.search(p, text, flags=re.IGNORECASE | re.DOTALL):
            found.append(p)
    return found


# =====================================================================
# CONTRACT-01 — Block envelope and identity
# =====================================================================

def test_contract_01_block_is_marker_wrapped():
    """CONTRACT-01a: rendered block opens/closes with codenook markers."""
    out = render()
    assert out.startswith(BEGIN)
    assert out.rstrip().endswith(END)


def test_contract_01_header_carries_version():
    """CONTRACT-01b: header must declare 'CodeNook v<X.Y.Z> bootloader'."""
    out = render()
    assert re.search(rf"CodeNook v{re.escape(VERSION)} bootloader", out)


def test_contract_01_do_not_edit_warning_present():
    """CONTRACT-01c: the do-not-edit-by-hand warning must remain."""
    out = render()
    assert "DO NOT EDIT BY HAND" in out


# =====================================================================
# CONTRACT-02 — Identity / role of the LLM
# =====================================================================

def test_contract_02_pure_conductor_role():
    """CONTRACT-02a: LLM is told it acts as a pure conductor (relay role)."""
    out = render()
    assert has_any(out, r"pure conductor")


def test_contract_02_no_self_initiated_tasks():
    """CONTRACT-02b: LLM must not decide to start tasks on its own."""
    out = render()
    assert has_any(
        out,
        r"do \*?\*?not\*?\*? decide on your own",
        r"only when the user explicitly asks",
    )


def test_contract_02_relay_verbatim():
    """CONTRACT-02c: orchestrator messages are relayed verbatim."""
    out = render()
    assert has_any(out, r"verbatim")


# =====================================================================
# CONTRACT-03 — When to start a task (triggers)
# =====================================================================

def test_contract_03_trigger_phrases_en_and_zh():
    """CONTRACT-03: explicit trigger phrases listed in EN and ZH."""
    out = render()
    # English form
    assert has_any(out, r"start a (?:codenook )?task", r"new task")
    # Chinese form: at least one canonical ZH trigger phrase must appear.
    zh_patterns = [
        r"走\s*codenook",
        r"用\s*codenook",
        r"新建\s*codenook",
        r"开个?\s*codenook",
        r"交给\s*codenook",
        r"codenook\s*任务",
    ]
    assert any(re.search(p, out, flags=re.IGNORECASE) for p in zh_patterns), \
        "No canonical ZH trigger phrase found."


# =====================================================================
# CONTRACT-04 — Wrapper command surface
# =====================================================================

def test_contract_04_wrapper_placeholder_explained():
    """CONTRACT-04a: <codenook> placeholder convention is explained."""
    out = render()
    assert "<codenook>" in out
    # Must show how to invoke on at least one OS form.
    assert has_any(out, r"bin/codenook", r"codenook\.cmd", r"codenook\.sh")


def test_contract_04_required_subcommands_documented():
    """CONTRACT-04b: every subcommand the conductor may issue is named."""
    out = render()
    required = [
        r"task new",
        r"\btick\b",
        r"\bdecide\b",
        r"\bstatus\b",
    ]
    missing = [r for r in required if not re.search(r, out)]
    assert not missing, f"Missing wrapper subcommands in bootloader: {missing}"


# =====================================================================
# CONTRACT-05 — Boot ritual (what to read at session start)
# =====================================================================

def test_contract_05_boot_ritual_lists_authoritative_files():
    """CONTRACT-05: conductor is told to read state.json, plugin.yaml, memory index."""
    out = render()
    for needle in ("state.json", "plugin.yaml", "memory/index.yaml"):
        assert needle in out, f"Boot-ritual reference missing: {needle}"


def test_contract_05_installed_plugins_is_source_of_truth():
    """CONTRACT-05b: installed_plugins in state.json is the canonical list."""
    out = render()
    assert "installed_plugins" in out


# =====================================================================
# CONTRACT-06 — Plugin seed line (renderer behaviour)
# =====================================================================

def test_contract_06_seed_line_zero_plugins():
    out = render_block(VERSION, [])
    assert "Workspace has plugin" not in out
    assert "Workspace has plugins" not in out


def test_contract_06_seed_line_one_plugin():
    out = render_block(VERSION, ["development"])
    assert "Workspace has plugin installed:" in out
    assert "**development**" in out


def test_contract_06_seed_line_many_plugins():
    out = render_block(VERSION, ["development", "writing", "research"])
    assert "Workspace has plugins installed:" in out
    for p in ("**development**", "**writing**", "**research**"):
        assert p in out


def test_contract_06_render_block_accepts_str_none_list():
    """Backward-compat: render_block tolerates str / None / list input."""
    assert "Workspace has plugin installed:" in render_block(VERSION, "writing")
    out_none = render_block(VERSION, None)
    assert "Workspace has plugin" not in out_none
    assert "Workspace has plugins installed:" in render_block(
        VERSION, ["a", "b"]
    )


# =====================================================================
# CONTRACT-07 — Task creation flow
# =====================================================================

def test_contract_07_task_new_input_semantics():
    """CONTRACT-07a: --input is documented as the user-intent payload."""
    out = render()
    assert "--input" in out
    # must mention multi-line / heredoc support somehow
    assert has_any(out, r"multi-line", r"<<['\"]?EOF", r"heredoc")


def test_contract_07_slug_derivation_documented():
    """CONTRACT-07b: slug derivation order is documented."""
    out = render()
    # We only require that the canonical priority mentions title/input/summary
    # together — a refactor is free to reword.
    assert re.search(
        r"slug.*?(--?title|title).*?(--?input|input).*?(--?summary|summary)",
        out, flags=re.DOTALL | re.IGNORECASE,
    ), "Slug-derivation rule (title → input → summary) missing or out of order."


# =====================================================================
# CONTRACT-08 — Tick / dispatch envelope protocol
# =====================================================================

def test_contract_08_tick_returns_json_envelope():
    out = render()
    assert has_any(out, r"--json", r"JSON envelope", r"envelope")
    # The envelope must be described as containing dispatch instructions.
    assert has_any(out, r"dispatch", r"sub-?agent", r"sub agent")


def test_contract_08_envelope_fields_documented():
    """The envelope has at least an action/role/prompt-like contract."""
    out = render()
    # Allow renaming but core fields must appear somewhere.
    fields = [r"\baction\b", r"\brole\b", r"\bprompt\b"]
    missing = [f for f in fields if not re.search(f, out, flags=re.IGNORECASE)]
    assert not missing, f"Envelope contract fields missing: {missing}"


# =====================================================================
# CONTRACT-09 — HITL / gates
# =====================================================================

def test_contract_09_hitl_gate_handling_documented():
    out = render()
    assert has_any(out, r"\bHITL\b", r"human-in-the-loop", r"\bgate\b")
    # Conductor must know about `decide` to resolve gates.
    assert "decide" in out


# =====================================================================
# CONTRACT-10 — Clarifier (inline) rule
# =====================================================================

def test_contract_10_clarifier_runs_inline():
    out = render()
    assert "clarifier" in out.lower()
    assert has_any(out, r"inline", r"in[- ]process", r"same process")


# =====================================================================
# CONTRACT-11 — Model field handling
# =====================================================================

def test_contract_11_model_field_pass_through():
    out = render()
    # The conductor must pass the model field as-is from the envelope.
    assert "model" in out.lower()
    assert has_any(out, r"verbatim", r"as[- ]is", r"do not modify", r"don't modify")


# =====================================================================
# CONTRACT-12 — Execution mode (inline_dispatch)
# =====================================================================

def test_contract_12_execution_mode_documented():
    out = render()
    assert has_any(out, r"execution_mode", r"inline_dispatch", r"sub-?agent mode")


# =====================================================================
# CONTRACT-13 — Workspace layout
# =====================================================================

def test_contract_13_workspace_layout_referenced():
    out = render()
    for needle in (".codenook", "tasks", "memory"):
        assert needle in out, f"Workspace-layout reference missing: {needle}"


# =====================================================================
# CONTRACT-14 — Hard rules block
# =====================================================================

def test_contract_14_hard_rules_present():
    """CONTRACT-14: bootloader contains an explicit hard-rules section."""
    out = render()
    assert re.search(r"hard rules?|^### Rules", out, flags=re.IGNORECASE | re.MULTILINE)
    # And uses normative language.
    assert re.search(r"\bMUST\b|\bMUST NOT\b", out)


# =====================================================================
# CONTRACT-15 — Control-byte freedom (regression for v0.27.2)
# =====================================================================

def test_contract_15_no_control_bytes():
    """CONTRACT-15: rendered text contains no stray control bytes (\\b, \\a, \\f, \\v)."""
    out = render()
    forbidden = {0x07, 0x08, 0x0B, 0x0C}  # bell, backspace, vtab, formfeed
    bad = [hex(b) for b in out.encode() if b in forbidden]
    assert not bad, f"Control bytes leaked into rendered block: {bad}"


def test_contract_15_multiline_continuations_intact():
    """CONTRACT-15b: bash continuation `\\\\\\n` (backslash + newline) preserved."""
    out = render()
    # At least one bash continuation must survive in the rendered shell snippets.
    assert "\\\n" in out, "Bash line-continuations were collapsed by the renderer."
