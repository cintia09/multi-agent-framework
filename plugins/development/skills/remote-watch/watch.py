#!/usr/bin/env python3
"""remote-watch/watch.py — generic three-tier remote review/CI poller.

Knows nothing system-specific; specifics live in memory or come via
--config. Spec: see SKILL.md.

The --config file is sourced as a Python module (NOT shell). Trust
boundary documented in SKILL.md §Threat model. It must define a module-
level variable PROBE_CMD: str (shell command emitting the probe output);
it MAY define STATUS_REGEX_MERGED, STATUS_REGEX_REJECTED,
STATUS_REGEX_PENDING (default ".*").

Exit codes:
  0  classified status emitted
  2  probe failed (network / auth / missing CLI) — status=unknown emitted
  3  needs_user_config (no recognised tier-1, no --config) — caller asks user
"""
from __future__ import annotations

import argparse
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path


def _print_help_from_skill_md(here: Path) -> None:
    sm = here / "SKILL.md"
    if sm.is_file():
        with sm.open() as fh:
            for i, line in enumerate(fh):
                if i >= 80:
                    break
                sys.stdout.write(line)


def _emit(json_out: bool, *, status: str, source: str, raw: str, hint: str,
          needs_user_config: bool = False) -> None:
    if json_out:
        out = {"status": status, "source": source, "raw": raw,
               "memory_search_hint": hint}
        if needs_user_config:
            out["needs_user_config"] = True
        print(json.dumps(out))
    else:
        print(f"status: {status}")
        print(f"source: {source}")
        print(f"memory_search_hint: {hint}")
        if needs_user_config:
            print("needs_user_config: true")
        if raw:
            print("raw:")
            print(raw)


def _classify(out: str, mre: str, rre: str, pre: str) -> str:
    if mre and re.search(mre, out):
        return "merged"
    if rre and re.search(rre, out):
        return "rejected"
    if pre and re.search(pre, out):
        return "pending"
    return "unknown"


def _run_probe(cmd: str, env_extra: dict[str, str]) -> tuple[int, str]:
    env = os.environ.copy()
    env.update(env_extra)
    proc = subprocess.run(
        cmd, shell=True, env=env, check=False,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )
    return proc.returncode, (proc.stdout or "")


def _load_config(path: Path) -> dict:
    try:
        ns = runpy.run_path(str(path), run_name="<watch-config>")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"watch.py: --config failed to load: {exc}") from exc
    return {
        "PROBE_CMD":             ns.get("PROBE_CMD", ""),
        "STATUS_REGEX_MERGED":   ns.get("STATUS_REGEX_MERGED", ""),
        "STATUS_REGEX_REJECTED": ns.get("STATUS_REGEX_REJECTED", ""),
        "STATUS_REGEX_PENDING":  ns.get("STATUS_REGEX_PENDING", ".*"),
    }


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(prog="watch.py", add_help=False)
    p.add_argument("--target-dir", dest="target", default=None)
    p.add_argument("--ref",        dest="ref",    default="")
    p.add_argument("--config",     dest="config", default=None)
    p.add_argument("--json",       dest="json_out", action="store_true")
    p.add_argument("-h", "--help", action="store_true")
    try:
        args = p.parse_args(argv)
    except SystemExit:
        return 2

    if args.help:
        _print_help_from_skill_md(here)
        return 0
    if not args.target:
        print("watch.py: --target-dir required", file=sys.stderr)
        return 2

    target = Path(args.target)
    if not target.is_dir():
        print(f"watch.py: target dir not found: {target}", file=sys.stderr)
        return 2

    hint_base = os.path.basename(target.resolve())
    hint = f"remote-watch-config target={hint_base}"
    env_extra = {"REF": args.ref or "", "TARGET": str(target)}

    # tier 2: --config wins
    if args.config:
        cpath = Path(args.config)
        if not cpath.is_file() or not os.access(cpath, os.R_OK):
            print(f"watch.py: --config not readable: {cpath}", file=sys.stderr)
            return 2
        cfg = _load_config(cpath)
        if not cfg["PROBE_CMD"]:
            print("watch.py: config did not set PROBE_CMD", file=sys.stderr)
            return 2
        rc, out = _run_probe(cfg["PROBE_CMD"], env_extra)
        if rc != 0:
            _emit(args.json_out, status="unknown", source="tier2-config",
                  raw=out, hint=hint)
            return 2
        status = _classify(out, cfg["STATUS_REGEX_MERGED"],
                           cfg["STATUS_REGEX_REJECTED"],
                           cfg["STATUS_REGEX_PENDING"])
        _emit(args.json_out, status=status, source="tier2-config",
              raw=out, hint=hint)
        return 0

    # tier 1a: GitHub PR (gh CLI present + .github/ in target + ref given)
    if (target / ".github").is_dir() and shutil.which("gh") and args.ref:
        cmd = f"gh pr view {shlex_quote(args.ref)} --json state,mergedAt"
        rc, out = _run_probe(cmd, env_extra)
        if rc != 0:
            _emit(args.json_out, status="unknown", source="tier1-github",
                  raw=out, hint=hint)
            return 2
        status = _classify(out, r'"state":"MERGED"',
                           r'"state":"CLOSED"', r'"state":"OPEN"')
        _emit(args.json_out, status=status, source="tier1-github",
              raw=out, hint=hint)
        return 0

    # tier 1b: Gerrit (.gerrit marker + recorded host + ref given)
    gerrit_marker = target / ".gerrit"
    if gerrit_marker.exists() and args.ref:
        try:
            host = gerrit_marker.read_text().splitlines()[0].strip()
        except (OSError, IndexError):
            host = ""
        if host and shutil.which("ssh"):
            cmd = (f"ssh -o BatchMode=yes {shlex_quote(host)} "
                   f"gerrit query --format=JSON change:{shlex_quote(args.ref)}")
            rc, out = _run_probe(cmd, env_extra)
            if rc != 0:
                _emit(args.json_out, status="unknown", source="tier1-gerrit",
                      raw=out, hint=hint)
                return 2
            status = _classify(out, r'"status":"MERGED"',
                               r'"status":"ABANDONED"',
                               r'"status":"NEW"|"status":"DRAFT"')
            _emit(args.json_out, status=status, source="tier1-gerrit",
                  raw=out, hint=hint)
            return 0

    # tier 3: needs_user_config
    _emit(args.json_out, status="unknown", source="none", raw="",
          hint=hint, needs_user_config=True)
    return 3


def shlex_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


if __name__ == "__main__":
    sys.exit(main())
