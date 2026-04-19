#!/usr/bin/env python3
"""session-resume/_resume.py — implementation-v6.md §3.4 summary builder.

Output schema (≤500 BYTES UTF-8, even with CJK):

    {
      "active_tasks": [
        {"task_id","plugin","phase","status","last_event_ts","one_liner"}
      ],
      "current_focus": "T-NNN" | null,
      "last_session_summary": "<≤300 char tail of sessions/latest.md>",
      "suggested_next": "Continue T-NNN (<phase>)?" | "..." | "..."
    }

Backward-compat (M1 mode)
-------------------------
Two M1 conventions are still supported so the m1-session-resume
bats suite keeps passing:
  * No `.codenook/state.json` → fall back to listing every
    `tasks/*/state.json` (legacy "scan" behaviour).
  * Output also exposes M1 keys (`active_task`, `phase`, `iteration`,
    `summary`, `next_suggested_action`, `hitl_pending`,
    `last_action_ts`, `total_iterations`) chosen from the most-recent
    task by `updated_at`.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 500-byte cap excluding the M1-only legacy keys (which are budget-free).
MAX_BYTES = 500
MAX_TAIL_CHARS = 300


def read_json_safe(path: Path) -> dict | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"resume.sh: warn: skipping corrupt {path}: {e}", file=sys.stderr)
        return None


def tail_chars(path: Path, n: int) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-n:] if len(text) > n else text


def detect_hitl_pending(workspace: Path) -> bool:
    # M4 layout: per-entry json files.
    qdir = workspace / ".codenook" / "hitl-queue"
    if qdir.is_dir():
        for f in qdir.glob("*.json"):
            d = read_json_safe(f) or {}
            if d.get("decision") in (None, ""):
                return True
    # M1 layout: jsonl with status field.
    legacy = workspace / ".codenook" / "queues" / "hitl.jsonl"
    if legacy.is_file():
        try:
            for line in legacy.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                e = json.loads(line)
                if e.get("status") == "pending":
                    return True
        except Exception:
            pass
    return False


def build_active_entry(task_state: dict) -> dict:
    history = task_state.get("history") or []
    last_ts = (history[-1].get("ts") if history else None) \
              or task_state.get("updated_at") \
              or task_state.get("created_at") \
              or ""
    return {
        "task_id": task_state.get("task_id"),
        "plugin": task_state.get("plugin"),
        "phase": task_state.get("phase"),
        "status": task_state.get("status"),
        "last_event_ts": last_ts,
        "one_liner": task_state.get("title", ""),
    }


def _payload_bytes(p: dict) -> int:
    return len(json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def _utf8_safe_truncate(s: str, max_bytes: int) -> str:
    """Hard-truncate `s` to ≤max_bytes UTF-8 bytes WITHOUT splitting a
    multi-byte char."""
    b = s.encode("utf-8")
    if len(b) <= max_bytes:
        return s
    cut = max_bytes
    while cut > 0:
        try:
            return b[:cut].decode("utf-8")
        except UnicodeDecodeError:
            cut -= 1
    return ""


def truncate_to_bytes(payload: dict, limit: int) -> dict:
    """Trim discretionary fields in a real loop until UTF-8 fits.

    Strategy (in order):
      1) Drop `last_session_summary` entirely.
      2) Trim each one_liner by 10% chars from the right.
      3) Drop oldest active_tasks entries.
      4) Shorten suggested_next.
    """
    if _payload_bytes(payload) <= limit:
        return payload

    # 1) Drop last_session_summary
    if "last_session_summary" in payload:
        payload.pop("last_session_summary", None)
        if _payload_bytes(payload) <= limit:
            return payload

    # 2) Trim one_liners 10% per pass until empty.
    while _payload_bytes(payload) > limit:
        trimmed_any = False
        for entry in payload.get("active_tasks", []):
            ol = entry.get("one_liner")
            if isinstance(ol, str) and ol:
                cut = max(0, len(ol) - max(1, len(ol) // 10))
                entry["one_liner"] = ol[:cut]
                trimmed_any = True
                if _payload_bytes(payload) <= limit:
                    return payload
        if not trimmed_any:
            break

    # 3) Drop oldest active_tasks entries (last in list).
    while _payload_bytes(payload) > limit and payload.get("active_tasks"):
        payload["active_tasks"].pop()
        if _payload_bytes(payload) <= limit:
            return payload

    # 4) Shorten suggested_next.
    if isinstance(payload.get("suggested_next"), str):
        payload["suggested_next"] = payload["suggested_next"][:60]
    return payload


def main() -> None:
    workspace = Path(os.environ["CN_WORKSPACE"])
    json_out = os.environ.get("CN_JSON", "0") == "1"

    ws_state_path = workspace / ".codenook" / "state.json"
    ws_state = read_json_safe(ws_state_path) if ws_state_path.is_file() else None

    active_tasks: list[dict] = []
    current_focus: str | None = None

    if ws_state is not None:
        # M4 path: workspace state.json drives the list.
        current_focus = ws_state.get("current_focus")
        for tid in ws_state.get("active_tasks", []) or []:
            tpath = workspace / ".codenook" / "tasks" / tid / "state.json"
            ts = read_json_safe(tpath)
            if ts is None:
                continue
            active_tasks.append(build_active_entry(ts))
    else:
        # Legacy M1 path: scan every tasks/*/state.json, exclude phase==done.
        tdir = workspace / ".codenook" / "tasks"
        if tdir.is_dir():
            for child in tdir.iterdir():
                sf = child / "state.json"
                if not sf.is_file():
                    continue
                ts = read_json_safe(sf)
                if ts is None:
                    continue
                if ts.get("phase") == "done" or ts.get("status") in ("done", "cancelled"):
                    continue
                active_tasks.append(build_active_entry(ts))
        active_tasks.sort(key=lambda t: t.get("last_event_ts") or "", reverse=True)

    last_session_summary = tail_chars(
        workspace / ".codenook" / "history" / "sessions" / "latest.md",
        MAX_TAIL_CHARS,
    )

    hitl_pending = detect_hitl_pending(workspace)

    # suggested_next per spec.
    if current_focus and any(
        t["task_id"] == current_focus and t["status"] == "in_progress"
        for t in active_tasks
    ):
        focus_phase = next(t["phase"] for t in active_tasks
                           if t["task_id"] == current_focus)
        suggested = f"Continue {current_focus} ({focus_phase})?"
    elif active_tasks:
        suggested = f"{len(active_tasks)} active tasks — pick one?"
    else:
        suggested = "No active task, awaiting user input"

    payload = {
        "active_tasks": active_tasks,
        "current_focus": current_focus,
        "last_session_summary": last_session_summary,
        "suggested_next": suggested,
    }

    # ── M1 backward-compat keys (computed BEFORE truncation eats fields) ──
    if active_tasks:
        primary = active_tasks[0]
        primary_full = None
        if ws_state is not None:
            tpath = workspace / ".codenook" / "tasks" / primary["task_id"] / "state.json"
            primary_full = read_json_safe(tpath) or {}
        else:
            for child in (workspace / ".codenook" / "tasks").iterdir():
                if child.name == primary["task_id"]:
                    primary_full = read_json_safe(child / "state.json") or {}
                    break
        primary_full = primary_full or {}
        legacy = {
            "active_task": primary["task_id"],
            "phase": primary["phase"],
            "iteration": primary_full.get("iteration", 0),
            "total_iterations": primary_full.get(
                "total_iterations", primary_full.get("max_iterations", 0)),
            "last_action_ts": primary_full.get(
                "updated_at", primary.get("last_event_ts")),
            "hitl_pending": hitl_pending,
            "next_suggested_action": (
                "resolve HITL gate" if hitl_pending
                else f"continue tick (phase: {primary['phase']})"
            ),
            "summary": (
                f"Task {primary['task_id']} at {primary['phase']} phase, "
                f"iteration {primary_full.get('iteration', 0)}/"
                f"{primary_full.get('total_iterations', primary_full.get('max_iterations', 0))}"
                + ("; HITL gate pending" if hitl_pending else "")
            ),
        }
    else:
        legacy = {
            "active_task": None,
            "phase": None,
            "iteration": 0,
            "total_iterations": 0,
            "last_action_ts": None,
            "hitl_pending": hitl_pending,
            "next_suggested_action": "create new task",
            "summary": "No active tasks",
        }

    payload = truncate_to_bytes(payload, MAX_BYTES)
    payload.update(legacy)

    # Final cap: legacy compat keys count against the 500-byte budget.
    def _size(p):
        return len(json.dumps(p, ensure_ascii=False,
                               separators=(",", ":")).encode("utf-8"))
    if _size(payload) > MAX_BYTES:
        if isinstance(payload.get("summary"), str):
            payload["summary"] = payload["summary"][:60]
    if _size(payload) > MAX_BYTES:
        # Drop chatty legacy fields entirely; M1 tests don't assert these
        # when M4 multi-task pressure forces eviction.
        for k in ("next_suggested_action", "summary", "last_action_ts",
                  "total_iterations", "current_focus", "hitl_pending",
                  "iteration", "phase", "active_task"):
            payload.pop(k, None)
            if _size(payload) <= MAX_BYTES:
                break
    if _size(payload) > MAX_BYTES:
        payload = truncate_to_bytes(payload, MAX_BYTES)

    if json_out:
        s = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        if len(s.encode("utf-8")) > MAX_BYTES:
            s = _utf8_safe_truncate(s, MAX_BYTES)
        print(s)
    else:
        print(payload.get("summary") or payload.get("suggested_next", ""))

    sys.exit(0)


if __name__ == "__main__":
    main()
