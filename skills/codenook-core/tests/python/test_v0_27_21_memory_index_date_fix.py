"""Regression: ``memory_index.build_index`` must not crash when a
knowledge file's frontmatter contains a YAML-native ``date`` value
(e.g. ``created: 2026-04-22``). Before v0.27.21 the snapshot writer
raised ``TypeError: Object of type date is not JSON serializable``,
and ``full_index._scan_memory`` swallowed it — making every memory
entry invisible to ``knowledge search`` and ``index.yaml``.
"""
from __future__ import annotations

from pathlib import Path

import memory_index


def test_date_frontmatter_does_not_crash_build_index(workspace: Path):
    kdir = workspace / ".codenook" / "memory" / "knowledge"
    kdir.mkdir(parents=True, exist_ok=True)
    (kdir / "dated.md").write_text(
        "---\n"
        "title: Dated note\n"
        "summary: Contains a raw YAML date.\n"
        "tags: [ops]\n"
        "created: 2026-04-22\n"
        "---\n"
        "Body.\n",
        encoding="utf-8",
    )

    # Must not raise.
    idx = memory_index.build_index(workspace)
    paths = [m.get("path") for m in idx.get("knowledge", [])]
    assert any(str(p).endswith("dated.md") for p in paths)

    # Second call uses the on-disk snapshot — must also not crash.
    idx2 = memory_index.build_index(workspace)
    paths2 = [m.get("path") for m in idx2.get("knowledge", [])]
    assert any(str(p).endswith("dated.md") for p in paths2)
