#!/usr/bin/env python3
"""Gate G04 — plugin-version-check.  Uses _lib.semver."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from semver import parse, cmp_key  # noqa: E402

GATE = "plugin-version-check"


def main() -> int:
    src = Path(os.environ["CN_SRC"])
    workspace = os.environ.get("CN_WORKSPACE", "") or None
    upgrade = os.environ.get("CN_UPGRADE", "0") == "1"
    json_out = os.environ.get("CN_JSON", "0") == "1"
    reasons: list[str] = []

    pl = src / "plugin.yaml"
    try:
        plugin = yaml.safe_load(pl.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as e:
        reasons.append(f"cannot read plugin.yaml: {e}")
        return _emit(json_out, reasons)

    ver = plugin.get("version")
    if not isinstance(ver, str):
        reasons.append("plugin.yaml.version missing or not a string")
        return _emit(json_out, reasons)

    parsed = parse(ver)
    if parsed is None:
        reasons.append(f"version {ver!r} is not valid semver")
        return _emit(json_out, reasons)

    if upgrade and workspace:
        pid = plugin.get("id")
        if isinstance(pid, str):
            installed_yaml = (
                Path(workspace) / ".codenook" / "plugins" / pid / "plugin.yaml"
            )
            if installed_yaml.is_file():
                try:
                    inst = yaml.safe_load(
                        installed_yaml.read_text(encoding="utf-8")
                    ) or {}
                except yaml.YAMLError:
                    inst = {}
                inst_ver = inst.get("version")
                inst_parsed = parse(inst_ver) if isinstance(inst_ver, str) else None
                if inst_parsed and cmp_key(parsed) <= cmp_key(inst_parsed):
                    reasons.append(
                        f"--upgrade rejected: would downgrade or no-op "
                        f"(installed={inst_ver}, new={ver})"
                    )

    return _emit(json_out, reasons)


def _emit(json_out: bool, reasons: list[str]) -> int:
    ok = not reasons
    if json_out:
        print(json.dumps({"ok": ok, "gate": GATE, "reasons": reasons}))
    else:
        for r in reasons:
            print(f"[G04] {r}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
