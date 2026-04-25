#!/usr/bin/env python3
"""hitl-adapter/_hitl.py — list / decide / show subcommands.

State files: `.codenook/hitl-queue/<id>.json` (M4.4 schema).
History mirror: `.codenook/history/hitl.jsonl` (append-only).

All writes go through `_lib/atomic.py` so a crash mid-decide leaves
either the original or the new file — never partial.
"""
from __future__ import annotations

import datetime
import fcntl
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

# Allow ASCII alphanum, dot, dash, underscore, plus the same East-Asian
# script ranges that ``_lib/cli/config.py``'s slugify keeps (CJK Unified
# Ideographs, Ext A, Hiragana, Katakana, Hangul Syllables). Kept inline
# (vs. importing config) because hitl-adapter is a standalone helper
# spawned with a different sys.path; importing kernel modules from here
# breaks pytest sandboxing.
_EID_RE = re.compile(
    r"^[A-Za-z0-9._\u3040-\u309f\u30a0-\u30ff"
    r"\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af-]+$"
)


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


def _apply_reader_view(md: str) -> str:
    """Strip role-output noise meant for the distiller, not the reviewer.

    Mirrors the JS toggle on the HTML preview:
      - drop a leading 'Role — T-XXX' style H1,
      - strip parenthetical hints from headings (e.g. 'Goal (user vocabulary)'),
      - drop any '## ... rationale' section and its body until the next H1/H2.
    """
    lines = md.split("\n")
    out: list[str] = []
    skip_section = False
    first_h1_seen = False
    for line in lines:
        h = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if h:
            level, title = len(h.group(1)), h.group(2)
            if not first_h1_seen and level == 1 and re.search(r"[—-]", title):
                first_h1_seen = True
                continue
            first_h1_seen = True
            if level <= 2 and re.search(r"rationale", title, re.IGNORECASE):
                skip_section = True
                continue
            if skip_section and level <= 2:
                skip_section = False
            title = re.sub(r"\s*\([^)]+\)\s*$", "", title)
            out.append(f"{h.group(1)} {title}")
            continue
        if skip_section:
            continue
        out.append(line)
    return "\n".join(out)


_INLINE_CODE_RE = re.compile(r"`([^`\n]+?)`")
_BOLD_RE = re.compile(r"\*\*([^*\n]+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _render_terminal(md: str, color: bool = True, reader: bool = True) -> str:
    """Minimal markdown -> ANSI-styled text for terminal display.

    Honors NO_COLOR and color=False by emitting plain text. Covers the
    same constructs as _render_markdown: headers, fenced code blocks,
    blockquotes, lists, paragraphs, plus inline code/bold/italic/links.

    When reader=True (default), applies the same content trimming as the
    HTML preview's Reader view. Pass reader=False (or call cmd_show
    --raw) to keep the original markdown verbatim.
    """
    if not md:
        return ""
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    fm = re.match(r"^---\n.*?\n---\n?", md, re.DOTALL)
    if fm:
        md = md[fm.end():]
    if reader:
        md = _apply_reader_view(md)

    if not color or os.environ.get("NO_COLOR"):
        BOLD = DIM = RESET = ITAL = UND = ""
        FG_CYAN = FG_BLUE = FG_MAGENTA = FG_GREEN = FG_YELLOW = FG_GREY = ""
    else:
        BOLD = "\033[1m"; DIM = "\033[2m"; ITAL = "\033[3m"
        UND = "\033[4m"; RESET = "\033[0m"
        FG_CYAN = "\033[36m"; FG_BLUE = "\033[34m"; FG_MAGENTA = "\033[35m"
        FG_GREEN = "\033[32m"; FG_YELLOW = "\033[33m"; FG_GREY = "\033[90m"

    def inline(text: str) -> str:
        text = _INLINE_CODE_RE.sub(lambda m: f"{FG_GREEN}{m.group(1)}{RESET}", text)
        text = _BOLD_RE.sub(lambda m: f"{BOLD}{m.group(1)}{RESET}", text)
        text = _ITALIC_RE.sub(lambda m: f"{ITAL}{m.group(1)}{RESET}", text)
        text = _LINK_RE.sub(lambda m: f"{UND}{m.group(1)}{RESET} {DIM}({m.group(2)}){RESET}", text)
        return text

    lines = md.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        m = re.match(r"^```(\S*)\s*$", line)
        if m:
            lang = m.group(1)
            label = f"{DIM}─── {lang or 'code'} ───{RESET}"
            out.append(label)
            i += 1
            while i < len(lines) and not re.match(r"^```\s*$", lines[i]):
                out.append(f"{FG_GREEN}{lines[i]}{RESET}")
                i += 1
            i += 1
            out.append(f"{DIM}───{RESET}")
            continue

        if not stripped:
            out.append("")
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            level = len(m.group(1))
            color_pick = (FG_CYAN, FG_BLUE, FG_MAGENTA, FG_YELLOW, FG_GREY, FG_GREY)[min(level - 1, 5)]
            prefix = "#" * level
            out.append(f"{BOLD}{color_pick}{prefix} {inline(m.group(2))}{RESET}")
            i += 1
            continue

        if stripped.startswith(">"):
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            for b in buf:
                out.append(f"{FG_GREY}│ {inline(b)}{RESET}")
            continue

        m = re.match(r"^(\s*)[-*+]\s+(.*)$", line)
        if m:
            indent = m.group(1)
            out.append(f"{indent}{FG_YELLOW}•{RESET} {inline(m.group(2))}")
            i += 1
            continue

        m = re.match(r"^(\s*)(\d+)\.\s+(.*)$", line)
        if m:
            out.append(f"{m.group(1)}{FG_YELLOW}{m.group(2)}.{RESET} {inline(m.group(3))}")
            i += 1
            continue

        out.append(inline(line))
        i += 1

    return "\n".join(out) + "\n"



def cmd_show(ws: Path, eid: str, raw: bool = False) -> int:
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
    text = target.read_text(encoding="utf-8")
    if raw or not target.suffix.lower() in (".md", ".markdown"):
        sys.stdout.write(text)
    else:
        use_color = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
        sys.stdout.write(_render_terminal(text, color=use_color))
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

    # v0.29.5: serialise the read-modify-write cycle under an
    # exclusive flock on the entry file so two concurrent `decide`
    # calls (e.g. CLI + HTTP serve UI) cannot both observe
    # decision=None and both win. The flock is released
    # automatically when the with-block exits or the process dies.
    ep = entry_path(ws, eid)
    lock_fd = os.open(str(ep), os.O_RDONLY)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        # Re-read under the lock; another decider may have committed
        # between our load_entry above and our acquisition of the lock.
        entry = load_entry(ws, eid)
        if entry is None:
            print(f"terminal.sh: hitl entry vanished mid-decide: {eid}",
                  file=sys.stderr)
            return 2
        if entry.get("decision") not in (None, ""):
            print(f"terminal.sh: entry already decided "
                  f"({entry.get('decision')}); refuse to overwrite "
                  "(race detected)", file=sys.stderr)
            return 1

        entry["decision"] = decision
        entry["decided_at"] = now_iso()
        entry["reviewer"] = reviewer
        entry["comment"] = comment if comment else None

        atomic_write_json_validated(
            str(ep), entry, HITL_ENTRY_SCHEMA)

        # Mirror to append-only history (under the same lock so the
        # audit log can never disagree with the on-disk decision).
        # Pass-2 P2 #6: also take an exclusive fcntl.flock on the
        # JSONL so concurrent decide/extract writes never interleave
        # mid-line (lines can exceed PIPE_BUF).
        hist = ws / ".codenook" / "history" / "hitl.jsonl"
        hist.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        try:
            import fcntl as _fcntl  # POSIX only
        except ImportError:
            _fcntl = None  # type: ignore[assignment]
        with hist.open("a", encoding="utf-8") as f:
            if _fcntl is not None:
                _fcntl.flock(f.fileno(), _fcntl.LOCK_EX)
                try:
                    f.write(line)
                    f.flush()
                finally:
                    _fcntl.flock(f.fileno(), _fcntl.LOCK_UN)
            else:
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
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(lock_fd)
        except OSError:
            pass

    return 0


def main() -> None:
    sub = os.environ["CN_SUBCMD"]
    ws = Path(os.environ["CN_WORKSPACE"])
    if sub == "list":
        sys.exit(cmd_list(ws, os.environ.get("CN_JSON", "0") == "1"))
    if sub == "show":
        sys.exit(cmd_show(ws, os.environ.get("CN_ID", ""),
                          raw=os.environ.get("CN_RAW", "0") == "1"))
    if sub == "decide":
        sys.exit(cmd_decide(
            ws,
            os.environ.get("CN_ID", ""),
            os.environ.get("CN_DECISION", ""),
            os.environ.get("CN_REVIEWER", ""),
            os.environ.get("CN_COMMENT", ""),
        ))
    print(f"terminal.sh: unknown subcommand: {sub}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
