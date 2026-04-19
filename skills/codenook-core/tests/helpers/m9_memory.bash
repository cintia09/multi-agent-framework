#!/usr/bin/env bash
# Helpers for M9.1 memory-layer / memory-index bats suites.
#
# All paths are absolute. We rely on m9-* tests using $LIB_DIR for PYTHONPATH
# (mirrors m8-overlay.bats convention).

# Resolve once.
M9_LIB_DIR="$CORE_ROOT/skills/builtin/_lib"
M9_INIT_SKILL_SH="$CORE_ROOT/skills/builtin/init/init.sh"

export M9_LIB_DIR M9_INIT_SKILL_SH

# m9_py <python source> — run python with PYTHONPATH=$M9_LIB_DIR.
m9_py() {
  PYTHONPATH="$M9_LIB_DIR" python3 -c "$1"
}

# m9_seed_workspace — create a fresh workspace dir & return its path.
m9_seed_workspace() {
  local d
  d=$(make_scratch)
  mkdir -p "$d/.codenook"
  echo "$d"
}

# m9_init_memory <ws> — invoke the init skill against $ws.
m9_init_memory() {
  local ws="$1"
  ( cd "$ws" && bash "$M9_INIT_SKILL_SH" )
}

# m9_write_knowledge <ws> <topic> <summary> <tags-csv> <body>
m9_write_knowledge() {
  local ws="$1" topic="$2" summary="$3" tags_csv="$4" body="$5"
  PYTHONPATH="$M9_LIB_DIR" WS="$ws" TOPIC="$topic" SUMMARY="$summary" \
    TAGS="$tags_csv" BODY="$body" python3 - <<'PY'
import os
import memory_layer as ml
ws = os.environ["WS"]
topic = os.environ["TOPIC"]
tags = [t for t in os.environ["TAGS"].split(",") if t]
ml.write_knowledge(
    ws,
    topic=topic,
    summary=os.environ["SUMMARY"],
    tags=tags,
    body=os.environ["BODY"],
)
PY
}

# m9_seed_n_knowledge <ws> <n> — generate N minimal frontmatter knowledge files.
m9_seed_n_knowledge() {
  local ws="$1" n="$2"
  PYTHONPATH="$M9_LIB_DIR" WS="$ws" N="$n" python3 - <<'PY'
import os
import memory_layer as ml
ws = os.environ["WS"]
n = int(os.environ["N"])
body = "x" * 1024
for i in range(n):
    ml.write_knowledge(
        ws,
        topic=f"topic-{i:04d}",
        summary=f"summary {i}",
        tags=[f"t{i % 5}"],
        body=body,
    )
PY
}
