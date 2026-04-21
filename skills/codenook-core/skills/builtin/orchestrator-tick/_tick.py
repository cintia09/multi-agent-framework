#!/usr/bin/env python3
"""orchestrator-tick/_tick.py — full M4 state-machine algorithm.

Implements implementation-v6.md §3.3 verbatim:
  read state.json → decide → execute one step → persist → return summary.

Two-mode dispatch
-----------------
  * M4 mode: state.json contains `plugin` (and the schema implied by
    M4.2). Full algorithm runs, reading phases.yaml + transitions.yaml
    + entry-questions.yaml from .codenook/plugins/<plugin>/ and writing
    queue/, hitl-queue/, history/dispatch.jsonl entries.
  * Legacy mode (no state.plugin): the original M1 stub behaviour
    (preflight + iteration++ + tick_log) is preserved so the M1 bats
    suite keeps passing without churn. See `_legacy_tick`.

Real Task-tool dispatch is M5+: dispatch_agent only writes a marker
file under outputs/<phase-N>-<role>.dispatched containing the rendered
manifest. The agent_id returned is deterministic
(`ag_<task>_<phase_idx>_<n>`) so test fixtures can reason about it.
The kernel that actually invokes Task() lives in main session and is
out of M4 scope — see SKILL.md "M4 scope" section.
"""
from __future__ import annotations

import copy
import datetime
import json
import os
import re
import subprocess
import sys as _early_sys
from pathlib import Path as _early_Path
_early_sys.path.insert(0, str(_early_Path(__file__).resolve().parent.parent / "_lib"))
from sh_run import sh_run as _sh_run  # noqa: E402
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from atomic import atomic_write_json, atomic_write_json_validated  # noqa: E402
from role_index import is_role_allowed  # noqa: E402  (M8.10)

# Schemas live at codenook-core/schemas/.
SCHEMAS_DIR = Path(__file__).resolve().parents[3] / "schemas"
TASK_STATE_SCHEMA = str(SCHEMAS_DIR / "task-state.schema.json")
HITL_ENTRY_SCHEMA = str(SCHEMAS_DIR / "hitl-entry.schema.json")
QUEUE_ENTRY_SCHEMA = str(SCHEMAS_DIR / "queue-entry.schema.json")


def persist_state(state_file: Path, state: dict) -> None:
    atomic_write_json_validated(str(state_file), state, TASK_STATE_SCHEMA)


def _assert_under(p: Path, root: Path) -> Path:
    """Resolve `p` and ensure it stays under `root`. Exits 2 on escape (S3)."""
    try:
        rp = p.resolve()
        root_r = root.resolve()
        rp.relative_to(root_r)
    except (ValueError, OSError):
        print(f"_tick.py: path escapes task root: {p}", file=sys.stderr)
        sys.exit(2)
    return rp


def task_root(workspace: Path, task_id: str) -> Path:
    return workspace / ".codenook" / "tasks" / task_id


# ── Fix #5: task_id format guard (S4) ───────────────────────────────────
_TASK_ID_RE = re.compile(r"^T-[A-Za-z0-9_-]+$")


def _check_task_id(tid: str) -> None:
    if not isinstance(tid, str) or not _TASK_ID_RE.match(tid):
        print(f"_tick.py: invalid task_id format: {tid!r}", file=sys.stderr)
        sys.exit(2)

try:
    import yaml  # PyYAML
except ImportError as e:  # pragma: no cover
    print(f"_tick.py: PyYAML required ({e})", file=sys.stderr)
    sys.exit(2)


# ── small utilities ──────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utf8_safe_truncate(s: str, max_bytes: int) -> str:
    """Hard-truncate `s` to ≤max_bytes UTF-8 bytes WITHOUT splitting a
    multi-byte char. Walks back from byte position max_bytes until a
    valid UTF-8 boundary is found."""
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


def _payload_bytes(p: dict) -> int:
    return len(json.dumps(p, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def emit_summary(payload: dict) -> None:
    """Write the ≤500-byte summary to stdout (json) for the caller.

    Byte-correct UTF-8 truncation:
      * Loop progressively trims `message_for_user`/`next_action` by 10%
        chars from the right until the encoded payload fits.
      * If still too large, drop optional informational fields
        (`missing`, `allowed_values`, `recovery`, `detail`, `file`,
        `reason`) one at a time.
      * Final guard hard-truncates the JSON string at 500 bytes on a
        valid UTF-8 char boundary (rare; only kicks in if every other
        knob has been exhausted)."""
    limit = 500
    while _payload_bytes(payload) > limit:
        trimmed = False
        for k in ("message_for_user", "next_action"):
            v = payload.get(k)
            if isinstance(v, str) and len(v) > 1:
                cut = max(1, len(v) - max(1, len(v) // 10))
                if cut < len(v):
                    payload[k] = v[:cut]
                    trimmed = True
                    if _payload_bytes(payload) <= limit:
                        break
        if not trimmed:
            break
    # Drop optional/informational fields if still too large.
    for k in ("missing", "allowed_values", "recovery", "detail", "file", "reason"):
        if _payload_bytes(payload) <= limit:
            break
        if k in payload:
            payload.pop(k, None)
    s = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    if len(s.encode("utf-8")) > limit:
        s = _utf8_safe_truncate(s, limit)
    print(s)


def read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


# ── frontmatter / verdict ────────────────────────────────────────────────
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


class _OutputState:
    """Sentinel results for verdict reads (E2E-005)."""
    MISSING = "missing"
    NO_FRONTMATTER = "no_frontmatter"
    YAML_PARSE_ERROR = "yaml_parse_error"
    BAD_VERDICT = "bad_verdict"


def read_verdict_detailed(workspace: Path, task_id: str,
                          expected_output: str) -> tuple[str | None, str, str]:
    """Returns ``(verdict, status, detail)``.

    status ∈ {ok, missing, no_frontmatter, yaml_parse_error, bad_verdict}.
    detail is human-readable (parse error message / file path / etc).
    """
    root = task_root(workspace, task_id)
    p = _assert_under(root / expected_output, root)
    rel = expected_output
    if not p.is_file():
        return None, _OutputState.MISSING, str(rel)
    text = p.read_text(encoding="utf-8")
    m = _FM_RE.match(text)
    if not m:
        return None, _OutputState.NO_FRONTMATTER, str(rel)
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        return None, _OutputState.YAML_PARSE_ERROR, f"{rel}: {str(e).splitlines()[0]}"
    v = fm.get("verdict") if isinstance(fm, dict) else None
    if v in ("ok", "needs_revision", "blocked"):
        return v, "ok", str(rel)
    return None, _OutputState.BAD_VERDICT, f"{rel}: verdict={v!r}"


def output_ready(workspace: Path, task_id: str, expected_output: str) -> bool:
    """File exists AND has frontmatter `verdict: <v>` matching enum."""
    v, status, _ = read_verdict_detailed(workspace, task_id, expected_output)
    return v is not None and status == "ok"


def read_verdict(workspace: Path, task_id: str, expected_output: str) -> str | None:
    v, _, _ = read_verdict_detailed(workspace, task_id, expected_output)
    return v


# ── phase / transition lookup ────────────────────────────────────────────
def find_phase(phases: list[dict], pid: str) -> dict | None:
    for ph in phases:
        if ph.get("id") == pid:
            return ph
    return None


def lookup_transition(trans: dict, cur_id: str, verdict: str,
                      profile: str | None = None) -> str | None:
    """Resolve transitions[cur_id][verdict].

    Supports three layouts:
      1. Flat:   transitions: {phase: {verdict: target}}        (legacy)
      2. Nested: transitions: <flat>                            (legacy w/ wrapper)
      3. Profile-keyed: transitions: {profile: {phase: {...}}}  (v0.2.0+)

    When ``profile`` is provided and the transitions doc has a
    ``transitions:`` wrapper whose first-level value (for that profile)
    looks like a phase map, we descend one level. Falls back to flat
    layout for backward compatibility.
    """
    table = trans.get("transitions", {}) or trans  # tolerant of either layout
    # Profile-keyed: prefer profile lookup, fall back to "default" then flat.
    if profile and isinstance(table, dict) and profile in table \
            and isinstance(table[profile], dict) \
            and any(isinstance(v, dict) for v in table[profile].values()):
        ptable = table[profile]
        cur = ptable.get(cur_id, {}) or {}
        nxt = cur.get(verdict)
        if nxt is not None:
            return nxt
        # Allow profile-level entries to inherit from "default" profile.
        if "default" in table and isinstance(table["default"], dict):
            cur = table["default"].get(cur_id, {}) or {}
            return cur.get(verdict)
        return None
    cur = table.get(cur_id, {}) or {}
    nxt = cur.get(verdict)
    return nxt


# ── profile resolution (v0.2.0 development plugin) ──────────────────────
def _read_clarifier_task_type(workspace: Path, task_id: str) -> str | None:
    """Best-effort: scan task outputs/ for the most recent clarifier file
    and return its frontmatter ``task_type`` field. Returns None if no
    clarifier output exists or it lacks the field."""
    out = task_root(workspace, task_id) / "outputs"
    if not out.is_dir():
        return None
    candidates = sorted(out.glob("*clarifier*.md"))
    if not candidates:
        return None
    try:
        text = candidates[-1].read_text(encoding="utf-8")
    except OSError:
        return None
    m = _FM_RE.match(text)
    if not m:
        return None
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    if not isinstance(fm, dict):
        return None
    tt = fm.get("task_type")
    if isinstance(tt, str) and tt.strip():
        return tt.strip()
    return None


def _normalise_phase_catalogue(phases_doc: dict) -> dict[str, dict]:
    """Return ``{phase_id: phase_dict}`` from either layout:
      1. v1 flat list:  phases: [{id, role, ...}, ...]
      2. v2 catalogue:  phases: {<id>: {role, ...}, ...}
    """
    raw = phases_doc.get("phases", [])
    if isinstance(raw, dict):
        out: dict[str, dict] = {}
        for pid, spec in raw.items():
            spec = dict(spec or {})
            spec.setdefault("id", pid)
            out[pid] = spec
        return out
    out = {}
    for ph in raw:
        if not isinstance(ph, dict):
            continue
        pid = ph.get("id")
        if pid:
            out[pid] = ph
    return out


def _resolve_profile(phases_doc: dict, state: dict,
                     workspace: Path) -> tuple[str | None, list[str]]:
    """Return ``(profile_name, phase_id_chain)``.

    For backward compatibility (no ``profiles:`` key in phases.yaml), a
    flat ``phases:`` list is treated as the single implicit ``default``
    profile and the chain is the order they appear in.

    Resolution order (v0.2.0+):
      1. ``state['profile']``      — already-cached resolution.
      2. clarifier output frontmatter ``task_type``.
      3. ``state['task_type']``    — caller hint (entry-questions seed).
      4. fallback default          — ``feature`` if defined, else first
                                     declared profile.
    Only resolutions from sources 1-3 are cached; source 4 is treated
    as provisional so a clarifier output that arrives later (i.e. after
    the very first tick) can still pin the real profile.
    """
    profiles = phases_doc.get("profiles")
    if not profiles or not isinstance(profiles, dict):
        # Legacy layout: chain is the flat list order.
        raw = phases_doc.get("phases", [])
        if isinstance(raw, list):
            chain = [ph.get("id") for ph in raw if isinstance(ph, dict) and ph.get("id")]
        else:
            chain = list(raw.keys()) if isinstance(raw, dict) else []
        return None, chain

    cached = state.get("profile")
    name: str | None = cached if cached in profiles else None
    cache_ok = name is not None
    if not name:
        tt = _read_clarifier_task_type(workspace, state["task_id"])
        if tt and tt in profiles:
            name = tt
            cache_ok = True
    if not name:
        hint = state.get("task_type")
        if hint and hint in profiles:
            name = hint
            cache_ok = True
    if not name:
        # Provisional: do NOT cache so clarifier output (when written)
        # still wins on the very next tick.
        name = "feature" if "feature" in profiles else next(iter(profiles))
        cache_ok = False

    chain_spec = profiles.get(name)
    if isinstance(chain_spec, dict):
        chain = chain_spec.get("phases") or []
    else:
        chain = chain_spec or []
    if not isinstance(chain, list):
        chain = []
    return (name if cache_ok else None), [str(x) for x in chain]


def _build_phase_list(phases_doc: dict, chain: list[str]) -> list[dict]:
    """Order the phase catalogue per ``chain``. Unknown ids are dropped."""
    cat = _normalise_phase_catalogue(phases_doc)
    out: list[dict] = []
    for pid in chain:
        spec = cat.get(pid)
        if spec is not None:
            out.append(spec)
    return out


def _load_pipeline(workspace: Path, state: dict
                   ) -> tuple[list[dict], dict, str | None]:
    """Read phases.yaml + transitions.yaml and resolve the active pipeline
    (profile-aware). Returns ``(phases, trans_doc, profile_name)``.

    Side effect: caches ``state['profile']`` once resolved so subsequent
    ticks are stable even after the clarifier output changes.
    """
    plugin = state["plugin"]
    pdir = workspace / ".codenook" / "plugins" / plugin
    phases_doc = read_yaml(pdir / "phases.yaml")
    trans_doc = read_yaml(pdir / "transitions.yaml")

    profile, chain = _resolve_profile(phases_doc, state, workspace)
    is_legacy = not isinstance(phases_doc.get("profiles"), dict) \
                or not phases_doc.get("profiles")
    if is_legacy:
        raw = phases_doc.get("phases", [])
        if isinstance(raw, list) and all(isinstance(p, dict) for p in raw):
            phases = list(raw)
        else:
            phases = _build_phase_list(phases_doc, chain)
    else:
        phases = _build_phase_list(phases_doc, chain)
        if profile is not None and state.get("profile") != profile:
            state["profile"] = profile
    return phases, trans_doc, profile


# ── manifest + audit + dispatch (stubbed for M4) ─────────────────────────
def render_manifest(state: dict, phase: dict) -> str:
    """Compose the ≤500-byte dispatch payload (kept tiny — full role
    template rendering is M5+)."""
    payload = {
        "execute": "agent",
        "task": state["task_id"],
        "plugin": state["plugin"],
        "phase": phase.get("id"),
        "role": phase.get("role"),
        "produces": phase.get("produces"),
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def append_dispatch_log(workspace: Path, role: str, payload: str) -> None:
    audit_sh = Path(__file__).resolve().parent.parent / "dispatch-audit" / "emit.sh"
    if audit_sh.is_file():
        _sh_run(
            [str(audit_sh), "--role", role, "--payload", payload,
             "--workspace", str(workspace)],
            check=False, capture_output=True,
        )


def _phase_artifact_basename(phase: dict) -> str:
    """Return the canonical ``phase-N-role.md`` basename for a phase.

    Derived from the phase's ``produces:`` field when available (so the
    template / prompt / output filenames stay aligned with the artifact
    contract). Falls back to ``phase-{id}-{role}.md`` when ``produces``
    is missing or malformed.
    """
    produces = (phase.get("produces") or "").strip()
    if produces:
        base = Path(produces).name
        if base:
            return base
    pid = phase.get("id", "?")
    role = phase.get("role", "?")
    return f"phase-{pid}-{role}.md"


def _render_phase_prompt(workspace: Path, state: dict, phase: dict) -> str | None:
    """Read the phase manifest template and substitute {{TASK_CONTEXT}} (M10+).

    Template lookup uses the canonical basename derived from the phase's
    ``produces:`` field (e.g. ``phase-2-designer.md``). Falls back to
    ``phase-{id}-{role}.md`` for plugins that omit ``produces``.

    Returns the rendered text, or None if no template is found.
    Best-effort; never raises.
    """
    try:
        plugin = state.get("plugin", "")
        basename = _phase_artifact_basename(phase)
        template_path = (
            workspace / ".codenook" / "plugins" / plugin
            / "manifest-templates" / basename
        )
        if not template_path.is_file():
            # Backward-compat fallback: try the legacy id-based name.
            pid = phase.get("id", "")
            role = phase.get("role", "")
            template_path = (
                workspace / ".codenook" / "plugins" / plugin
                / "manifest-templates" / f"phase-{pid}-{role}.md"
            )
            if not template_path.is_file():
                return None
        template = template_path.read_text(encoding="utf-8")
        task_id = state.get("task_id", "")
        task_context = ""
        try:
            _lib = Path(__file__).resolve().parent.parent / "_lib"
            import sys as _sys
            _sys.path.insert(0, str(_lib))
            import memory_layer as _ml
            task_context = _ml.build_task_context(workspace, task_id)
        except Exception:
            pass
        rendered = template.replace("{{TASK_CONTEXT}}", task_context)
        # v0.22.0 — auto-inject {{KNOWLEDGE_HITS}} via find_relevant. The
        # CLI cmd_tick re-renders into the same prompts/<basename>.md
        # path after we return, so this is mostly a parity write — keep
        # them in sync so direct callers of dispatch_agent (and tests
        # that drive the orchestrator without the CLI shim) see the
        # substituted block too.
        try:
            _lib = Path(__file__).resolve().parent.parent / "_lib"
            import sys as _sys
            _sys.path.insert(0, str(_lib))
            import knowledge_query as _kq
            query_parts: list[str] = []
            ti = state.get("task_input")
            if isinstance(ti, str) and ti.strip():
                query_parts.append(ti.strip())
            kws = state.get("keywords")
            if isinstance(kws, list):
                query_parts.extend(str(k) for k in kws if k)
            query = " ".join(query_parts)
            top_n = _kq.resolve_top_n(workspace, default=8)
            rendered = _kq.substitute_placeholder(
                rendered,
                workspace,
                query=query,
                role=str(phase.get("role") or ""),
                phase_id=str(phase.get("id") or ""),
                plugin=plugin,
                top_n=top_n,
            )
        except Exception:
            pass
        return rendered
    except Exception:
        return None


def dispatch_agent(workspace: Path, state: dict, phase: dict, n: int = 1) -> str:
    """Stub: write marker file with manifest + return deterministic agent_id.
    Real Task() invocation is M5+ kernel work."""
    pid = phase.get("id", "?")
    role = phase.get("role", "?")
    agent_id = f"ag_{state['task_id']}_{pid}_{n}"
    root = task_root(workspace, state["task_id"])
    marker = _assert_under(
        root / "outputs" / f"phase-{pid}-{role}.dispatched", root
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(render_manifest(state, phase) + "\n", encoding="utf-8")
    # M10+ — write rendered phase prompt when a manifest template exists.
    rendered = _render_phase_prompt(workspace, state, phase)
    if rendered is not None:
        prompt_dir = _assert_under(root / "prompts", root)
        prompt_dir.mkdir(parents=True, exist_ok=True)
        basename = _phase_artifact_basename(phase)
        prompt_file = _assert_under(
            root / "prompts" / basename, root
        )
        prompt_file.write_text(rendered, encoding="utf-8")
    return agent_id


def dispatch_distiller(workspace: Path, task_id: str) -> None:
    pdir = workspace / ".codenook" / "memory" / "_pending"
    pdir.mkdir(parents=True, exist_ok=True)
    atomic_write_json(str(pdir / f"{task_id}.json"),
                      {"task_id": task_id, "queued_at": now_iso()})


# ── post_validate (skip with _warning if missing) ────────────────────────
def run_post_validate(workspace: Path, plugin: str, script_rel: str,
                      state: dict) -> None:
    sp = workspace / ".codenook" / "plugins" / plugin / script_rel
    if not sp.is_file():
        last = state["history"][-1] if state["history"] else None
        if last is not None:
            last["_warning"] = f"post_validate script missing: {script_rel}"
        return
    _sh_run([str(sp), state["task_id"]], cwd=str(workspace),
            check=False, capture_output=True)


# ── HITL ────────────────────────────────────────────────────────────────
def hitl_required(state: dict, phase: dict, cfg: dict) -> bool:
    if phase.get("gate"):
        return True
    return bool(cfg.get("hitl_required", {}).get(phase.get("id")))


def _render_hitl_prompt(workspace: Path, state: dict, phase: dict,
                        gate: str, verdict: str | None,
                        context_path: str) -> str:
    """Render a human-readable approval prompt the conductor can relay
    verbatim. Pulls the gate description from hitl-gates.yaml and adds
    a short context summary so the human reviewer has enough to decide
    without the conductor having to read plugin internals."""
    plugin = state.get("plugin", "")
    role = phase.get("role", "?")
    phase_id = phase.get("id", "?")
    title = state.get("title", "")
    summary = state.get("summary", "")
    desc = ""
    gates_yaml = workspace / ".codenook" / "plugins" / plugin / "hitl-gates.yaml"
    if gates_yaml.is_file():
        try:
            doc = read_yaml(gates_yaml) or {}
            entry = ((doc.get("gates") or {}).get(gate) or {})
            desc = (entry.get("description") or "").strip()
        except Exception:
            desc = ""
    parts = [
        f"Task **{state.get('task_id','?')}** — {title}".rstrip(" —"),
        f"Plugin: `{plugin}`  Phase: `{phase_id}` (role `{role}`)  "
        f"Verdict at gate: `{verdict or 'n/a'}`",
        "",
    ]
    if desc:
        parts.extend([f"**Why this gate:** {desc}", ""])
    if summary:
        parts.extend([f"**Original request:** {summary}", ""])
    parts.extend([
        f"**Review the role's output before deciding:**",
        f"- `{context_path}`",
    ])
    return "\n".join(parts) + "\n"


def write_hitl_entry(workspace: Path, state: dict, phase: dict,
                     verdict: str | None = None) -> Path:
    gate = phase.get("gate") or phase.get("id")
    qdir = workspace / ".codenook" / "hitl-queue"
    qdir.mkdir(parents=True, exist_ok=True)
    entry_id = f"{state['task_id']}-{gate}"
    path = qdir / f"{entry_id}.json"
    context_path = f".codenook/tasks/{state['task_id']}/{phase.get('produces','')}"
    prompt = _render_hitl_prompt(workspace, state, phase, gate, verdict, context_path)
    entry = {
        "id": entry_id,
        "task_id": state["task_id"],
        "plugin": state["plugin"],
        "gate": gate,
        "created_at": now_iso(),
        "context_path": context_path,
        "decision": None,
        "decided_at": None,
        "reviewer": None,
        "comment": None,
        "verdict_at_gate": verdict,
        "prompt": prompt,
    }
    atomic_write_json_validated(str(path), entry, HITL_ENTRY_SCHEMA)
    return path


# ── HITL decision consumer ──────────────────────────────────────────────
def hitl_check_resolved(ws: Path, state: dict, cur_phase: dict
                        ) -> tuple[str, str | None]:
    """Return (status, stored_verdict). Status is one of:
       "pending", "approve", "reject", "needs_changes", "not_found"."""
    gate = cur_phase.get("gate") or cur_phase.get("id")
    eid = f"{state['task_id']}-{gate}"
    p = ws / ".codenook" / "hitl-queue" / f"{eid}.json"
    if not p.is_file():
        return ("not_found", None)
    try:
        entry = read_json(p)
    except Exception:
        return ("not_found", None)
    decision = entry.get("decision")
    if decision in (None, ""):
        return ("pending", None)
    if decision == "approve":
        return ("approve", entry.get("verdict_at_gate"))
    if decision == "reject":
        return ("reject", None)
    if decision == "needs_changes":
        return ("needs_changes", None)
    return ("pending", None)


def hitl_consume_entry(ws: Path, state: dict, cur_phase: dict) -> None:
    gate = cur_phase.get("gate") or cur_phase.get("id")
    eid = f"{state['task_id']}-{gate}"
    src = ws / ".codenook" / "hitl-queue" / f"{eid}.json"
    if not src.is_file():
        return
    dst_dir = ws / ".codenook" / "hitl-queue" / "_consumed"
    dst_dir.mkdir(parents=True, exist_ok=True)
    os.replace(str(src), str(dst_dir / f"{eid}.json"))


# ── entry-questions ────────────────────────────────────────────────────
def check_entry_questions(workspace: Path, plugin: str, phase_id: str,
                          state: dict) -> list[str]:
    eq = read_yaml(workspace / ".codenook" / "plugins" / plugin / "entry-questions.yaml") or {}
    spec = eq.get(phase_id) or {}
    required = spec.get("required") or []
    missing = []
    for key in required:
        if key not in state or state.get(key) in (None, "", [], {}):
            missing.append(key)
    return missing


def entry_question_meta(workspace: Path, plugin: str, phase_id: str,
                        keys: list[str]) -> dict:
    """Return per-key {allowed_values?, description?} dict (E2E-006).

    Falls back to the JSON schema enum for well-known fields (e.g.
    ``dual_mode``) when the plugin's entry-questions.yaml omits them.
    """
    eq = read_yaml(workspace / ".codenook" / "plugins" / plugin / "entry-questions.yaml") or {}
    spec = eq.get(phase_id) or {}
    questions = spec.get("questions") or {}
    out: dict[str, dict] = {}
    for k in keys:
        meta = {}
        q = questions.get(k) if isinstance(questions, dict) else None
        if isinstance(q, dict):
            if "allowed_values" in q:
                meta["allowed_values"] = q["allowed_values"]
            elif "enum" in q:
                meta["allowed_values"] = q["enum"]
            if "description" in q:
                meta["description"] = q["description"]
        # Fallback enums for well-known schema fields.
        if "allowed_values" not in meta:
            try:
                schema = read_json(SCHEMAS_DIR / "task-state.schema.json")
                props = (schema.get("properties") or {}).get(k) or {}
                if isinstance(props.get("enum"), list):
                    meta["allowed_values"] = list(props["enum"])
            except Exception:
                pass
        out[k] = meta
    return out


def _missing_field_response(workspace: Path, plugin: str, phase_id: str,
                            missing: list[str]) -> dict:
    meta = entry_question_meta(workspace, plugin, phase_id, missing)
    parts = []
    for k in missing:
        m = meta.get(k) or {}
        av = m.get("allowed_values")
        if av:
            parts.append(f"{k} (allowed: {'|'.join(map(str, av))})")
        else:
            parts.append(k)
    primary = missing[0]
    primary_av = (meta.get(primary) or {}).get("allowed_values")
    recovery = (
        f"rerun: codenook task set --task <id> --field {primary} "
        f"--value {(primary_av[0] if primary_av else '<value>')}"
    )
    return {
        "status": "blocked",
        "next_action": f"missing: {','.join(missing)}",
        "message_for_user": "Please answer first: " + ", ".join(parts),
        "missing": missing,
        "allowed_values": {k: (meta.get(k) or {}).get("allowed_values")
                           for k in missing
                           if (meta.get(k) or {}).get("allowed_values")},
        "recovery": recovery,
    }


# ── seed_subtasks (fanout) ──────────────────────────────────────────────
def seed_subtasks(workspace: Path, state: dict, phase: dict) -> dict:
    parent = state["task_id"]
    _check_task_id(parent)
    units = state.get("subtasks")
    if not units:
        return {
            "status": "blocked",
            "next_action": "decomposed=true requires subtasks",
            "message_for_user": "decomposed=true requires subtasks",
        }
    queue_dir = workspace / ".codenook" / "queue"
    queue_dir.mkdir(parents=True, exist_ok=True)
    created: list[str] = []
    for i, _u in enumerate(units, 1):
        cid = f"{parent}-c{i}"
        _check_task_id(cid)
        cdir = workspace / ".codenook" / "tasks" / cid
        (cdir / "outputs").mkdir(parents=True, exist_ok=True)
        child_state = {
            "schema_version": 1,
            "task_id": cid,
            "plugin": state["plugin"],
            "phase": None,
            "iteration": 0,
            "max_iterations": state.get("max_iterations", 3),
            "dual_mode": state.get("dual_mode", "serial"),
            "status": "in_progress",
            "depends_on": [parent],
            "config_overrides": state.get("config_overrides", {}),
            "history": [],
        }
        atomic_write_json_validated(
            str(cdir / "state.json"), child_state, TASK_STATE_SCHEMA
        )
        atomic_write_json_validated(str(queue_dir / f"{cid}.json"), {
            "task_id": cid,
            "plugin": state["plugin"],
            "priority": 5,
            "ready_at": now_iso(),
            "blocked_by": [],
            "next_action": f"dispatch_role:{phase.get('role','')}",
        }, QUEUE_ENTRY_SCHEMA)
        created.append(cid)
    return {
        "status": "advanced",
        "next_action": f"seeded {len(created)} subtasks",
    }


# ── dispatch parallel ────────────────────────────────────────────────────
def dispatch_parallel(workspace: Path, state: dict, phase: dict, cfg: dict) -> dict:
    n = int(cfg.get("parallel_n", 2))
    agent_ids = [dispatch_agent(workspace, state, phase, i + 1) for i in range(n)]
    state["in_flight_agent"] = {
        "agent_id": agent_ids,
        "role": phase.get("role"),
        "dispatched_at": now_iso(),
        "expected_output": phase.get("produces", ""),
    }
    state["phase"] = phase.get("id")
    state["phase_started_at"] = now_iso()
    payload = render_manifest(state, phase)
    append_dispatch_log(workspace, phase.get("role", "?"), payload)
    return {"status": "advanced",
            "next_action": f"dispatched {n} parallel {phase.get('role')}"}


# ── dispatch_role (single-role default branch) ───────────────────────────
def dispatch_role(workspace: Path, state: dict, phase: dict, cfg: dict) -> dict:
    missing = check_entry_questions(workspace, state["plugin"], phase.get("id"), state)
    if missing:
        # E2E-P-005: pin state to the target phase + mark blocked so the
        # next tick does NOT fall through to the recovery branch and re-
        # dispatch the previous role (which was the v0.11.3 papercut).
        state["phase"] = phase.get("id")
        state["status"] = "blocked"
        state["in_flight_agent"] = None
        return _missing_field_response(workspace, state["plugin"],
                                       phase.get("id"), missing)
    if phase.get("allows_fanout") and state.get("decomposed"):
        return seed_subtasks(workspace, state, phase)
    if phase.get("dual_mode_compatible") and (
        state.get("dual_mode") == "parallel"
        or cfg.get("dual_mode") == "parallel"
    ):
        return dispatch_parallel(workspace, state, phase, cfg)

    payload = render_manifest(state, phase)
    agent_id = dispatch_agent(workspace, state, phase, 1)
    state["in_flight_agent"] = {
        "agent_id": agent_id,
        "role": phase.get("role"),
        "dispatched_at": now_iso(),
        "expected_output": phase.get("produces", ""),
    }
    state["phase"] = phase.get("id")
    state["phase_started_at"] = now_iso()
    append_dispatch_log(workspace, phase.get("role", "?"), payload)
    return {
        "status": "advanced",
        "next_action": f"dispatched {phase.get('role')}",
        "dispatched_agent_id": agent_id,
    }


# ── M8.10 role-skip wrapper ──────────────────────────────────────────────
def dispatch_or_skip(
    workspace: Path,
    state: dict,
    phase: dict,
    cfg: dict,
    phases: list[dict],
    trans_doc: dict,
    profile: str | None = None,
) -> dict:
    """Dispatch ``phase`` unless its role is excluded by
    ``state.role_constraints``. When excluded, mark the phase as
    ``skipped`` in history (mirroring ``done`` semantics) and walk
    forward via the ``ok`` transition until an allowed phase is found
    or the task completes. Disabled when role_constraints is missing.
    """
    constraints = state.get("role_constraints") or {}
    plugin = state.get("plugin", "")
    visited: set[str] = set()
    cur = phase
    while True:
        if is_role_allowed(plugin, cur.get("role", ""), constraints):
            return dispatch_role(workspace, state, cur, cfg)

        pid = cur.get("id", "")
        if pid in visited:
            return {
                "status": "error",
                "next_action": f"role-skip cycle at {pid}",
            }
        visited.add(pid)
        state["history"].append(
            {
                "ts": now_iso(),
                "phase": pid,
                "verdict": "skipped",
                "_warning": (
                    f"role-skip: {cur.get('role','')}"
                    f" excluded by role_constraints"
                ),
            }
        )
        nxt = lookup_transition(trans_doc, pid, "ok", profile=profile)
        if nxt is None:
            return {
                "status": "error",
                "next_action": f"no transition from {pid}/ok (skip)",
            }
        if nxt == "complete":
            state["status"] = "done"
            state["phase"] = "complete"
            dispatch_distiller(workspace, state["task_id"])
            return {"status": "done", "next_action": "noop"}
        nxt_phase = find_phase(phases, nxt)
        if nxt_phase is None:
            return {
                "status": "error",
                "next_action": f"transition target unknown: {nxt} (skip)",
            }
        cur = nxt_phase


# ── tick (M4 algorithm) ─────────────────────────────────────────────────
def tick(workspace: Path, state_file: Path) -> tuple[dict, dict]:
    """Run one tick of the state machine.

    Transactional state-mutation contract (v0.18.1 hotfix)
    ------------------------------------------------------
    The on-disk ``state.json`` is mutated AT MOST ONCE per ``tick``
    invocation, by the caller (``main``), using the dict returned from
    this function. Internally:

    1. ``state.json`` is read once at entry into ``original_state``.
    2. A deep copy of that snapshot becomes the ``working_state`` that
       the algorithm body (``_tick_body``) is allowed to mutate freely.
    3. On the SUCCESS path, ``working_state`` is returned. The caller
       persists it.
    4. On any failure path — either ``_tick_body`` raises an
       exception, or it returns a summary envelope with
       ``status == "error"`` — the ORIGINAL pre-tick state is returned
       instead, so persisting it is a byte-for-byte no-op. This
       guarantees that a mid-tick failure cannot leave ``state.json``
       in a partially-mutated state (verdict consumed +
       ``in_flight_agent`` cleared but ``phase`` not advanced) that
       would cause the next tick to enter the recovery branch and
       re-dispatch the just-completed phase.

    The error envelope returned to the caller still describes what
    went wrong so the operator can fix the underlying issue (e.g. add
    a missing ``transitions.yaml``); the next tick can then resume
    cleanly from the unchanged state.
    """
    original_state = read_json(state_file)
    working_state = copy.deepcopy(original_state)
    try:
        summary = _tick_body(workspace, working_state)
    except Exception as exc:
        return original_state, {
            "status": "error",
            "next_action": (
                f"exception: {type(exc).__name__}: {exc}"
            ),
        }
    if summary.get("status") == "error":
        # Body returned an error envelope after partial mutation.
        # Roll back by handing the original snapshot to the caller.
        return original_state, summary
    return working_state, summary


def _tick_body(workspace: Path, state: dict) -> dict:
    """Algorithm body — mutates ``state`` in place, returns summary.

    MUST NOT be called directly by ``main`` — go through ``tick`` so
    the transactional snapshot/rollback wrapper is in effect.
    """
    plugin = state["plugin"]
    phases, trans_doc, profile = _load_pipeline(workspace, state)
    cfg = state.get("config_overrides", {})  # M5 will full-merge; M4 uses task-only

    state["last_tick_ts"] = now_iso()
    status_in = state.get("status")

    # ── 0. terminal / waiting short-circuit ──
    if status_in in ("done", "cancelled", "error"):
        del state["last_tick_ts"]
        return {"status": status_in, "next_action": "noop"}

    if status_in == "waiting":
        cur_w = find_phase(phases, state.get("phase")) if state.get("phase") else None
        decided = False
        if cur_w is not None and hitl_required(state, cur_w, cfg):
            res, _ = hitl_check_resolved(workspace, state, cur_w)
            if res in ("approve", "reject", "needs_changes"):
                decided = True
        if not decided:
            del state["last_tick_ts"]
            return {"status": "waiting", "next_action": "noop"}
        # else: fall through to step 3.5 via main flow.

    # ── 1. phase=null → dispatch first ──
    if state.get("phase") in (None, ""):
        if not phases:
            return {"status": "error", "next_action": "no phases defined"}
        first = phases[0]
        pre_check = check_entry_questions(workspace, plugin, first.get("id"), state)
        if pre_check:
            return _missing_field_response(workspace, plugin,
                                                  first.get("id"), pre_check)
        result = dispatch_or_skip(workspace, state, first, cfg, phases, trans_doc, profile=profile)
        return result

    cur = find_phase(phases, state["phase"])
    if cur is None:
        return {"status": "error", "next_action": f"unknown phase {state['phase']}"}

    # ── 2. in_flight present ──
    in_flight = state.get("in_flight_agent")
    just_consumed_verdict: str | None = None
    if in_flight:
        expected = in_flight.get("expected_output", "")
        v, vstatus, vdetail = read_verdict_detailed(
            workspace, state["task_id"], expected)
        if v is None:
            del state["last_tick_ts"]
            if vstatus == _OutputState.MISSING:
                return {
                    "status": "waiting",
                    "next_action": f"awaiting {in_flight.get('role')}",
                }
            # E2E-005: surface parse / frontmatter / verdict errors instead
            # of looking like the agent never returned.
            reason_map = {
                _OutputState.NO_FRONTMATTER: "no_frontmatter",
                _OutputState.YAML_PARSE_ERROR: "yaml_parse_error",
                _OutputState.BAD_VERDICT: "bad_verdict",
            }
            reason = reason_map.get(vstatus, "malformed_output")
            print(
                f"[orchestrator-tick] WARNING: {in_flight.get('role')} output "
                f"present but unusable ({reason}): {vdetail}",
                file=sys.stderr,
            )
            return {
                "status": "blocked",
                "next_action": f"awaiting {in_flight.get('role')}",
                "reason": reason,
                "detail": vdetail,
                "file": expected,
                "message_for_user": (
                    f"Role output present but unusable ({reason}). "
                    f"Fix: {expected}"
                ),
            }
        just_consumed_verdict = v
        state["history"].append(
            {"ts": now_iso(), "phase": cur.get("id"), "verdict": just_consumed_verdict}
        )
        state["in_flight_agent"] = None
        if cur.get("post_validate"):
            run_post_validate(workspace, plugin, cur["post_validate"], state)
        # fall through to step 3.5

    # ── 3.5. HITL gate consumer ──
    verdict_for_transition = just_consumed_verdict
    if hitl_required(state, cur, cfg):
        resolution, stored = hitl_check_resolved(workspace, state, cur)
        if resolution == "approve":
            verdict_for_transition = stored or just_consumed_verdict or "ok"
            hitl_consume_entry(workspace, state, cur)
            state["status"] = "in_progress"
            state["history"].append(
                {"ts": now_iso(), "phase": cur.get("id"),
                 "_warning": "hitl_approved"}
            )
            # fall through to transition step 5
        elif resolution == "reject":
            state["status"] = "blocked"
            state["history"].append(
                {"ts": now_iso(), "phase": cur.get("id"),
                 "_warning": "hitl_rejected"}
            )
            return {"status": "blocked",
                           "next_action": "hitl_rejected"}
        elif resolution == "needs_changes":
            hitl_consume_entry(workspace, state, cur)
            state["iteration"] = state.get("iteration", 0) + 1
            if state["iteration"] > state.get("max_iterations", 0):
                state["status"] = "blocked"
                return {"status": "blocked",
                               "next_action": "max_iterations exceeded"}
            state["status"] = "in_progress"
            state["history"].append(
                {"ts": now_iso(), "phase": cur.get("id"),
                 "_warning": "hitl_needs_changes"}
            )
            return dispatch_or_skip(workspace, state, cur, cfg, phases, trans_doc, profile=profile)
        else:
            # pending or not_found
            if just_consumed_verdict is not None:
                write_hitl_entry(workspace, state, cur, just_consumed_verdict)
                state["status"] = "waiting"
                return {
                    "status": "waiting",
                    "next_action": f"hitl:{cur.get('gate') or cur.get('id')}",
                }
            # waiting + still pending → noop
            del state["last_tick_ts"]
            return {"status": "waiting", "next_action": "noop"}

    # ── 5. transition (only when we have a verdict to act on) ──
    if verdict_for_transition is not None:
        nxt = lookup_transition(trans_doc, cur.get("id"), verdict_for_transition,
                                profile=profile)
        if nxt is None:
            return {"status": "error",
                           "next_action": f"no transition from {cur.get('id')}/{verdict_for_transition}"}
        if nxt == "complete":
            state["status"] = "done"
            state["phase"] = "complete"
            dispatch_distiller(workspace, state["task_id"])
            return {"status": "done", "next_action": "noop"}
        if nxt == cur.get("id"):
            state["iteration"] = state.get("iteration", 0) + 1
            if state["iteration"] > state.get("max_iterations", 0):
                state["status"] = "blocked"
                return {"status": "blocked",
                               "next_action": "max_iterations exceeded"}
            return dispatch_or_skip(workspace, state, cur, cfg, phases, trans_doc, profile=profile)
        nxt_phase = find_phase(phases, nxt)
        if nxt_phase is None:
            return {"status": "error",
                           "next_action": f"transition target unknown: {nxt}"}
        return dispatch_or_skip(workspace, state, nxt_phase, cfg, phases, trans_doc, profile=profile)

    # ── 6. recovery (only when status==in_progress + phase set + no in_flight) ──
    if state.get("status") == "in_progress":
        state["history"].append(
            {"ts": now_iso(), "phase": cur.get("id"),
             "_warning": "recover: re-dispatch (no in_flight)"}
        )
        return dispatch_or_skip(workspace, state, cur, cfg, phases, trans_doc, profile=profile)

    # Default: nothing to do (e.g., status=blocked + phase set + no in_flight).
    del state["last_tick_ts"]
    return {"status": state.get("status", "noop"), "next_action": "noop"}


# ── legacy stub mode (M1) ────────────────────────────────────────────────
def _legacy_tick(workspace: Path, state_file: Path, dry_run: bool,
                 dispatch_cmd: str, task: str) -> int:
    """Original M1 behaviour: preflight + dispatch + iteration++.
    Activated when state.json lacks the M4 `plugin` field."""
    import tempfile

    with state_file.open("r") as f:
        state = json.load(f)

    phase = state.get("phase", "")
    iteration = state.get("iteration", 0)
    total = state.get("total_iterations", 0)
    core_root = _find_core_root()

    if phase == "done":
        print("tick.sh: task at terminal phase 'done'", file=sys.stderr)
        return 3
    if iteration >= total:
        print(f"tick.sh: iteration limit reached ({iteration}/{total})", file=sys.stderr)
        _legacy_log(state, "preflight", "blocked: iteration limit")
        if not dry_run:
            atomic_write_json(str(state_file), state)
        return 1

    preflight = os.path.join(core_root, "skills/builtin/preflight/preflight.sh")
    res = _sh_run(
        [preflight, "--task", task, "--workspace", str(workspace), "--json"],
        capture_output=True, text=True,
    )
    if res.returncode != 0:
        reasons: list[str] = []
        try:
            reasons = json.loads(res.stdout).get("reasons", [])
        except Exception:
            pass
        _legacy_log(state, "preflight",
                    f"blocked: {', '.join(reasons) if reasons else 'failed'}")
        if not dry_run:
            atomic_write_json(str(state_file), state)
        for line in (res.stderr or "").strip().split("\n"):
            if line:
                print(line, file=sys.stderr)
        return 1

    if dry_run:
        print("tick.sh: dry-run mode, not dispatching", file=sys.stderr)
        return 0

    payload = json.dumps({"task": state.get("task_id"), "phase": phase,
                          "iteration": iteration}, ensure_ascii=False)
    if len(payload) > 500:
        payload = payload[:497] + "..."

    audit = os.path.join(core_root, "skills/builtin/dispatch-audit/emit.sh")
    if os.path.exists(audit):
        _sh_run([audit, "--role", "executor", "--payload", payload,
                 "--workspace", str(workspace)], check=False)

    if dispatch_cmd:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json",
                                          delete=False) as fp:
            sf = fp.name
        try:
            env = os.environ.copy()
            env["CODENOOK_DISPATCH_PAYLOAD"] = payload
            env["CODENOOK_DISPATCH_SUMMARY"] = sf
            r = _sh_run([dispatch_cmd], env=env, capture_output=True, text=True)
            ok = r.returncode == 0
        finally:
            if os.path.exists(sf):
                os.unlink(sf)
        if not ok:
            print("tick.sh: dispatch failed", file=sys.stderr)
            _legacy_log(state, "dispatch", "failed")
            atomic_write_json(str(state_file), state)
            return 1

    state["iteration"] = iteration + 1
    _legacy_log(state, "dispatch", "success")
    atomic_write_json(str(state_file), state)
    return 0


def _legacy_log(state: dict, action: str, result: str) -> None:
    state.setdefault("tick_log", []).append(
        {"ts": now_iso(), "action": action, "result": result}
    )


def after_phase(workspace_root: Path, task_id: str, phase: str | None,
                summary_status: str) -> None:
    """M9.2 hook: dispatch extractor-batch when a tick produces a phase
    transition or terminal status.  Best-effort — never raises (FR-EXT-5 /
    AC-TRG-4).  Default batch path can be overridden via CN_EXTRACTOR_BATCH
    (used by tests to inject a stub)."""
    import subprocess
    if summary_status not in ("done", "blocked", "advanced"):
        return
    batch = os.environ.get("CN_EXTRACTOR_BATCH", "")
    if not batch:
        core = _find_core_root()
        if not core:
            return
        batch = os.path.join(core, "skills", "builtin",
                             "extractor-batch", "extractor-batch.sh")
    if not os.path.exists(batch):
        return
    cmd = ["bash", batch,
           "--task-id", task_id,
           "--reason", "after_phase",
           "--workspace", str(workspace_root),
           "--phase", phase or ""]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode != 0:
            print(f"orchestrator-tick: extractor batch failed (exit={proc.returncode})",
                  file=sys.stderr)
            if proc.stderr:
                print(proc.stderr.rstrip(), file=sys.stderr)
    except subprocess.TimeoutExpired:
        print("orchestrator-tick: extractor batch failed (exit=timeout)",
              file=sys.stderr)
    except Exception as exc:  # noqa: BLE001 - best-effort
        print(f"orchestrator-tick: extractor batch failed (exit=exception:{exc})",
              file=sys.stderr)


def _find_core_root() -> str:
    cur = os.path.dirname(os.path.abspath(__file__))
    while cur != "/":
        if os.path.exists(os.path.join(cur, "skills", "builtin", "preflight")):
            return cur
        cur = os.path.dirname(cur)
    return os.environ.get("CORE_ROOT", "")


# ── entry point ─────────────────────────────────────────────────────────
def main() -> None:
    task = os.environ["CN_TASK"]
    state_file = Path(os.environ["CN_STATE_FILE"])
    workspace = Path(os.environ["CN_WORKSPACE"])
    dry_run = os.environ.get("CN_DRY_RUN", "0") == "1"
    json_mode = os.environ.get("CN_JSON", "0") == "1"
    dispatch_cmd = os.environ.get("CN_DISPATCH_CMD", "")

    state = read_json(state_file)

    # Mode select.
    if "plugin" not in state:
        sys.exit(_legacy_tick(workspace, state_file, dry_run, dispatch_cmd, task))

    if dry_run:
        # M4 dry-run: don't persist or dispatch; just compute.
        new_state, summary = tick(workspace, state_file)
        if json_mode:
            emit_summary(summary)
        sys.exit(_exit_for(summary))

    prior_state = read_json(state_file)
    new_state, summary = tick(workspace, state_file)
    # Skip persist for pure observers (no progress made):
    waiting_noop = (summary.get("status") == "waiting"
                    and summary.get("next_action", "").startswith("awaiting"))
    inert_noop = (summary.get("next_action") == "noop"
                  and prior_state.get("status") in
                  ("done", "cancelled", "error", "blocked", "waiting")
                  and prior_state.get("status") == new_state.get("status"))
    # v0.18.1 — never persist on error: tick() guarantees new_state ==
    # prior_state in that case (transactional rollback), so the write
    # would be a byte-for-byte no-op anyway. Skipping it is both faster
    # and a clearer signal that error paths leave on-disk state intact.
    error_noop = summary.get("status") == "error"
    if not (waiting_noop or inert_noop or error_noop):
        new_state["updated_at"] = now_iso()
        persist_state(state_file, new_state)
    # M9.2 — after_phase hook (best-effort; never blocks tick exit).
    after_phase(workspace, task,
                new_state.get("phase") or prior_state.get("phase"),
                summary.get("status", ""))
    if json_mode:
        emit_summary(summary)
    sys.exit(_exit_for(summary))


def _exit_for(summary: dict) -> int:
    """E2E-P-009 — documented tick exit-code contract.

      0  phase advanced, task done, or benign re-dispatch
      2  entry-question pending (status=blocked + missing field)
      3  HITL pending (status=waiting on hitl gate)
      1  actual error (cancelled / error / blocked-without-recovery)
    """
    s = summary.get("status")
    if s in ("advanced", "done"):
        return 0
    if s == "blocked":
        # Entry-question blocked → exit 2.
        if summary.get("missing"):
            return 2
        return 1
    if s == "waiting":
        nxt = summary.get("next_action", "") or ""
        if nxt.startswith("hitl:") or nxt.startswith("awaiting"):
            # awaiting role output is benign waiting → 0; explicit hitl → 3.
            return 3 if nxt.startswith("hitl:") else 0
        return 0
    if s in ("cancelled", "error"):
        return 1
    return 0


if __name__ == "__main__":
    main()
