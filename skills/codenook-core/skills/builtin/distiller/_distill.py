#!/usr/bin/env python3
"""distiller/_distill.py — route + audit a distilled knowledge artifact.

Inputs (env, set by distill.sh):
  CN_PLUGIN     plugin name owning the distillation
  CN_TOPIC      single-segment topic id (becomes filename stem)
  CN_CONTENT    path to the already-distilled markdown content
  CN_WORKSPACE  workspace root (the dir containing .codenook/)

Side effects:
  - writes <ws>/.codenook/{knowledge|memory/<plugin>}/by-topic/<topic>.md
  - appends a JSONL line to <ws>/.codenook/history/distillation-log.jsonl
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "_lib"))
from expr_eval import safe_eval, ExprError  # noqa: E402

try:
    import yaml  # PyYAML
except ImportError:
    print("distill.sh: PyYAML not installed", file=sys.stderr)
    sys.exit(2)


SAFE_TOPIC_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def die(msg: str, code: int = 1) -> None:
    print(f"distill.sh: {msg}", file=sys.stderr)
    sys.exit(code)


def now_iso() -> str:
    return dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".distill-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def main() -> None:
    plugin = os.environ["CN_PLUGIN"]
    topic = os.environ["CN_TOPIC"]
    content_path = Path(os.environ["CN_CONTENT"])
    ws = Path(os.environ["CN_WORKSPACE"]).resolve()

    if not SAFE_TOPIC_RE.match(topic):
        die(f"unsafe topic id: {topic!r}", 2)

    plugin_yaml_path = ws / ".codenook/plugins" / plugin / "plugin.yaml"
    rules: list[str] = []
    if plugin_yaml_path.is_file():
        with plugin_yaml_path.open("r", encoding="utf-8") as f:
            try:
                manifest = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                die(f"plugin.yaml parse error: {e}")
        if isinstance(manifest, dict):
            knowledge = manifest.get("knowledge") or {}
            produces = (knowledge.get("produces") or {}) if isinstance(knowledge, dict) else {}
            raw_rules = produces.get("promote_to_workspace_when") or [] if isinstance(produces, dict) else []
            if isinstance(raw_rules, list):
                rules = [str(r) for r in raw_rules]

    body = content_path.read_text(encoding="utf-8", errors="replace")
    byte_size = content_path.stat().st_size

    ctx = {
        "topic": topic,
        "plugin": plugin,
        "byte_size": byte_size,
        "has_examples": "```" in body,
    }

    rule_matched = False
    for rule in rules:
        try:
            if safe_eval(rule, ctx):
                rule_matched = True
                break
        except ExprError as e:
            die(f"unsafe expression rejected: {e}", 1)

    if rule_matched:
        target_root = ws / ".codenook/knowledge"
    else:
        target_root = ws / ".codenook/memory" / plugin

    out_path = target_root / "by-topic" / f"{topic}.md"
    file_text = f"# {topic}\n\n{body}"
    if not file_text.endswith("\n"):
        file_text += "\n"
    atomic_write_text(out_path, file_text)

    log_dir = ws / ".codenook/history"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_line = {
        "ts": now_iso(),
        "plugin": plugin,
        "topic": topic,
        "target_root": str(target_root.relative_to(ws)),
        "rule_matched": rule_matched,
        "_content_bytes": byte_size,
    }
    with (log_dir / "distillation-log.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_line, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
