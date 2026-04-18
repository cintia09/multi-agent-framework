#!/usr/bin/env python3
"""Gate G01 — plugin-format.

Checks:
  * <src>/plugin.yaml exists at the root.
  * No symlink under <src> escapes the realpath(<src>) subtree.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

GATE = "plugin-format"


def main() -> int:
    src = Path(os.environ["CN_SRC"]).resolve()
    json_out = os.environ.get("CN_JSON", "0") == "1"
    reasons: list[str] = []

    if not (src / "plugin.yaml").is_file():
        reasons.append("missing plugin.yaml at staged root")

    src_real = str(src)
    for root, dirs, files in os.walk(src, followlinks=False):
        for name in dirs + files:
            p = Path(root) / name
            if p.is_symlink():
                target = os.readlink(p)
                # Resolve target relative to the symlink's directory.
                if os.path.isabs(target):
                    resolved = os.path.realpath(target)
                else:
                    resolved = os.path.realpath(os.path.join(root, target))
                if not (resolved == src_real or resolved.startswith(src_real + os.sep)):
                    reasons.append(
                        f"symlink escapes src tree: {p.relative_to(src)} -> {target}"
                    )

    ok = not reasons
    if json_out:
        print(json.dumps({"ok": ok, "gate": GATE, "reasons": reasons}))
    else:
        for r in reasons:
            print(f"[G01] {r}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
