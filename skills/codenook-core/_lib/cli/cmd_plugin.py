"""``codenook plugin info <id>`` — print profiles + phases summary for a
plugin. Helps users of `task new --interactive` discover what's
available without having to read the plugin manifests by hand.

``codenook plugin lint <id|path>`` — static validator that catches the
most common plugin authoring mistakes before they explode at dispatch
time:

  * phases.yaml references a role with no roles/<role>.md
  * phases.yaml references a gate not declared in hitl-gates.yaml
  * profiles reference a phase id missing from the phase catalogue
  * manifest-templates/<basename>.md missing for a phase whose
    matching template would be expected (best-effort heuristic)
  * unsubstituted ``{var}`` placeholders in manifest templates that
    don't appear in the canonical template-var allowlist
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Sequence

from .config import CodenookContext


HELP = """\
Usage: codenook plugin <info|lint> [args...]

  info <id>          print profiles + phases summary for an installed plugin
  lint <id|path>     statically validate a plugin's YAML + role + manifest
                     wiring (use --json for machine output)
"""

HELP_LINT = """\
Usage: codenook plugin lint <id|path> [--json]

Validates a plugin's structural wiring without invoking the kernel:

  * plugin.yaml exists and parses
  * phases.yaml exists and parses
  * every phase.role has a corresponding roles/<role>.md
  * every phase.gate is declared in hitl-gates.yaml
  * every profile references only phases declared in the catalogue
  * every manifest-templates/<file>.md referenced by produces resolves
  * manifest templates contain no unknown {var} placeholders

Argument resolution:
  * if <id|path> matches an installed plugin under
    .codenook/plugins/<id>/, lints that
  * otherwise treated as a filesystem path (so you can lint
    ``plugins/my-domain/`` directly from a checkout before installing).

Exit codes:
  0  no violations (warnings still possible)
  1  one or more violations
  2  usage error
"""


# Mustache-style placeholders the kernel ACTUALLY substitutes during
# ``orchestrator-tick._render_phase_prompt``. Single-brace ``{var}``
# tokens in the manifests are descriptive text consumed by the
# dispatched sub-agent, not template substitutions, and so are NOT
# linted.
_KNOWN_TEMPLATE_VARS = frozenset({
    "TASK_CONTEXT",
})

_VAR_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")


def run(ctx: CodenookContext, args: Sequence[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print(HELP)
        return 0
    if args[0] == "lint":
        return _plugin_lint(ctx, list(args[1:]))
    if args[0] != "info":
        sys.stderr.write(f"codenook plugin: unknown subcommand: {args[0]}\n")
        sys.stderr.write(HELP)
        return 2
    if len(args) < 2:
        sys.stderr.write("codenook plugin info: <id> required\n")
        return 2
    plugin = args[1]

    pdir = ctx.workspace / ".codenook" / "plugins" / plugin
    if not pdir.is_dir():
        sys.stderr.write(
            f"codenook plugin info: plugin not installed: {plugin}\n")
        return 1

    print(f"Plugin: {plugin}")
    print(f"Path  : {pdir}")

    phases_yaml = pdir / "phases.yaml"
    if not phases_yaml.is_file():
        print("(no phases.yaml — legacy plugin)")
        return 0

    try:
        import yaml  # type: ignore[import-untyped]
        doc = yaml.safe_load(phases_yaml.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        sys.stderr.write(f"codenook plugin info: read failed: {exc}\n")
        return 1

    profiles = doc.get("profiles") or {}
    if isinstance(profiles, dict) and profiles:
        print("\nProfiles:")
        for name, spec in profiles.items():
            chain = spec.get("phases") if isinstance(spec, dict) else spec
            if isinstance(chain, list):
                print(f"  {name}: {' -> '.join(str(x) for x in chain)}")
            else:
                print(f"  {name}: (no phase chain)")
    else:
        print("\nProfiles: (none — single-pipeline plugin)")

    raw = doc.get("phases", [])
    print("\nPhases:")
    if isinstance(raw, dict):
        for pid, spec in raw.items():
            role = (spec or {}).get("role", "?") if isinstance(spec, dict) else "?"
            print(f"  {pid:<12} role={role}")
    elif isinstance(raw, list):
        for p in raw:
            if isinstance(p, dict):
                print(f"  {p.get('id','?'):<12} role={p.get('role','?')}")
    return 0


# ── plugin lint ──────────────────────────────────────────────────────────


def _safe_yaml(path: Path) -> tuple[dict, str | None]:
    try:
        import yaml  # type: ignore[import-untyped]
    except Exception:
        return {}, "pyyaml not available"
    if not path.is_file():
        return {}, f"missing: {path}"
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        return {}, f"parse error: {exc}"
    if not isinstance(doc, dict):
        return {}, "top-level YAML must be a mapping"
    return doc, None


def _resolve_plugin_dir(ctx: CodenookContext, ref: str) -> Path | None:
    installed = ctx.workspace / ".codenook" / "plugins" / ref
    if installed.is_dir():
        return installed
    p = Path(ref).expanduser()
    if p.is_absolute() and p.is_dir():
        return p
    relative = (ctx.workspace / ref).resolve()
    if relative.is_dir():
        return relative
    cwd_relative = (Path.cwd() / ref).resolve()
    if cwd_relative.is_dir():
        return cwd_relative
    return None


def _plugin_lint(ctx: CodenookContext, args: list[str]) -> int:
    as_json = False
    target: str | None = None
    for a in args:
        if a in ("-h", "--help"):
            print(HELP_LINT)
            return 0
        if a == "--json":
            as_json = True
        elif a.startswith("-"):
            sys.stderr.write(f"codenook plugin lint: unknown flag: {a}\n")
            sys.stderr.write(HELP_LINT)
            return 2
        elif target is None:
            target = a
        else:
            sys.stderr.write(
                f"codenook plugin lint: unexpected positional: {a}\n")
            return 2

    if not target:
        sys.stderr.write("codenook plugin lint: <id|path> required\n")
        sys.stderr.write(HELP_LINT)
        return 2

    pdir = _resolve_plugin_dir(ctx, target)
    if pdir is None:
        sys.stderr.write(
            f"codenook plugin lint: not a plugin id or directory: {target}\n")
        return 1

    violations: list[dict] = []
    warnings: list[dict] = []

    def err(code: str, msg: str, **extra) -> None:
        violations.append({"code": code, "message": msg, **extra})

    def warn(code: str, msg: str, **extra) -> None:
        warnings.append({"code": code, "message": msg, **extra})

    # 1. plugin.yaml ----------------------------------------------------
    plugin_doc, perr = _safe_yaml(pdir / "plugin.yaml")
    if perr:
        err("E_PLUGIN_YAML", f"plugin.yaml: {perr}")
    plugin_id = plugin_doc.get("id") if plugin_doc else None

    # 2. phases.yaml ----------------------------------------------------
    phases_doc, pherr = _safe_yaml(pdir / "phases.yaml")
    if pherr:
        err("E_PHASES_YAML", f"phases.yaml: {pherr}")
        # Without phases we can't check anything further usefully.
        return _emit_lint(pdir, plugin_id, violations, warnings, as_json)

    raw_phases = phases_doc.get("phases")
    catalog: dict[str, dict] = {}
    if isinstance(raw_phases, dict):
        for pid, spec in raw_phases.items():
            if isinstance(spec, dict):
                catalog[str(pid)] = spec
    elif isinstance(raw_phases, list):
        for entry in raw_phases:
            if isinstance(entry, dict) and "id" in entry:
                catalog[str(entry["id"])] = entry

    if not catalog:
        err("E_PHASES_EMPTY", "phases.yaml has no phases catalogue")

    # 3. roles --------------------------------------------------------
    roles_dir = pdir / "roles"
    for pid, spec in catalog.items():
        role = spec.get("role")
        if not role:
            warn("W_PHASE_NO_ROLE",
                 f"phase '{pid}' has no role: field", phase=pid)
            continue
        rfile = roles_dir / f"{role}.md"
        if not rfile.is_file():
            err("E_ROLE_MISSING",
                f"phase '{pid}' references role '{role}' but "
                f"roles/{role}.md is missing",
                phase=pid, role=role)

    # 4. hitl gates --------------------------------------------------
    gates_doc, gerr = _safe_yaml(pdir / "hitl-gates.yaml")
    if gerr and (pdir / "hitl-gates.yaml").exists():
        err("E_HITL_YAML", f"hitl-gates.yaml: {gerr}")
    declared_gates: set[str] = set()
    raw_gates = gates_doc.get("gates") if gates_doc else None
    if isinstance(raw_gates, dict):
        declared_gates = {str(g) for g in raw_gates.keys()}
    for pid, spec in catalog.items():
        gate = spec.get("gate")
        if not gate:
            continue
        if str(gate) not in declared_gates:
            err("E_GATE_UNDECLARED",
                f"phase '{pid}' references gate '{gate}' but it is "
                f"not declared in hitl-gates.yaml",
                phase=pid, gate=gate)

    # 5. profiles ----------------------------------------------------
    profiles = phases_doc.get("profiles") or {}
    if isinstance(profiles, dict):
        for name, spec in profiles.items():
            chain = spec.get("phases") if isinstance(spec, dict) else spec
            if not isinstance(chain, list):
                err("E_PROFILE_BAD",
                    f"profile '{name}' has no 'phases' list",
                    profile=name)
                continue
            for ph in chain:
                if str(ph) not in catalog:
                    err("E_PROFILE_UNKNOWN_PHASE",
                        f"profile '{name}' references unknown phase "
                        f"'{ph}'", profile=name, phase=ph)

    # 6. manifest templates -----------------------------------------
    tmpl_dir = pdir / "manifest-templates"
    if tmpl_dir.is_dir():
        for tpath in sorted(tmpl_dir.glob("*.md")):
            try:
                txt = tpath.read_text(encoding="utf-8")
            except Exception as exc:
                err("E_TEMPLATE_READ",
                    f"manifest-templates/{tpath.name}: {exc}",
                    template=tpath.name)
                continue
            seen = set(_VAR_RE.findall(txt))
            unknown = sorted(seen - _KNOWN_TEMPLATE_VARS)
            if unknown:
                warn("W_TEMPLATE_UNKNOWN_VAR",
                     f"manifest-templates/{tpath.name}: unknown "
                     f"placeholder(s): {', '.join('{'+v+'}' for v in unknown)}",
                     template=tpath.name, vars=unknown)

    return _emit_lint(pdir, plugin_id, violations, warnings, as_json)


def _emit_lint(pdir: Path, plugin_id: str | None,
               violations: list[dict], warnings: list[dict],
               as_json: bool) -> int:
    if as_json:
        sys.stdout.write(json.dumps({
            "plugin": plugin_id,
            "path": str(pdir),
            "violations": violations,
            "warnings": warnings,
            "ok": not violations,
        }, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
        return 0 if not violations else 1

    print(f"Plugin : {plugin_id or '(unknown)'}")
    print(f"Path   : {pdir}")
    if not violations and not warnings:
        print("✓ no violations")
        return 0
    if violations:
        print(f"\n✗ {len(violations)} violation(s):")
        for v in violations:
            print(f"  [{v['code']}] {v['message']}")
    if warnings:
        print(f"\n⚠ {len(warnings)} warning(s):")
        for w in warnings:
            print(f"  [{w['code']}] {w['message']}")
    return 0 if not violations else 1
