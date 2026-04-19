"""chain_summarize — M10.4 two-pass LLM chain summarizer.

Renders the ancestor chain of ``task_id`` into a markdown block suitable
for injection into the router-agent prompt's ``{{TASK_CHAIN}}`` slot.

Public API::

    summarize(workspace, task_id, *, max_tokens=8192, llm_mode=None) -> str

Behaviour summary (spec §6 of docs/v6/task-chains-v6.md):

* Walks ancestors via ``task_chain.walk_ancestors`` and drops self.
* No ancestors → returns ``""``.
* Pass-1: per-ancestor LLM call (``call_name="chain_summarize"``).
* Pass-2 (only if rendered > ``max_tokens``): one whole-chain
  compression call with the same ``call_name``.
* Secret scan via ``secret_scan``; on hit → redact + audit
  ``chain_summarize_redacted`` (verdict ``redacted``) and return the
  redacted text (still useful for prompt injection).
* Any unhandled exception → audit ``chain_summarize_failed``
  (verdict ``failed``) and return ``""``. Never raises to the caller.

Path-traversal defence: every read resolves under
``<workspace>/.codenook/tasks/<ancestor>/`` and is rejected otherwise.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

# Sibling _lib imports (tests set PYTHONPATH=$M10_LIB_DIR).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import extract_audit  # noqa: E402
import secret_scan  # noqa: E402
import task_chain  # noqa: E402
import token_estimate  # noqa: E402
from llm_call import call_llm  # noqa: E402

# ---- spec constants (docs/v6/task-chains-v6.md §6 / §11) ---------------
_BRIEF_BYTES = 1024
_DOC_BYTES = 4096
_ARTIFACT_CAP = 20
_NEWEST_VERBATIM = 3  # pass-2 keeps newest 3 untouched (spec §6.5)
_DOC_FILES = ("decisions.md", "design.md", "impl-plan.md", "test.md")

_TASKS_REL = Path(".codenook") / "tasks"


# ─────────────────────────────────────────────────────── filesystem helpers

def _tasks_root(workspace: Path) -> Path:
    return (workspace / _TASKS_REL).resolve()


def _safe_resolve(workspace: Path, ancestor: str, name: str) -> Optional[Path]:
    """Resolve ``<ws>/.codenook/tasks/<ancestor>/<name>`` and assert it stays
    inside the ancestor directory **and** the ancestor directory itself
    stays inside ``<ws>/.codenook/tasks/`` (belt-and-suspenders against a
    malformed ancestor id that escaped earlier validation). Returns None
    on per-file traversal; raises ``ValueError`` on tasks-root escape so
    the top-level try/except in ``summarize`` audits + returns "".
    """
    tasks_root = _tasks_root(workspace)
    ancestor_dir = (workspace / _TASKS_REL / ancestor).resolve()
    # Belt-and-suspenders: ancestor_dir must stay under tasks_root.
    ancestor_dir.relative_to(tasks_root)
    target = (ancestor_dir / name).resolve()
    try:
        target.relative_to(ancestor_dir)
    except ValueError:
        return None
    return target


def _read_capped(path: Optional[Path], cap: int) -> str:
    if path is None or not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:cap]
    except OSError:
        return ""


def _read_brief(workspace: Path, ancestor: str) -> str:
    p = _safe_resolve(workspace, ancestor, "draft-config.yaml")
    raw = _read_capped(p, _BRIEF_BYTES)
    if not raw:
        return ""
    # Lightweight extraction: pull the value of ``input:`` if present;
    # fall back to the raw bytes otherwise. We do not import yaml to
    # keep the dependency surface zero.
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("input:"):
            v = s[len("input:"):].strip()
            if v.startswith('"') and v.endswith('"') and len(v) >= 2:
                v = v[1:-1]
            elif v.startswith("'") and v.endswith("'") and len(v) >= 2:
                v = v[1:-1]
            return v
    return raw


def _list_artifacts(workspace: Path, ancestor: str) -> list[str]:
    """Return up to _ARTIFACT_CAP relative paths of existing artifacts.

    Includes existing files under ``outputs/`` plus the four canonical
    doc files (decisions/design/impl-plan/test) that exist. Sorted
    alphabetically for determinism.
    """
    items: list[str] = []
    tasks_root = _tasks_root(workspace)
    ancestor_dir = (workspace / _TASKS_REL / ancestor).resolve()
    # Belt-and-suspenders: ancestor_dir must stay under tasks_root.
    ancestor_dir.relative_to(tasks_root)
    outputs_dir = (ancestor_dir / "outputs").resolve()
    if outputs_dir.is_dir():
        try:
            outputs_dir.relative_to(ancestor_dir)
        except ValueError:
            outputs_dir = None  # type: ignore[assignment]
        if outputs_dir is not None:
            for entry in sorted(outputs_dir.iterdir()):
                if entry.is_file():
                    items.append(f"outputs/{entry.name}")
    for name in _DOC_FILES:
        p = _safe_resolve(workspace, ancestor, name)
        if p is not None and p.is_file():
            items.append(name)
    items = sorted(set(items))
    return items[:_ARTIFACT_CAP]


def _collect_ancestor(workspace: Path, ancestor: str) -> Optional[dict[str, Any]]:
    # Spec §6 / review-r1 fix #2: reject malformed ancestor ids before
    # any filesystem read. walk_ancestors trusts state.json contents,
    # so a corrupted "parent_id": "../../etc" would otherwise reach
    # _safe_resolve / _list_artifacts. Skip + audit, never raise.
    try:
        task_chain._check_task_id(ancestor)
    except (ValueError, TypeError):
        _audit_safe(
            workspace,
            outcome="chain_summarize_failed",
            verdict="failed",
            source_task=ancestor if isinstance(ancestor, str) else "",
            reason=f"bad_ancestor_id:{ancestor!r}"[:200],
        )
        return None
    state = task_chain._read_state_json(workspace, ancestor) or {}
    title = state.get("title") or state.get("task_id") or ancestor
    phase = state.get("phase") or "unknown"
    status = state.get("status") or "unknown"
    brief = _read_brief(workspace, ancestor)
    decisions = _read_capped(_safe_resolve(workspace, ancestor, "decisions.md"), _DOC_BYTES)
    design = _read_capped(_safe_resolve(workspace, ancestor, "design.md"), _DOC_BYTES)
    impl_plan = _read_capped(_safe_resolve(workspace, ancestor, "impl-plan.md"), _DOC_BYTES)
    test = _read_capped(_safe_resolve(workspace, ancestor, "test.md"), _DOC_BYTES)
    artifacts = _list_artifacts(workspace, ancestor)
    return {
        "task_id": ancestor,
        "title": title,
        "phase": phase,
        "status": status,
        "brief": brief,
        "decisions": decisions,
        "design": design,
        "impl_plan": impl_plan,
        "test": test,
        "artifacts": artifacts,
    }


# ─────────────────────────────────────────────────────── prompt builders

def _materials_block(meta: dict[str, Any]) -> str:
    parts: list[str] = []
    if meta["brief"]:
        parts.append(f"[brief]\n{meta['brief']}")
    if meta["decisions"]:
        parts.append(f"[decisions.md]\n{meta['decisions']}")
    if meta["design"]:
        parts.append(f"[design.md]\n{meta['design']}")
    if meta["impl_plan"]:
        parts.append(f"[impl-plan.md]\n{meta['impl_plan']}")
    if meta["test"]:
        parts.append(f"[test.md]\n{meta['test']}")
    if meta["artifacts"]:
        parts.append("[artifacts]\n" + "\n".join(meta["artifacts"]))
    return "\n\n".join(parts) if parts else "(no materials)"


def _pass1_prompt(meta: dict[str, Any]) -> str:
    return (
        "你是 CodeNook 的链摘要器。下面是任务 "
        f"{meta['task_id']} 的完整工作产物。"
        "请输出 ≤ 1500 token 的中文摘要，结构:\n"
        "1. 任务目标 (≤ 100 字)\n"
        "2. 关键决策 (bullet list)\n"
        "3. 已落定的设计点 (bullet list)\n"
        "4. 仍未解决 / 留给子任务 (bullet list)\n\n"
        "—— 原始材料 ——\n"
        f"{_materials_block(meta)}\n"
    )


def _pass2_prompt(per_ancestor_sections: list[str]) -> str:
    joined = "\n\n".join(per_ancestor_sections)
    n = len(per_ancestor_sections)
    return (
        f"下方是 {n} 段任务摘要，按 child→root 顺序。请重写为新文档:\n"
        "- 完整保留最近 3 段 (newest 3 ancestors) 的原文\n"
        "- 把更早的所有段合并为 1 段 ≤ 2000 token 的「远祖背景」\n"
        "- 保留每段开头的「## T-XXX」标题以便溯源\n\n"
        "—— 输入 ——\n"
        f"{joined}\n"
    )


# ─────────────────────────────────────────────────────── render

def _h3_header(meta: dict[str, Any]) -> str:
    return (
        f"### {meta['task_id']} — {meta['title']} "
        f"(phase: {meta['phase']}, status: {meta['status']})"
    )


def _render_section(meta: dict[str, Any], body: str) -> str:
    out = [_h3_header(meta), "", body.strip()]
    if meta["artifacts"]:
        out.append("")
        out.append("**产物**:")
        for a in meta["artifacts"]:
            out.append(f"- {a}")
    return "\n".join(out)


def _wrap(body: str, n_ancestors: int) -> str:
    header = (
        "## TASK_CHAIN (M10)\n\n"
        f"This task descends from {n_ancestors} ancestor(s). Newest first.\n"
    )
    return f"{header}\n{body.rstrip()}\n"


# ─────────────────────────────────────────────────────── audit helpers

def _audit_safe(workspace: Path, *, outcome: str, verdict: str,
                source_task: str, reason: str = "") -> None:
    try:
        extract_audit.audit(
            workspace,
            asset_type="chain",
            outcome=outcome,
            verdict=verdict,
            source_task=source_task,
            reason=reason,
        )
    except Exception:
        # Audit MUST never mask the primary contract (return value).
        pass


# ─────────────────────────────────────────────────────── public API

def summarize(workspace: Path | str,
              task_id: str,
              *,
              max_tokens: int = 8192,
              llm_mode: str | None = None) -> str:
    """Return the rendered TASK_CHAIN markdown block (or "" on no-op/failure)."""
    ws = Path(workspace).resolve()
    try:
        chain = task_chain.walk_ancestors(ws, task_id)
        ancestors = chain[1:] if chain else []
        if not ancestors:
            return ""

        # Pass-1: per-ancestor LLM summarisation.
        metas: list[dict[str, Any]] = []
        pass1: list[str] = []
        for aid in ancestors:
            meta = _collect_ancestor(ws, aid)
            if meta is None:
                # Bad ancestor id (already audited); skip silently.
                continue
            metas.append(meta)
            prompt = _pass1_prompt(meta)
            resp = call_llm(prompt, call_name="chain_summarize", mode=llm_mode)
            pass1.append(resp if isinstance(resp, str) else str(resp))

        if not metas:
            return ""

        # Initial render (pass-1 only).
        sections = [_render_section(meta, body)
                    for meta, body in zip(metas, pass1)]
        body = "\n\n".join(sections)
        rendered = _wrap(body, len(metas))

        # Pass-2 if over budget.
        pass2_used = False
        if token_estimate.estimate(rendered) > max_tokens:
            pass2_used = True
            per_ancestor_sections = [
                f"## {meta['task_id']}\n{txt}".strip()
                for meta, txt in zip(metas, pass1)
            ]
            p2_prompt = _pass2_prompt(per_ancestor_sections)
            p2_resp = call_llm(p2_prompt, call_name="chain_summarize", mode=llm_mode)
            if not isinstance(p2_resp, str):
                p2_resp = str(p2_resp)
            rendered = _wrap(p2_resp, len(metas))

        # Secret scan + redact (returns redacted text; not a failure).
        hit, rule_id = secret_scan.scan_secrets(rendered)
        if hit:
            rendered = secret_scan.redact(rendered)
            _audit_safe(
                ws,
                outcome="chain_summarize_redacted",
                verdict="redacted",
                source_task=task_id,
                reason=f"secret_match:{rule_id or 'unknown'}",
            )

        # Spec §9.1: terminal success outcome. Co-occurs with
        # chain_summarize_redacted when redaction was applied (the
        # redacted record is a sub-event; chain_summarized signals the
        # call returned a non-empty rendering).
        try:
            tok = token_estimate.estimate(rendered)
        except Exception:  # noqa: BLE001
            tok = len(rendered) // 4
        _audit_safe(
            ws,
            outcome="chain_summarized",
            verdict="ok",
            source_task=task_id,
            reason=f"depth={len(metas)},tokens~{tok},pass2={pass2_used}",
        )

        return rendered

    except Exception as e:  # noqa: BLE001 — spec §6.8 forbids re-raise
        msg = f"{type(e).__name__}: {e}"[:200]
        _audit_safe(
            ws,
            outcome="chain_summarize_failed",
            verdict="failed",
            source_task=task_id,
            reason=msg,
        )
        return ""
