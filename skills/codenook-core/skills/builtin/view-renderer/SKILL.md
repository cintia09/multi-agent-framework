# view-renderer (builtin skill)

## Role

LLM-side rewriter that turns a phase role's rigid output (designed for
the distiller) into a reviewer-friendly HTML + ANSI surface for the
HITL preview. Produces:

- `.codenook/hitl-queue/<eid>.reviewer.html` — self-contained page
  with optional inline `<pre class="mermaid">` blocks (mermaid CDN
  loaded in the same file).
- `.codenook/hitl-queue/<eid>.reviewer.ansi` — ANSI-styled plain text
  for `<codenook> hitl show --id <eid>` (or any TTY consumer).

`_hitl.py`'s `cmd_render_html` and `cmd_show` will prefer these
artefacts when present; otherwise they fall back to the stdlib
markdown renderer shipped in v0.15.2 (no behavioral regression).

## When to invoke

After a successful `<codenook> tick` that opens or advances any HITL
gate (i.e. `tick --json` returns `status: waiting` with at least one
`hitl-queue/*.json` having `decision == null`). The host SHOULD invoke
`view-renderer prepare --id <entry-id>` for each new pending gate
before relaying it to the user. This is best-effort — failures are
silently ignored and the Python fallback covers the gap.

## CLI

```
# Python (preferred — works on Windows, macOS, Linux):
python render.py prepare --id <entry-id> [--workspace <dir>]

# Windows cmd shim:
render.cmd prepare --id <entry-id> [--workspace <dir>]

# POSIX shell shim (calls render.py via python3 or python):
render.sh prepare --id <entry-id> [--workspace <dir>]

# Via the codenook CLI (recommended; OS-agnostic):
<codenook> hitl prepare --id <entry-id>
```

`prepare` collects everything the host LLM needs and prints a JSON
envelope on stdout:

```json
{
  "eid": "T-001-requirements_signoff",
  "task_id": "T-001",
  "gate": "requirements_signoff",
  "context_path": ".codenook/tasks/T-001/outputs/phase-1-clarifier.md",
  "context": "<full markdown source>",
  "html_out": ".codenook/hitl-queue/T-001-requirements_signoff.reviewer.html",
  "ansi_out": ".codenook/hitl-queue/T-001-requirements_signoff.reviewer.ansi",
  "html_template": "<absolute path to templates/reviewer.html.template>",
  "prompt_template": "<absolute path to templates/prompt.md>"
}
```

The host then:

1. Reads `prompt_template` and substitutes the `{{...}}` slots.
2. Runs the substituted prompt through its own LLM.
3. Writes the LLM's two outputs (HTML body fragment + ANSI text) into
   the paths in the envelope. The HTML body fragment is wrapped by
   `templates/reviewer.html.template` first (the host substitutes
   `{{title}}`, `{{body}}`, `{{src_path}}`).

## Output contract

The host writes exactly two files atomically:

- `<html_out>` — full HTML document; UTF-8; self-contained except for
  the mermaid CDN script (`https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js`).
- `<ansi_out>` — plain text with ANSI escape codes; UTF-8; trailing
  newline.

If the host cannot complete the rewrite, it MUST NOT write a partial
file. `_hitl.py` falls through to its stdlib renderer when the
artefact is missing, so a no-op is always safe.

## What the LLM should do

The full prompt lives at `templates/prompt.md`. Highlights:

- Drop YAML front-matter and `## ... rationale` sections (they target
  the distiller, not the human).
- Translate jargon section names into the reader's language while
  keeping the source verbatim available via the Spec view toggle.
- When the content describes a flow / architecture / state machine,
  emit a `<pre class="mermaid">flowchart LR\n  ...</pre>` block above
  the relevant section. Mermaid CDN is preloaded by the wrapper
  template, so blocks render automatically in the browser.
- Render fenced code as `<pre><code class="language-X">...</code></pre>`.
- Always include a `Source: <context_path>` footer.

## Why a script + template instead of pure prompt

Centralises path resolution and the atomic write contract; the host
LLM stays focused on content rewriting. No hardcoded list of role
types in the script — it works for any phase output.

## Failure modes

- Missing entry → exit 2, no envelope.
- Workspace not detected → exit 2.
- Context file missing → envelope still emitted with empty `context`;
  the host should refuse to render and exit cleanly.
