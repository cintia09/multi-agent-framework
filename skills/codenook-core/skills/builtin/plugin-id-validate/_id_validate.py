#!/usr/bin/env python3
"""Gate G03 — plugin-id-validate."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import yaml

GATE = "plugin-id-validate"
ID_RE = re.compile(r"^[a-z][a-z0-9-]{2,30}$")
RESERVED = {"core", "builtin", "generic", "codenook"}


def main() -> int:
    src = Path(os.environ["CN_SRC"])
    workspace = os.environ.get("CN_WORKSPACE", "") or None
    upgrade = os.environ.get("CN_UPGRADE", "0") == "1"
    json_out = os.environ.get("CN_JSON", "0") == "1"
    reasons: list[str] = []

    pl = src / "plugin.yaml"
    if not pl.is_file():
        reasons.append("missing plugin.yaml at staged root")
        return _emit(json_out, reasons)

    try:
        plugin = yaml.safe_load(pl.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        reasons.append(f"plugin.yaml is not valid YAML: {e}")
        return _emit(json_out, reasons)

    pid = plugin.get("id")
    if not isinstance(pid, str) or not pid:
        reasons.append("plugin.yaml missing string field: id")
        return _emit(json_out, reasons)

    if not ID_RE.match(pid):
        reasons.append(
            f"id {pid!r} does not match ^[a-z][a-z0-9-]{{2,30}}$"
        )
    if pid in RESERVED:
        reasons.append(f"id {pid!r} is reserved (one of {sorted(RESERVED)})")

    if workspace:
        installed = Path(workspace) / ".codenook" / "plugins" / pid
        if installed.is_dir() and not upgrade:
            reasons.append(
                f"id {pid!r} already installed at {installed}; use --upgrade"
            )

    return _emit(json_out, reasons)


def _emit(json_out: bool, reasons: list[str]) -> int:
    ok = not reasons
    if json_out:
        print(json.dumps({"ok": ok, "gate": GATE, "reasons": reasons}))
    else:
        for r in reasons:
            print(f"[G03] {r}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
