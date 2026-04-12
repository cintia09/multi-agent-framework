#!/usr/bin/env python3
"""
HITL Local Review Server — Human-in-the-Loop review server.
Starts a lightweight HTTP server providing a document review UI.

Usage:
    python3 hitl-server.py <port> <task_id> <role> <content_file> <feedback_dir>

Features:
- Renders markdown documents as HTML (markdown lib with fallback)
- Mermaid diagram rendering via CDN
- Inline image support
- Code syntax highlighting (highlight.js CDN)
- Multi-round feedback: comment → Agent revises → refresh to see new version
- Feedback history: shows both human feedback and agent responses
- Approve / Request Changes buttons
- Writes feedback JSON for Agent polling
"""

import http.server
import html as _html
import json
import os
import re as _re
import sys
import tempfile as _tempfile
import urllib.parse
from datetime import datetime
from pathlib import Path

# Parse arguments
if len(sys.argv) < 6:
    print("Usage: hitl-server.py <port> <task_id> <role> <content_file> <feedback_dir> [bind_host]")
    sys.exit(1)

PORT = int(sys.argv[1])
TASK_ID = sys.argv[2]
ROLE = sys.argv[3]
CONTENT_FILE = sys.argv[4]
FEEDBACK_DIR = sys.argv[5]
BIND_HOST = sys.argv[6] if len(sys.argv) > 6 else "127.0.0.1"

FEEDBACK_FILE = os.path.join(FEEDBACK_DIR, f"{TASK_ID}-{ROLE}-feedback.json")
HISTORY_FILE = os.path.join(FEEDBACK_DIR, f"{TASK_ID}-{ROLE}-history.json")

ROLE_EMOJI = {
    "acceptor": "🎯", "designer": "🏗️", "implementer": "💻",
    "reviewer": "🔍", "tester": "🧪"
}

os.makedirs(FEEDBACK_DIR, exist_ok=True)


def read_content():
    """Read the latest content file."""
    try:
        with open(CONTENT_FILE, "r") as f:
            return f.read()
    except FileNotFoundError:
        return "*Document not found*"


def read_history():
    """Read feedback history."""
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _extract_mermaid_blocks(md_text):
    """Extract mermaid code blocks before markdown processing, replace with placeholders.

    Note: This uses a simple regex and will incorrectly match mermaid blocks nested
    inside other code blocks (e.g., in Python strings). This is a known limitation.
    Avoid placing ```mermaid inside other code fences in review documents.
    """
    blocks = []
    def replace_mermaid(m):
        blocks.append(m.group(1))
        return f"\n<!--MERMAID_{len(blocks) - 1}-->\n"
    text = _re.sub(r"```mermaid\n(.*?)```", replace_mermaid, md_text, flags=_re.S)
    return text, blocks


def _restore_mermaid_blocks(html, blocks):
    """Restore mermaid blocks as rendered divs in HTML."""
    for i, block in enumerate(blocks):
        placeholder = f"<!--MERMAID_{i}-->"
        mermaid_html = f'<div class="mermaid">{block}</div>'
        html = html.replace(placeholder, mermaid_html)
        html = html.replace(f"<p>{placeholder}</p>", mermaid_html)
    return html


def _fix_indented_fences(raw_md):
    """Fix indented fenced code blocks that the markdown library cannot parse."""
    placeholder_map = {}
    counter = [0]
    def replace_fence(m):
        indent = m.group(1)
        lang = m.group(2) or ''
        code = m.group(3)
        lines = code.split('\n')
        dedented = []
        for line in lines:
            if line.startswith(indent):
                dedented.append(line[len(indent):])
            else:
                dedented.append(line)
        code_html = '\n'.join(dedented).strip()
        code_html = code_html.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        lang_attr = f' class="language-{lang}"' if lang else ''
        key = f'CODEPLACEHOLDER{counter[0]}'
        counter[0] += 1
        placeholder_map[key] = f'<pre><code{lang_attr}>{code_html}</code></pre>'
        return f'\n{key}\n'
    fixed = _re.sub(
        r'^([ \t]+)```(\w*)\n(.*?)^\1```',
        replace_fence,
        raw_md,
        flags=_re.M | _re.S
    )
    return fixed, placeholder_map


def md_to_html(md_text):
    """Convert markdown to HTML. Uses markdown library if available, falls back to regex."""
    # Extract mermaid blocks first (before any processing)
    md_text, mermaid_blocks = _extract_mermaid_blocks(md_text)

    try:
        import markdown
        # Fix indented fences
        md_text, placeholders = _fix_indented_fences(md_text)
        html = markdown.markdown(
            md_text,
            extensions=['tables', 'fenced_code', 'toc']
        )

        # Restore indented fence placeholders
        for key, code_html in placeholders.items():
            html = html.replace(key, code_html)
            html = html.replace(f'<p>{key}</p>', code_html)

        # Post-process: render ```markdown blocks as preview
        def render_markdown_block(match):
            raw = match.group(1)
            raw = raw.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
            raw, inner_ph = _fix_indented_fences(raw)
            inner_html = markdown.markdown(raw, extensions=['tables', 'fenced_code'])
            for k, v in inner_ph.items():
                inner_html = inner_html.replace(k, v)
                inner_html = inner_html.replace(f'<p>{k}</p>', v)
            return f'<div class="md-preview"><div class="md-preview-label">📄 Markdown Preview</div>{inner_html}</div>'

        html = _re.sub(
            r'<pre><code class="language-markdown">(.*?)</code></pre>',
            render_markdown_block,
            html,
            flags=_re.S
        )

    except ImportError:
        # Fallback: regex-based conversion
        html = md_text
        html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Code blocks
        code_blocks = []
        def stash_code(m):
            lang = m.group(1)
            content = m.group(2)
            code_blocks.append(f"<pre><code>{content}</code></pre>")
            return f"$$CODE_BLOCK_{len(code_blocks) - 1}$$"
        html = _re.sub(r"```(\w*)\n(.*?)```", stash_code, html, flags=_re.S)
        # Images
        html = _re.sub(r"!\[([^\]]*)\]\(([^)]+)\)",
                       r'<img src="\2" alt="\1" style="max-width:100%;border-radius:4px;margin:1rem 0;">',
                       html)
        # Headers h6->h1
        for i in range(6, 0, -1):
            pat = r"^" + "#" * i + r" (.+)$"
            html = _re.sub(pat, rf"<h{i}>\1</h{i}>", html, flags=_re.M)
        # Bold, inline code
        html = _re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
        html = _re.sub(r"`(.+?)`", r"<code>\1</code>", html)
        # Lists
        html = _re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=_re.M)
        # Tables
        lines = html.split("\n")
        in_table = False
        result = []
        for line in lines:
            if "|" in line and line.strip().startswith("|"):
                if not in_table:
                    result.append("<table>")
                    in_table = True
                if _re.match(r"^\|[\s\-|]+\|$", line.strip()):
                    continue
                cells = [c.strip() for c in line.strip().split("|")[1:-1]]
                result.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
            else:
                if in_table:
                    result.append("</table>")
                    in_table = False
                result.append(line)
        if in_table:
            result.append("</table>")
        html = "\n".join(result)
        # Restore code blocks
        for i, block in enumerate(code_blocks):
            html = html.replace(f"$$CODE_BLOCK_{i}$$", block)
        # Paragraphs
        html = _re.sub(r"\n\n", r"</p><p>", html)
        html = f"<p>{html}</p>"

    # Restore mermaid blocks (works for both paths)
    html = _restore_mermaid_blocks(html, mermaid_blocks)
    return html


def generate_page():
    """Generate the full review HTML page."""
    content = read_content()
    history = read_history()
    emoji = ROLE_EMOJI.get(ROLE, "📋")

    # Check if there's already a decision
    current_status = "pending"
    try:
        with open(FEEDBACK_FILE, "r") as f:
            fb = json.load(f)
            current_status = fb.get("decision", "pending")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    status_badge = {
        "pending": '<span class="badge pending">⏳ Pending Review</span>',
        "approve": '<span class="badge approved">✅ Approved</span>',
        "feedback": '<span class="badge feedback">💬 Changes Requested</span>',
    }.get(current_status, '<span class="badge pending">⏳ Pending</span>')

    content_html = md_to_html(content)

    history_html = ""
    for item in history:
        entry_by = item.get("by", "human")
        if entry_by == "agent":
            agent_role = _html.escape(item.get("role", "agent"))
            summary = _html.escape(item.get("summary", item.get("feedback", "Agent revised the document.")))
            history_html += f'''
        <div class="history-item agent-response">
            <div class="history-header">
                <strong>🤖 {agent_role.upper()} RESPONSE</strong>
                <span class="time">{_html.escape(item.get("at", ""))}</span>
            </div>
            <p>{summary}</p>
        </div>'''
        else:
            decision = item.get("decision", "")
            decision_label = "✅ APPROVED" if decision == "approve" else "💬 FEEDBACK"
            css_class = "approved" if decision == "approve" else "feedback"
            feedback_text = _html.escape(item.get("feedback", "")) if item.get("feedback") else ""
            history_html += f'''
        <div class="history-item {css_class}">
            <div class="history-header">
                <strong>👤 {decision_label}</strong>
                <span class="time">{_html.escape(item.get("at", ""))}</span>
            </div>
            {"<p>" + feedback_text + "</p>" if feedback_text else ""}
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HITL Review: {TASK_ID} — {ROLE}</title>
<style>
  :root {{ --bg: #f8f9fa; --card: #ffffff; --accent: #e9ecef; --border: #dee2e6; --text: #212529; --text-secondary: #6c757d; --green: #28a745; --yellow: #fd7e14; --red: #dc3545; --blue: #0d6efd; --link: #0969da; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.7; }}
  .container {{ max-width:960px; margin:0 auto; padding:2rem; }}
  .header {{ display:flex; justify-content:space-between; align-items:center; padding:1.5rem 0; border-bottom:2px solid var(--border); margin-bottom:2rem; }}
  .header h1 {{ font-size:1.4rem; font-weight:600; }}
  .badge {{ padding:.3rem .8rem; border-radius:12px; font-size:.8rem; font-weight:600; }}
  .badge.pending {{ background:#fff3cd; color:#856404; border:1px solid #ffc107; }}
  .badge.approved {{ background:#d4edda; color:#155724; border:1px solid var(--green); }}
  .badge.feedback {{ background:#cce5ff; color:#004085; border:1px solid var(--blue); }}
  .round-info {{ background:var(--accent); padding:.5rem 1rem; border-radius:6px; margin-bottom:1.5rem; font-size:.9rem; color:var(--text-secondary); }}
  .content {{ background:var(--card); padding:2rem; border-radius:8px; margin-bottom:2rem; border:1px solid var(--border); box-shadow:0 1px 3px rgba(0,0,0,.06); }}
  .content h1,.content h2,.content h3,.content h4,.content h5,.content h6 {{ color:#1a1a2e; margin:1.2rem 0 .5rem; font-weight:600; }}
  .content h1 {{ font-size:1.6rem; border-bottom:1px solid var(--border); padding-bottom:.4rem; }}
  .content h2 {{ font-size:1.3rem; border-bottom:1px solid var(--accent); padding-bottom:.3rem; }}
  .content table {{ width:100%; border-collapse:collapse; margin:1rem 0; }}
  .content th,.content td {{ padding:.6rem .8rem; border:1px solid var(--border); text-align:left; font-size:.9rem; }}
  .content th {{ background:var(--accent); font-weight:600; }}
  .content code {{ background:#f0f1f3; padding:.15rem .4rem; border-radius:3px; font-size:.88rem; color:#d63384; }}
  .content pre {{ background:#f6f8fa; padding:1rem; border-radius:6px; overflow-x:auto; border:1px solid var(--border); margin:1rem 0; font-family:'SF Mono','Fira Code',Menlo,Monaco,monospace; font-size:.85rem; line-height:1.5; }}
  .content pre code {{ background:none; padding:0; color:var(--text); }}
  .content .mermaid {{ background:#fafbfc; padding:1rem; border-radius:6px; margin:1rem 0; text-align:center; border:1px solid var(--border); }}
  .content img {{ max-width:100%; border-radius:6px; margin:1rem 0; border:1px solid var(--border); }}
  .content .md-preview {{ background:#fafbfc; border:1px solid var(--border); border-radius:8px; padding:1.2rem 1.5rem; margin:1rem 0; position:relative; }}
  .content .md-preview .md-preview-label {{ position:absolute; top:-0.7rem; left:1rem; background:#fafbfc; padding:0 0.5rem; font-size:.75rem; color:var(--text-secondary); border:1px solid var(--border); border-radius:4px; }}
  .content .md-preview h1,.content .md-preview h2,.content .md-preview h3,.content .md-preview h4 {{ color:#1a1a2e; border-bottom:1px solid var(--accent); padding-bottom:0.3rem; }}
  .content .md-preview pre {{ background:#f0f1f3; border:1px solid var(--border); }}
  .content .md-preview code {{ background:#e9ecef; }}
  .content .md-preview pre code {{ background:none; }}
  .content blockquote {{ border-left:3px solid var(--blue); padding:.5rem 1rem; margin:1rem 0; background:rgba(13,110,253,.05); color:var(--text-secondary); }}
  .content hr {{ border:none; border-top:1px solid var(--border); margin:1.5rem 0; }}
  .content ul,.content ol {{ padding-left:1.5rem; margin:.5rem 0; }}
  .content li {{ margin:.25rem 0; }}
  .feedback-form {{ background:var(--card); padding:2rem; border-radius:8px; margin-bottom:2rem; border:1px solid var(--border); box-shadow:0 1px 3px rgba(0,0,0,.06); }}
  .feedback-form h2 {{ color:#1a1a2e; margin-bottom:1rem; }}
  textarea {{ width:100%; min-height:150px; background:#fff; color:var(--text); border:1px solid var(--border); border-radius:6px; padding:.8rem; font-family:inherit; font-size:.95rem; resize:vertical; }}
  textarea:focus {{ outline:none; border-color:var(--blue); box-shadow:0 0 0 3px rgba(13,110,253,.15); }}
  .actions {{ display:flex; gap:1rem; margin-top:1.5rem; flex-wrap:wrap; }}
  button {{ padding:.8rem 2rem; border:none; border-radius:6px; font-size:1rem; cursor:pointer; font-weight:600; transition:all .2s; }}
  button:hover {{ opacity:.9; transform:translateY(-1px); box-shadow:0 2px 8px rgba(0,0,0,.12); }}
  .btn-approve {{ background:var(--green); color:#fff; }}
  .btn-feedback {{ background:var(--yellow); color:#fff; }}
  .history {{ margin-top:2rem; }}
  .history h2 {{ color:#1a1a2e; margin-bottom:1rem; }}
  .history-item {{ background:var(--card); padding:1rem; border-radius:6px; margin-bottom:.5rem; border:1px solid var(--border); }}
  .history-item.approved {{ border-left:3px solid var(--green); }}
  .history-item.feedback {{ border-left:3px solid var(--yellow); }}
  .history-item.agent-response {{ border-left:3px solid var(--blue); background:rgba(13,110,253,.03); }}
  .history-header {{ display:flex; justify-content:space-between; margin-bottom:.5rem; }}
  .time {{ color:var(--text-secondary); font-size:.85rem; }}
  .result {{ padding:1rem; border-radius:6px; margin-top:1rem; font-weight:600; background:#d4edda; border:1px solid var(--green); color:#155724; }}
  .refresh-hint {{ text-align:center; color:var(--text-secondary); font-size:.85rem; margin-top:2rem; }}
</style>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css">
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🚪 HITL Review: {TASK_ID} — {emoji} {ROLE}</h1>
    {status_badge}
  </div>

  <div class="round-info">
    📊 Feedback rounds: {len(history)} | 🕐 Last updated: {datetime.now().strftime("%H:%M:%S")}
    | <a href="/" style="color:var(--link);">🔄 Refresh</a>
  </div>

  <div class="content">
    {content_html}
  </div>

  {"" if current_status == "approve" else f"""
  <div class="feedback-form">
    <h2>💬 Your Feedback</h2>
    <form method="POST" action="/submit">
      <textarea name="feedback" placeholder="Enter your feedback here... (optional for approval, required for changes request)"></textarea>
      <div class="actions">
        <button type="submit" name="decision" value="approve" class="btn-approve">✅ Approve</button>
        <button type="submit" name="decision" value="feedback" class="btn-feedback">💬 Request Changes</button>
      </div>
    </form>
  </div>
  """}

  {"<div class='result'>✅ Document approved. Agent can proceed.</div>" if current_status == "approve" else ""}

  <div class="history">
    <h2>📋 Feedback History</h2>
    {history_html if history_html else "<p style='color:var(--text-secondary);'>No feedback yet.</p>"}
  </div>

  <div class="refresh-hint">
    Page auto-refreshes when Agent republishes document after addressing feedback.
    <br>Or click 🔄 Refresh above.
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<script>
  hljs.highlightAll();
  document.querySelectorAll('pre code.hljs').forEach(el => {{
    el.style.background = 'transparent';
    el.style.padding = '0';
  }});
  mermaid.initialize({{startOnLoad:true, theme:'default'}});
</script>
</body>
</html>'''


class HITLHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(generate_page().encode("utf-8"))

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length).decode("utf-8")
        params = urllib.parse.parse_qs(post_data)

        decision = params.get("decision", [""])[0]
        feedback_text = params.get("feedback", [""])[0].strip()

        if decision == "feedback" and not feedback_text:
            # Redirect back with error (in practice, just show the page again)
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()
            return

        # Record feedback
        entry = {
            "task_id": TASK_ID,
            "role": ROLE,
            "decision": decision,
            "feedback": feedback_text or None,
            "at": datetime.now().isoformat(),
            "by": "human"
        }

        # Write current decision (atomic: unique temp file then rename)
        fd, tmp_feedback = _tempfile.mkstemp(dir=FEEDBACK_DIR, prefix=".fb-", suffix=".tmp")
        with os.fdopen(fd, 'w') as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)
        os.rename(tmp_feedback, FEEDBACK_FILE)

        # Append to history (atomic: unique temp file then rename)
        history = read_history()
        history.append(entry)
        fd, tmp_history = _tempfile.mkstemp(dir=FEEDBACK_DIR, prefix=".hist-", suffix=".tmp")
        with os.fdopen(fd, 'w') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        os.rename(tmp_history, HISTORY_FILE)

        # Redirect to main page
        self.send_response(302)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, format, *args):
        # Suppress default logging
        pass


if __name__ == "__main__":
    server = http.server.HTTPServer((BIND_HOST, PORT), HITLHandler)
    print(f"🚪 HITL Review Server running at http://{BIND_HOST}:{PORT}")
    print(f"   Task: {TASK_ID} | Role: {ROLE}")
    print(f"   Feedback: {FEEDBACK_FILE}")
    if BIND_HOST == "0.0.0.0":
        print(f"   ⚠️  Headless mode: access from host via http://<container-ip>:{PORT}")
    print(f"   Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped")
        server.server_close()
