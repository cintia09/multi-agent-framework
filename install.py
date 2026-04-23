#!/usr/bin/env python3
"""CodeNook v0.15.0 installer entry point.

Replaces the legacy ``install.sh`` (kept as ``install.sh.legacy`` for
one release). Surface:

  python install.py [--target <workspace>] [--upgrade] [--plugin <id|all>]
                    [--no-claude-md] [--yes] [--check] [--dry-run] [--help]

Exit codes:
  0  installed (or dry-run pass / check ok)
  1  any gate failed
  2  usage / IO error
  3  already installed (without --upgrade)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

VERSION = "0.27.21"

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE / "skills" / "codenook-core"))

from _lib.install.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
