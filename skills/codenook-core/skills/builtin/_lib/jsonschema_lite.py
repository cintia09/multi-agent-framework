"""Tiny JSON-Schema validator (subset) — vendored for CodeNook M4.

Why vendor: PyPI `jsonschema` is not guaranteed installed in user
workspaces; runtime schemas are stable and only need a handful of
keywords. Keeping the validator in-tree removes a hard runtime dep.

Supported keywords (intentional subset):
  - type           ("object","array","string","integer","number","boolean","null")
                   may be a list of types (union, e.g. ["string","null"])
  - required       list of property names
  - properties     per-key sub-schemas
  - additionalProperties  bool (only `false` is enforced; default true)
  - enum           list of allowed values
  - minimum        numeric lower bound (inclusive)
  - items          single sub-schema applied to every array element

Anything else is silently ignored — keep this in mind when authoring
schemas: stick to the subset above for runtime guarantees, and use
external tools (ajv, etc.) for full draft-07 conformance in CI.
"""
from __future__ import annotations

import json
import sys
from typing import Any

_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}


class ValidationError(Exception):
    pass


def _check_type(instance: Any, t: Any, path: str) -> None:
    if isinstance(t, list):
        if not any(_matches(instance, one) for one in t):
            raise ValidationError(f"{path}: type {instance!r} not in {t}")
        return
    if not _matches(instance, t):
        raise ValidationError(f"{path}: expected type {t!r}, got {type(instance).__name__}")


def _matches(instance: Any, t: str) -> bool:
    types = _TYPE_MAP.get(t)
    if types is None:
        return True
    if t == "integer" and isinstance(instance, bool):
        return False
    if t == "number" and isinstance(instance, bool):
        return False
    return isinstance(instance, types)


def validate(instance: Any, schema: dict, path: str = "$") -> None:
    if "type" in schema:
        _check_type(instance, schema["type"], path)

    if "enum" in schema:
        if instance not in schema["enum"]:
            raise ValidationError(f"{path}: {instance!r} not in enum {schema['enum']}")

    if "minimum" in schema and isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if instance < schema["minimum"]:
            raise ValidationError(f"{path}: {instance} < minimum {schema['minimum']}")

    if isinstance(instance, dict):
        props = schema.get("properties", {})
        for req in schema.get("required", []):
            if req not in instance:
                raise ValidationError(f"{path}: missing required property {req!r}")
        if schema.get("additionalProperties") is False:
            extra = set(instance.keys()) - set(props.keys())
            if extra:
                raise ValidationError(f"{path}: unexpected properties {sorted(extra)}")
        for k, v in instance.items():
            if k in props:
                validate(v, props[k], f"{path}.{k}")

    if isinstance(instance, list) and "items" in schema:
        sub = schema["items"]
        for i, el in enumerate(instance):
            validate(el, sub, f"{path}[{i}]")


def _cli() -> int:
    if len(sys.argv) != 3:
        print("usage: jsonschema_lite.py <schema.json> <doc.json>", file=sys.stderr)
        return 2
    with open(sys.argv[1], "r", encoding="utf-8") as f:
        schema = json.load(f)
    with open(sys.argv[2], "r", encoding="utf-8") as f:
        doc = json.load(f)
    try:
        validate(doc, schema)
    except ValidationError as e:
        print(f"INVALID: {e}", file=sys.stderr)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
