#!/usr/bin/env python3
"""hitl-adapter/_hitl.py — list / decide / show subcommands.

State files: `.codenook/hitl-queue/<id>.json` (M4.4 schema).
History mirror: `.codenook/history/hitl.jsonl` (append-only).

All writes go through `_lib/atomic.py` so a crash mid-decide leaves
either the original or the new file — never partial.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from atomic import atomic_write_json_validated  # noqa: E402

VALID_DECISIONS = ("approve", "reject", "needs_changes")

SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "schemas"
HITL_ENTRY_SCHEMA = str(SCHEMAS_DIR / "hitl-entry.schema.json")

_EID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def _check_eid(eid: str) -> None:
    """Reject ids containing path-separator or traversal sequences (S1)."""
    if (not eid
            or not _EID_RE.match(eid)
            or eid.startswith(".")
            or ".." in eid):
        print("terminal.sh: invalid --id", file=sys.stderr)
        sys.exit(2)


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def queue_dir(ws: Path) -> Path:
    return ws / ".codenook" / "hitl-queue"


def entry_path(ws: Path, eid: str) -> Path:
    return queue_dir(ws) / f"{eid}.json"


def load_entry(ws: Path, eid: str) -> dict | None:
    p = entry_path(ws, eid)
    if not p.is_file():
        return None
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def cmd_list(ws: Path, json_out: bool) -> int:
    entries = []
    qd = queue_dir(ws)
    if qd.is_dir():
        for f in sorted(qd.glob("*.json")):
            try:
                with f.open("r", encoding="utf-8") as fh:
                    d = json.load(fh)
            except Exception as e:
                print(f"terminal.sh: warn: skipping {f.name}: {e}", file=sys.stderr)
                continue
            if d.get("decision") in (None, ""):
                entries.append(d)
    if json_out:
        print(json.dumps({"entries": entries}, ensure_ascii=False,
                         separators=(",", ":")))
    else:
        for e in entries:
            print(f"{e.get('id')}\t{e.get('task_id')}\t{e.get('gate')}\t{e.get('created_at')}")
    return 0


def cmd_show(ws: Path, eid: str) -> int:
    if not eid:
        print("terminal.sh: --id is required", file=sys.stderr); return 2
    _check_eid(eid)
    entry = load_entry(ws, eid)
    if entry is None:
        print(f"terminal.sh: hitl entry not found: {eid}", file=sys.stderr); return 2
    cp = entry.get("context_path") or ""
    if not cp:
        print(f"terminal.sh: entry has no context_path", file=sys.stderr); return 1
    # Reject absolute context_path outright (would escape ws).
    if os.path.isabs(cp):
        print("terminal.sh: context_path escapes workspace",
              file=sys.stderr); return 2
    target = (ws / cp).resolve()
    ws_resolved = ws.resolve()
    try:
        target.relative_to(ws_resolved)
    except ValueError:
        print("terminal.sh: context_path escapes workspace",
              file=sys.stderr); return 2
    if not target.is_file():
        print(f"terminal.sh: context file missing: {cp}", file=sys.stderr); return 1
    sys.stdout.write(target.read_text(encoding="utf-8"))
    return 0


def cmd_decide(ws: Path, eid: str, decision: str, reviewer: str,
               comment: str) -> int:
    if not eid:
        print("terminal.sh: --id is required", file=sys.stderr); return 2
    _check_eid(eid)
    if decision not in VALID_DECISIONS:
        print(f"terminal.sh: invalid --decision {decision!r} "
              f"(want one of: {', '.join(VALID_DECISIONS)})", file=sys.stderr)
        return 2
    if not reviewer:
        print("terminal.sh: --reviewer is required for decide", file=sys.stderr); return 2

    entry = load_entry(ws, eid)
    if entry is None:
        print(f"terminal.sh: hitl entry not found: {eid}", file=sys.stderr); return 2
    if entry.get("decision") not in (None, ""):
        print(f"terminal.sh: entry already decided "
              f"({entry.get('decision')}); refuse to overwrite", file=sys.stderr)
        return 1

    entry["decision"] = decision
    entry["decided_at"] = now_iso()
    entry["reviewer"] = reviewer
    entry["comment"] = comment if comment else None

    atomic_write_json_validated(str(entry_path(ws, eid)), entry, HITL_ENTRY_SCHEMA)

    # Mirror to append-only history.
    hist = ws / ".codenook" / "history" / "hitl.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    with hist.open("a", encoding="utf-8") as f:
        f.write(line)

    # E2E-P-007 — per-task audit.jsonl tee.
    task_id = entry.get("task_id")
    if task_id:
        try:
            tdir = ws / ".codenook" / "tasks" / str(task_id)
            tdir.mkdir(parents=True, exist_ok=True)
            with (tdir / "audit.jsonl").open("a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass

    return 0


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;"))


def cmd_render_html(ws: Path, eid: str, out_path: str) -> int:
    """Render HITL entry as a self-contained HTML file for human review.

    The resulting file is static — submission still happens via
    `terminal.sh decide` (or the `codenook decide` wrapper). The
    HTML simply renders the prompt, context, and a quick-copy
    decide command so the operator can answer from any browser.
    """
    if not eid:
        print("html.sh: --id is required", file=sys.stderr); return 2
    _check_eid(eid)
    entry = load_entry(ws, eid)
    if entry is None:
        print(f"html.sh: hitl entry not found: {eid}", file=sys.stderr); return 2

    cp = entry.get("context_path") or ""
    ctx_text = ""
    if cp and not os.path.isabs(cp):
        target = (ws / cp).resolve()
        try:
            target.relative_to(ws.resolve())
            if target.is_file():
                ctx_text = target.read_text(encoding="utf-8")
        except ValueError:
            pass

    prompt = entry.get("prompt") or "(no prompt)"
    task_id = entry.get("task_id") or "?"
    gate = entry.get("gate") or "?"
    created = entry.get("created_at") or "?"

    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>HITL gate {_html_escape(eid)}</title>
<style>
body{{font:14px/1.5 -apple-system,Segoe UI,sans-serif;max-width:920px;margin:2em auto;padding:0 1em;color:#222}}
h1{{font-size:1.4em}}
.meta{{color:#666;font-size:.9em;margin-bottom:1em}}
.prompt{{background:#fffbe6;border-left:4px solid #f5b301;padding:.7em 1em;margin:1em 0;white-space:pre-wrap}}
.ctx{{background:#f7f7f7;padding:1em;border-radius:4px;white-space:pre-wrap;font-family:Menlo,Consolas,monospace;font-size:13px;max-height:60vh;overflow:auto}}
.cmd{{background:#1e1e1e;color:#d4d4d4;padding:.8em 1em;border-radius:4px;font-family:Menlo,Consolas,monospace;font-size:13px;white-space:pre-wrap;overflow-x:auto}}
.decisions span{{display:inline-block;margin:.3em .5em .3em 0;padding:.25em .6em;border-radius:3px;color:#fff;font-size:.85em}}
.decisions .a{{background:#2e8b57}} .decisions .r{{background:#c0392b}} .decisions .n{{background:#d68910}}
</style></head><body>
<h1>HITL gate · {_html_escape(eid)}</h1>
<div class="meta">task <b>{_html_escape(task_id)}</b> · gate <b>{_html_escape(gate)}</b> · created {_html_escape(created)}</div>

<h2>Prompt</h2>
<div class="prompt">{_html_escape(prompt)}</div>

<h2>Context ({_html_escape(cp) if cp else 'none'})</h2>
<div class="ctx">{_html_escape(ctx_text) if ctx_text else '(no context)'}</div>

<h2>How to answer</h2>
<p>This page is read-only. Decide from the terminal:</p>
<div class="cmd">codenook decide --id {_html_escape(eid)} \\
        --decision &lt;approve|reject|needs_changes&gt; \\
        --reviewer "&lt;your name&gt;" \\
        --comment "&lt;optional&gt;"</div>
<p class="decisions">Possible decisions:
<span class="a">approve</span><span class="r">reject</span><span class="n">needs_changes</span></p>
</body></html>
"""

    out = Path(out_path) if out_path else queue_dir(ws) / f"{eid}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(str(out))
    return 0


def main() -> None:
    sub = os.environ["CN_SUBCMD"]
    ws = Path(os.environ["CN_WORKSPACE"])
    if sub == "list":
        sys.exit(cmd_list(ws, os.environ.get("CN_JSON", "0") == "1"))
    if sub == "show":
        sys.exit(cmd_show(ws, os.environ.get("CN_ID", "")))
    if sub == "decide":
        sys.exit(cmd_decide(
            ws,
            os.environ.get("CN_ID", ""),
            os.environ.get("CN_DECISION", ""),
            os.environ.get("CN_REVIEWER", ""),
            os.environ.get("CN_COMMENT", ""),
        ))
    if sub == "render-html":
        sys.exit(cmd_render_html(
            ws,
            os.environ.get("CN_ID", ""),
            os.environ.get("CN_OUT", ""),
        ))
    print(f"terminal.sh: unknown subcommand: {sub}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
