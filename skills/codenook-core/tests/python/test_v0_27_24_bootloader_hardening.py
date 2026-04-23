"""v0.27.24 — bootloader hardening (review fixes 1, 4-10, 12, 13).

Each test pins ONE concrete fix from the deep review of the
v0.27.23 workspace CLAUDE.md. Together they prove the rendered
template no longer has the contradictions / coverage gaps the
review flagged.
"""
from __future__ import annotations

import re
from pathlib import Path
import sys

LIB = Path(__file__).resolve().parents[2] / "skills" / "builtin" / "_lib"
sys.path.insert(0, str(LIB))

from claude_md_sync import render_block  # noqa: E402

VERSION = "0.27.24"


def render() -> str:
    return render_block(VERSION, ["development", "writing", "research"])


def _has(text: str, pattern: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL) is not None


# ---------------------------------------------------------------------
# Issue #1 — workflow ordering: Duplicate check BEFORE Pre-creation
# ---------------------------------------------------------------------

def test_issue1_auto_engagement_lists_duplicate_before_config():
    out = render()
    assert _has(
        out,
        r"Pick a profile.{0,30}Duplicate / parent check.{0,80}Pre-creation config ask",
    ), "auto-engagement flow must list Duplicate before Pre-creation"


def test_issue1_duplicate_section_says_before_config_ask():
    out = render()
    assert _has(
        out,
        r"Duplicate / parent check.{0,1500}before.{0,40}Pre-creation config ask",
    )


def test_issue1_pre_creation_says_after_duplicate_check():
    out = render()
    assert _has(
        out,
        r"Pre-creation config ask.{0,500}after.{0,80}Duplicate / parent check",
    )


# ---------------------------------------------------------------------
# Issue #4 — .codenook/ detection guidance
# ---------------------------------------------------------------------

def test_issue4_codenook_detection_uses_state_json():
    out = render()
    assert _has(out, r"\.codenook/state\.json.{0,200}(view|file-read|read|exists|parses)")


# ---------------------------------------------------------------------
# Issue #5 — unknown tick status fallback
# ---------------------------------------------------------------------

def test_issue5_unknown_tick_status_handled():
    out = render()
    assert _has(out, r"(any other value|other status|not in this list|future kernel).{0,300}(stop|surface|ask)")


# ---------------------------------------------------------------------
# Issue #6 — missing/empty index.yaml
# ---------------------------------------------------------------------

def test_issue6_missing_index_yaml_handled():
    out = render()
    assert _has(out, r"(missing|empty|fails to parse).{0,200}index\.yaml|index\.yaml.{0,200}(missing|empty|fails to parse)")


# ---------------------------------------------------------------------
# Issue #7 — "you" ambiguity in role/phase prompt restriction
# ---------------------------------------------------------------------

def test_issue7_inline_exception_documented():
    out = render()
    # Must explicitly carve out the inline-execution case.
    assert _has(out, r"Exception.{0,800}(clarifier|inline).{0,800}follow")
    assert _has(out, r"conductor mode")


# ---------------------------------------------------------------------
# Issue #8 — no-plugin / weak-match fallback
# ---------------------------------------------------------------------

def test_issue8_zero_plugins_fallback():
    out = render()
    assert _has(out, r"(zero plugins|no plugins (are )?(installed|present))")


def test_issue8_weak_match_acknowledged():
    out = render()
    assert _has(out, r"(weak match|none match well|all .* score < 0\.\d|no match.*overlap)")


# ---------------------------------------------------------------------
# Issue #9 — multiple HITL gates resolved serially
# ---------------------------------------------------------------------

def test_issue9_multiple_gates_serial():
    out = render()
    assert _has(out, r"multiple gates.{0,400}serial")
    assert _has(out, r"never batch|do not batch|never call .decide. for more than one gate")


# ---------------------------------------------------------------------
# Issue #10 — knowledge search vs cached index.yaml
# ---------------------------------------------------------------------

def test_issue10_search_vs_cached_disambiguated():
    out = render()
    # Section must explicitly describe both paths and when to use each.
    assert _has(out, r"cached.{0,80}index\.yaml|index\.yaml.{0,80}cached")
    assert _has(out, r"(when in doubt|trivial single-topic).{0,200}knowledge search")


# ---------------------------------------------------------------------
# Issue #12 — model verbatim vs omit-when-empty
# ---------------------------------------------------------------------

def test_issue12_model_verbatim_scope_clarified():
    out = render()
    # The hard rule must say: verbatim WHEN non-empty; omit when empty.
    assert _has(out, r"non-empty.{0,300}absent.{0,200}empty.{0,200}omit")


# ---------------------------------------------------------------------
# Issue #13 — _pending/ is extractor-only, not searched
# ---------------------------------------------------------------------

def test_issue13_pending_is_extractor_staging():
    out = render()
    # Three independent assertions — the layout-table mention of `_pending/`
    # confounds positional regexes, so just check the substantive wording exists.
    assert _has(out, r"extractor staging area")
    assert _has(out, r"NOT.{0,40}searched by.{0,40}knowledge search|NOT in .index\.yaml")
    assert _has(out, r"memory/knowledge/<slug>/index\.md")
    assert _has(out, r"flat\s+.?<slug>\.md.?\s+(file\s+)?is\s+silently\s+ignored")
    assert _has(out, r"Do not write hand-authored\s+notes to .?_pending"), \
        "must explicitly forbid manual writes to _pending/"
