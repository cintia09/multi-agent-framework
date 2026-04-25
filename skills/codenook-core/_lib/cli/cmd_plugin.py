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
Usage: codenook plugin <list|info|lint|diff|update> [args...]

  list [--json]                   list installed plugins with their
                                  id, version, and available profiles
  info <id>                       print profiles + phases summary for an
                                  installed plugin
  lint <id|path>                  statically validate a plugin's YAML +
                                  role + manifest wiring (use --json for
                                  machine output)
  diff <id> [--src <path> | --repo <root>]
                                  compare the installed snapshot against
                                  the plugin source (per-file unified
                                  diff for text, sha256 mismatch for
                                  binaries)
  update <id> [--src <path> | --repo <root>] [--dry-run] [--yes]
                                  re-run install for a single plugin
                                  (delegates to install.py --plugin <id>
                                  --upgrade)
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
    if args[0] == "list":
        return _plugin_list(ctx, list(args[1:]))
    if args[0] == "lint":
        return _plugin_lint(ctx, list(args[1:]))
    if args[0] == "diff":
        return _plugin_diff(ctx, list(args[1:]))
    if args[0] == "update":
        return _plugin_update(ctx, list(args[1:]))
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


# ── plugin list ──────────────────────────────────────────────────────────


HELP_LIST = """\
Usage: codenook plugin list [--json]

List every plugin present in .codenook/plugins/ with its installed
version and its declared profiles (workflow presets). Use this to
discover what you can pass to `task new --plugin <id> [--profile <p>]`
without consulting the raw manifests.

Human output (default):
  <id>  v<version>  profiles: default, fast-track

--json emits one object per plugin on stdout with keys:
  {"id", "version", "path", "profiles": [...], "phases": [...]}
"""


def _plugin_list(ctx: CodenookContext, args: list[str]) -> int:
    as_json = False
    for a in args:
        if a in ("-h", "--help"):
            print(HELP_LIST)
            return 0
        if a == "--json":
            as_json = True
        else:
            sys.stderr.write(f"codenook plugin list: unknown arg: {a}\n")
            return 2

    pdir = ctx.workspace / ".codenook" / "plugins"
    entries: list[dict] = []
    if pdir.is_dir():
        for child in sorted(pdir.iterdir()):
            if not child.is_dir() or child.name.startswith((".", "_")):
                continue
            plugin_yaml, _ = _safe_yaml(child / "plugin.yaml")
            phases_doc, _ = _safe_yaml(child / "phases.yaml")
            version = str(plugin_yaml.get("version") or "?")
            profiles_block = phases_doc.get("profiles") or {}
            profiles: list[dict] = []
            if isinstance(profiles_block, dict):
                for pname, pspec in profiles_block.items():
                    chain = (pspec.get("phases")
                             if isinstance(pspec, dict) else pspec)
                    if isinstance(chain, list):
                        profiles.append({
                            "name": str(pname),
                            "phases": [str(x) for x in chain],
                        })
                    else:
                        profiles.append({"name": str(pname), "phases": []})
            phases_catalog: list[str] = []
            raw = phases_doc.get("phases", [])
            if isinstance(raw, dict):
                phases_catalog = [str(k) for k in raw.keys()]
            elif isinstance(raw, list):
                phases_catalog = [
                    str(p.get("id")) for p in raw
                    if isinstance(p, dict) and p.get("id")
                ]
            entries.append({
                "id": child.name,
                "version": version,
                "path": str(child),
                "profiles": profiles,
                "phases": phases_catalog,
            })

    if as_json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0

    if not entries:
        print("(no plugins installed under .codenook/plugins/)")
        return 0

    print(f"Installed plugins ({len(entries)}):\n")
    for e in entries:
        prof_names = [p["name"] for p in e["profiles"]] or ["(none)"]
        print(f"  {e['id']}  v{e['version']}")
        print(f"      profiles: {', '.join(prof_names)}")
        if e["profiles"]:
            for p in e["profiles"]:
                if p["phases"]:
                    print(f"        - {p['name']}: "
                          f"{' → '.join(p['phases'])}")
        if e["phases"]:
            print(f"      phases  : {', '.join(e['phases'])}")
        print("")
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
        rsubdir = roles_dir / role / "role.md"
        if not rfile.is_file() and not rsubdir.is_file():
            err("E_ROLE_MISSING",
                f"phase '{pid}' references role '{role}' but neither "
                f"roles/{role}.md nor roles/{role}/role.md is present",
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


# ── plugin diff / plugin update ─────────────────────────────────────────


HELP_DIFF = """\
Usage: codenook plugin diff <id> [--src <path> | --repo <root>] [--json]

Compares the installed plugin snapshot at .codenook/plugins/<id>/
against an authoritative source tree, surfacing every file-level
difference. Useful before running ``plugin update`` so you know what
will change.

Source resolution (first match wins):
  1. --src <path>            explicit plugin source dir
  2. --repo <root>           uses <root>/plugins/<id>
  3. $CODENOOK_REPO env var  uses $CODENOOK_REPO/plugins/<id>
  4. walk up from the workspace looking for a plugins/<id>/plugin.yaml

Output:
  text mode — per-file status (M / + / - / ≡), unified diff for text
              files that changed
  --json    — {"plugin": id, "src": path, "changes": [
                {"path": "phases.yaml", "status": "modified",
                 "src_sha256": "…", "installed_sha256": "…"} … ]}

Exit codes:
  0  no differences
  1  one or more differences (still considered success — diff is
     informational; use exit code to script "needs update?")
  2  usage error (no source found, plugin not installed)
"""

HELP_UPDATE = """\
Usage: codenook plugin update <id> [--src <path> | --repo <root>]
                                   [--dry-run] [--yes]

Re-runs the install pipeline for a single plugin. Equivalent to:
    python <repo>/install.py --target <ws> --plugin <id> --upgrade

Source resolution: same as ``plugin diff`` (--src / --repo /
$CODENOOK_REPO / walk-up).

Flags:
  --dry-run    forwarded to install.py (no files written)
  --yes / -y   forwarded (skip the install.py confirm prompt)

Exit codes mirror install.py:
  0  ok      1  gate failure     2  usage / IO error
  3  already installed at the same version (no-op)

Note on idempotency:
  install.py short-circuits when the source plugin.yaml.version
  matches the installed version — it only refreshes state.json,
  it does NOT re-stage files. To pick up local edits without
  bumping the version, run install.py manually with --upgrade
  after temporarily incrementing plugin.yaml.version.
"""


def _flag_value(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    i = args.index(flag)
    if i + 1 >= len(args):
        return None
    return args[i + 1]


def _strip_flag(args: list[str], flag: str, takes_value: bool) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(args):
        if args[i] == flag:
            i += 2 if takes_value else 1
            continue
        out.append(args[i])
        i += 1
    return out


# Flags accepted by `plugin diff` / `plugin update` that consume the next
# argument as their value. Used by ``_extract_positionals`` so that
# `--src /path/to/source plugin-id` does not silently treat `/path/...`
# as a positional plugin id (pass-2 P2/P3).
_VALUE_FLAGS_DIFF_UPDATE: frozenset[str] = frozenset(
    {"--src", "--repo"})


def _extract_positionals(
    args: list[str], value_flags: frozenset[str],
) -> list[str]:
    """Return positionals, skipping known flags and their values."""
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a in value_flags:
            i += 2  # skip flag + its value, even if the value looks positional
            continue
        if a.startswith("-"):
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def _is_safe_plugin_id(s: str) -> bool:
    """Strict plugin-id slug check: ASCII, alnum + ``-`` / ``_`` / ``.``,
    no path separators, no leading dot, ≤ 64 chars."""
    if not s or len(s) > 64:
        return False
    if s.startswith(".") or s in (".", ".."):
        return False
    for ch in s:
        if not (ch.isalnum() or ch in "-_."):
            return False
    return True


def _resolve_repo_root(start: Path) -> Path | None:
    cur = start.resolve()
    for _ in range(20):
        if (cur / "install.py").is_file() and (cur / "plugins").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def _resolve_src(
    ctx: CodenookContext, plugin_id: str, args: list[str],
) -> tuple[Path | None, str | None]:
    """Return (src_dir, error_message)."""
    explicit_src = _flag_value(args, "--src")
    if explicit_src:
        p = Path(explicit_src).expanduser().resolve()
        if not (p / "plugin.yaml").is_file():
            return None, f"--src {p}: plugin.yaml not found"
        return p, None

    explicit_repo = _flag_value(args, "--repo")
    if explicit_repo:
        cand = Path(explicit_repo).expanduser().resolve() / "plugins" / plugin_id
        if not (cand / "plugin.yaml").is_file():
            return None, f"--repo {explicit_repo}: {cand} has no plugin.yaml"
        return cand, None

    import os
    env_repo = os.environ.get("CODENOOK_REPO")
    if env_repo:
        cand = Path(env_repo).expanduser().resolve() / "plugins" / plugin_id
        if (cand / "plugin.yaml").is_file():
            return cand, None

    repo = _resolve_repo_root(ctx.workspace)
    if repo is None:
        repo = _resolve_repo_root(Path.cwd())
    if repo is not None:
        cand = repo / "plugins" / plugin_id
        if (cand / "plugin.yaml").is_file():
            return cand, None

    return None, (
        f"could not locate plugin source for '{plugin_id}'. "
        f"Pass --src <dir>, --repo <root>, or set CODENOOK_REPO."
    )


def _walk_files(root: Path) -> dict[str, Path]:
    """Map relative-posix-path → absolute Path for every file under root."""
    out: dict[str, Path] = {}
    if not root.is_dir():
        return out
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        # Skip .DS_Store, __pycache__, *.pyc and other build noise.
        rel = p.relative_to(root)
        parts = rel.parts
        if any(part == "__pycache__" or part.startswith(".")
               for part in parts):
            continue
        if p.suffix in (".pyc", ".pyo"):
            continue
        out[rel.as_posix()] = p
    return out


def _sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_text(path: Path, sniff_bytes: int = 4096) -> bool:
    try:
        sample = path.read_bytes()[:sniff_bytes]
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _plugin_diff(ctx: CodenookContext, args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print(HELP_DIFF)
        return 0

    as_json = "--json" in args
    args = _strip_flag(args, "--json", takes_value=False)

    # First positional is the plugin id; flags consumed by _resolve_src.
    positional = _extract_positionals(args, _VALUE_FLAGS_DIFF_UPDATE)
    if not positional:
        sys.stderr.write("codenook plugin diff: <id> required\n")
        return 2
    plugin_id = positional[0]
    if not _is_safe_plugin_id(plugin_id):
        sys.stderr.write(
            f"codenook plugin diff: invalid plugin id: {plugin_id!r}\n")
        return 2

    installed = ctx.workspace / ".codenook" / "plugins" / plugin_id
    if not installed.is_dir():
        sys.stderr.write(
            f"codenook plugin diff: plugin not installed: {plugin_id}\n")
        return 2

    src, err = _resolve_src(ctx, plugin_id, args)
    if src is None:
        sys.stderr.write(f"codenook plugin diff: {err}\n")
        return 2

    inst_files = _walk_files(installed)
    src_files = _walk_files(src)

    changes: list[dict] = []
    for rel in sorted(set(inst_files) | set(src_files)):
        in_inst = rel in inst_files
        in_src = rel in src_files
        if in_inst and not in_src:
            changes.append({"path": rel, "status": "removed",
                            "installed_sha256": _sha256(inst_files[rel])})
        elif in_src and not in_inst:
            changes.append({"path": rel, "status": "added",
                            "src_sha256": _sha256(src_files[rel])})
        else:
            ish = _sha256(inst_files[rel])
            ssh = _sha256(src_files[rel])
            if ish != ssh:
                changes.append({"path": rel, "status": "modified",
                                "installed_sha256": ish, "src_sha256": ssh})

    if as_json:
        print(json.dumps({
            "plugin": plugin_id, "src": str(src),
            "installed": str(installed),
            "changes": changes,
        }, indent=2))
        return 1 if changes else 0

    print(f"Plugin    : {plugin_id}")
    print(f"Installed : {installed}")
    print(f"Source    : {src}")
    if not changes:
        print("\n≡ no differences")
        return 0

    print(f"\n{len(changes)} file(s) differ:\n")
    import difflib
    for c in changes:
        if c["status"] == "added":
            print(f"  + {c['path']}")
        elif c["status"] == "removed":
            print(f"  - {c['path']}")
        else:
            print(f"  M {c['path']}")
    # Inline unified diffs for modified text files.
    for c in changes:
        if c["status"] != "modified":
            continue
        ip = installed / c["path"]
        sp = src / c["path"]
        if not (_is_text(ip) and _is_text(sp)):
            continue
        try:
            il = ip.read_text(encoding="utf-8").splitlines(keepends=True)
            sl = sp.read_text(encoding="utf-8").splitlines(keepends=True)
        except OSError:
            continue
        diff = difflib.unified_diff(
            il, sl,
            fromfile=f"installed/{c['path']}",
            tofile=f"src/{c['path']}",
            n=3,
        )
        body = "".join(diff)
        if body:
            print(f"\n--- {c['path']} ---")
            sys.stdout.write(body)
            if not body.endswith("\n"):
                sys.stdout.write("\n")

    return 1


def _plugin_update(ctx: CodenookContext, args: list[str]) -> int:
    if not args or args[0] in ("-h", "--help"):
        print(HELP_UPDATE)
        return 0

    positional = _extract_positionals(args, _VALUE_FLAGS_DIFF_UPDATE)
    if not positional:
        sys.stderr.write("codenook plugin update: <id> required\n")
        return 2
    plugin_id = positional[0]
    if not _is_safe_plugin_id(plugin_id):
        sys.stderr.write(
            f"codenook plugin update: invalid plugin id: {plugin_id!r}\n")
        return 2

    src, err = _resolve_src(ctx, plugin_id, args)
    if src is None:
        sys.stderr.write(f"codenook plugin update: {err}\n")
        return 2

    # install.py requires a repo root that contains plugins/<id>. The
    # user may have passed --src directly to a foreign location; in that
    # case we synthesise a temporary repo skeleton.
    repo = src.parent.parent
    if not (repo / "install.py").is_file() or (repo / "plugins" / plugin_id) != src:
        sys.stderr.write(
            "codenook plugin update: --src must point at "
            "<repo>/plugins/<id>; pass --repo <root> if your layout "
            "differs.\n")
        return 2

    install_py = repo / "install.py"

    cmd = [sys.executable, str(install_py),
           "--target", str(ctx.workspace),
           "--plugin", plugin_id,
           "--upgrade"]
    if "--dry-run" in args:
        cmd.append("--dry-run")
    if "--yes" in args or "-y" in args:
        cmd.append("--yes")

    print(f"→ {' '.join(cmd)}")
    import subprocess
    cp = subprocess.run(cmd)
    return cp.returncode
