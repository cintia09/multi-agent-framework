"""Task state.json schema migrations.

Each migration is registered in :data:`MIGRATIONS` keyed by its source
version (e.g. ``1`` means "this migration upgrades v1 → v2"). Applying
``upgrade(state)`` walks the chain in order until ``state["schema_version"]``
equals :data:`CURRENT_SCHEMA_VERSION`.

Contracts:

* Migrations MUST be idempotent — re-running them on already-upgraded
  state is a no-op.
* Migrations MUST NOT raise on missing optional fields; degrade
  gracefully (this is recovery code, not validation).
* Migrations MUST set ``state["schema_version"]`` to their target
  version on success.

The :func:`upgrade` helper returns ``(new_state, applied_versions)``
where ``applied_versions`` is the list of source-version migrations
that ran (empty if state was already current).
"""
from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from . import v1_to_v2

CURRENT_SCHEMA_VERSION = 2

MIGRATIONS: Dict[int, Callable[[dict], dict]] = {
    1: v1_to_v2.migrate,
}


def upgrade(state: dict) -> Tuple[dict, List[int]]:
    """Walk migrations until *state* reaches CURRENT_SCHEMA_VERSION.

    Returns a (new_state, applied_versions) tuple. *applied_versions*
    is the list of source versions that were migrated from (empty
    when *state* was already current).
    """
    out = dict(state)
    applied: List[int] = []
    ver = out.get("schema_version", 1)
    cur = int(ver) if ver is not None else 1
    # R21 P1 fix: refuse to silently pass through state.json from a
    # future kernel — downgrades would otherwise corrupt data without
    # any warning. Caller can downgrade explicitly via cmd_upgrade.
    if cur > CURRENT_SCHEMA_VERSION:
        raise RuntimeError(
            f"state.json schema_version {cur} is newer than this kernel "
            f"supports (max {CURRENT_SCHEMA_VERSION}); refusing to load"
        )
    while cur < CURRENT_SCHEMA_VERSION:
        fn = MIGRATIONS.get(cur)
        if fn is None:
            raise RuntimeError(
                f"no migration registered for schema_version {cur} → "
                f"{cur + 1}"
            )
        out = fn(out)
        applied.append(cur)
        new_ver = out.get("schema_version", cur)
        new_cur = int(new_ver) if new_ver is not None else cur
        if new_cur <= cur:
            raise RuntimeError(
                f"migration {cur} → {cur + 1} did not advance "
                f"schema_version (still {new_cur})"
            )
        cur = new_cur
    return out, applied
