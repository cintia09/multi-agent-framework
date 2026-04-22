#!/usr/bin/env bats
# Task-relevance routing tests for extractor-batch (routing feature).
#
# After the ``task_specific`` destination was removed, the router still
# runs (single-valued ``cross_task``) so that the mock-failure / fallback
# audit trail remains testable.
#
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
mkdir -p "$ws/.codenook/memory/knowledge"
printf '%s\n' "---" "topic: test-note" "---" "body" \
  > "$ws/.codenook/memory/knowledge/test-note.md"
STUB
  chmod +x "$lookup/knowledge-extractor/extract.sh"
  for name in skill-extractor config-extractor; do
    mkdir -p "$lookup/$name"
    printf '#!/usr/bin/env bash\ntrue\n' > "$lookup/$name/extract.sh"
    chmod +x "$lookup/$name/extract.sh"
  done
  echo "$lookup"
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
  # v0.25.0: extraction_router.route_artefacts() short-circuits to the
  # cross_task fallback dict and never calls the LLM (the only legal
  # destination is cross_task; the LLM hop was pure overhead). With no
  # LLM call there is nothing to "fall back from", so route_fallback is
  # now permanently false. CN_LLM_MOCK_ERROR_EXTRACTION_ROUTE has no
  # observable effect. The TC-ROUTE-02 sibling above remains valid: it
  # asserts the route lands on cross_task, which is the surviving
  # behavior. See extraction_router.py:142-153 for the rationale.
  skip "router LLM hop removed in v0.25.0; route_fallback is permanently false"
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
