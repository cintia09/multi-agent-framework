#!/usr/bin/env bash
set -euo pipefail

# Multi-Agent Framework — Agent Configuration Helper
# Usage:
#   config.sh list                    — Show all agent model settings
#   config.sh get <agent>             — Show model for specific agent
#   config.sh set <agent> <model>     — Set model for an agent
#   config.sh reset <agent>           — Reset model to empty (use system default)
#   config.sh set-all <model>         — Set model for all agents
#   config.sh reset-all               — Reset all agents to system default
#   config.sh platforms               — Show detected platforms

AGENTS=(acceptor designer implementer reviewer tester)

# Detect all platform agent directories
detect_dirs() {
    local dirs=()
    [ -d "${HOME}/.claude/agents" ] && dirs+=("${HOME}/.claude/agents")
    [ -d "${HOME}/.copilot/agents" ] && dirs+=("${HOME}/.copilot/agents")
    # Project-level agents
    [ -d ".agents" ] && dirs+=(".agents")
    [ -d ".github/agents" ] && dirs+=(".github/agents")
    echo "${dirs[@]}"
}

get_model() {
    local file="$1"
    if [ -f "$file" ]; then
        # Extract model from YAML frontmatter
        sed -n '/^---$/,/^---$/p' "$file" | grep '^model:' | head -1 | sed 's/^model: *//; s/^"//; s/"$//'
    fi
}

get_hint() {
    local file="$1"
    if [ -f "$file" ]; then
        sed -n '/^---$/,/^---$/p' "$file" | grep '^model_hint:' | head -1 | sed 's/^model_hint: *//; s/^"//; s/"$//'
    fi
}

set_model() {
    local file="$1" model="$2"
    if [ ! -f "$file" ]; then
        echo "  ⚠ File not found: $file"
        return 1
    fi
    # Use sed to replace model line in YAML frontmatter
    if grep -q '^model:' "$file"; then
        sed -i '' "s|^model:.*|model: \"${model}\"|" "$file"
    else
        # Insert model field after description line
        sed -i '' "/^description:/a\\
model: \"${model}\"" "$file"
    fi
}

cmd_list() {
    echo "📋 Agent Model Configuration"
    echo ""
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        echo "  📁 ${dir}:"
        for agent in "${AGENTS[@]}"; do
            local file="${dir}/${agent}.agent.md"
            if [ -f "$file" ]; then
                local model=$(get_model "$file")
                local hint=$(get_hint "$file")
                if [ -n "$model" ]; then
                    printf "    %-14s → %s" "$agent" "$model"
                else
                    printf "    %-14s → (system default)" "$agent"
                fi
                [ -n "$hint" ] && printf "  [%s]" "$hint"
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
            local model=$(get_model "$file")
            local hint=$(get_hint "$file")
            echo "${dir}: model=${model:-<empty>} hint=${hint:-<none>}"
        fi
    done
}

cmd_set() {
    local agent="$1" model="$2"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            set_model "$file" "$model"
            echo "  ✓ ${dir}/${agent}.agent.md → model: \"${model}\""
        fi
    done
}

cmd_reset() {
    local agent="$1"
    local dirs
    read -ra dirs <<< "$(detect_dirs)"
    for dir in "${dirs[@]}"; do
        local file="${dir}/${agent}.agent.md"
        if [ -f "$file" ]; then
            set_model "$file" ""
            echo "  ✓ ${dir}/${agent}.agent.md → model: \"\" (system default)"
        fi
    done
}

cmd_set_all() {
    local model="$1"
    echo "Setting all agents to model: ${model}"
    for agent in "${AGENTS[@]}"; do
        cmd_set "$agent" "$model"
    done
}

cmd_reset_all() {
    echo "Resetting all agents to system default"
    for agent in "${AGENTS[@]}"; do
        cmd_reset "$agent"
    done
}

cmd_platforms() {
    echo "🔍 Detected platforms:"
    [ -d "${HOME}/.claude/agents" ] && echo "  ✅ Claude Code  — ${HOME}/.claude/agents/ ($(ls "${HOME}/.claude/agents/"*.agent.md 2>/dev/null | wc -l | tr -d ' ') agents)"
    [ -d "${HOME}/.copilot/agents" ] && echo "  ✅ Copilot CLI  — ${HOME}/.copilot/agents/ ($(ls "${HOME}/.copilot/agents/"*.agent.md 2>/dev/null | wc -l | tr -d ' ') agents)"
    [ -d ".agents" ] && echo "  ✅ Project      — .agents/"
    [ -d ".github/agents" ] && echo "  ✅ GitHub       — .github/agents/"
    true
}

# Validate agent name
validate_agent() {
    local agent="$1"
    for a in "${AGENTS[@]}"; do
        [ "$a" = "$agent" ] && return 0
    done
    echo "❌ Unknown agent: ${agent}"
    echo "   Valid agents: ${AGENTS[*]}"
    exit 1
}

# Main
case "${1:-}" in
    list|ls)
        cmd_list
        ;;
    get)
        [ -z "${2:-}" ] && echo "Usage: config.sh get <agent>" && exit 1
        validate_agent "$2"
        cmd_get "$2"
        ;;
    set)
        [ -z "${2:-}" ] || [ -z "${3:-}" ] && echo "Usage: config.sh set <agent> <model>" && exit 1
        validate_agent "$2"
        cmd_set "$2" "$3"
        ;;
    reset)
        [ -z "${2:-}" ] && echo "Usage: config.sh reset <agent>" && exit 1
        validate_agent "$2"
        cmd_reset "$2"
        ;;
    set-all)
        [ -z "${2:-}" ] && echo "Usage: config.sh set-all <model>" && exit 1
        cmd_set_all "$2"
        ;;
    reset-all)
        cmd_reset_all
        ;;
    platforms)
        cmd_platforms
        ;;
    -h|--help|help|"")
        echo "Agent Configuration Helper"
        echo ""
        echo "Commands:"
        echo "  list                  Show all agent model settings"
        echo "  get <agent>           Show model for specific agent"
        echo "  set <agent> <model>   Set model for an agent"
        echo "  reset <agent>         Reset agent to system default"
        echo "  set-all <model>       Set model for all agents"
        echo "  reset-all             Reset all agents to system default"
        echo "  platforms             Show detected platforms"
        echo ""
        echo "Agents: ${AGENTS[*]}"
        echo ""
        echo "Changes are applied to ALL detected platforms simultaneously."
        ;;
    *)
        echo "Unknown command: $1"
        echo "Run 'config.sh help' for usage"
        exit 1
        ;;
esac
