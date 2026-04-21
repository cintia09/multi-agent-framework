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


def _render_terminal(md: str, color: bool = True) -> str:
    """Minimal markdown -> ANSI-styled text for terminal display.

    Honors NO_COLOR and color=False by emitting plain text. Covers the
    same constructs as _render_markdown: headers, fenced code blocks,
    blockquotes, lists, paragraphs, plus inline code/bold/italic/links.
    """
    if not md:
        return ""
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    fm = re.match(r"^---\n.*?\n---\n?", md, re.DOTALL)
    if fm:
        md = md[fm.end():]

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


_INLINE_CODE_RE = re.compile(r"`([^`\n]+?)`")
_BOLD_RE = re.compile(r"\*\*([^*\n]+?)\*\*")
_ITALIC_RE = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")


def _render_inline(text: str) -> str:
    """Inline markdown: escape HTML first, then re-introduce safe tags."""
    out = _html_escape(text)
    # inline code first (so its content is not touched by bold/italic)
    out = _INLINE_CODE_RE.sub(lambda m: f"<code>{m.group(1)}</code>", out)
    out = _BOLD_RE.sub(lambda m: f"<strong>{m.group(1)}</strong>", out)
    out = _ITALIC_RE.sub(lambda m: f"<em>{m.group(1)}</em>", out)
    out = _LINK_RE.sub(
        lambda m: f'<a href="{_html_escape(m.group(2))}" target="_blank" rel="noopener">{m.group(1)}</a>',
        out,
    )
    return out


def _render_markdown(md: str) -> str:
    """Minimal markdown -> HTML.

    Supports: ATX headers (# .. ######), fenced code blocks (``` ... ```),
    blockquotes, ordered/unordered lists, paragraphs, plus inline code,
    bold, italic, and links via _render_inline.

    All HTML in the source is escaped first, so user content cannot inject
    arbitrary tags. The output is intentionally minimal but covers >95%
    of HITL prompt / phase-output content.
    """
    if not md:
        return ""
    md = md.replace("\r\n", "\n").replace("\r", "\n")
    # Strip YAML front-matter (--- ... ---) from the very top.
    fm = re.match(r"^---\n.*?\n---\n?", md, re.DOTALL)
    if fm:
        md = md[fm.end():]
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    in_ul = in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code block
        m = re.match(r"^```(\S*)\s*$", line)
        if m:
            close_lists()
            lang = m.group(1)
            buf = []
            i += 1
            while i < len(lines) and not re.match(r"^```\s*$", lines[i]):
                buf.append(lines[i])
                i += 1
            i += 1  # consume closing fence
            cls = f' class="lang-{_html_escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{_html_escape(chr(10).join(buf))}</code></pre>")
            continue

        # Blank line — paragraph break
        if not stripped:
            close_lists()
            i += 1
            continue

        # ATX header
        m = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
        if m:
            close_lists()
            level = len(m.group(1))
            out.append(f"<h{level}>{_render_inline(m.group(2))}</h{level}>")
            i += 1
            continue

        # Blockquote (single line, accumulate consecutive)
        if stripped.startswith(">"):
            close_lists()
            buf = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner = _render_markdown("\n".join(buf))
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # Unordered list item
        m = re.match(r"^\s*[-*+]\s+(.*)$", line)
        if m:
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{_render_inline(m.group(1))}</li>")
            i += 1
            continue

        # Ordered list item
        m = re.match(r"^\s*\d+\.\s+(.*)$", line)
        if m:
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{_render_inline(m.group(1))}</li>")
            i += 1
            continue

        # Paragraph — gather contiguous non-blank, non-special lines
        close_lists()
        buf = [line]
        i += 1
        while i < len(lines):
            nxt = lines[i]
            if (not nxt.strip()) or re.match(r"^(#{1,6}\s|```|>|\s*[-*+]\s|\s*\d+\.\s)", nxt):
                break
            buf.append(nxt)
            i += 1
        out.append(f"<p>{_render_inline(' '.join(b.strip() for b in buf))}</p>")

    close_lists()
    return "\n".join(out)


def cmd_render_html(ws: Path, eid: str, out_path: str, do_open: bool = False) -> int:
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
<title>{_html_escape(eid)}</title>
<style>
body{{font:15px/1.6 -apple-system,Segoe UI,sans-serif;max-width:880px;margin:2em auto;padding:0 1.2em;color:#222}}
.hint{{color:#888;font-size:.85em;margin-bottom:1em;letter-spacing:.02em}}
.prompt{{background:#fffbe6;border-left:4px solid #f5b301;padding:.9em 1.2em;margin-bottom:1.6em;border-radius:0 4px 4px 0}}
.ctx{{background:#fafafa;padding:1em 1.4em;border:1px solid #eee;border-radius:4px}}
.prompt h1,.ctx h1{{font-size:1.25em;margin:.9em 0 .3em}}
.prompt h2,.ctx h2{{font-size:1.1em;margin:.9em 0 .3em}}
.prompt h3,.ctx h3{{font-size:1em;margin:.9em 0 .3em}}
.prompt h4,.ctx h4{{font-size:.95em;margin:.9em 0 .3em}}
.prompt pre,.ctx pre{{background:#1e1e1e;color:#d4d4d4;padding:.8em 1em;border-radius:4px;overflow-x:auto;font-family:Menlo,Consolas,monospace;font-size:12.5px}}
.prompt code,.ctx code{{background:#eef;color:#06f;padding:.05em .35em;border-radius:3px;font-family:Menlo,Consolas,monospace;font-size:.92em}}
.prompt pre code,.ctx pre code{{background:none;color:inherit;padding:0;font-size:inherit}}
.prompt blockquote,.ctx blockquote{{border-left:3px solid #ccc;padding:.2em .9em;color:#555;margin:.6em 0}}
.prompt ul,.prompt ol,.ctx ul,.ctx ol{{padding-left:1.6em}}
.prompt a,.ctx a{{color:#06f;text-decoration:none}}
.prompt a:hover,.ctx a:hover{{text-decoration:underline}}
.prompt p,.ctx p{{margin:.5em 0}}
#toggle{{position:fixed;top:1em;right:1em;background:#fff;border:1px solid #ccc;color:#444;font-size:.85em;padding:.35em .8em;border-radius:4px;cursor:pointer;font-family:inherit;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
#toggle:hover{{background:#f3f3f3}}
.hidden-by-reader{{display:none}}
</style></head><body>
<button id="toggle" type="button">Spec view</button>
<div class="ctx" id="ctx">{_render_markdown(ctx_text) if ctx_text else '<p><em>(no context)</em></p>'}</div>
<script>
(function(){{
  var ctx = document.getElementById('ctx');
  var btn = document.getElementById('toggle');
  // Save originals so we can restore.
  var hs = ctx.querySelectorAll('h1,h2,h3,h4');
  hs.forEach(function(h){{ h.dataset.orig = h.textContent; }});

  function applyReader(){{
    // 1. Hide a leading H1 that looks like a role label ("Clarifier — T-001").
    var firstH1 = ctx.querySelector('h1');
    if (firstH1 && /[—-]/.test(firstH1.textContent)) firstH1.classList.add('hidden-by-reader');
    // 2. Strip parenthetical hints from headings ("Goal (user vocabulary)" -> "Goal").
    hs.forEach(function(h){{
      h.textContent = h.dataset.orig.replace(/\\s*\\([^)]+\\)\\s*$/, '');
    }});
    // 3. Hide noisy "rationale" sections (and following siblings until next H1/H2).
    ctx.querySelectorAll('h2,h3').forEach(function(h){{
      if (/rationale/i.test(h.dataset.orig)){{
        h.classList.add('hidden-by-reader');
        var sib = h.nextElementSibling;
        while (sib && !/^H[12]$/.test(sib.tagName)){{
          var next = sib.nextElementSibling;
          sib.classList.add('hidden-by-reader');
          sib = next;
        }}
      }}
    }});
  }}
  function applySpec(){{
    hs.forEach(function(h){{ h.textContent = h.dataset.orig; }});
    ctx.querySelectorAll('.hidden-by-reader').forEach(function(el){{ el.classList.remove('hidden-by-reader'); }});
  }}

  var mode = 'reader';
  applyReader();
  btn.addEventListener('click', function(){{
    if (mode === 'reader'){{ applySpec(); btn.textContent = 'Reader view'; mode = 'spec'; }}
    else {{ applyReader(); btn.textContent = 'Spec view'; mode = 'reader'; }}
  }});
}})();
</script>
</body></html>
"""

    out = Path(out_path) if out_path else queue_dir(ws) / f"{eid}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(str(out))

    if do_open:
        url = out.resolve().as_uri()
        opened = False
        try:
            import webbrowser
            opened = webbrowser.open(url)
        except Exception:
            opened = False
        if not opened:
            import shutil, subprocess
            opener = None
            if sys.platform == "darwin" and shutil.which("open"):
                opener = ["open", str(out)]
            elif sys.platform.startswith("linux") and shutil.which("xdg-open"):
                opener = ["xdg-open", str(out)]
            elif sys.platform == "win32":
                opener = ["cmd", "/c", "start", "", str(out)]
            if opener is not None:
                try:
                    subprocess.Popen(opener, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    opened = True
                except Exception:
                    opened = False
        if not opened:
            print(f"html.sh: could not auto-open browser; open manually: {url}", file=sys.stderr)
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
    if sub == "render-html":
        sys.exit(cmd_render_html(
            ws,
            os.environ.get("CN_ID", ""),
            os.environ.get("CN_OUT", ""),
            os.environ.get("CN_OPEN", "0") == "1",
        ))
    print(f"terminal.sh: unknown subcommand: {sub}", file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
