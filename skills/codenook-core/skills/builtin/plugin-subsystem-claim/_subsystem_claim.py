#!/usr/bin/env python3
"""Gate G07 — plugin-subsystem-claim."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

GATE = "plugin-subsystem-claim"


def load_plugin(p: Path):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return None


def main() -> int:
    src = Path(os.environ["CN_SRC"])
    workspace = os.environ.get("CN_WORKSPACE", "") or None
    upgrade = os.environ.get("CN_UPGRADE", "0") == "1"
    json_out = os.environ.get("CN_JSON", "0") == "1"
    reasons: list[str] = []

    plugin = load_plugin(src / "plugin.yaml") or {}
    pid = plugin.get("id")
    claims = plugin.get("declared_subsystems") or []
    if not isinstance(claims, list):
        reasons.append("declared_subsystems must be a list")
        return _emit(json_out, reasons)

    if not workspace:
        return _emit(json_out, reasons)

    plugins_root = Path(workspace) / ".codenook" / "plugins"
    if not plugins_root.is_dir():
        return _emit(json_out, reasons)

    # Build claim → owner map from peers.
    claim_owner: dict[str, str] = {}
    for peer_dir in sorted(plugins_root.iterdir()):
        if not peer_dir.is_dir():
            continue
        peer_yaml = peer_dir / "plugin.yaml"
        if not peer_yaml.is_file():
            continue
        peer = load_plugin(peer_yaml) or {}
        peer_id = peer.get("id") or peer_dir.name
        if peer_id == pid and upgrade:
            continue
        for c in peer.get("declared_subsystems") or []:
            if isinstance(c, str):
                claim_owner.setdefault(c, peer_id)

    for c in claims:
        if not isinstance(c, str):
            continue
        if c in claim_owner:
            reasons.append(
                f"subsystem claim {c!r} already owned by plugin {claim_owner[c]!r}"
            )

    return _emit(json_out, reasons)


def _emit(json_out: bool, reasons: list[str]) -> int:
    ok = not reasons
    if json_out:
        print(json.dumps({"ok": ok, "gate": GATE, "reasons": reasons}))
    else:
        for r in reasons:
            print(f"[G07] {r}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
