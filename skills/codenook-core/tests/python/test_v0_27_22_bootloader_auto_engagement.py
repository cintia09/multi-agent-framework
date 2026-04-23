"""v0.27.22 — bootloader auto-engagement contract.

Asserts the four-layer auto-engagement model is encoded in the
rendered CLAUDE.md template:

  Layer 1 (Awareness):       session-start ritual fires on first
                             tool call, not only on explicit mention.
  Layer 2 (Knowledge lookup): proactive `knowledge search` MUST rule
                              still present (already covered in v0.27.21).
  Layer 3 (Task recommend):   substantial requests trigger an
                              ask_user recommendation; user decides.
  Layer 4 (Inline):           trivial requests handled directly.

Plus: the old "Only when the user explicitly asks" gating wording
is gone, replaced by §Auto-engagement.
"""
from __future__ import annotations

import re
from pathlib import Path
import sys

LIB = Path(__file__).resolve().parents[2] / "skills" / "builtin" / "_lib"
sys.path.insert(0, str(LIB))

from claude_md_sync import render_block  # noqa: E402

VERSION = "0.27.22"


def render() -> str:
    return render_block(VERSION, ["development", "writing", "research"])


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) is not None


# ---------------------------------------------------------------------
# Layer 1 — awareness fires on first tool call (no explicit mention required)
# ---------------------------------------------------------------------

def test_session_start_triggers_on_first_tool_call():
    out = render()
    assert _has(out, r"first tool call")
    assert _has(out, r"\.codenook/.{0,40}exists"), \
        "ritual trigger must mention .codenook/ existence as the gate"


def test_session_start_no_longer_gated_on_explicit_mention():
    out = render()
    # The old trigger phrase must be gone from the ritual section.
    assert not _has(out, r"first time the user mentions CodeNook"), \
        "old explicit-mention trigger must be removed"


# ---------------------------------------------------------------------
# Layer 3 — substantial requests proactively recommend a task
# ---------------------------------------------------------------------

def test_auto_engagement_section_present():
    out = render()
    assert _has(out, r"###\s+Auto-engagement"), \
        "§Auto-engagement section must exist"


def test_substantial_vs_trivial_rubric():
    out = render()
    assert _has(out, r"\bsubstantial\b")
    assert _has(out, r"\btrivial\b")
    # Rubric must mention spanning multiple files / matching plugin / phases.
    assert _has(out, r"two or more files|2 files|multiple files|spans .* files")
    assert _has(out, r"match.*field|use[- ]case|keyword")
    assert _has(out, r"phase|decompose")


def test_recommendation_is_an_ask_user_with_three_choices():
    out = render()
    # The recommendation flow must offer create-task / handle-inline /
    # explain-what-it-would-do as choices to the user.
    assert _has(out, r"create a CodeNook task")
    assert _has(out, r"handle inline")
    assert _has(out, r"Explain what CodeNook would do|explain.*codenook would")


def test_proactive_recommend_hard_rule():
    out = render()
    assert _has(out, r"MUST.{0,40}proactively.{0,40}recommend"), \
        "hard rule must require proactive recommendation"


# ---------------------------------------------------------------------
# Layer 4 — trivial requests bypass task creation but still use memory
# ---------------------------------------------------------------------

def test_trivial_requests_handled_inline():
    out = render()
    assert _has(out, r"trivial.{0,200}inline|inline.{0,200}trivial")
    # Trivial requests still use proactive knowledge lookup.
    assert _has(out, r"trivial.{0,400}knowledge|knowledge.{0,400}trivial")


def test_old_explicit_only_policy_removed():
    out = render()
    assert not _has(out, r"Only when the user explicitly asks\.\s*Recognise"), \
        "the legacy 'When to start' subsection must be replaced"


# ---------------------------------------------------------------------
# Trigger phrases preserved as a fast-path
# ---------------------------------------------------------------------

def test_explicit_trigger_phrases_still_listed():
    """Even with auto-engagement, the explicit phrases remain a fast-path."""
    out = render()
    assert _has(out, r"走\s*codenook")
    assert _has(out, r"use codenook to")
