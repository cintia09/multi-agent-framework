#!/usr/bin/env python3
"""test-runner/runner.py — workspace-agnostic test dispatcher.

v0.4.1 — three-tier lookup (rewrite of v0.4.0 runner.sh):

  1. Marker detection inside <target-dir> (pyproject.toml / package.json
     / go.mod) → run the recognised local runner.
  2. When markers fail OR --config <path> is provided, source the
     command + verdict-criterion from a workspace-supplied config
     (typically resolved from memory by the role calling this skill —
     e.g. `<codenook> knowledge search "test-runner-config target=foo"`).
  3. When neither yields a runnable command, emit a JSON envelope
     flagged "needs_user_config":true and exit code 3 — the calling
     role (tester / test-planner) is then expected to ask the user
     via HITL and either pass --config back into the next call or
     promote the answer into memory for future reuse.

This script never hard-codes device / simulator semantics: ADB, QEMU,
SSH-into-board, JTAG fixtures, etc. all flow through tier 2 (a config
describing the command line + pass criterion). The user's environment
is the source of truth, asked once and remembered via memory.

Spec: see SKILL.md in this directory.

The --config file is sourced as a Python module (NOT shell). Trust
boundary documented in SKILL.md §Threat model. It must define a module-
level variable TEST_CMD: str (full command line); it MAY define
TEST_LABEL: str = "custom" and PASS_CRITERION: str = "exit0" or
"regex:<pattern>".

Exit codes:
  0  pass
  1  test command failed
  2  usage / config error
  3  no runnable command (needs_user_config) — caller should ask user
"""
from __future__ import annotations

import argparse
import json
import os
import re
import runpy
import shlex
import subprocess
import sys
import time
from pathlib import Path


def _print_help_from_skill_md(here: Path) -> None:
    sm = here / "SKILL.md"
    if sm.is_file():
        with sm.open() as fh:
            for i, line in enumerate(fh):
                if i >= 80:
                    break
                sys.stdout.write(line)


def _emit(json_out: bool, **kv) -> None:
    if json_out:
        print(json.dumps(kv))


def _detect_marker_runner(target: Path) -> str:
    pyfiles = ("pyproject.toml", "setup.py", "pytest.ini", "tox.ini")
    if any((target / f).is_file() for f in pyfiles):
        return "pytest"
    if (target / "package.json").is_file():
        return "npm"
    if (target / "go.mod").is_file():
        return "go"
    return "none"


def _run_marker(runner: str, target: Path) -> tuple[int, str]:
    if runner == "pytest":
        cmd = ["pytest", "-q"]
    elif runner == "npm":
        cmd = ["npm", "test", "--silent"]
    elif runner == "go":
        cmd = ["go", "test", "./..."]
    else:
        return 2, f"unknown marker runner: {runner}"
    try:
        rc = subprocess.run(cmd, cwd=str(target), check=False).returncode
    except FileNotFoundError:
        return 2, f"{runner} not installed"
    return rc, ""


def _load_config(path: Path) -> dict:
    """Source --config as a Python module; return a dict of allowed keys."""
    try:
        ns = runpy.run_path(str(path), run_name="<runner-config>")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"runner.py: --config failed to load: {exc}") from exc
    return {
        "TEST_CMD":       ns.get("TEST_CMD", ""),
        "TEST_LABEL":     ns.get("TEST_LABEL", "custom"),
        "PASS_CRITERION": ns.get("PASS_CRITERION", "exit0"),
    }


def _run_config(cfg: dict, target: Path) -> int:
    cmd_str: str = cfg["TEST_CMD"]
    pc: str = cfg["PASS_CRITERION"]
    if pc == "exit0":
        rc = subprocess.run(cmd_str, cwd=str(target), shell=True, check=False).returncode
        return rc
    elif pc.startswith("regex:"):
        pat = pc[len("regex:"):]
        proc = subprocess.run(
            cmd_str,
            cwd=str(target),
            shell=True,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        sys.stderr.write(proc.stdout or "")
        return 0 if re.search(pat, proc.stdout or "") else 1
    else:
        sys.stderr.write(f"runner.py: unknown PASS_CRITERION '{pc}'\n")
        return 2


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    p = argparse.ArgumentParser(prog="runner.py", add_help=False)
    p.add_argument("--target-dir", dest="target", default=None)
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
        print("runner.py: --target-dir required", file=sys.stderr)
        return 2

    target = Path(args.target)
    if not target.is_dir():
        print(f"runner.py: target dir not found: {target}", file=sys.stderr)
        return 2

    start_ms = int(time.time() * 1000)

    # tier 2: --config wins
    if args.config:
        cpath = Path(args.config)
        if not cpath.is_file():
            print(f"runner.py: --config not found: {cpath}", file=sys.stderr)
            return 2
        cfg = _load_config(cpath)
        if not cfg["TEST_CMD"]:
            print("runner.py: --config did not define TEST_CMD", file=sys.stderr)
            return 2
        rc = _run_config(cfg, target)
        dur = int(time.time() * 1000) - start_ms
        _emit(
            args.json_out,
            ok=(rc == 0),
            runner=cfg["TEST_LABEL"],
            exit_code=rc,
            duration_ms=dur,
            source="config",
        )
        return rc

    # tier 1: marker-based local runner
    runner = _detect_marker_runner(target)
    if runner == "none":
        # tier 3: needs_user_config
        dur = int(time.time() * 1000) - start_ms
        _emit(
            args.json_out,
            ok=False,
            runner="none",
            exit_code=3,
            duration_ms=dur,
            source="none",
            needs_user_config=True,
        )
        sys.stderr.write(
            f'runner.py: no recognised runner inside "{target}" (no '
            f"pyproject.toml / package.json / go.mod) and no --config was supplied.\n"
            "The calling role should:\n"
            "  1. Search memory:\n"
            f'       <codenook> knowledge search "test-runner-config target={target.name}"\n'
            '       <codenook> knowledge search "test-environment <repo or device hint>"\n'
            "  2. If a memory entry is found, write its TEST_CMD + PASS_CRITERION\n"
            "     to a temp .py file and re-invoke with --config <file>.\n"
            "  3. Otherwise, ask the user (via HITL ask_user) for:\n"
            '       - the test command line (e.g. "ssh dut@10.0.0.5 \'pytest /opt/app\'")\n'
            '       - the pass criterion ("exit0" or "regex:<pattern>")\n'
            "     Optionally promote the answer to\n"
            "     .codenook/memory/knowledge/test-runner-config-<slug>/index.md so\n"
            "     the next run finds it without asking.\n"
        )
        return 3

    rc, err = _run_marker(runner, target)
    dur = int(time.time() * 1000) - start_ms
    if err:
        sys.stderr.write(f"runner.py: {err}\n")
    _emit(
        args.json_out,
        ok=(rc == 0),
        runner=runner,
        exit_code=rc,
        duration_ms=dur,
        source="marker",
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
