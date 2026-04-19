---
task_id: T-042
created_at: 2026-05-12T10:11:00Z
started_at: 2026-05-12T10:11:00Z
state: drafting
turn_count: 2
draft_config_path: ./draft-config.yaml
selected_plugin: development
last_router_action: reply
decisions:
  - ts: 2026-05-12T10:11:18Z
    turn: 1
    kind: plugin_pick
    detail: "Tentative pick: development."
  - ts: 2026-05-12T10:13:02Z
    turn: 2
    kind: clarification
    detail: "Asked user to confirm target_dir."
---

### user (2026-05-12T10:11:00Z)

Add a `--tag` filter to the xueba CLI `list` command. Multi-value,
comma-separated, AND'd.

### router (2026-05-12T10:11:18Z)

Use the **development** plugin? Two questions:

1. Target dir is `~/code/xueba/`?
2. Require new tests?

### user (2026-05-12T10:13:02Z)

Yes to both.
