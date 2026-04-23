"""Regression: ``knowledge search`` must not crash when entries carry
non-string tags (e.g. YAML hex literals like ``0x2c2000`` parsed as
``int``). Fixed in v0.27.21 by the ``[str(t) for t in ...]``
coercion in ``_lib/cli/cmd_knowledge.py``.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
_CORE = _REPO / "skills" / "codenook-core"
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))


class _Ctx:
    def __init__(self, ws: Path) -> None:
        self.workspace = ws


def _seed_plugin_knowledge(workspace: Path, plugin: str,
                           filename: str, body: str) -> None:
    kdir = workspace / ".codenook" / "plugins" / plugin / "knowledge"
    kdir.mkdir(parents=True, exist_ok=True)
    (kdir / filename).write_text(body, encoding="utf-8")


def test_hex_tag_renders_without_crash(workspace: Path, capsys):
    _seed_plugin_knowledge(
        workspace, "development", "fp.md",
        "---\n"
        "title: Fingerprint\n"
        "summary: Crash fingerprint from 0x2c2000.\n"
        "tags: [0x2c2000, memory]\n"
        "---\n"
        "Body.\n",
    )

    from _lib.cli import cmd_knowledge  # type: ignore

    rc = cmd_knowledge.run(_Ctx(workspace), ["search", "fingerprint"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Fingerprint" in out
    # A tag line must print — either the hex value (coerced to str) or
    # the sibling "memory" tag — without triggering a TypeError.
    assert "tags:" in out
