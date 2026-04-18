#!/usr/bin/env python3
"""Gate G05 — plugin-signature."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

GATE = "plugin-signature"


def main() -> int:
    src = Path(os.environ["CN_SRC"])
    json_out = os.environ.get("CN_JSON", "0") == "1"
    require_sig = os.environ.get("CN_REQUIRE_SIG", "0") == "1"
    reasons: list[str] = []

    pl = src / "plugin.yaml"
    sig = src / "plugin.yaml.sig"

    if not sig.is_file():
        if require_sig:
            reasons.append(
                "CODENOOK_REQUIRE_SIG=1 but no signature file "
                "(plugin.yaml.sig) present"
            )
        return _emit(json_out, reasons)

    if not pl.is_file():
        reasons.append("plugin.yaml.sig present but plugin.yaml missing")
        return _emit(json_out, reasons)

    expected = hashlib.sha256(pl.read_bytes()).hexdigest()
    raw = sig.read_text(encoding="utf-8", errors="replace")
    token = ""
    for line in raw.splitlines():
        s = line.strip()
        if s:
            token = s.split()[0]
            break
    if not hmac.compare_digest(token.lower().encode("ascii"),
                               expected.lower().encode("ascii")):
        reasons.append(
            f"signature mismatch: expected sha256={expected}, got {token!r}"
        )

    return _emit(json_out, reasons)


def _emit(json_out: bool, reasons: list[str]) -> int:
    ok = not reasons
    if json_out:
        print(json.dumps({"ok": ok, "gate": GATE, "reasons": reasons}))
    else:
        for r in reasons:
            print(f"[G05] {r}", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
