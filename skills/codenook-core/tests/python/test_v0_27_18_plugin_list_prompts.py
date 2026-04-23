"""Regression tests for v0.27.18 — plugin list + task new prompts."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
INSTALL_PY = REPO_ROOT / "install.py"


def _run(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
         stdin_data: str | None = None) -> subprocess.CompletedProcess:
    e = os.environ.copy()
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    if env:
        e.update(env)
    return subprocess.run(
        cmd, cwd=str(cwd) if cwd else None, env=e,
        text=True, capture_output=True,
        input=stdin_data,
        encoding="utf-8", errors="replace",
    )


@pytest.fixture(scope="module")
def ws(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("cn_v1728")
    cp = _run([sys.executable, str(INSTALL_PY), "--target", str(d), "--yes"])
    assert cp.returncode == 0, cp.stderr
    return d


def _bin(ws: Path) -> list[str]:
    if sys.platform == "win32":
        return [str(ws / ".codenook" / "bin" / "codenook.cmd")]
    return [sys.executable, str(ws / ".codenook" / "bin" / "codenook")]


# ---------------------------------------------------------------- plugin list

def test_plugin_list_human(ws: Path) -> None:
    cp = _run(_bin(ws) + ["plugin", "list"])
    assert cp.returncode == 0, cp.stderr
    assert "Installed plugins" in cp.stdout
    # The install bundles at least 'development', 'generic', 'writing'.
    for pid in ("development", "generic", "writing"):
        assert pid in cp.stdout, f"{pid!r} missing from plugin list output"
    # Profile chain rendering for 'development'
    assert "feature" in cp.stdout
    assert "→" in cp.stdout or "->" in cp.stdout


def test_plugin_list_json(ws: Path) -> None:
    cp = _run(_bin(ws) + ["plugin", "list", "--json"])
    assert cp.returncode == 0, cp.stderr
    data = json.loads(cp.stdout)
    assert isinstance(data, list) and len(data) >= 1
    ids = {e["id"] for e in data}
    assert "development" in ids
    dev = next(e for e in data if e["id"] == "development")
    assert dev["version"]
    assert isinstance(dev["profiles"], list)
    assert isinstance(dev["phases"], list)
    prof_names = {p["name"] for p in dev["profiles"]}
    assert "feature" in prof_names


def test_plugin_list_unknown_arg(ws: Path) -> None:
    cp = _run(_bin(ws) + ["plugin", "list", "--bogus"])
    assert cp.returncode == 2, (cp.stdout, cp.stderr)


# ---------------------------------------------------------------- task new plugin validation

def test_task_new_unknown_plugin_rejected(ws: Path) -> None:
    cp = _run(_bin(ws) + [
        "task", "new", "--title", "x", "--plugin", "does-not-exist",
        "--accept-defaults",
    ])
    assert cp.returncode == 2, (cp.stdout, cp.stderr)
    assert "not installed" in cp.stderr
    assert "available:" in cp.stderr


def test_task_new_accept_defaults_picks_first(ws: Path) -> None:
    """With --accept-defaults and multiple plugins, auto-select first
    without prompting (no interactive menu, no echo lines)."""
    cp = _run(_bin(ws) + [
        "task", "new", "--title", "accept-defaults-probe",
        "--accept-defaults",
    ])
    assert cp.returncode in (0, 1), cp.stderr
    # The auto-pick path should NOT render the menu header.
    assert "Pick one" not in cp.stdout
    # Clean up any task that got created.
    for tdir in (ws / ".codenook" / "tasks").glob("T-*-accept-defaults-probe"):
        _run(_bin(ws) + [
            "task", "delete", tdir.name, "--purge", "--yes", "--force",
        ])


def test_task_new_non_tty_auto_default(ws: Path) -> None:
    """Non-TTY stdin (pipe) → menu echoed, default auto-selected."""
    cp = _run(_bin(ws) + [
        "task", "new", "--title", "non-tty-probe",
    ], stdin_data="")
    # With a pipe, no --accept-defaults, plugin menu shown + auto-picks.
    assert "Plugin:" in cp.stdout, cp.stdout
    assert "auto-selecting default" in cp.stdout
    # Clean up.
    for tdir in (ws / ".codenook" / "tasks").glob("T-*-non-tty-probe"):
        _run(_bin(ws) + [
            "task", "delete", tdir.name, "--purge", "--yes", "--force",
        ])


def test_task_new_invalid_profile_rejected(ws: Path) -> None:
    cp = _run(_bin(ws) + [
        "task", "new", "--title", "y",
        "--plugin", "development", "--profile", "nope",
        "--accept-defaults",
    ])
    assert cp.returncode == 2, (cp.stdout, cp.stderr)
    assert "invalid --profile" in cp.stderr
    assert "valid:" in cp.stderr


# ---------------------------------------------------------------- summary + confirm (v0.27.19)

@pytest.mark.skipif(sys.platform == "win32",
                    reason="pty module is POSIX-only")
def test_task_new_tty_shows_summary_and_confirm(ws: Path) -> None:
    """Under a real TTY, a prompted task new renders Summary + confirm."""
    import pty
    import select

    pid, fd = pty.fork()
    if pid == 0:  # child
        os.execvpe(sys.executable, _bin(ws) + [
            "task", "new", "--title", "tty-confirm-probe",
        ], os.environ.copy() | {
            "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
        })
    # parent: drive the PTY
    buf = b""
    deadline = __import__("time").time() + 10.0
    sent_plugin = sent_profile = sent_confirm = False
    while __import__("time").time() < deadline:
        r, _, _ = select.select([fd], [], [], 0.25)
        if fd in r:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            buf += chunk
        # Send a newline (accept default) for each prompt.
        text = buf.decode("utf-8", errors="replace")
        if not sent_plugin and "Pick one" in text:
            os.write(fd, b"\n")
            sent_plugin = True
            buf = b""
            continue
        if sent_plugin and not sent_profile and "Pick one" in text:
            os.write(fd, b"\n")
            sent_profile = True
            buf = b""
            continue
        if sent_profile and not sent_confirm and "Create?" in text:
            os.write(fd, b"Y\n")
            sent_confirm = True
            buf = b""
            continue
        # Child exited (dual_mode entry_question → exit 2) after create.
        try:
            _, status = os.waitpid(pid, os.WNOHANG)
            if _:
                break
        except ChildProcessError:
            break

    # Drain any remaining output.
    try:
        while True:
            r, _, _ = select.select([fd], [], [], 0.25)
            if not r:
                break
            c = os.read(fd, 4096)
            if not c:
                break
            buf += c
    except OSError:
        pass
    os.close(fd)
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass

    full = buf.decode("utf-8", errors="replace")
    assert sent_plugin, f"plugin prompt never appeared; output so far:\n{full}"
    assert sent_profile, f"profile prompt never appeared; output so far:\n{full}"
    assert sent_confirm, f"Create? confirm never appeared; output so far:\n{full}"

    # Post-condition: a task dir should have been created.
    created = list(
        (ws / ".codenook" / "tasks").glob("T-*-tty-confirm-probe")
    )
    assert created, "no task dir created after TTY confirm"
    # Clean up.
    for tdir in created:
        _run(_bin(ws) + [
            "task", "delete", tdir.name, "--purge", "--yes", "--force",
        ])
