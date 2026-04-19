"""Read/write helpers for tasks/<tid>/router-context.md.

The file format is YAML frontmatter (between two `---` lines) followed
by a markdown chat body of alternating

    ### user (<iso8601>)
    <free-form markdown>

    ### router (<iso8601>)
    <free-form markdown>

blocks. See docs/v6/router-agent-v6.md §4.1 for the canonical spec.

This module is pure-Python (yaml + stdlib only) and re-uses
`atomic.py` for crash-safe writes. It deliberately does NOT import the
M5 config-validate skill (which is a sub-process boundary): a small
in-tree validator covers the M8 frontmatter shape.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml


class _NoDatetimeLoader(yaml.SafeLoader):
    """SafeLoader variant that keeps ISO-8601 timestamps as raw strings.

    Default PyYAML eagerly resolves things like `2026-05-12T10:11:00Z`
    into `datetime.datetime`, which then breaks our `isinstance(..., str)`
    checks against the frontmatter schema. We strip the implicit
    `tag:yaml.org,2002:timestamp` resolver so timestamps round-trip as
    strings — matching the §4.1 spec.
    """


_NoDatetimeLoader.yaml_implicit_resolvers = {
    k: [(tag, regexp) for tag, regexp in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
from atomic import atomic_write_json  # noqa: E402  (re-used for tempfile pattern)

CONTEXT_FILENAME = "router-context.md"
SCHEMA_PATH = (
    _HERE.parent
    / "router-agent"
    / "schemas"
    / "router-context.frontmatter.yaml"
)

_TASK_ID_RE = re.compile(r"^T-[A-Z0-9.\-]+$")
_HEADING_RE = re.compile(r"^###\s+(user|router)\s+\(([^)]+)\)\s*$")
_VALID_STATES = ("drafting", "confirmed", "cancelled")
_VALID_ROLES = ("user", "router")
_REQUIRED_KEYS = (
    "task_id",
    "created_at",
    "started_at",
    "state",
    "turn_count",
    "draft_config_path",
    "selected_plugin",
    "decisions",
)


# ---------------------------------------------------------------- helpers


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _validate_frontmatter(fm: dict) -> None:
    if not isinstance(fm, dict):
        raise ValueError("frontmatter must be a mapping")
    for k in _REQUIRED_KEYS:
        if k not in fm:
            raise ValueError(f"frontmatter missing required key: {k!r}")

    tid = fm["task_id"]
    if not isinstance(tid, str) or not _TASK_ID_RE.match(tid):
        raise ValueError(f"task_id {tid!r} does not match ^T-[A-Z0-9.-]+$")

    for ts_key in ("created_at", "started_at"):
        if not isinstance(fm[ts_key], str) or not fm[ts_key]:
            raise ValueError(f"{ts_key} must be a non-empty string")

    if fm["state"] not in _VALID_STATES:
        raise ValueError(
            f"state {fm['state']!r} not in {list(_VALID_STATES)}"
        )

    tc = fm["turn_count"]
    if isinstance(tc, bool) or not isinstance(tc, int) or tc < 0:
        raise ValueError(f"turn_count must be int >= 0, got {tc!r}")

    dcp = fm["draft_config_path"]
    if dcp is not None and not isinstance(dcp, str):
        raise ValueError("draft_config_path must be a string or null")

    sp = fm["selected_plugin"]
    if sp is not None and not isinstance(sp, str):
        raise ValueError("selected_plugin must be a string or null")

    decisions = fm["decisions"]
    if not isinstance(decisions, list):
        raise ValueError("decisions must be a list")
    for i, d in enumerate(decisions):
        if not isinstance(d, dict):
            raise ValueError(f"decisions[{i}] must be a mapping")
        for need in ("ts", "kind"):
            if need not in d:
                raise ValueError(
                    f"decisions[{i}] missing required key: {need!r}"
                )

    lra = fm.get("last_router_action")
    if lra is not None and lra not in ("reply", "handoff", "cancelled"):
        raise ValueError(
            f"last_router_action {lra!r} not in [reply, handoff, cancelled]"
        )


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("router-context.md missing leading '---'")
    # tolerant of CRLF & trailing whitespace on the marker line
    parts = text.split("\n", 1)
    if len(parts) != 2:
        raise ValueError("router-context.md truncated after opening '---'")
    rest = parts[1]
    end = rest.find("\n---")
    if end == -1:
        raise ValueError("router-context.md missing closing '---'")
    fm_text = rest[:end]
    body = rest[end + len("\n---"):]
    # strip a single leading newline after closing marker
    if body.startswith("\n"):
        body = body[1:]
    fm = yaml.load(fm_text, Loader=_NoDatetimeLoader) or {}
    if not isinstance(fm, dict):
        raise ValueError("frontmatter is not a YAML mapping")
    return fm, body


def _parse_body(body: str) -> list[dict]:
    """Parse alternating ### user / ### router blocks. Lenient on
    trailing whitespace; strict on heading shape."""
    turns: list[dict] = []
    current: dict | None = None
    buf: list[str] = []
    for raw in body.splitlines():
        m = _HEADING_RE.match(raw)
        if m:
            if current is not None:
                current["content"] = "\n".join(buf).strip("\n")
                turns.append(current)
            role, ts = m.group(1), m.group(2).strip()
            if role not in _VALID_ROLES:
                raise ValueError(f"unexpected role {role!r}")
            current = {"role": role, "timestamp": ts, "content": ""}
            buf = []
        else:
            if current is None:
                # ignore preamble whitespace before the first heading
                if raw.strip():
                    raise ValueError(
                        f"content before first heading: {raw!r}"
                    )
                continue
            buf.append(raw)
    if current is not None:
        current["content"] = "\n".join(buf).strip("\n")
        turns.append(current)
    return turns


def _render_body(turns: Iterable[dict]) -> str:
    out: list[str] = []
    for t in turns:
        role = t["role"]
        ts = t["timestamp"]
        if role not in _VALID_ROLES:
            raise ValueError(f"turn role {role!r} not in {list(_VALID_ROLES)}")
        out.append(f"### {role} ({ts})")
        out.append("")
        content = (t.get("content") or "").rstrip()
        out.append(content)
        out.append("")  # blank line between blocks
    return "\n".join(out).rstrip() + "\n"


def _atomic_write_text(path: Path, text: str) -> None:
    """Same temp-then-rename pattern as atomic.py, for text files."""
    import tempfile

    d = path.parent
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".rctx-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------- API


def initial_context(
    task_id: str,
    user_input: str,
    *,
    now: str | None = None,
) -> tuple[dict, list[dict]]:
    """Pure helper: frontmatter + first user turn for a brand-new task."""
    ts = now or _utcnow()
    fm = {
        "task_id": task_id,
        "created_at": ts,
        "started_at": ts,
        "state": "drafting",
        "turn_count": 1,
        "draft_config_path": None,
        "selected_plugin": None,
        "decisions": [],
        "last_router_action": None,
    }
    _validate_frontmatter(fm)
    turns = [
        {"role": "user", "timestamp": ts, "content": user_input.rstrip()}
    ]
    return fm, turns


def read_context(task_dir: Path) -> dict:
    p = Path(task_dir) / CONTEXT_FILENAME
    text = p.read_text(encoding="utf-8")
    fm, body = _split_frontmatter(text)
    _validate_frontmatter(fm)
    turns = _parse_body(body)
    return {"frontmatter": fm, "turns": turns}


def write_context(
    task_dir: Path,
    frontmatter: dict,
    turns: list[dict],
) -> None:
    _validate_frontmatter(frontmatter)
    fm_text = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    ).rstrip() + "\n"
    body = _render_body(turns) if turns else ""
    blob = "---\n" + fm_text + "---\n\n" + body
    _atomic_write_text(Path(task_dir) / CONTEXT_FILENAME, blob)


def append_turn(
    task_dir: Path,
    role: str,
    content: str,
    timestamp: str | None = None,
) -> None:
    if role not in _VALID_ROLES:
        raise ValueError(f"role {role!r} not in {list(_VALID_ROLES)}")
    ctx = read_context(task_dir)
    fm = ctx["frontmatter"]
    turns = ctx["turns"]
    ts = timestamp or _utcnow()
    turns.append({"role": role, "timestamp": ts, "content": content.rstrip()})
    if role == "user":
        fm["turn_count"] = int(fm.get("turn_count", 0)) + 1
    write_context(task_dir, fm, turns)


def update_frontmatter(task_dir: Path, **kwargs: Any) -> None:
    ctx = read_context(task_dir)
    fm = ctx["frontmatter"]
    fm.update(kwargs)
    write_context(task_dir, fm, ctx["turns"])


__all__ = [
    "initial_context",
    "read_context",
    "write_context",
    "append_turn",
    "update_frontmatter",
    "CONTEXT_FILENAME",
    "SCHEMA_PATH",
]


# Avoid an unused-import warning while keeping atomic_write_json
# importable from this module for downstream helpers.
_ = atomic_write_json
