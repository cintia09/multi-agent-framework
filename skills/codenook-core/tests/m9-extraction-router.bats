#!/usr/bin/env bats
# Task-relevance routing tests for extractor-batch (routing feature).
#
# TC-ROUTE-01: mock LLM returns task_specific → artefact goes to task extracted dir
# TC-ROUTE-02: mock LLM failure / fallback → artefacts go to memory/ (cross_task)
# TC-ROUTE-03: route_fallback=true appears in extraction log on LLM error

load helpers/load
load helpers/assertions
load helpers/m9_memory

BATCH_SH="$CORE_ROOT/skills/builtin/extractor-batch/extractor-batch.sh"

# Build a fake lookup root with a real knowledge-extractor stub that records
# its route env var and creates a placeholder artefact.
seed_routing_lookup() {
  local ws="$1"
  local lookup="$ws/_extractors"
  mkdir -p "$lookup/knowledge-extractor"
  cat > "$lookup/knowledge-extractor/extract.sh" <<STUB
#!/usr/bin/env bash
# Record the route env var passed by extractor-batch.sh
echo "ROUTE=\${CN_EXTRACTION_ROUTE_KNOWLEDGE:-cross_task}" \
  >> "$ws/route-calls.log"
# Parse --task-id arg for path construction.
task_id=""
while [ \$# -gt 0 ]; do
  case "\$1" in
    --task-id) task_id="\$2"; shift 2 ;;
    *) shift ;;
  esac
done
if [ "\${CN_EXTRACTION_ROUTE_KNOWLEDGE:-cross_task}" = "task_specific" ]; then
  mkdir -p "$ws/.codenook/tasks/\${task_id}/extracted/knowledge"
  printf '%s\n' "---" "topic: test-note" "---" "body" \
    > "$ws/.codenook/tasks/\${task_id}/extracted/knowledge/test-note.md"
else
  mkdir -p "$ws/.codenook/memory/knowledge"
  printf '%s\n' "---" "topic: test-note" "---" "body" \
    > "$ws/.codenook/memory/knowledge/test-note.md"
fi
STUB
  chmod +x "$lookup/knowledge-extractor/extract.sh"
  for name in skill-extractor config-extractor; do
    mkdir -p "$lookup/$name"
    printf '#!/usr/bin/env bash\ntrue\n' > "$lookup/$name/extract.sh"
    chmod +x "$lookup/$name/extract.sh"
  done
  echo "$lookup"
}

@test "[route] TC-ROUTE-01 task_specific route: artefact lands in task extracted dir" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(seed_routing_lookup "$ws")
  tid="T-ROUTE01"

  mock_resp='{"knowledge":"task_specific","skill":"task_specific","config":"task_specific","route_fallback":false}'
  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" \
         CN_LLM_MOCK_EXTRACTION_ROUTE="$mock_resp" \
         CN_LLM_MODE="mock" \
      bash "$BATCH_SH" --task-id "$tid" --reason after_phase \
           --workspace "$ws" --phase clarify
  [ "$status" -eq 0 ] || { echo "batch exit=$status out=$output"; return 1; }

  sleep 1.5

  [ -f "$ws/route-calls.log" ] || { echo "route-calls.log not created"; return 1; }
  grep -q "ROUTE=task_specific" "$ws/route-calls.log" \
    || { echo "expected task_specific route, got: $(cat "$ws/route-calls.log")"; return 1; }
}

@test "[route] TC-ROUTE-02 LLM failure → fallback to cross_task route" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(seed_routing_lookup "$ws")
  tid="T-ROUTE02"

  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" \
         CN_LLM_MOCK_ERROR_EXTRACTION_ROUTE="simulated router error" \
         CN_LLM_MODE="mock" \
      bash "$BATCH_SH" --task-id "$tid" --reason after_phase \
           --workspace "$ws" --phase clarify
  [ "$status" -eq 0 ] || { echo "batch exit=$status out=$output"; return 1; }

  sleep 1.5

  [ -f "$ws/route-calls.log" ] || { echo "route-calls.log not created"; return 1; }
  grep -q "ROUTE=cross_task" "$ws/route-calls.log" \
    || { echo "expected cross_task fallback route, got: $(cat "$ws/route-calls.log")"; return 1; }
}

@test "[route] TC-ROUTE-03 route_fallback logged on LLM error" {
  ws=$(m9_seed_workspace); m9_init_memory "$ws"
  lookup=$(seed_routing_lookup "$ws")
  tid="T-ROUTE03"

  run env CN_EXTRACTOR_LOOKUP_ROOT="$lookup" \
         CN_LLM_MOCK_ERROR_EXTRACTION_ROUTE="router error" \
         CN_LLM_MODE="mock" \
      bash "$BATCH_SH" --task-id "$tid" --reason after_phase \
           --workspace "$ws" --phase clarify
  [ "$status" -eq 0 ] || { echo "batch exit=$status out=$output"; return 1; }

  route_files=("$ws/.codenook/memory/history"/.route-*.json)
  [ "${#route_files[@]}" -ge 1 ] || { echo "no .route-*.json file found"; return 1; }
  route_file="${route_files[0]}"
  [ -f "$route_file" ] || { echo "route file not found: $route_file"; return 1; }
  route_fallback=$(jq -r '.route_fallback' "$route_file" 2>/dev/null || echo "")
  [ "$route_fallback" = "true" ] \
    || { echo "expected route_fallback=true, got: $route_fallback from $route_file"; return 1; }
}
