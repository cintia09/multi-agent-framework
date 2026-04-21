"""Unit tests for v0.23.0 slug derivation + task-id composition."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
KERNEL_LIB = REPO / "skills" / "codenook-core" / "_lib"
sys.path.insert(0, str(KERNEL_LIB))

from cli.config import compose_task_id, next_task_id, slugify  # noqa: E402


# ── slugify ────────────────────────────────────────────────────────────

def test_slugify_basic_ascii() -> None:
    assert slugify("FPGA Bounce Debug") == "fpga-bounce-debug"


def test_slugify_cjk_preserved() -> None:
    # ASCII normalisation drops CJK; we fall through to the CJK branch
    # which preserves CJK chars and lowercases the latin tail.
    assert slugify("测试hub") == "测试hub"


def test_slugify_empty_returns_empty() -> None:
    assert slugify("") == ""
    assert slugify("   ") == ""
    assert slugify("!!!@@@") == ""


def test_slugify_windows_reserved_name_guarded() -> None:
    assert slugify("CON") == "task-con"
    assert slugify("com1") == "task-com1"
    assert slugify("LPT9") == "task-lpt9"


def test_slugify_max_len_respected() -> None:
    out = slugify("a" * 100, max_len=24)
    assert len(out) <= 24


def test_slugify_snaps_to_dash_boundary() -> None:
    out = slugify("foo bar baz qux quux corge grault", max_len=24)
    # Must not end on a dangling dash and must be ≤ 24
    assert len(out) <= 24
    assert not out.endswith("-")
    # The cut should snap to a dash boundary if one is in the trailing
    # 8 chars of the 24-char window. Verify the slug terminates cleanly
    # on a word boundary, not mid-word.
    assert "-" in out
    last = out.rsplit("-", 1)[-1]
    # The last word must be one that started before max_len.
    assert last in ("foo", "bar", "baz", "qux", "quux", "corge")


def test_slugify_strip_dashes() -> None:
    assert slugify("---hello---") == "hello"
    assert slugify("__hello__") == "hello"


# ── compose_task_id ────────────────────────────────────────────────────

def test_compose_task_id_empty_slug() -> None:
    assert compose_task_id(5, "") == "T-005"


def test_compose_task_id_with_slug() -> None:
    assert compose_task_id(5, "foo") == "T-005-foo"
    assert compose_task_id(123, "fpga-bounce") == "T-123-fpga-bounce"


# ── next_task_id ───────────────────────────────────────────────────────

def test_next_task_id_skips_slugged_dirs(tmp_path: Path) -> None:
    """Slot N is occupied when either T-NNN/ or T-NNN-<slug>/ exists."""
    tasks = tmp_path / ".codenook" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "T-001").mkdir()
    (tasks / "T-002-foo").mkdir()
    assert next_task_id(tmp_path) == 3


def test_next_task_id_empty_workspace(tmp_path: Path) -> None:
    assert next_task_id(tmp_path) == 1


def test_next_task_id_only_slugged(tmp_path: Path) -> None:
    tasks = tmp_path / ".codenook" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "T-001-init").mkdir()
    (tasks / "T-002-debug-fpga").mkdir()
    assert next_task_id(tmp_path) == 3
