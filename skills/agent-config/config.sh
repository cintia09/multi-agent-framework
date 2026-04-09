#!/usr/bin/env bash
set -euo pipefail

# Multi-Agent Framework — Agent Configuration Helper
# Supports model and tools configuration across all platforms.
#
# Usage:
#   config.sh list                           — Show all agent config (model + tools)
#   config.sh get <agent>                    — Show full config for one agent
#   config.sh model set <agent> <model>      — Set model for an agent
#   config.sh model set-all <model>          — Set model for all agents
#   config.sh model reset <agent>            — Reset model to system default
#   config.sh model reset-all               — Reset all models
#   config.sh tools get <agent>              — Show tools for an agent
#   config.sh tools set <agent> <t1,t2,...>  — Set tools (comma-separated)
#   config.sh tools add <agent> <tool>       — Add a tool to agent
#   config.sh tools rm <agent> <tool>        — Remove a tool from agent
#   config.sh tools reset <agent>            — Remove tools restriction (all tools)
#   config.sh platforms                      — Show detected platforms

BUILTIN_AGENTS=(acceptor designer implementer reviewer tester)

# ── Platform Detection ──────────────────────────────────────────
detect_dirs() {
    local dirs=()
    [ -d "${HOME}/.claude/agents" ] && dirs+=("${HOME}/.claude/agents")
    [ -d "${HOME}/.copilot/agents" ] && dirs+=("${HOME}/.copilot/agents")
    [ -d ".agents" ] && dirs+=(".agents")
    [ -d ".github/agents" ] && dirs+=(".github/agents")
    echo "${dirs[@]}"
}

# Discover all unique agent names across all platforms
discover_agents() {
    local dirs agents_seen=()
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        for f in "${dir}/"*.agent.md; do
            [ -f "$f" ] || continue
            local name
            name=$(basename "$f" .agent.md)
            # Deduplicate
            local found=false
            for seen in "${agents_seen[@]+"${agents_seen[@]}"}"; do
                [ "$seen" = "$name" ] && found=true && break
            done
            [ "$found" = false ] && agents_seen+=("$name")
        done
    done
    echo "${agents_seen[@]+"${agents_seen[@]}"}"
}

# ── YAML Field Read/Write ──────────────────────────────────────
get_field() {
    local file="$1" field="$2"
    if [ -f "$file" ]; then
        sed -n '/^---$/,/^---$/p' "$file" | grep "^${field}:" | head -1 | sed "s/^${field}: *//; s/^\"//; s/\"$//"
    fi
}

set_field() {
    local file="$1" field="$2" value="$3"
    [ ! -f "$file" ] && return 1
    if grep -q "^${field}:" "$file"; then
        sed -i '' "s|^${field}:.*|${field}: \"${value}\"|" "$file"
    else
        sed -i '' "/^description:/a\\
${field}: \"${value}\"" "$file"
    fi
}

# ── Tools Field (YAML array) ──────────────────────────────────
get_tools() {
    local file="$1"
    if [ -f "$file" ]; then
        local line
        line=$(sed -n '/^---$/,/^---$/p' "$file" | grep '^tools:' | head -1)
        if [ -n "$line" ]; then
            echo "$line" | sed 's/^tools: *//; s/\[//; s/\]//; s/"//g; s/ *, */,/g'
        fi
    fi
}

set_tools_field() {
    local file="$1" tools_csv="$2"
    [ ! -f "$file" ] && return 1
    # Convert csv to YAML array: tool1,tool2 → ["tool1", "tool2"]
    local yaml_array
    if [ -z "$tools_csv" ]; then
        # Remove tools field entirely (unrestricted)
        if grep -q '^tools:' "$file"; then
            sed -i '' '/^tools:/d' "$file"
        fi
        return 0
    fi
    yaml_array=$(echo "$tools_csv" | sed 's/,/", "/g; s/^/["/; s/$/"]/')
    if grep -q '^tools:' "$file"; then
        sed -i '' "s|^tools:.*|tools: ${yaml_array}|" "$file"
    else
        sed -i '' "/^description:/a\\
tools: ${yaml_array}" "$file"
    fi
}

# ── Validation ──────────────────────────────────────────────────
validate_agent() {
    local agent="$1"
    local all_agents
    read -ra all_agents <<< "$(discover_agents)"
    for a in "${all_agents[@]+"${all_agents[@]}"}"; do
        [ "$a" = "$agent" ] && return 0
    done
    echo "❌ Unknown agent: ${agent}"
    echo "   Detected agents: ${all_agents[*]+"${all_agents[*]}"}"
    exit 1
}

# ── Commands ────────────────────────────────────────────────────
cmd_list() {
    echo "📋 Agent Configuration"
    echo ""
    local dirs all_agents
    read -ra dirs <<< "$(detect_dirs)"
    read -ra all_agents <<< "$(discover_agents)"
    for dir in "${dirs[@]}"; do
        echo "  📁 ${dir}:"
        for agent in "${all_agents[@]+"${all_agents[@]}"}"; do
            local file="${dir}/${agent}.agent.md"
            if [ -f "$file" ]; then
                local model hint tools
                model=$(get_field "$file" "model")
                hint=$(get_field "$file" "model_hint")
                tools=$(get_tools "$file")
                printf "    %-20s" "$agent"
                if [ -n "$model" ]; then
                    printf "model=%-20s" "$model"
                else
                    printf "model=%-20s" "(default)"
                fi
                if [ -n "$tools" ]; then
                    printf "tools=[%s]" "$tools"
                else
                    printf "tools=(all)"
                fi
                echo ""
            fi
        done
        echo ""
    done
}

cmd_get() {
    local agent="$1"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            local model hint tools desc
            model=$(get_field "$file" "model")
            hint=$(get_field "$file" "model_hint")
            tools=$(get_tools "$file")
            desc=$(get_field "$file" "description")
            echo "📁 ${dir}/${agent}.agent.md"
            echo "  description: ${desc:-<none>}"
            echo "  model:       ${model:-<default>}"
            echo "  model_hint:  ${hint:-<none>}"
            echo "  tools:       ${tools:-<all>}"
            echo ""
        fi
    done
}

cmd_model_set() {
    local agent="$1" model="$2"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            set_field "$file" "model" "$model"
            echo "  ✓ ${dir}/${agent} → model: \"${model}\""
        fi
    done
}

cmd_model_reset() {
    local agent="$1"
    cmd_model_set "$agent" ""
}

cmd_model_set_all() {
    local model="$1"
    local all_agents
    read -ra all_agents <<< "$(discover_agents)"
    echo "Setting all agents model → ${model}"
    for agent in "${all_agents[@]+"${all_agents[@]}"}"; do
        cmd_model_set "$agent" "$model"
    done
}

cmd_model_reset_all() {
    local all_agents
    read -ra all_agents <<< "$(discover_agents)"
    echo "Resetting all agents to system default model"
    for agent in "${all_agents[@]+"${all_agents[@]}"}"; do
        cmd_model_set "$agent" ""
    done
}

cmd_tools_get() {
    local agent="$1"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            local tools
            tools=$(get_tools "$file")
            echo "${dir}/${agent}: tools=${tools:-<all (unrestricted)>}"
        fi
    done
}

cmd_tools_set() {
    local agent="$1" tools_csv="$2"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            set_tools_field "$file" "$tools_csv"
            echo "  ✓ ${dir}/${agent} → tools: [${tools_csv}]"
        fi
    done
}

cmd_tools_add() {
    local agent="$1" tool="$2"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            local current
            current=$(get_tools "$file")
            if [ -z "$current" ]; then
                set_tools_field "$file" "$tool"
            elif echo ",$current," | grep -q ",$tool,"; then
                echo "  ⚠ ${dir}/${agent}: tool '${tool}' already present"
                continue
            else
                set_tools_field "$file" "${current},${tool}"
            fi
            echo "  ✓ ${dir}/${agent} → added tool: ${tool}"
        fi
    done
}

cmd_tools_rm() {
    local agent="$1" tool="$2"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            local current new_tools
            current=$(get_tools "$file")
            if [ -z "$current" ]; then
                echo "  ⚠ ${dir}/${agent}: no tools restriction set"
                continue
            fi
            # Remove tool from csv
            new_tools=$(echo "$current" | sed "s/^${tool},//; s/,${tool},/,/; s/,${tool}$//; s/^${tool}$//")
            if [ "$new_tools" = "$current" ]; then
                echo "  ⚠ ${dir}/${agent}: tool '${tool}' not found"
                continue
            fi
            set_tools_field "$file" "$new_tools"
            echo "  ✓ ${dir}/${agent} → removed tool: ${tool}"
        fi
    done
}

cmd_tools_reset() {
    local agent="$1"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            set_tools_field "$file" ""
            echo "  ✓ ${dir}/${agent} → tools: (all — unrestricted)"
        fi
    done
}

cmd_platforms() {
    echo "🔍 Detected platforms:"
    [ -d "${HOME}/.claude/agents" ] && echo "  ✅ Claude Code  — ${HOME}/.claude/agents/"
    [ -d "${HOME}/.copilot/agents" ] && echo "  ✅ Copilot CLI  — ${HOME}/.copilot/agents/"
    [ -d ".agents" ] && echo "  ✅ Project      — .agents/"
    [ -d ".github/agents" ] && echo "  ✅ GitHub       — .github/agents/"
    true
}

show_help() {
    local all_agents
    read -ra all_agents <<< "$(discover_agents)"
    cat <<EOF
Agent Configuration Helper — Multi-Agent Framework

OVERVIEW:
  config.sh list                           Show all agent config
  config.sh get <agent>                    Show full config for one agent
  config.sh platforms                      Show detected platforms

MODEL:
  config.sh model set <agent> <model>      Set model for an agent
  config.sh model set-all <model>          Set model for all agents
  config.sh model reset <agent>            Reset model to system default
  config.sh model reset-all                Reset all models

TOOLS (Copilot CLI native, guidance-only for Claude Code):
  config.sh tools get <agent>              Show tools for an agent
  config.sh tools set <agent> <t1,t2,...>  Set tools (comma-separated)
  config.sh tools add <agent> <tool>       Add a tool to agent
  config.sh tools rm <agent> <tool>        Remove a tool from agent
  config.sh tools reset <agent>            Remove tools restriction

BACKWARD COMPAT:
  config.sh set <agent> <model>            Alias for: model set
  config.sh reset <agent>                  Alias for: model reset
  config.sh set-all <model>                Alias for: model set-all
  config.sh reset-all                      Alias for: model reset-all

Detected agents: ${all_agents[*]+"${all_agents[*]}"}
Changes apply to ALL detected platforms simultaneously.
EOF
}

# ── Main Router ─────────────────────────────────────────────────
case "${1:-}" in
    list|ls)
        cmd_list
        ;;
    get)
        [ -z "${2:-}" ] && echo "Usage: config.sh get <agent>" && exit 1
        validate_agent "$2"
        cmd_get "$2"
        ;;
    model)
        case "${2:-}" in
            set)
                [ -z "${3:-}" ] || [ -z "${4:-}" ] && echo "Usage: config.sh model set <agent> <model>" && exit 1
                validate_agent "$3"
                cmd_model_set "$3" "$4"
                ;;
            set-all)
                [ -z "${3:-}" ] && echo "Usage: config.sh model set-all <model>" && exit 1
                cmd_model_set_all "$3"
                ;;
            reset)
                [ -z "${3:-}" ] && echo "Usage: config.sh model reset <agent>" && exit 1
                validate_agent "$3"
                cmd_model_reset "$3"
                ;;
            reset-all)
                cmd_model_reset_all
                ;;
            *)
                echo "Usage: config.sh model {set|set-all|reset|reset-all} ..."
                exit 1
                ;;
        esac
        ;;
    tools)
        case "${2:-}" in
            get)
                [ -z "${3:-}" ] && echo "Usage: config.sh tools get <agent>" && exit 1
                validate_agent "$3"
                cmd_tools_get "$3"
                ;;
            set)
                [ -z "${3:-}" ] || [ -z "${4:-}" ] && echo "Usage: config.sh tools set <agent> <t1,t2,...>" && exit 1
                validate_agent "$3"
                cmd_tools_set "$3" "$4"
                ;;
            add)
                [ -z "${3:-}" ] || [ -z "${4:-}" ] && echo "Usage: config.sh tools add <agent> <tool>" && exit 1
                validate_agent "$3"
                cmd_tools_add "$3" "$4"
                ;;
            rm|remove)
                [ -z "${3:-}" ] || [ -z "${4:-}" ] && echo "Usage: config.sh tools rm <agent> <tool>" && exit 1
                validate_agent "$3"
                cmd_tools_rm "$3" "$4"
                ;;
            reset)
                [ -z "${3:-}" ] && echo "Usage: config.sh tools reset <agent>" && exit 1
                validate_agent "$3"
                cmd_tools_reset "$3"
                ;;
            *)
                echo "Usage: config.sh tools {get|set|add|rm|reset} ..."
                exit 1
                ;;
        esac
        ;;
    # Backward-compatible aliases
    set)
        [ -z "${2:-}" ] || [ -z "${3:-}" ] && echo "Usage: config.sh set <agent> <model>" && exit 1
        validate_agent "$2"
        cmd_model_set "$2" "$3"
        ;;
    reset)
        [ -z "${2:-}" ] && echo "Usage: config.sh reset <agent>" && exit 1
        validate_agent "$2"
        cmd_model_reset "$2"
        ;;
    set-all)
        [ -z "${2:-}" ] && echo "Usage: config.sh set-all <model>" && exit 1
        cmd_model_set_all "$2"
        ;;
    reset-all)
        cmd_model_reset_all
        ;;
    platforms)
        cmd_platforms
        ;;
    -h|--help|help|"")
        show_help
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run 'config.sh help' for usage"
        exit 1
        ;;
esac
