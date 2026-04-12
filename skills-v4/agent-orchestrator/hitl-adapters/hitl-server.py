#!/usr/bin/env python3
"""
HITL Local Review Server — Human-in-the-Loop review server.
Starts a lightweight HTTP server providing a document review UI.

Usage:
    python3 hitl-server.py <port> <task_id> <role> <content_file> <feedback_dir>

Features:
- Renders markdown documents as HTML
- Multi-round feedback: comment → Agent revises → refresh to see new version
- Approve / Request Changes buttons
- Feedback history display
- Writes feedback JSON for Agent polling
"""

import http.server
import json
import os
import sys
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


def md_to_html(md_text):
    """Basic markdown to HTML conversion (Python 3.13 compatible)."""
    import re
    html = md_text
    # Escape HTML
    html = html.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # Code blocks FIRST — protect contents from further processing
    code_blocks = []
    def stash_code(m):
        code_blocks.append(m.group(2))
        return f"$$CODE_BLOCK_{len(code_blocks) - 1}$$"
    html = re.sub(r"```(\w*)\n(.*?)```", stash_code, html, flags=re.S)
    # Headers
    html = re.sub(r"^### (.+)$", r"<h3>\1</h3>", html, flags=re.M)
    html = re.sub(r"^## (.+)$", r"<h2>\1</h2>", html, flags=re.M)
    html = re.sub(r"^# (.+)$", r"<h1>\1</h1>", html, flags=re.M)
    # Bold
    html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", html)
    # Inline code
    html = re.sub(r"`(.+?)`", r"<code>\1</code>", html)
    # Lists
    html = re.sub(r"^- (.+)$", r"<li>\1</li>", html, flags=re.M)
    # Tables (basic) — escape hyphen in character class for Python 3.13+
    lines = html.split("\n")
    in_table = False
    result = []
    for line in lines:
        if "|" in line and line.strip().startswith("|"):
            if not in_table:
                result.append("<table>")
                in_table = True
            if re.match(r"^\|[\s\-|]+\|$", line.strip()):
                continue  # Skip separator rows
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
        html = html.replace(f"$$CODE_BLOCK_{i}$$", f"<pre><code>{block}</code></pre>")
    # Paragraphs
    html = re.sub(r"\n\n", r"</p><p>", html)
    html = f"<p>{html}</p>"
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
        "approved": '<span class="badge approved">✅ Approved</span>',
        "feedback": '<span class="badge feedback">💬 Changes Requested</span>',
    }.get(current_status, '<span class="badge pending">⏳ Pending</span>')

    content_html = md_to_html(content)

    history_html = ""
    for item in history:
        decision_label = "✅ APPROVED" if item.get("decision") == "approved" else "💬 FEEDBACK"
        history_html += f'''
        <div class="history-item {'approved' if item.get('decision') == 'approved' else 'feedback'}">
            <div class="history-header">
                <strong>{decision_label}</strong>
                <span class="time">{item.get("at", "")}</span>
            </div>
            {"<p>" + item.get("feedback", "") + "</p>" if item.get("feedback") else ""}
        </div>'''

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>HITL Review: {TASK_ID} — {ROLE}</title>
<style>
  :root {{ --bg: #0f0f23; --card: #1a1a3e; --accent: #2a2a5e; --text: #e4e4e4; --green: #4caf50; --yellow: #ff9800; --red: #f44336; --blue: #2196f3; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:var(--bg); color:var(--text); line-height:1.6; }}
  .container {{ max-width:960px; margin:0 auto; padding:2rem; }}
  .header {{ display:flex; justify-content:space-between; align-items:center; padding:1.5rem 0; border-bottom:2px solid var(--accent); margin-bottom:2rem; }}
  .header h1 {{ font-size:1.4rem; }}
  .badge {{ padding:.3rem .8rem; border-radius:4px; font-size:.85rem; font-weight:600; }}
  .badge.pending {{ background:var(--yellow); color:#000; }}
  .badge.approved {{ background:var(--green); color:#fff; }}
  .badge.feedback {{ background:var(--blue); color:#fff; }}
  .round-info {{ background:var(--accent); padding:.5rem 1rem; border-radius:4px; margin-bottom:1.5rem; font-size:.9rem; }}
  .content {{ background:var(--card); padding:2rem; border-radius:8px; margin-bottom:2rem; }}
  .content h1,.content h2,.content h3 {{ color:#7ec8e3; margin:1rem 0 .5rem; }}
  .content table {{ width:100%; border-collapse:collapse; margin:1rem 0; }}
  .content th,.content td {{ padding:.5rem; border:1px solid var(--accent); text-align:left; font-size:.9rem; }}
  .content th {{ background:var(--accent); }}
  .content code {{ background:rgba(255,255,255,.1); padding:.15rem .4rem; border-radius:3px; font-size:.9rem; }}
  .content pre {{ background:rgba(0,0,0,.3); padding:1rem; border-radius:4px; overflow-x:auto; }}
  .feedback-form {{ background:var(--card); padding:2rem; border-radius:8px; margin-bottom:2rem; }}
  .feedback-form h2 {{ color:#7ec8e3; margin-bottom:1rem; }}
  textarea {{ width:100%; min-height:150px; background:rgba(0,0,0,.3); color:var(--text); border:1px solid var(--accent); border-radius:4px; padding:.8rem; font-family:inherit; font-size:.95rem; resize:vertical; }}
  .actions {{ display:flex; gap:1rem; margin-top:1.5rem; flex-wrap:wrap; }}
  button {{ padding:.8rem 2rem; border:none; border-radius:4px; font-size:1rem; cursor:pointer; font-weight:600; transition:all .2s; }}
  button:hover {{ opacity:.85; transform:translateY(-1px); }}
  .btn-approve {{ background:var(--green); color:#fff; }}
  .btn-feedback {{ background:var(--yellow); color:#000; }}
  .history {{ margin-top:2rem; }}
  .history h2 {{ color:#7ec8e3; margin-bottom:1rem; }}
  .history-item {{ background:rgba(0,0,0,.2); padding:1rem; border-radius:4px; margin-bottom:.5rem; }}
  .history-item.approved {{ border-left:3px solid var(--green); }}
  .history-item.feedback {{ border-left:3px solid var(--yellow); }}
  .history-header {{ display:flex; justify-content:space-between; margin-bottom:.5rem; }}
  .time {{ color:#888; font-size:.85rem; }}
  .result {{ padding:1rem; border-radius:4px; margin-top:1rem; font-weight:600; background:rgba(76,175,80,.2); border:1px solid var(--green); }}
  .refresh-hint {{ text-align:center; color:#888; font-size:.85rem; margin-top:2rem; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>🚪 HITL Review: {TASK_ID} — {emoji} {ROLE}</h1>
    {status_badge}
  </div>

  <div class="round-info">
    📊 Feedback rounds: {len(history)} | 🕐 Last updated: {datetime.now().strftime("%H:%M:%S")}
    | <a href="/" style="color:#7ec8e3;">🔄 Refresh</a>
  </div>

  <div class="content">
    {content_html}
  </div>

  {"" if current_status == "approved" else f"""
  <div class="feedback-form">
    <h2>💬 Your Feedback</h2>
    <form method="POST" action="/submit">
      <textarea name="feedback" placeholder="Enter your feedback here... (optional for approval, required for changes request)"></textarea>
      <div class="actions">
        <button type="submit" name="decision" value="approved" class="btn-approve">✅ Approve</button>
        <button type="submit" name="decision" value="feedback" class="btn-feedback">💬 Request Changes</button>
      </div>
    </form>
  </div>
  """}

  {"<div class='result'>✅ Document approved. Agent can proceed.</div>" if current_status == "approved" else ""}

  <div class="history">
    <h2>📋 Feedback History</h2>
    {history_html if history_html else "<p style='color:#888;'>No feedback yet.</p>"}
  </div>

  <div class="refresh-hint">
    Page auto-refreshes when Agent republishes document after addressing feedback.
    <br>Or click 🔄 Refresh above.
  </div>
</div>
</body>
</html>'''


class HITLHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
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

        # Write current decision (atomic: write temp file then rename)
        tmp_feedback = FEEDBACK_FILE + ".tmp"
        with open(tmp_feedback, "w") as f:
            json.dump(entry, f, indent=2, ensure_ascii=False)
        os.rename(tmp_feedback, FEEDBACK_FILE)

        # Append to history (atomic: write temp file then rename)
        history = read_history()
        history.append(entry)
        tmp_history = HISTORY_FILE + ".tmp"
        with open(tmp_history, "w") as f:
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
