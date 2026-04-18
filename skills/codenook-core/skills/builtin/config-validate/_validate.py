#!/usr/bin/env python3
"""config-validate core logic. Invoked by validate.sh.

Inputs (env):
  CN_CONFIG   path to merged config JSON (produced by config-resolve)
  CN_SCHEMA   path to config-schema.yaml
  CN_JSON     "1" to emit JSON on stdout, else plain

Exit codes:
  0 valid (warnings OK)
  1 validation errors
  2 usage / IO error
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("validate.sh: PyYAML not installed", file=sys.stderr)
    sys.exit(2)


def load_schema(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        print(f"validate.sh: schema malformed: {path}", file=sys.stderr)
        sys.exit(2)
    return data


def load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"validate.sh: config not valid JSON: {e}", file=sys.stderr)
            sys.exit(2)
    if not isinstance(data, dict):
        print("validate.sh: config top-level must be an object", file=sys.stderr)
        sys.exit(2)
    return data


def validate_field(value, spec: dict, path: str, errors: list) -> None:
    ftype = spec.get("type")
    if ftype == "string":
        if not isinstance(value, str):
            errors.append({"path": path, "msg": f"expected string, got {type(value).__name__}"})
            return
        ml = spec.get("min_length")
        if ml is not None and len(value) < ml:
            errors.append({"path": path, "msg": f"must be at least {ml} char(s)"})
        enum = spec.get("enum")
        if enum is not None and value not in enum:
            errors.append({"path": path, "msg": f"must be one of {enum}, got {value!r}"})
    elif ftype == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            errors.append({"path": path, "msg": f"expected integer, got {type(value).__name__}"})
            return
        mn = spec.get("min")
        if mn is not None and value < mn:
            errors.append({"path": path, "msg": f"must be >= {mn}, got {value}"})
    elif ftype == "object":
        if not isinstance(value, dict):
            errors.append({"path": path, "msg": f"expected object, got {type(value).__name__}"})
            return
        walk_object(value, spec.get("fields") or {}, path, errors)


def walk_object(obj: dict, fields: dict, prefix: str, errors: list) -> None:
    for name, spec in fields.items():
        fp = f"{prefix}.{name}" if prefix else name
        if name not in obj:
            if spec.get("required"):
                errors.append({"path": fp, "msg": "missing required field"})
            continue
        validate_field(obj[name], spec, fp, errors)


def main() -> int:
    cfg_path = Path(os.environ["CN_CONFIG"])
    schema_path = Path(os.environ["CN_SCHEMA"])
    as_json = os.environ.get("CN_JSON") == "1"

    schema = load_schema(schema_path)
    cfg = load_config(cfg_path)

    errors: list = []
    warnings: list = []

    walk_object(cfg, schema.get("fields") or {}, "", errors)

    for key in schema.get("deprecated") or []:
        if key in cfg:
            warnings.append({"path": key, "msg": "deprecated key"})

    if as_json:
        print(json.dumps({
            "ok": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
        }, indent=2))

    for w in warnings:
        print(f"warning: deprecated key: {w['path']}", file=sys.stderr)

    if errors:
        for e in errors:
            print(f"error: {e['path']}: {e['msg']}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
