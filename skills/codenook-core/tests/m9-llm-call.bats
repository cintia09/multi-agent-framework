#!/usr/bin/env bats
# M9.3 — _lib/llm_call.py wrapper.
# Spec: docs/memory-and-extraction.md §6 (decision LLM)
# Plan: post-decision #3 (mock-first wrapper, env-gated real backend)

load helpers/load
load helpers/assertions
load helpers/m9_memory

# Run python3 with PYTHONPATH and arbitrary env vars (caller passes
# `VAR=val ... -- code`).  Use this instead of `env` directly because
# `env -u` must lead the arg list and we need fine-grained control.
py_run() {
  local code="${@: -1}"
  local args=("${@:1:$#-1}")
  PYTHONPATH="$M9_LIB_DIR" env "${args[@]}" python3 -c "$code"
}

# py_run_unset: same but first prunes given vars, then sets others.
# Usage: py_run_unset VAR1 VAR2 -- VAR3=val python_code
py_run_unset() {
  local unsets=()
  while [ "$1" != "--" ] && [ $# -gt 0 ]; do
    unsets+=(-u "$1"); shift
  done
  shift  # drop the --
  local code="${@: -1}"
  local sets=("${@:1:$#-1}")
  env "${unsets[@]}" PYTHONPATH="$M9_LIB_DIR" "${sets[@]}" python3 -c "$code"
}

@test "[m9.3] llm_call mock returns CN_LLM_MOCK_RESPONSE verbatim" {
  run py_run CN_LLM_MOCK_RESPONSE='hello-world' "
import llm_call
print(llm_call.call_llm('any prompt', call_name='extract'))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = "hello-world" ] || { echo "got: $output"; return 1; }
}

@test "[m9.3] llm_call mock prefers per-call dir over generic env" {
  ws=$(make_scratch)
  mkdir -p "$ws/_mock"
  printf '{"action":"merge","rationale":"fixture"}' > "$ws/_mock/decide.json"
  run py_run CN_LLM_MOCK_DIR="$ws/_mock" CN_LLM_MOCK_RESPONSE='generic' "
import llm_call
print(llm_call.call_llm('p', call_name='decide'))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = '{"action":"merge","rationale":"fixture"}' ] \
    || { echo "got: $output"; return 1; }
}

@test "[m9.3] llm_call mock falls back to deterministic placeholder" {
  run py_run_unset CN_LLM_MOCK_RESPONSE CN_LLM_MOCK_DIR CN_LLM_MOCK_FILE \
       CN_LLM_MOCK_ERROR CN_LLM_MOCK_EXTRACT -- "
import llm_call
print(llm_call.call_llm('the quick brown fox jumps', call_name='extract'))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  case "$output" in
    "[mock-llm:extract] "*) :;;
    *) echo "got: $output"; return 1;;
  esac
}

@test "[m9.3] llm_call mock supports CN_LLM_MOCK_FILE" {
  ws=$(make_scratch)
  echo 'from-file' > "$ws/payload.txt"
  run py_run_unset CN_LLM_MOCK_RESPONSE CN_LLM_MOCK_DIR -- \
       CN_LLM_MOCK_FILE="$ws/payload.txt" "
import llm_call
print(llm_call.call_llm('p', call_name='x').rstrip())
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = 'from-file' ] || { echo "got: $output"; return 1; }
}

@test "[m9.3] llm_call mock per-call env override wins" {
  run py_run CN_LLM_MOCK_EXTRACT='per-call' CN_LLM_MOCK_RESPONSE='generic' "
import llm_call
print(llm_call.call_llm('p', call_name='extract'))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = 'per-call' ] || { echo "got: $output"; return 1; }
}

@test "[m9.3] llm_call mock raises on injected error (per-call)" {
  run py_run CN_LLM_MOCK_ERROR_DECIDE='timeout' "
import llm_call
try:
    llm_call.call_llm('p', call_name='decide')
    print('NO_RAISE')
except RuntimeError as e:
    print('RAISED:' + str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = 'RAISED:timeout' ] || { echo "got: $output"; return 1; }
}

@test "[m9.3] llm_call mock raises on injected error (generic)" {
  run py_run CN_LLM_MOCK_ERROR='boom' "
import llm_call
try:
    llm_call.call_llm('p', call_name='decide')
    print('NO_RAISE')
except RuntimeError as e:
    print('RAISED:' + str(e))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = 'RAISED:boom' ] || { echo "got: $output"; return 1; }
}

@test "[m9.3] llm_call rejects unknown mode" {
  run py_run "
import llm_call
try:
    llm_call.call_llm('p', call_name='x', mode='bogus')
    print('NO_RAISE')
except ValueError as e:
    print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = 'OK' ] || { echo "got: $output"; return 1; }
}

@test "[m9.3] llm_call default mode resolves to mock when CN_LLM_MODE unset" {
  run py_run_unset CN_LLM_MODE -- CN_LLM_MOCK_RESPONSE='ok' "
import llm_call
print(llm_call.call_llm('p'))
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = 'ok' ] || { echo "got: $output"; return 1; }
}

@test "[m9.3] llm_call rejects non-string prompt" {
  run py_run "
import llm_call
try:
    llm_call.call_llm(123)
    print('NO_RAISE')
except TypeError:
    print('OK')
"
  [ "$status" -eq 0 ] || { echo "$output"; return 1; }
  [ "$output" = 'OK' ] || { echo "got: $output"; return 1; }
}
